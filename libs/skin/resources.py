"""Resource loading for Kodi skins: colors, fonts, and media files."""

import os
import logging
from typing import Dict, List, Generator, Optional, Tuple
from lxml import etree as ET

from ..utils.files import check_paths
from ..utils.xml import file_needs_expansion, get_root_from_file

logger = logging.getLogger(__name__)


class SkinResources:
    """Reads a skin's colors, fonts and media file list off disk."""

    def __init__(self, skin_path: str, xml_folders: List[str]):
        self.skin_path = skin_path
        self.xml_folders = xml_folders

    def load_colors(self, system_colors_path: Optional[str] = None) -> Tuple[List[Dict], set]:
        """Load the skin's colors/*.xml then Kodi core's; returns the rows and their name set."""
        colors = []

        if self.skin_path:
            color_dir = os.path.join(self.skin_path, "colors")
            if os.path.isdir(color_dir):
                for name in sorted(os.listdir(color_dir)):
                    if not name.lower().endswith(".xml"):
                        continue
                    file_path = os.path.join(color_dir, name)
                    root = get_root_from_file(file_path)
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
            root = get_root_from_file(system_colors_path)
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
        """Load each folder's Font.xml, includes expanded; returns fonts per folder, last file."""
        fonts = {}
        font_file = None

        for folder in self.xml_folders:
            paths = [
                os.path.join(self.skin_path, folder, "Font.xml"),
                os.path.join(self.skin_path, folder, "font.xml"),
            ]
            font_file = check_paths(paths)
            if not font_file:
                continue

            fonts[folder] = []

            root = get_root_from_file(font_file)
            if root is None:
                continue

            if file_needs_expansion(font_file) and resolver:
                try:
                    for fontset in root.findall("fontset"):
                        resolver.resolve_includes(fontset, folder)
                except Exception as e:
                    logger.debug("Failed to expand includes in Font.xml: %s", e)

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
                    # a spliced font's line number belongs to the include's file
                    "file": node.get("_kdk_inc_file") or font_file_path,
                    "filename": (file_el.text or "").strip(),
                }

            for fontset in fontsets:
                for font_node in fontset.findall("font"):
                    font = collect_font(font_node, font_file)
                    if font:
                        fonts[folder].append(font)

        return fonts, font_file

    def load_media_files(self, media_path: str) -> Generator[str, None, None]:
        """Yield every media file as a forward-slash path relative to the media folder."""
        for path, _, files in os.walk(media_path):
            for filename in files:
                yield os.path.relpath(os.path.join(path, filename), media_path).replace("\\", "/")

    def get_font_references(self, window_files: Dict[str, List[str]]) -> Optional[Dict[str, List[Dict]]]:
        """Get every <font> reference per folder as {file, name, line}; None on a parse failure."""
        font_refs = {}
        for folder in self.xml_folders:
            font_refs[folder] = []
            if folder not in window_files:
                continue
            for xml_file in window_files[folder]:
                path = os.path.join(self.skin_path, folder, xml_file)
                root = get_root_from_file(path)
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
