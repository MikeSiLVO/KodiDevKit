"""Navigation and jump-to-definition mixin for InfoProvider."""

from __future__ import annotations

import os
import re
import logging
from lxml import etree as ET

from .. import utils
from .checker import CheckerMixin

from typing import Any

logger = logging.getLogger(__name__)


# Extends the engine's own implementations via super(); InfoProvider lists this
# before CheckerMixin, so the MRO is unchanged.
class NavigationMixin(CheckerMixin):
    """Handles jump-to-definition for fonts, includes, colors, labels."""

    addon: Any

    def go_to_tag(self, keyword, folder):
        """Jump to a definition by ref name or label id."""
        if not self.addon or not keyword:
            return False
        kw = str(keyword).strip()
        # Caret lands in a whole `$MAP[Name, ListItem.X]` body; the name is the first arg.
        if "," in kw:
            kw = kw.split(",", 1)[0].strip()

        if kw.lower().endswith(".xml"):
            path = self._xml_file_in_folder(kw, folder)
            if path:
                return "%s:1" % path

        if kw.isdigit():
            for po_file in self.get_po_files():
                for entry in po_file:
                    if entry.msgctxt == "#" + kw:
                        return "%s:%s" % (po_file.fpath, entry.linenum)
            return False

        font_node = None
        for node in self.addon.fonts.get(folder, []):
            if node.get("name") == kw:
                font_node = node
                path = (node.get("file") or "").strip()
                if path and os.path.basename(path).lower() not in ("font.xml", "fonts.xml"):
                    return "%s:%s" % (path, int(node.get("line") or 0))
                break  # found matching font; try resolving include below

        if font_node:
            for inc in self._get_includes_for_folder(folder):
                if inc.get("type") != "include":
                    continue
                content = utils.resolve_include_content(inc)
                if not content:
                    continue
                try:
                    root = ET.fromstring(f"<root>{content}</root>")
                    for n in root.findall(".//font/name"):
                        if (n.text or "").strip() == kw:
                            line = utils.find_font_line_in_include(inc, kw)
                            return "%s:%s" % (inc.get("file"), line)
                except Exception:
                    if isinstance(content, str):
                        pat = rf"<name>\s*{re.escape(kw)}\s*</name>"
                        if re.search(pat, content, re.I):
                            return "%s:%s" % (inc.get("file"), int(inc.get("line") or 0))

            path = font_node.get("file") or os.path.join(self.addon.path, folder, "Font.xml")
            return "%s:%s" % (path, int(font_node.get("line") or 0))

        for node in self._get_includes_for_folder(folder):
            if node.get("name") == kw:
                return "%s:%s" % (node.get("file"), node.get("line"))

        for node in self.addon.colors:
            if node.get("name") == kw and node.get("file", "").endswith(("defaults.xml", "colors.xml")):
                return "%s:%s" % (node.get("file"), node.get("line"))

        logger.info("no node with name %s found", kw)
        return False

    def _xml_file_in_folder(self, filename, folder):
        """Path of `filename` in the skin's `folder`, matched case-sensitively.

        Kodi reads loose skin files through the OS, so a reference whose case does not match
        the file works on Windows and fails on Linux. Comparing against the real directory
        entries keeps the jump honest on either host.
        """
        if not folder:
            return None
        directory = os.path.join(self.addon.path, folder)
        try:
            entries = os.listdir(directory)
        except OSError:
            return None
        if filename in entries:
            return os.path.join(directory, filename)
        return None

    def _get_includes_for_folder(self, folder):
        """Engine's list plus the expression/constant entries goto-def needs."""
        result = super()._get_includes_for_folder(folder)
        if not self.addon or not hasattr(self.addon, "include_map"):
            return result

        expr_source = getattr(self.addon, "expression_source_map", {}).get(folder, {})
        for name, (file_path, line) in expr_source.items():
            result.append({
                "name": name,
                "type": "expression",
                "file": file_path,
                "line": line,
                "content": self.addon.expression_map.get(folder, {}).get(name, ""),
            })

        for name, (node, file_path) in getattr(self.addon, "map_map", {}).get(folder, {}).items():
            result.append({
                "name": name,
                "type": "map",
                "file": file_path,
                "line": getattr(node, "sourceline", 0) or 0,
                "content": node,
            })

        const_source = getattr(self.addon, "constant_source_map", {}).get(folder, {})
        for name, (file_path, line) in const_source.items():
            result.append({
                "name": name,
                "type": "constant",
                "file": file_path,
                "line": line,
                "content": self.addon.constant_map.get(folder, {}).get(name, ""),
            })

        return result
