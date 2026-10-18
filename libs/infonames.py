"""Info names Kodi's parser accepts, read from an xbmc source tree."""

from __future__ import annotations

import os
import re

# category: (arrays searched, names compared inline); anything else in the source fails reading
CATEGORIES = {
    "string": (["string_bools"], ["isempty"]),
    "integer": (["integer_bools"], ["valueof"]),
    "player": (["player_labels", "player_times", "player_param"], ["process"]),
    "addon": (["addons"], []),
    "weather": (["weather"], ["data"]),
    "network": (["network_labels"], []),
    "musicpartymode": (["musicpartymode"], []),
    "system": (["system_labels", "system_param"],
               ["getbool", "memory", "addontitle", "addonicon", "addonversion", "idletime", "locale",
                "alarmlessorequal", "date", "time"]),
    "library": ([], ["isscanning", "isscanningvideo", "isscanningmusic", "hascontent", "hasnode"]),
    "musicplayer": (["player_times", "musicplayer"], ["content", "genre", "property", "channels"]),
    "videoplayer": (["player_times", "videoplayer"],
                    ["content", "uniqueid", "art", "cast", "castandrole", "writer", "director", "genre",
                     "nextgenre", "audiochannels"]),
    "retroplayer": (["retroplayer"], []),
    "slideshow": (["slideshow"], []),
    "container": (["mediacontainer", "container_bools", "container_ints", "container_str"], ["sortdirection"]),
    "listitem": (["listitem_labels"], []),
    "visualisation": (["visualisation"], []),
    "fanart": (["fanart_labels"], []),
    "skin": (["skin_labels"], ["string", "numeric", "hassetting", "hastheme", "timerisrunning", "timerelapsedsecs"]),
    "window": (["window_bools"], ["property"]),
    "control": (["control_labels"], []),
    "controlgroup": ([], ["hasfocus"]),
    "playlist": (["playlist"], []),
    "pvr": (["pvr", "pvr_times"], []),
    "rds": (["rds"], ["getline"]),
}
LISTITEM_ALIASES = ["listitemposition", "listitemnowrap", "listitemabsolute"]
# three-part <player>.position(n).<name> forms and the arrays their last part is looked up in
PLAYERS = {"player": "player_labels", "musicplayer": "musicplayer", "videoplayer": "videoplayer"}
# searched only through the process(name) param, never as a property name
PARAM_ONLY = {"player_process"}

ARRAY = re.compile(r"(?:constexpr std::array<InfoMap,\s*\d+>\s*(\w+)|const infomap\s+(\w+)\[\])\s*=\s*\{(.*?)\};",
                   re.S)
ENTRY = re.compile(r'\{\s*"([^"]+)"\s*,\s*([A-Z]\w+)')
PROPERTY = re.compile(r'prop\.(?:Name\(\)|name) == "(\w+)"')

SOURCE = os.path.join("xbmc", "GUIInfoManager.cpp")

_cache: dict[str, tuple[float, int, dict]] = {}


def dispatch(source):
    """The source's info-string dispatch body, from the last overload, which does the work."""
    start = [m.start() for m in re.finditer(r"int CGUIInfoManager::TranslateSingleString\(", source)][-1]
    return source[start:source.index("int CGUIInfoManager::TranslateListItem", start)]


def arrays_of(source):
    """Lowercased name and info id of each entry, per InfoMap array the source defines."""
    return {(m.group(1) or m.group(2)): [(n.lower(), info) for n, info in ENTRY.findall(m.group(3))]
            for m in ARRAY.finditer(source)}


def check_mapping(body, arrays):
    """Check the source's InfoMap and dispatch names against the module's tables, listing misses."""
    mapped_arrays = {a for found, _ in CATEGORIES.values() for a in found} | set(PLAYERS.values()) | PARAM_ONLY
    mapped_literals = {lit for _, found in CATEGORIES.values() for lit in found}
    known = set(CATEGORIES) | set(LISTITEM_ALIASES) | {"true", "false", "yes", "no"}
    problems = []
    for label, found, mapped in (
        ("category", set(re.findall(r'cat\.(?:Name\(\)|name) == "(\w+)"', body)), known),
        ("array", set(re.findall(r"for \(const (?:auto|infomap)& \w+ :\s*(\w+)\)", body)) | set(arrays),
         mapped_arrays),
        ("property", set(PROPERTY.findall(body)), mapped_literals),
    ):
        problems += [f"unmapped {label} {name}" for name in sorted(found - mapped)]
    return problems


def names_of(source):
    """Table in infonames.json's shape, or ValueError on a missing dispatch or unmapped name."""
    arrays = arrays_of(source)
    try:
        body = dispatch(source)
    except (IndexError, ValueError):
        raise ValueError("no info-string dispatch found") from None
    problems = check_mapping(body, arrays)
    if problems:
        raise ValueError(", ".join(problems))
    literals = set(PROPERTY.findall(body))
    return {
        "categories": {cat: sorted({n for a in found for n, _ in arrays.get(a, [])} | (set(inline) & literals))
                       for cat, (found, inline) in CATEGORIES.items()},
        "listitem_aliases": LISTITEM_ALIASES,
        "platforms": sorted(set(re.findall(r'platform == "(\w+)"', body))),
        "players": {player: sorted({n for n, _ in arrays.get(array, [])}) for player, array in PLAYERS.items()},
    }


def from_tree(root):
    """Table read from the root's Kodi source, reused until it changes; None without that source."""
    path = os.path.join(root, SOURCE)
    try:
        stat = os.stat(path)
    except OSError:
        return None
    cached = _cache.get(path)
    if cached and cached[:2] == (stat.st_mtime, stat.st_size):
        return cached[2]
    with open(path, encoding="utf-8", errors="replace") as f:
        names = names_of(f.read())
    _cache[path] = (stat.st_mtime, stat.st_size, names)
    return names
