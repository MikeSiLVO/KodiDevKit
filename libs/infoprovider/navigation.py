"""
Navigation and jump-to-definition mixin for InfoProvider.
"""

from __future__ import annotations

import os
import re
import logging
from typing import TYPE_CHECKING
from lxml import etree as ET

from .. import utils

from typing import Any

logger = logging.getLogger(__name__)


class NavigationMixin:
    """Handles jump-to-definition for fonts, includes, colors, labels."""

    addon: Any

    if TYPE_CHECKING:
        def get_po_files(self) -> list: ...

    def go_to_tag(self, keyword, folder):
        """
        Jump to a definition by ref name or label id.
        """
        if not self.addon or not keyword:
            return False
        kw = str(keyword).strip()

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

    def _get_includes_for_folder(self, folder):
        """
        Get includes for a folder, supporting both legacy and new 5-map structure.
        Returns a list of include-like dicts for iteration.
        Works with both Skin (5 maps) and Addon (legacy) instances.
        """
        if not self.addon:
            return []

        if hasattr(self.addon, 'include_map'):
            result = []

            for name, (node, params, file_path) in self.addon.include_map.get(folder, {}).items():  # type: ignore[attr-defined]
                from ..skin.include import SkinInclude
                definition = node.find("definition")
                include_body = definition if definition is not None else node
                inc = SkinInclude(node=include_body, file=file_path)
                result.append({
                    "name": name,
                    "type": "include",
                    "file": inc.file,
                    "line": inc.line,
                    "content": inc.content,
                    "node": inc.node,
                    "params": params
                })

            for name, (node, file_path) in self.addon.variable_map.get(folder, {}).items():  # type: ignore[attr-defined]
                from ..skin.include import SkinInclude
                var_inc = SkinInclude(node=node, file=file_path)
                result.append({
                    "name": name,
                    "type": "variable",
                    "file": var_inc.file,
                    "line": var_inc.line,
                    "content": var_inc.content,
                    "node": var_inc.node
                })

            for control_type, (node, file_path) in self.addon.default_map.get(folder, {}).items():  # type: ignore[attr-defined]
                from ..skin.include import SkinInclude
                def_inc = SkinInclude(node=node, file=file_path)
                result.append({
                    "name": control_type,
                    "type": "default",
                    "file": def_inc.file,
                    "line": def_inc.line,
                    "content": def_inc.content,
                    "node": def_inc.node
                })

            return result

        return self.addon.includes.get(folder, [])
