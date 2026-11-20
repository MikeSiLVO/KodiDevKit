"""Resource loading for Kodi skins: colors, fonts, and media files."""

import copy
import os
import logging
from typing import Dict, List, Generator, Optional, Tuple
from lxml import etree as ET

from ..utils.files import check_paths, folder_entries, miscased_name, xml_folder_paths
from ..utils.xml import file_needs_expansion, get_root_from_file

logger = logging.getLogger(__name__)


def _read_colors(file_path: str) -> Optional[List[Dict]]:
    """Read colors file into name, line, value, file rows; None if unparseable or not <colors>."""
    root = get_root_from_file(file_path)
    if root is None or root.tag != "colors":
        logger.info("Invalid color file: %s", file_path)
        return None
    # Kodi skips a color without a name or a value
    return [{
        "name": node.attrib.get("name"),
        "line": getattr(node, "sourceline", None),
        "content": (node.text or "").strip(),
        "file": file_path,
    } for node in root.findall("color") if node.get("name") and node.text]


def _on_disk(folder: str, name: str) -> Optional[str]:
    """Find the exact entry on disk, else one differing only by case; None if neither."""
    return name if name in folder_entries(folder) else miscased_name(folder, name)


def _font_row(node, font_file_path: str) -> Optional[Dict]:
    """Read one <font> into a row; None when it lacks a name or filename."""
    name_el = node.find("name")
    file_el = node.find("filename")
    if name_el is None or file_el is None:
        return None
    return {
        "name": (name_el.text or "").strip(),
        "size": (node.findtext("size") or "").strip(),
        "line": getattr(node, "sourceline", None),
        "filename_line": getattr(file_el, "sourceline", None),
        "content": ET.tostring(node, pretty_print=True, encoding="unicode"),
        # a spliced font's line number belongs to the include's file
        "file": node.get("_kdk_inc_file") or font_file_path,
        "filename": (file_el.text or "").strip(),
    }


class SkinResources:
    """Reads a skin's colors, fonts and media file list off disk."""

    def __init__(self, skin_path: str, xml_folders: List[str], default_folder: Optional[str] = None):
        self.skin_path = skin_path
        self.xml_folders = xml_folders
        self.default_folder = default_folder

    def load_colors(self, system_colors_path: Optional[str] = None) -> Tuple[List[Dict], set, set]:
        """Load colors/*.xml and Kodi core's: rows, names every theme has, theme-only names."""
        colors = []
        theme_names = set()
        default_path = None

        # Kodi finds colors/defaults.xml in any case, the exact name first
        folder = _on_disk(self.skin_path, "colors") if self.skin_path else None
        color_dir = os.path.join(self.skin_path, folder) if folder else ""
        if color_dir and os.path.isdir(color_dir):
            default = _on_disk(color_dir, "defaults.xml")
            default_path = os.path.join(color_dir, default) if default else None
            for name in sorted(os.listdir(color_dir)):
                if not name.lower().endswith(".xml"):
                    continue
                file_path = os.path.join(color_dir, name)
                rows = _read_colors(file_path)
                if rows is not None:
                    colors.extend(rows)
                    # the default theme loads defaults.xml and no other skin colors file
                    if file_path != default_path:
                        theme_names.update(row["name"] for row in rows)
                    logger.info("found color file %s including %d colors", file_path, len(rows))

        if system_colors_path and os.path.isfile(system_colors_path):
            rows = _read_colors(system_colors_path)
            if rows is not None:
                colors.extend(rows)
                logger.info("loaded Kodi-core colors from %s (%d entries)",
                            system_colors_path, len(rows))
        else:
            logger.info("Kodi-core colors unavailable (resolved path: %s)", system_colors_path)

        if not colors:
            logger.info("No color file found in skin or system paths")

        color_labels = {c["name"] for c in colors if c["file"] in (default_path, system_colors_path)}

        return colors, color_labels, theme_names - color_labels

    def load_fonts(self, resolver=None) -> Tuple[Dict[str, List[Dict]], Optional[str]]:
        """Load each folder's Font.xml, includes expanded; returns fonts per folder, last file."""
        fonts = {}
        font_file = None

        for folder in self.xml_folders:
            paths = xml_folder_paths(self.skin_path, folder, self.default_folder, "Font.xml", "font.xml")
            font_file = check_paths(paths)
            if not font_file:
                continue

            fonts[folder] = []

            root = get_root_from_file(font_file)
            if root is None:
                continue

            if file_needs_expansion(font_file) and resolver:
                # resolved on a copy; the parse cache shares this root with every other reader
                root = copy.deepcopy(root)
                try:
                    resolver.resolve(root, folder, source_file=font_file)
                except Exception as e:
                    logger.debug("Failed to expand includes in Font.xml: %s", e)

            # Kodi loads no fontset without an id
            fontsets = [fs for fs in root.findall("fontset") if fs.get("id")]
            if not fontsets:
                continue

            for fontset in fontsets:
                for font_node in fontset.findall("font"):
                    font = _font_row(font_node, font_file)
                    if font:
                        fonts[folder].append(font)

        return fonts, font_file

    def load_media_files(self, media_path: str) -> Generator[str, None, None]:
        """Yield every media file as a forward-slash path relative to the media folder."""
        for path, _, files in os.walk(media_path):
            for filename in files:
                yield os.path.relpath(os.path.join(path, filename), media_path).replace("\\", "/")

    def get_font_references(self, window_files: Dict[str, List[str]]) -> Optional[Dict[str, List[Dict]]]:
        """Get every font and monofont use per folder as {file, name, line}; None on bad XML."""
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
                for node in root.xpath(".//font | .//monofont"):
                    if len(node):
                        continue
                    item = {
                        "file": path,
                        "name": node.text if node.text else "",
                        "line": node.sourceline
                    }
                    font_refs[folder].append(item)
        return font_refs
