"""Checks labels for undefined or out-of-range ids, broken strings and untranslated text."""

import re
import logging

from ..addon.translations import strings_po_faults
from ..utils.colors import is_kodi_hex
from ..utils.infobool import is_known_info
from .constants import SEVERITY_ERROR, SEVERITY_WARNING

logger = logging.getLogger(__name__)


# first part of every add-on id in the Kodi repo, plus repository
ADDON_ID_PREFIXES = (
    'audiodecoder', 'audioencoder', 'context', 'game', 'imagedecoder', 'inputstream', 'metadata',
    'peripheral', 'plugin', 'pvr', 'repository', 'resource', 'screensaver', 'script', 'service',
    'skin', 'vfs', 'visualization', 'weather', 'webinterface',
)

_ADDON_ID = re.compile(rf"^({'|'.join(ADDON_ID_PREFIXES)})\.[a-z0-9._-]+$")

_PO_PROBLEMS = {
    "unclosed": "does not close on this line",
    "text": "has text after its closing quote on this line",
    "spaces": "has spaces outside its quotes on this line",
}
_PO_EFFECTS = {
    "empty": "reads it as empty and its labels show nothing",
    "cut": "shows only the text before this line",
    "english": "shows the English text in place of this translation",
}

# names that read the same in every language
BRAND_NAMES = {
    'imdb', 'tmdb', 'tvdb', 'trakt', 'youtube', 'netflix', 'spotify',
    'plex', 'emby', 'jellyfin', 'kodi', 'opensubtitles',
    'rotten tomatoes', 'metacritic', 'lastfm', 'last.fm',
    'fanart.tv', 'theaudiodb', 'themoviedb', 'thetvdb',
    'google', 'facebook', 'twitter', 'reddit', 'discord',
    'wikipedia', 'wiki',
    'libreelec', 'coreelec',
}

# terms and acronyms kept as-is in every language
TECHNICAL_TERMS = {
    'hdr', 'sdr',
    'pvr', 'dvr',
    'eotf',
    'iptv', 'rtsp', 'rtmp',
    'mpaa', 'bbfc',
    'atmos', 'dts', 'ac3',
    'hevc', 'h264', 'h265',
}


class ValidationLabel:
    """Checker for undefined or out-of-range label ids, broken strings and untranslated text."""

    def __init__(self, addon, get_po_files_fn, validation_index=None, info_names=None):
        self.addon = addon
        self._get_po_files = get_po_files_fn
        self._validation_index = validation_index
        self._info_names = info_names or {}

    def _is_addon_id(self, text):
        """True when the text looks like an addon ID."""
        return bool(_ADDON_ID.match(text.strip().lower()))

    def _is_brand_name(self, text):
        """True when the text is a known brand name that needs no translation."""
        text = text.strip().lower()
        return text in BRAND_NAMES

    def _is_technical_term(self, text):
        """True when the text is a known technical term or acronym that needs no translation."""
        text = text.strip().lower()
        return text in TECHNICAL_TERMS

    def _is_bare_infolabel(self, text):
        """True when the text is an info Kodi knows, such as Player.Art(fanart), with no $INFO[]."""
        text = text.strip()
        if not self._info_names or " " in text or "." not in text:
            return False
        return is_known_info(text, self._info_names)

    def check(self, progress_callback=None):
        """Check labels, one issue row per bad id, broken string or text that looks untranslated."""
        if not self._validation_index:
            return []
        if progress_callback:
            progress_callback("Initializing label validation...")

        listitems = []
        refs = []

        if progress_callback:
            progress_callback("Using cached validation index...")

        cached_labels = self._validation_index.get('labels_untranslated', [])

        for cached_item in cached_labels:
            label_text = cached_item.get('name', '') or cached_item.get('identifier', '')

            if is_kodi_hex(label_text.strip()):
                continue
            elif self._is_brand_name(label_text):
                continue
            elif self._is_technical_term(label_text):
                continue
            elif self._is_bare_infolabel(label_text):
                updated_item = cached_item.copy()
                updated_item['message'] = (
                    f"Possible missing $INFO[] wrapper: {label_text}. "
                    f"Use $INFO[{label_text}] or <info>{label_text}</info> if dynamic. "
                    f"Ignore if intentional descriptive text."
                )
                updated_item['severity'] = SEVERITY_WARNING
                updated_item.update(rule="labels.missing-info", subject=label_text)
                listitems.append(updated_item)
            elif self._is_addon_id(label_text):
                updated_item = cached_item.copy()
                updated_item['message'] = (
                    f"Possible addon ID: {label_text}. "
                    f"Check if intentional descriptive text or needs translation."
                )
                updated_item['severity'] = SEVERITY_WARNING
                updated_item.update(rule="labels.addon-id", subject=label_text)
                listitems.append(updated_item)
            else:
                item = cached_item.copy()
                item['severity'] = SEVERITY_WARNING
                item.update(rule="labels.not-translated", subject=label_text)
                listitems.append(item)

        for folder in self.addon.xml_folders:
            labels_used = self._validation_index.get('labels_used', {}).get(folder, {})
            for label_id, usages in labels_used.items():
                if usages:
                    first_usage = usages[0]
                    refs.append({
                        'name': label_id,
                        'type': first_usage.get('type', 'label'),
                        'file': first_usage.get('file', ''),
                        'line': first_usage.get('line', 0)
                    })

        if progress_callback:
            progress_callback(f"Checking {len(refs)} label references against translation files...")

        skin_po = {id(po) for po in getattr(self.addon, "po_files", None) or []}
        skin_ids, core_ids = set(), set()
        for po_file in self._get_po_files():
            (skin_ids if id(po_file) in skin_po else core_ids).update(entry.msgctxt for entry in po_file)
        # Kodi 22 reads a skin's own strings only in 31000-31999
        skin_range_only = getattr(self.addon, "api_version", None) not in (None, "omega")
        for ref in refs:
            key = "#" + ref["name"]
            outside = ref["name"].isdigit() and not 31000 <= int(ref["name"]) <= 31999
            if key not in skin_ids | core_ids:
                ref["message"] = "Label not defined: %s" % ref["name"]
                ref["rule"] = "labels.undefined"
            elif skin_range_only and outside and key in skin_ids:
                effect = "Kodi's own string" if key in core_ids else "nothing"
                ref["message"] = (f"Skin string {ref['name']} is outside 31000-31999, so Kodi 22 shows "
                                  f"{effect} for it")
                ref["rule"] = "labels.out-of-range"
            else:
                continue
            ref["severity"] = SEVERITY_ERROR
            ref["subject"] = ref["name"]
            listitems.append(ref)

        for path, line, string_id, problem, effect in strings_po_faults(self.addon.path):
            if not effect:
                continue
            message = f"String {string_id} {_PO_PROBLEMS[problem]}, so Kodi {_PO_EFFECTS[effect]}"
            if problem == "unclosed":
                message += "; Weblate cannot load the file either"
            listitems.append({"message": message, "file": path, "line": line, "severity": SEVERITY_ERROR,
                              "rule": "labels.broken-string", "subject": string_id})

        error_count = len(listitems)
        if progress_callback:
            progress_callback(f"Complete: {error_count} label issues found")

        return listitems
