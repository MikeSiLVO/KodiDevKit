"""Resource loading for Kodi skins: colors, fonts, and media files."""

import os
import logging
from typing import Dict, List, Generator, Optional, Tuple
from lxml import etree as ET

from .. import utils

logger = logging.getLogger(__name__)


class SkinResources:
    """Loads skin resources (colors, fonts, media)."""

    def __init__(self, skin_path: str, xml_folders: List[str]):
        self.skin_path = skin_path
        self.xml_folders = xml_folders

    def load_colors(self, system_colors_path: Optional[str] = None) -> Tuple[List[Dict], set]:
        """Load colors from skin and (optionally) Kodi-core paths.

        Loads from:
          1) <skin>/colors/*.xml (e.g., defaults.xml)
          2) `system_colors_path`, already resolved by `kodi_refs.kodi_colors_xml`
             to either the installed Kodi or a bundled snapshot

        Returns (colors_list, color_labels_set):
          - colors_list: list of dicts with keys name, line, content, file
          - color_labels_set: set of color names for quick lookup
        """
        colors = []

        if self.skin_path:
            color_dir = os.path.join(self.skin_path, "colors")
            if os.path.isdir(color_dir):
                for name in sorted(os.listdir(color_dir)):
                    if not name.lower().endswith(".xml"):
                        continue
                    file_path = os.path.join(color_dir, name)
                    root = utils.get_root_from_file(file_path)
                    if root is None:
                        logger.info("Invalid color file: %s", file_path)
                        continue
                    before = len(colors)
                    for node in root.findall("color"):
                        colors.append({
                            "name": node.attrib.get("name"),
                            "line": getattr(node, "sourceline", None),
                            "content": (node.text or "").strip(),
                            "file": file_path,
                        })
                    added = len(colors) - before
                    logger.info("found color file %s including %d colors", file_path, added)

        if system_colors_path and os.path.isfile(system_colors_path):
            root = utils.get_root_from_file(system_colors_path)
            if root is None:
                logger.info("Invalid color file: %s", system_colors_path)
            else:
                before = len(colors)
                for node in root.findall("color"):
                    colors.append({
                        "name": node.attrib.get("name"),
                        "line": getattr(node, "sourceline", None),
                        "content": (node.text or "").strip(),
                        "file": system_colors_path,
                    })
                logger.info("loaded Kodi-core colors from %s (%d entries)",
                            system_colors_path, len(colors) - before)
        else:
            logger.info("Kodi-core colors unavailable (resolved path: %s)", system_colors_path)

        if not colors:
            logger.info("No color file found in skin or system paths")

        color_labels = {c["name"] for c in colors if c.get("name")}

        return colors, color_labels

    def load_fonts(self, resolver=None) -> Tuple[Dict[str, List[Dict]], Optional[str]]:
        """Load fonts by parsing Font.xml/font.xml in each folder.

        Also expands includes inside fontsets using the provided resolver.
        Returns (fonts_dict, font_file_path) where fonts_dict maps each folder
        to a list of font dicts, and font_file_path is the last processed file.
        """
        fonts = {}
        font_file = None

        for folder in self.xml_folders:
            paths = [
                os.path.join(self.skin_path, folder, "Font.xml"),
                os.path.join(self.skin_path, folder, "font.xml"),
            ]
            font_file = utils.check_paths(paths)
            if not font_file:
                continue

            fonts[folder] = []

            root = utils.get_root_from_file(font_file)
            if root is None:
                continue

            # Expand includes in Font.xml (matches fontcheck.py behavior)
            # This resolves nested includes like Font_Default_Inter -> Font_Default
            if utils.file_needs_expansion(font_file) and resolver:
                try:
                    # Resolve includes in each fontset
                    for fontset in root.findall("fontset"):
                        resolver.resolve_includes(fontset, folder)
                except Exception as e:
                    logger.debug("Failed to expand includes in Font.xml: %s", e)
                    # Fall back to unexpanded if expansion fails

            fontsets = root.findall("fontset")
            if not fontsets:
                continue

            def collect_font(node, font_file_path):
                name_el = node.find("name")
                size_el = node.find("size")
                file_el = node.find("filename")
                if name_el is None or size_el is None or file_el is None:
                    return None
                return {
                    "name": (name_el.text or "").strip(),
                    "size": (size_el.text or "").strip(),
                    "line": getattr(node, "sourceline", None),
                    "filename_line": getattr(file_el, "sourceline", None),
                    "content": ET.tostring(node, pretty_print=True, encoding="unicode"),
                    "file": font_file_path,
                    "filename": (file_el.text or "").strip(),
                }

            # After Kodi-style expansion, includes are resolved and fonts are inline
            for fontset in fontsets:
                for font_node in fontset.findall("font"):
                    font = collect_font(font_node, font_file)
                    if font:
                        fonts[folder].append(font)

        return fonts, font_file

    def load_media_files(self, media_path: str) -> Generator[str, None, None]:
        """Yield relative paths of all files in `media_path`.

        Skips `studio` and `recordlabel` subdirectories. Paths use forward
        slashes with no leading slash.
        """
        for path, _, files in os.walk(media_path):
            if "studio" in path or "recordlabel" in path:
                continue
            for filename in files:
                img_path = os.path.join(path, filename)
                img_path = img_path.replace(media_path, "").replace("\\", "/")
                img_path = img_path.lstrip()
                if img_path.startswith("/"):
                    img_path = img_path[1:]
                yield img_path

    def get_font_references(self, window_files: Dict[str, List[str]]) -> Optional[Dict[str, List[Dict]]]:
        """Extract font references from all window files.

        Returns dict[folder -> list of {file, name, line}] or None on error.
        """
        font_refs = {}
        for folder in self.xml_folders:
            font_refs[folder] = []
            if folder not in window_files:
                continue
            for xml_file in window_files[folder]:
                path = os.path.join(self.skin_path, folder, xml_file)
                root = utils.get_root_from_file(path)
                if root is None:
                    return None
                for node in root.xpath(".//font"):
                    if node.getchildren():
                        continue
                    item = {
                        "file": path,
                        "name": node.text if node.text else "",
                        "line": node.sourceline
                    }
                    font_refs[folder].append(item)
        return font_refs
