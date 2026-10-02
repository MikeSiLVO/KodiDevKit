"""Label validation for Kodi skins."""

import re
import logging

from .constants import SEVERITY_ERROR, SEVERITY_WARNING

logger = logging.getLogger(__name__)


# InfoLabel namespace prefixes from Kodi source (GUIInfoManager.cpp)
# These are used to detect bare InfoLabels that may need $INFO[] wrapper
INFOLABEL_PREFIXES = {
    'player', 'videoplayer', 'musicplayer', 'container', 'listitem',
    'window', 'system', 'skin', 'control', 'weather', 'addon',
    'library', 'playlist', 'pvr', 'string', 'integer', 'slideshow',
    'fanart', 'game', 'retroplayer', 'visualisation', 'rds',
    'network', 'platform', 'role', 'musicpartymode',
    'audiocodec', 'audiochannels', 'audiolanguage', 'subtitlelanguage'
}

# Common brand names that should not be flagged as untranslated
# These remain the same across languages
BRAND_NAMES = {
    'imdb', 'tmdb', 'tvdb', 'trakt', 'youtube', 'netflix', 'spotify',
    'plex', 'emby', 'jellyfin', 'kodi', 'opensubtitles',
    'rotten tomatoes', 'metacritic', 'lastfm', 'last.fm',
    'fanart.tv', 'theaudiodb', 'themoviedb', 'thetvdb',
    'google', 'facebook', 'twitter', 'reddit', 'discord',
    # Added from validation analysis (2025-11-04)
    'wikipedia', 'wiki',  # Encyclopedia/proper nouns
    'libreelec', 'coreelec',  # OS/Platform names
}

# Technical terms and acronyms that should not be translated
# These are industry-standard terms that remain consistent across languages
TECHNICAL_TERMS = {
    'hdr', 'sdr',  # Video standards
    'pvr', 'dvr',  # Recording systems
    'eotf',  # Electro-Optical Transfer Function
    'iptv', 'rtsp', 'rtmp',  # Streaming protocols
    'mpaa', 'bbfc',  # Rating systems
    'atmos', 'dts', 'ac3',  # Audio formats
    'hevc', 'h264', 'h265',  # Video codecs
}


class ValidationLabel:
    """Validates label translations and definitions in Kodi skins."""

    def __init__(self, addon, get_po_files_fn, validation_index=None):
        self.addon = addon
        self._get_po_files = get_po_files_fn
        self._validation_index = validation_index

    def _is_hex_color(self, text):
        """
        Check if text is an ARGB hex color (8-char hex, case-insensitive).

        Examples: ff123456, FF123456, aabbccdd, AABBCCDD
        """
        text = text.strip()
        if len(text) != 8:
            return False

        # Check if all chars are valid hex: 0-9, a-f, A-F
        return bool(re.match(r'^[0-9a-fA-F]{8}$', text))

    def _is_addon_id(self, text):
        """
        Check if text looks like an addon ID.

        Examples: script.cu.lrclyrics, service.library.data.provider, plugin.video.netflix, resource.images.arctic.waves
        """
        text = text.strip().lower()
        return bool(re.match(r'^(script|service|plugin|skin|resource)\.[a-z0-9._-]+$', text))

    def _is_brand_name(self, text):
        """
        Check if text is a known brand name that doesn't need translation.

        Examples: IMDb, TMDb, TVDB, Rotten Tomatoes, Netflix
        """
        text = text.strip().lower()
        return text in BRAND_NAMES

    def _is_technical_term(self, text):
        """
        Check if text is a known technical term/acronym that doesn't need translation.

        Examples: HDR, PVR, EOTF, IPTV, H264
        """
        text = text.strip().lower()
        return text in TECHNICAL_TERMS

    def _is_bare_infolabel(self, text):
        """
        Detect bare InfoLabel without $INFO[] wrapper.

        Only matches EXACT InfoLabel syntax: Prefix.Method(args) with no surrounding text.
        Examples: Player.Art(fanart1), Container.Property(foo)

        Returns False for: "Testing Player.Art", "Player.Art debug", "Season.Two(2024)"
        """
        text = text.strip()

        if '(' not in text or '.' not in text:
            return False

        # Check if prefix is a known InfoLabel namespace
        prefix = text.split('.')[0].lower()
        if prefix not in INFOLABEL_PREFIXES:
            return False

        # Must be EXACTLY the InfoLabel - no extra words before/after
        # Pattern: Prefix.Method(args) and nothing else
        return bool(re.match(r'^[A-Za-z]+\.[A-Za-z]+\([^)]*\)$', text))

    def check(self, progress_callback=None):
        """Find untranslated/undefined labels.

        Returns list of {"message": str, "file": str, "line": int}.
        """
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

            if self._is_hex_color(label_text):
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
                listitems.append(updated_item)
            elif self._is_addon_id(label_text):
                updated_item = cached_item.copy()
                updated_item['message'] = (
                    f"Possible addon ID: {label_text}. "
                    f"Check if intentional descriptive text or needs translation."
                )
                updated_item['severity'] = SEVERITY_WARNING
                listitems.append(updated_item)
            else:
                item = cached_item.copy()
                item['severity'] = SEVERITY_WARNING
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
        # Kodi 22 reads a skin's own strings only in this range (addons/Skin.h:32)
        skin_range_only = getattr(self.addon, "api_version", None) not in (None, "omega")
        for ref in refs:
            key = "#" + ref["name"]
            outside = ref["name"].isdigit() and not 31000 <= int(ref["name"]) <= 31999
            if key not in skin_ids | core_ids:
                ref["message"] = "Label not defined: %s" % ref["name"]
            elif skin_range_only and outside and key in skin_ids:
                effect = "Kodi's own string" if key in core_ids else "nothing"
                ref["message"] = (f"Skin string {ref['name']} is outside 31000-31999, so Kodi 22 shows "
                                  f"{effect} for it")
            else:
                continue
            ref["severity"] = SEVERITY_ERROR
            listitems.append(ref)

        error_count = len(listitems)
        if progress_callback:
            progress_callback(f"Complete: {error_count} label issues found")

        return listitems
