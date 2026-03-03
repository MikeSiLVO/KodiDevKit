"""
KodiDevKit is a plugin to assist with Kodi skinning / scripting
using Sublime Text 4
Font validation for Kodi skins.
"""

from __future__ import annotations

import os
import logging
from lxml import etree as ET

from .. import utils
from .constants import SEVERITY_ERROR, SEVERITY_WARNING

logger = logging.getLogger(__name__)

# Fonts required by Kodi that don't need to be explicitly used in XML
REQUIRED_FONTS = {"font13"}


class ValidationFont:
    """Validates font definitions and usage in Kodi skins."""

    def __init__(self, addon, resolve_include_fn=None, validation_index=None):
        """
        Args:
            addon: Addon/Skin instance with fonts, includes, xml_folders
            resolve_include_fn: Callable to resolve include content (optional)
            validation_index: Pre-built validation index for performance (optional)
        """
        self.addon = addon
        self._resolve_include = resolve_include_fn
        self._validation_index = validation_index

    def check(self, progress_callback=None):
        """
        Validate fonts declared by the skin.
        Returns list of {"message": str, "file": str, "line": int}.
        """
        def row(message, file_path="", line=0, severity=SEVERITY_ERROR):
            return {"message": message, "file": file_path, "line": line, "severity": severity}

        if not self.addon:
            return [row("No font issues found", "", 0)]

        try:
            import sublime
            kodi_path = (
                sublime.load_settings("kodidevkit.sublime-settings")
                .get("kodi_path", "")
                .strip()
            )
        except ImportError:
            kodi_path = ""

        if kodi_path and not os.path.isdir(kodi_path):
            return [row(f"Kodi path not found: {kodi_path}")]

        skin_fonts_dir = os.path.join(self.addon.path, "fonts")
        core_dirs = []

        try:
            skin_files = {f.casefold(): f for f in os.listdir(skin_fonts_dir)} if os.path.isdir(skin_fonts_dir) else {}
        except Exception:
            skin_files = {}

        if kodi_path:
            core_dirs = [
                os.path.join(kodi_path, "media", "Fonts"),
                os.path.join(kodi_path, "media", "fonts"),
            ]

        core_files_maps = []
        for d in core_dirs:
            try:
                if os.path.isdir(d):
                    core_files_maps.append((d, {f.casefold(): f for f in os.listdir(d)}))
            except Exception:
                pass

        issues = []

        total_fonts = sum(len(items) for items in (self.addon.fonts or {}).values()) if getattr(self.addon, "fonts", None) else 0
        total_folders = len(getattr(self.addon, "xml_folders", []))

        if progress_callback:
            progress_callback(f"Checking {total_fonts} font definitions in {total_folders} folders...")

        if getattr(self.addon, "fonts", None):
            for folder, items in (self.addon.fonts or {}).items():
                for it in items:
                    name = (it.get("name") or "").strip()
                    filename = (it.get("filename") or "").strip()
                    file_src = it.get("file") or "N/A"
                    line_no = int(it.get("line") or 0)
                    fn_line = int(it.get("filename_line") or 0) or line_no

                    if filename and not utils.is_dynamic_expression(filename):
                        rel = filename.replace("\\", "/").strip()

                        # Skip validation for resource:// paths (font addon packages)
                        # These reference fonts from separate resource.font.* addons
                        if rel.startswith("resource://"):
                            continue

                        base = os.path.basename(rel)

                        exists = False
                        actual = None

                        if "/" not in rel:
                            actual = skin_files.get(base.casefold())
                            exists = bool(actual and os.path.isfile(os.path.join(skin_fonts_dir, actual)))
                        else:
                            rel_path = os.path.join(skin_fonts_dir, rel)
                            if os.path.isfile(rel_path):
                                exists = True
                                actual = os.path.basename(rel_path)

                        if exists and actual and actual != base:
                            issues.append(row(f"Case mismatch in font filename '{filename}' (actual '{actual}')", file_src, fn_line, SEVERITY_WARNING))

                        if not exists and core_files_maps:
                            for d, cmap in core_files_maps:
                                actual_core = cmap.get(base.casefold())
                                if actual_core:
                                    exists = os.path.isfile(os.path.join(d, actual_core))
                                    if exists and actual_core != base:
                                        issues.append(
                                            row(
                                                f"Case mismatch in core font filename '{filename}' (actual '{actual_core}')",
                                                file_src,
                                                fn_line,
                                                SEVERITY_WARNING,
                                            )
                                        )
                                    if exists:
                                        break

                        core_safe = {"arial.ttf", "teletext.ttf"}
                        if not exists and base.lower() not in core_safe:
                            issues.append(row(f"Missing font file '{filename}' for '{name or '?'}'", file_src, fn_line))

                        _, ext = os.path.splitext(base)
                        if not ext:
                            issues.append(row(f"Warning: font filename has no extension: '{filename}'", file_src, fn_line, SEVERITY_WARNING))
                        elif ext.lower() != ".ttf":
                            issues.append(row(f"Warning: Non-TTF font file '{filename}' for '{name or '?'}'", file_src, fn_line, SEVERITY_WARNING))

        for folder in getattr(self.addon, "xml_folders", []):
            fontsets = self._parse_fontsets(folder)
            if not fontsets:
                continue

            # Empty fontsets are allowed - they can be conditionally populated
            # or used as fallbacks, so we skip this check
            # for fs in fontsets:
            #     if not fs["fonts"]:
            #         issues.append(row(f"Empty <fontset> '{fs['id']}'", fs["file"], fs["line"]))

            if not any(fs["unicode"] for fs in fontsets):
                issues.append(row("At least one <fontset> must have unicode='true'", fontsets[0]["file"], fontsets[0]["line"]))

            any_font13 = any(any(f["name"] == "font13" for f in fs["fonts"]) for fs in fontsets)
            if not any_font13:
                issues.append(row("Missing required default font 'font13'", fontsets[0]["file"], fontsets[0]["line"]))
            else:
                for fs in fontsets:
                    if not any(f["name"] == "font13" for f in fs["fonts"]):
                        issues.append(row(f"Warning: 'font13' not present in fontset '{fs['id']}'", fs["file"], fs["line"], SEVERITY_WARNING))

            for fs in fontsets:
                name_to_locs = {}
                for f in fs["fonts"]:
                    nm = (f.get("name") or "").strip()
                    fn = (f.get("filename") or "").strip()
                    sz = (f.get("size") or "").strip()

                    if not nm:
                        issues.append(row("Missing <name> in <font>", f["file"], f["line"]))
                    if not fn:
                        issues.append(row(f"Missing <filename> for font '{nm or '?'}'", f["file"], f["line"]))

                    if not sz:
                        issues.append(row(f"Missing <size> for font '{nm or '?'}'", f["file"], f["line"]))
                    elif not utils.is_dynamic_expression(sz):
                        try:
                            sz_val = int(sz)
                            if sz_val <= 0:
                                issues.append(row(f"Font size must be a positive integer, got {sz}", f["file"], f["line"]))
                        except Exception:
                            issues.append(row(f"Invalid font size '{sz}' for '{nm or '?'}'", f["file"], f["line"]))

                    if nm:
                        name_to_locs.setdefault(nm, []).append((f["file"], f["line"]))

                for nm, locs in name_to_locs.items():
                    if len(locs) > 1:
                        for fp, ln in locs:
                            issues.append(row(f"Duplicate font name '{nm}' within fontset '{fs['id']}'", fp, ln, SEVERITY_WARNING))

            base = fontsets[0]
            base_names = {f["name"] for f in base["fonts"] if f["name"]}
            for fs in fontsets[1:]:
                names = {f["name"] for f in fs["fonts"] if f["name"]}
                missing = sorted(base_names - names)
                extra = sorted(names - base_names)
                for n in missing:
                    issues.append(row(f"fontset '{fs['id']}' missing font '{n}' compared to '{base['id']}'", fs["file"], fs["line"], SEVERITY_WARNING))
                for n in extra:
                    issues.append(row(f"fontset '{fs['id']}' has extra font '{n}' not in '{base['id']}'", fs["file"], fs["line"], SEVERITY_WARNING))

        if getattr(self.addon, "fonts", None):
            if self._validation_index:
                for folder in self.addon.xml_folders:
                    fonts_defined = self._validation_index.get('fonts_defined', {}).get(folder, {})
                    fonts_used = self._validation_index.get('fonts_used', {}).get(folder, {})
                    used_names = set()

                    for font_name, usages in fonts_used.items():
                        used_names.add(font_name)
                        if utils.is_dynamic_expression(font_name):
                            continue
                        if font_name not in fonts_defined:
                            first_usage = usages[0] if usages else {}
                            issues.append({
                                "message": f"Font '{font_name}' is used but not defined in Fonts.xml",
                                "file": first_usage.get('file', ''),
                                "line": first_usage.get('line', 0),
                                "severity": SEVERITY_ERROR,
                            })

                    for font_name, font_info in fonts_defined.items():
                        if font_name not in used_names and font_name not in REQUIRED_FONTS:
                            issues.append({
                                "message": f"Unused font definition: '{font_name}'",
                                "file": font_info.get('file', ''),
                                "line": font_info.get('line', 0),
                                "severity": SEVERITY_WARNING,
                            })
            else:
                defined_map = self._defined_font_names_map()
                for folder, defined in defined_map.items():
                    used = set()

                    for name, path, line in self._iter_used_font_names(folder):
                        used.add(name)
                        if utils.is_dynamic_expression(name):
                            continue
                        if name not in defined:
                            issues.append({"message": f"Font '{name}' is used but not defined in Fonts.xml", "file": path, "line": line, "severity": SEVERITY_ERROR})

                    for it in (self.addon.fonts.get(folder, []) or []):
                        nm = (it.get("name") or "").strip()
                        if nm and nm not in used and nm not in REQUIRED_FONTS:
                            issues.append({"message": f"Unused font definition: '{nm}'", "file": it.get("file") or "", "line": int(it.get("line") or 0), "severity": SEVERITY_WARNING})

        error_count = len(issues)
        missing_count = len([i for i in issues if "Missing font file" in i.get("message", "")])
        undefined_count = len([i for i in issues if "not defined in Fonts.xml" in i.get("message", "")])

        if progress_callback:
            if error_count > 0:
                progress_callback(f"Complete: {error_count} issues ({missing_count} missing files, {undefined_count} undefined)")
            else:
                progress_callback("Complete: No font issues found")

        return issues or [{"message": "No font issues found", "file": "", "line": 0}]

    def _parse_fontsets(self, folder):
        """Return list of fontset dicts with resolved includes."""
        out = []
        candidates = [
            os.path.join(self.addon.path, folder, "Fonts.xml"),
            os.path.join(self.addon.path, folder, "Font.xml"),
            os.path.join(self.addon.path, folder, "font.xml"),
        ]
        path = next((p for p in candidates if os.path.isfile(p)), None)
        if not path:
            return out

        root = utils.get_root_from_file(path)
        if root is None:
            return out

        # Expand includes and $PARAM in Font.xml if resolver available (with performance check)
        if self._resolve_include and utils.file_needs_expansion(path):
            try:
                root = self._resolve_include(root, folder=folder)
            except Exception:
                # Fall back to unexpanded if expansion fails
                pass

        def add_font_from_node(fnode, src_file, include_def=None):
            nm = (fnode.findtext("name") or "").strip()
            fn = (fnode.findtext("filename") or "").strip()
            sz = (fnode.findtext("size") or "").strip()
            ln = getattr(fnode, "sourceline", 0) or 0
            if include_def and nm:
                ln = utils.find_font_line_in_include(include_def, nm)
                src_file = include_def.get("file") or src_file
            return {"name": nm, "filename": fn, "size": sz, "file": src_file, "line": ln}

        for fs in root.findall(".//fontset"):
            fs_id = fs.attrib.get("id") or fs.attrib.get("name") or "fontset"
            unicode_flag = str(fs.attrib.get("unicode", "")).lower() == "true"
            fs_line = getattr(fs, "sourceline", 0) or 0

            fonts = [add_font_from_node(f, path) for f in fs.findall("font")]

            for inc_node in fs.findall("include"):
                inc_name = (inc_node.text or "").strip()
                if not inc_name:
                    continue
                for inc in self.addon.includes.get(folder, []):
                    if inc.get("type") == "include" and inc.get("name") == inc_name:
                        content = utils.resolve_include_content(inc, self._resolve_include)
                        if not content:
                            continue
                        try:
                            cont_root = ET.fromstring(f"<root>{content}</root>")
                            for f in cont_root.findall(".//font"):
                                fonts.append(add_font_from_node(f, path, include_def=inc))
                        except Exception:
                            pass

            out.append({"id": fs_id, "unicode": unicode_flag, "file": path, "line": fs_line, "fonts": fonts})
        return out

    def _defined_font_names_map(self):
        """{folder -> set of defined font names}."""
        out = {}
        if not getattr(self.addon, "fonts", None):
            return out
        for folder, items in (self.addon.fonts or {}).items():
            out[folder] = {
                (it.get("name") or "").strip()
                for it in (items or [])
                if (it.get("name") or "").strip()
            }
        return out

    def _iter_used_font_names(self, folder):
        """Yield (name, file_path, line) for font usages in window XMLs."""
        xml_dir = os.path.join(self.addon.path, folder)
        if not os.path.isdir(xml_dir):
            return
        for fname in os.listdir(xml_dir):
            if not fname.lower().endswith(".xml"):
                continue
            if fname.lower() in ("font.xml", "fonts.xml"):
                continue
            path = os.path.join(xml_dir, fname)
            root = utils.get_root_from_file(path)
            if root is None:
                continue

            # Expand includes and $PARAM if resolver available (with performance check)
            resolve_fn = self._resolve_include
            if resolve_fn and utils.file_needs_expansion(path):
                try:
                    root = resolve_fn(root, folder=folder)
                except Exception:
                    # Fall back to unexpanded if expansion fails
                    pass

            for node in root.xpath(".//font"):
                nm = (node.text or "").strip()
                # After expansion, skip only dynamic expressions (not simple $PARAM)
                if not nm or utils.is_dynamic_expression(nm):
                    continue
                yield nm, path, getattr(node, "sourceline", 0) or 0


def check(addon, validation_index):
    """
    Module-level check function for font validation.

    Args:
        addon: Skin instance
        validation_index: Validation index dict

    Returns:
        List of issues
    """
    checker = ValidationFont(addon, validation_index=validation_index)
    return checker.check()
