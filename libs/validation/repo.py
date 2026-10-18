"""Kodi repo submission rules that kodi-addon-checker enforces, reported as labeled warnings."""

from __future__ import annotations

import copy
import os
import re

from lxml import etree as ET
from lxml.etree import XMLSchema

from ..polib.polib import pofile
from ..utils.images import get_image_info
from ..utils.xml import PARSER
from .constants import SEVERITY_WARNING
from .filecheck import nested_addons, shipped_files

# a frozen build keeps no libs folders on disk for ".." to step out of
SCHEMA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data",
                                           "addon_schema"))

# kodi_addon_checker/check_allowed_versions.py
VERSION = re.compile(r"^(\d+\.\d+(\.\d+){0,4}([+~\w]+(\.\d+)?)?)$")
# kodi_addon_checker/check_string.py
LANG_CODE = re.compile(r"^[a-z]{2,3}(?:_[a-zA-Z]{2}(?:@\S+)?)?$")
# kodi_addon_checker/check_files.py
WHITELIST = re.compile(
    r"\.?(py|xml|gif|png|jpg|jpeg|md|txt|po|json|markdown|yml|rst|ini|flv|wav|mp4|html|css|lst|pkla|g|"
    r"template|in|cfg|xsd|directory|help|list|mpeg|pls|info|ttf|xsp|theme|yaml|dict|crt|ico)?$", re.I)
# kodi_addon_checker/check_artwork.py: extensions, sizes, largest file in KB
ARTWORK = {
    "icon": ((".png",), ((256, 256), (512, 512)), None),
    "fanart": ((".jpg", ".jpeg", ".png"), ((1280, 720), (1920, 1080), (3840, 2160)), 1000),
    "screenshot": ((".jpg", ".jpeg", ".png"), ((1280, 720), (1920, 1080)), 750),
    "banner": ((".jpg", ".jpeg", ".png"), ((1000, 185),), None),
    "clearlogo": ((".png",), ((400, 155), (800, 310)), None),
}
# the extension points the checker has schemas for; a skin validates the two it uses
SKIN_SCHEMAS = {"xbmc.addon.metadata": "matrix_metadata.xsd", "xbmc.gui.skin": "gotham_skin.xsd"}
KNOWN_POINTS = {
    "kodi.audiodecoder", "kodi.audioencoder", "kodi.context.item", "kodi.gameclient", "kodi.game.controller",
    "kodi.imagedecoder", "kodi.inputstream", "kodi.peripheral", "kodi.pvrclient", "kodi.resource.games",
    "kodi.resource.images", "kodi.resource.language", "kodi.addon.metadata", "kodi.resource.uisounds",
    "kodi.resource.font", "kodi.vfs", "xbmc.addon.metadata", "xbmc.addon.repository", "xbmc.gui.skin",
    "xbmc.metadata.scraper.albums", "xbmc.metadata.scraper.artists", "xbmc.metadata.scraper.movies",
    "xbmc.metadata.scraper.musicvideos", "xbmc.metadata.scraper.tvshows", "xbmc.metadata.scraper.library",
    "xbmc.player.musicviz", "xbmc.python.script", "xbmc.python.lyrics", "xbmc.python.weather",
    "xbmc.python.library", "xbmc.python.pluginsource", "xbmc.python.module", "xbmc.service",
    "xbmc.subtitle.module", "xbmc.ui.screensaver", "xbmc.webinterface",
}


class ValidationRepo:
    """Checker for addon.xml, artwork, language files and file types as the repo's CI sees them."""

    def __init__(self, addon):
        self.addon = addon
        self.issues = []

    def _add(self, rel, line, rule, message, subject=""):
        """Record one warning against a file of the addon."""
        self.issues.append({"message": f"Kodi repo: {message}", "file": os.path.join(self.addon.path, rel),
                            "line": line, "severity": SEVERITY_WARNING, "rule": rule, "subject": subject})

    def check(self, progress_callback=None):
        """Check the addon against the repo rules, one warning per finding."""
        self.issues = []
        if not self.addon:
            return self.issues
        if progress_callback:
            progress_callback("Checking addon.xml, artwork and language files...")
        try:
            root = ET.parse(os.path.join(self.addon.path, "addon.xml"), PARSER).getroot()
        except (OSError, ET.XMLSyntaxError):
            root = None
        if root is not None:
            self._check_addon_xml(root)
            self._check_artwork(root)
        self._check_languages()
        for folder in nested_addons(self.addon.path):
            self._add(folder, 0, "repo.nested-addon", f"{folder} is a separate add-on inside this one. The Kodi repo takes one "
                                 f"add-on per submission; outside the repo this works")
        for rel, _executable in shipped_files(self.addon.path):
            name = rel.rsplit("/", 1)[-1]
            # dotfiles never reach a submission; a shipped .xbt is reported by the image check
            if name.startswith(".") or name.lower().endswith(".xbt"):
                continue
            if "." in name and not WHITELIST.match("." + name.rsplit(".", 1)[1]):
                self._add(rel, 0, "repo.file-type", f"{rel} has a file type the repo does not accept")
        if progress_callback:
            progress_callback(f"Complete: {len(self.issues)} repo issues found")
        return self.issues

    def _check_addon_xml(self, root):
        """Check the version, id, extensions and xbmc.gui import in addon.xml."""
        version = root.get("version")
        if not version or not VERSION.match(version):
            self._add("addon.xml", root.sourceline, "repo.version",
                      f"version {version!r} is not major.minor.revision (e.g. 1.0.0)", version or "")
        folder = os.path.basename(os.path.normpath(self.addon.path))
        if root.get("id") != folder:
            self._add("addon.xml", root.sourceline, "repo.id-mismatch",
                      f"addon id {root.get('id')} does not match folder {folder}", root.get("id") or "")
        bare = copy.deepcopy(root)
        for ext in list(bare.findall("extension")):
            point = ext.get("point")
            if point not in KNOWN_POINTS:
                self._add("addon.xml", ext.sourceline, "repo.extension-point", f"{point} is not a valid extension point",
                          point or "")
            elif point in SKIN_SCHEMAS:
                self._validate(ext, SKIN_SCHEMAS[point])
            bare.remove(ext)
        self._validate(bare, "addon.xsd")
        if not root.findall("extension[@point='xbmc.addon.metadata']"):
            self._add("addon.xml", root.sourceline, "repo.no-metadata", "addon.xml has no xbmc.addon.metadata extension")
        self._check_release(root)

    def _check_release(self, root):
        """Check the xbmc.gui import against the release the settings force."""
        forced = str(self.addon.settings.get("kodi_release") or "").strip().lower()
        release = next((r for r in self.addon.RELEASES if r["name"] == forced), None)
        node = root.find("requires/import[@addon='xbmc.gui']")
        if release is None or node is None:
            return
        version = node.get("version") or ""
        wanted = self.addon._safe_version_tuple(version)
        lowest = self.addon._safe_version_tuple(node.get("minversion") or version)
        name = forced.capitalize()
        if wanted is None or lowest is None:
            return
        if lowest > self.addon._safe_version_tuple(release["gui_version"]):
            self._add("addon.xml", node.sourceline, "repo.gui-too-new", f"xbmc.gui {version} is newer than {name}'s "
                                                    f"{release['gui_version']}, so {name} will not load it")
        elif wanted < self.addon._safe_version_tuple(release["gui_abi"]):
            self._add("addon.xml", node.sourceline, "repo.gui-too-old", f"xbmc.gui {version} is older than the "
                                                    f"{release['gui_abi']} {name} still accepts, "
                                                    f"so {name} will not load it")

    def _validate(self, element, schema_name):
        """Validate against a schema, reporting each error at the addon.xml line it names."""
        schema = XMLSchema(ET.parse(os.path.join(SCHEMA_DIR, schema_name)))
        if not schema.validate(element):
            for error in schema.error_log:
                # an empty <assets> tag gets its own plainer message from the artwork check
                if "/assets/" in (error.path or "") and "The value '' is not accepted" in error.message:
                    continue
                self._add("addon.xml", error.line, "repo.schema", _plain_schema_error(error.message),
                          _plain_schema_error(error.message))

    def _check_artwork(self, root):
        """Check declared artwork exists and has an accepted type, size and file size."""
        for kind, (extensions, sizes, max_kb) in ARTWORK.items():
            images = [node.text for node in root.findall(f"extension/assets/{kind}")]
            fallback = {"icon": "icon.png", "fanart": "fanart.jpg"}.get(kind) if not images else None
            if fallback:
                if os.path.isfile(os.path.join(self.addon.path, fallback)):
                    self._add(fallback, 0, "repo.undeclared-asset", f"{fallback} should be declared in addon.xml <assets>")
                continue
            for image in images:
                if not image or not image.strip():
                    self._add("addon.xml", 0, "repo.empty-asset", f"empty <{kind}> tag in <assets>", kind)
                    continue
                path = os.path.join(self.addon.path, image.strip())
                if not os.path.isfile(path):
                    self._add("addon.xml", 0, "repo.missing-asset", f"{kind} {image.strip()} does not exist", kind)
                    continue
                ext = os.path.splitext(path)[1].lower()
                if ext not in extensions:
                    self._add(image.strip(), 0, "repo.asset-type", f"{kind} must be {'/'.join(extensions)}, not {ext}", kind)
                dims = dict(get_image_info(path)).get("Dimensions", "")
                if dims and tuple(int(v) for v in dims.split("x")) not in sizes:
                    allowed = " or ".join(f"{w}x{h}" for w, h in sizes)
                    self._add(image.strip(), 0, "repo.asset-size", f"{kind} is {dims}, the repo accepts {allowed}", kind)
                if max_kb and os.path.getsize(path) > max_kb * 1024:
                    self._add(image.strip(), 0, "repo.asset-file-size",
                              f"{kind} is {os.path.getsize(path) // 1024}KB, over {max_kb}KB", kind)

    def _check_languages(self):
        """Check language folders use resource.language.<code> and include en_gb, then each po."""
        found_en_gb = False
        for base in ("language", os.path.join("resources", "language")):
            base_path = os.path.join(self.addon.path, base)
            if not os.path.isdir(base_path):
                continue
            for folder in sorted(os.listdir(base_path)):
                if not os.path.isdir(os.path.join(base_path, folder)):
                    continue
                rel = os.path.join(base, folder).replace("\\", "/")
                if not folder.startswith("resource.language."):
                    self._add(rel, 0, "repo.language-layout", f"{rel} uses the old language folder layout; use resource.language.<code>")
                    continue
                code = folder[len("resource.language."):]
                if not LANG_CODE.match(code):
                    self._add(rel, 0, "repo.language-code", f"{code} is not a valid language code", code)
                found_en_gb |= code.lower() == "en_gb"
                po = os.path.join(base_path, folder, "strings.po")
                if os.path.isfile(po):
                    self._check_po(rel + "/strings.po", po)
        if not found_en_gb:
            self._add("addon.xml", 0, "repo.no-en-gb", "no resource.language.en_gb folder with the default strings")

    def _check_po(self, rel, path):
        """Check a strings.po is UTF-8, has Kodi's header, no BOM or duplicate ids, and parses."""
        try:
            with open(path, encoding="utf-8") as f:
                contents = f.read()
        except UnicodeDecodeError:
            self._add(rel, 0, "repo.po-encoding", f"{rel} is not saved as UTF-8")
            return
        except OSError:
            return
        first = contents.find('msgctxt "#')
        header = contents[:first] if first != -1 else contents
        if not re.search(r'msgid ""\s+msgstr ""', header):
            self._add(rel, 1, "repo.po-header", f'{rel} is missing the msgid "" / msgstr "" header')
        seen = {}
        for number, line in enumerate(contents.splitlines(), 1):
            found = re.match(r'\s*msgctxt\s+"#(\d+)"', line)
            if found and found.group(1) in seen:
                self._add(rel, number, "repo.po-duplicate-id", f"string id {found.group(1)} is defined twice (first on line "
                                                               f"{seen[found.group(1)]})", found.group(1))
            elif found:
                seen[found.group(1)] = number
        if contents.startswith("\ufeff"):
            self._add(rel, 1, "repo.po-bom", f"{rel} starts with a BOM (byte order mark)")
            return
        # kodi-addon-checker rewrites comment lines this way before handing the file to polib
        cleaned = "".join(
            "# " + line.replace("#", "").lstrip() if line.startswith("#") and line.replace("#", "").strip()
            else "\n" if line.startswith("#") else line
            for line in contents.splitlines(keepends=True))
        try:
            pofile(cleaned, encoding="utf-8")
        except Exception as error:
            found = re.search(r"\(line (?P<line>\d+)\)\s*:\s*(?P<detail>[\s\S]+?)\s*$", str(error))
            bare = re.search(r"Syntax error[\s\S]+\(line (?P<line>\d+)\)\s*$", str(error))
            if found:
                self._add(rel, int(found.group("line")), "repo.po-parse", f"{rel}: {found.group('detail')}")
            elif bare:
                line = int(bare.group("line"))
                self._add(rel, line, "repo.po-parse", f"{rel}: {_po_syntax_reason(cleaned, line)}")
            else:
                self._add(rel, 0, "repo.po-parse", f"{rel}: {error}")


def _po_syntax_reason(text, number):
    """What breaks the strings.po line a bare syntax error names, from it and the line before."""
    lines = text.splitlines()
    line = lines[number - 1].strip() if 0 < number <= len(lines) else ""
    before = next((prev.strip() for prev in reversed(lines[:number - 1]) if prev.strip()), "")
    word, _, value = line.partition(" ")
    if word.startswith(("msgctxt", "msgid", "msgstr")) and not value.strip().startswith('"'):
        return f"{word} has no quoted value"
    if word.startswith(("msgctxt", "msgid", "msgstr")) or line.startswith('"'):
        what = "quoted text" if line.startswith('"') else word
        return f"{what} cannot follow {before}" if before else f"{what} cannot start the file"
    return f"a line that is not a msgctxt, msgid, msgstr, comment or quoted text: {line}"


def _plain_schema_error(message):
    """The schema error in plain words where its form is known, else as lxml words it."""
    element = re.match(r"Element '([^']+)'", message)
    name = f"<{element.group(1)}>" if element else "An element"
    if "The value '' is not accepted" in message:
        return f"{name} is empty"
    length = re.search(r"length of '(\d+)'; this exceeds the allowed maximum length of '(\d+)'", message)
    if length:
        return f"{name} is {length.group(1)} characters, over the {length.group(2)} limit"
    return message
