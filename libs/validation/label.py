"""
KodiDevKit is a plugin to assist with Kodi skinning / scripting
using Sublime Text 4
Label validation for Kodi skins.
"""

import os
import re
import logging

from .. import utils
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

    def __init__(self, addon, get_po_files_fn, resolve_include_fn=None, validation_index=None):
        """
        Args:
            addon: Addon/Skin instance with xml_folders, path, window_files
            get_po_files_fn: Callable that returns list of PO files for label lookup
            resolve_include_fn: Callable to resolve includes and $PARAM (optional)
            validation_index: Pre-built validation index for performance (optional)
        """
        self.addon = addon
        self._get_po_files = get_po_files_fn
        self._resolve_include = resolve_include_fn
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

    def _is_untranslated_label(self, text):
        """
        Check if label text appears to be untranslated (hardcoded text).

        Now filters out false positives:
        - Hex colors (ARGB format)
        - Brand names (IMDb, TMDb, etc. - don't need translation)
        - Addon IDs, bare InfoLabels (handled separately with warnings)

        Returns True if text looks like untranslated hardcoded text.
        """
        text = text.strip()

        if len(text) <= 1:
            return False

        if text.endswith(".xml"):
            return False
        if text.startswith("$"):
            return False
        if "$INFO[" in text or "$VAR[" in text or "$PARAM[" in text:
            return False
        if "$NUMBER[" in text or "$ADDON[" in text:
            return False

        if not text[0].isalpha():
            return False

        if self._is_hex_color(text):
            return False

        if self._is_brand_name(text):
            return False

        if self._is_technical_term(text):
            return False


        # If we get here, it's likely untranslated text
        return True

    def check(self, progress_callback=None):
        """
        Find untranslated/undefined labels.

        Args:
            progress_callback: Optional callback for progress updates

        Returns list of {"message": str, "file": str, "line": int}.
        """
        total_files = sum(len(files) for files in self.addon.window_files.values()) if hasattr(self.addon, 'window_files') else 0

        if progress_callback:
            progress_callback("Initializing label validation...")

        listitems = []
        refs = []

        if self._validation_index:
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
        else:
            localize_regex = [r"\$LOCALIZE\[([0-9].*?)\]", r"^(\d+)$"]
            checks = [
                [".//viewtype[(@label)]", "label"],
                [".//fontset[(@idloc)]", "idloc"],
                [".//label[(@fallback)] | .//label2[(@fallback)]", "fallback"],
            ]
            processed_count = 0
            for folder in self.addon.xml_folders:
                for xml_file in self.addon.window_files[folder]:
                    path = os.path.join(self.addon.path, folder, xml_file)

                    if "script-skinshortcuts-includes.xml" in path.replace("\\", "/").lower():
                        continue

                    processed_count += 1
                    if progress_callback:
                        if processed_count <= 10:
                            progress_callback(f"Scanning {xml_file} ({processed_count}/{total_files})...")
                        elif total_files > 100 and processed_count % 10 == 0:
                            progress_callback(f"Scanning {xml_file} ({processed_count}/{total_files})...")
                        elif processed_count % 3 == 0:
                            progress_callback(f"Scanning {xml_file} ({processed_count}/{total_files})...")

                    root = utils.get_root_from_file(path)
                    if root is None:
                        continue

                    # Expand includes and $PARAM if resolver available
                    # Skip expansion if file contains no dynamic expressions (performance optimization)
                    if self._resolve_include and utils.file_needs_expansion(path):
                        try:
                            logger.debug("Expanding %s...", os.path.basename(path))
                            root = self._resolve_include(root, folder=folder)
                            logger.debug("Expansion complete for %s", os.path.basename(path))
                        except Exception as e:
                            # Fall back to unexpanded if expansion fails
                            logger.warning("Expansion failed for %s: %s", os.path.basename(path), e)
                    else:
                        logger.debug("Skipping expansion for %s (no params/includes detected)", os.path.basename(path))

                    for element in root.xpath(
                        ".//label | .//altlabel | .//label2 | .//hinttext"
                    ):
                        if not element.text:
                            continue
                        for match in re.finditer(localize_regex[0], element.text):
                            refs.append(
                                {
                                    "name": match.group(1),
                                    "type": element.tag,
                                    "file": path,
                                    "line": element.sourceline,
                                }
                            )
                        if element.text.isdigit():
                            refs.append(
                                {
                                    "name": element.text,
                                    "type": element.tag,
                                    "file": path,
                                    "line": element.sourceline,
                                }
                            )
                        elif self._is_untranslated_label(element.text):
                            if self._is_bare_infolabel(element.text):
                                listitems.append(
                                    {
                                        "name": element.text,
                                        "type": element.tag,
                                        "file": path,
                                        "identifier": element.text,
                                        "message": "Possible missing $INFO[] wrapper: %s. "
                                                   "Use $INFO[%s] or <info>%s</info> if dynamic. "
                                                   "Ignore if intentional descriptive text."
                                        % (element.text, element.text, element.text),
                                        "line": element.sourceline,
                                        "severity": SEVERITY_WARNING,
                                    }
                                )
                            elif self._is_addon_id(element.text):
                                listitems.append(
                                    {
                                        "name": element.text,
                                        "type": element.tag,
                                        "file": path,
                                        "identifier": element.text,
                                        "message": "Possible addon ID: %s. "
                                                   "Check if intentional descriptive text or needs translation."
                                        % element.text,
                                        "line": element.sourceline,
                                        "severity": SEVERITY_WARNING,
                                    }
                                )
                            else:
                                listitems.append(
                                    {
                                        "name": element.text,
                                        "type": element.tag,
                                        "file": path,
                                        "identifier": element.text,
                                        "message": "Label in <%s> not translated: %s"
                                        % (element.tag, element.text),
                                        "line": element.sourceline,
                                        "severity": SEVERITY_WARNING,
                                    }
                                )
                    for check in checks:
                        for element in root.xpath(check[0]):
                            attr = element.attrib[check[1]]
                            for regex in localize_regex:
                                for match in re.finditer(regex, attr):
                                    refs.append(
                                        {
                                            "name": match.group(1),
                                            "type": element.tag,
                                            "file": path,
                                            "line": element.sourceline,
                                        }
                                    )
                            if (
                                not attr.isdigit()
                                and len(attr.strip()) > 1
                                and attr.strip()[0].isalpha()
                            ):
                                if self._is_hex_color(attr):
                                    continue
                                elif self._is_brand_name(attr):
                                    continue
                                elif self._is_bare_infolabel(attr):
                                    listitems.append(
                                        {
                                            "name": attr,
                                            "type": element.tag,
                                            "file": path,
                                            "identifier": attr,
                                            "message": "Possible missing $INFO[] wrapper in attribute %s: %s. "
                                                       "Use $INFO[%s] or <info>%s</info> if dynamic. "
                                                       "Ignore if intentional descriptive text."
                                            % (check[1], attr, attr, attr),
                                            "line": element.sourceline,
                                            "severity": SEVERITY_WARNING,
                                        }
                                    )
                                elif self._is_addon_id(attr):
                                    listitems.append(
                                        {
                                            "name": attr,
                                            "type": element.tag,
                                            "file": path,
                                            "identifier": attr,
                                            "message": "Possible addon ID in attribute %s: %s. "
                                                       "Check if intentional descriptive text or needs translation."
                                            % (check[1], attr),
                                            "line": element.sourceline,
                                            "severity": SEVERITY_WARNING,
                                        }
                                    )
                                else:
                                    listitems.append(
                                        {
                                            "name": attr,
                                            "type": element.tag,
                                            "file": path,
                                            "identifier": attr,
                                            "message": "Label in attribute %s not translated: %s"
                                            % (check[1], attr),
                                            "line": element.sourceline,
                                            "severity": SEVERITY_WARNING,
                                        }
                                    )

        if progress_callback:
            progress_callback(f"Checking {len(refs)} label references against translation files...")

        label_ids = []
        for po_file in self._get_po_files():
            label_ids += [entry.msgctxt for entry in po_file]
        for ref in refs:
            if "#" + ref["name"] not in label_ids:
                ref["message"] = "Label not defined: %s" % ref["name"]
                ref["severity"] = SEVERITY_ERROR
                listitems.append(ref)

        error_count = len(listitems)
        if progress_callback:
            progress_callback(f"Complete: {error_count} label issues found")

        return listitems


def check(addon, validation_index):
    """
    Module-level check function for label validation.

    Args:
        addon: Skin instance
        validation_index: Validation index dict

    Returns:
        List of issues
    """
    checker = ValidationLabel(addon, get_po_files_fn=lambda: addon.get_po_files(), validation_index=validation_index)
    return checker.check()
