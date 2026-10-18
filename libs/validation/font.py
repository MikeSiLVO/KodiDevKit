"""Checks a skin's font definitions, their files, and where fonts are used."""

from __future__ import annotations

import os
import logging

from ..utils.files import folder_entries, miscased_name
from ..utils.xml import file_needs_expansion, get_root_from_file
from ..utils.validation import CallContexts, resolve_param_in_name
from ..utils.expressions import is_dynamic_expression
from .constants import SEVERITY_ERROR, SEVERITY_WARNING

logger = logging.getLogger(__name__)

# Kodi's fallback fonts, which count as used
REQUIRED_FONTS = {"font13"}

# the font files every Kodi install ships in its own media/Fonts
KODI_FONTS = {"arial.ttf", "teletext.ttf"}


def _undefined_font_issue(name, defined, folded, file, line, unloaded=()):
    """Issue for a used font name not defined exactly or never loaded, or None when it is fine."""
    if name.casefold() in unloaded:
        rule, message = "fonts.uses-not-loaded", f"Font '{name}' is never loaded: Kodi only loads .ttf fonts"
    elif name in defined:
        return None
    elif name.lower() in ("-", "noop"):
        rule, message = "fonts.not-empty", f"'{name}' is not an empty font in Kodi; leave the tag out"
    elif name.casefold() in folded:
        # Kodi matches font names case-insensitively, repo review requires the exact name
        rule = "fonts.name-case-mismatch"
        message = f"Case mismatch in font name '{name}' (defined as '{folded[name.casefold()]}')"
    else:
        rule, message = "fonts.undefined", f"Font '{name}' is used but not defined in Font.xml"
    return {"message": message, "file": file, "line": line, "severity": SEVERITY_ERROR,
            "rule": rule, "subject": name}


class ValidationFont:
    """Checker for font definitions, their files, their fontsets and where fonts are used."""

    def __init__(self, addon, resolve_include_fn=None, validation_index=None):
        self.addon = addon
        self._resolve_include = resolve_include_fn
        self._validation_index = validation_index

    def _resolve_font_path(self, base_dir, rel):
        """Resolve the path to its on-disk spelling, ignoring case; None when absent."""
        current = base_dir
        parts = []
        for part in rel.split("/"):
            match = next((e for e in folder_entries(current) if e.casefold() == part.casefold()), None)
            if match is None:
                return None
            parts.append(match)
            current = os.path.join(current, match)
        return "/".join(parts) if os.path.isfile(current) else None

    def check(self, progress_callback=None):
        """Check the fonts, a row per bad font, file, fontset or use, or one for a bad Kodi path."""
        def row(message, file_path="", line=0, severity=SEVERITY_ERROR, *, rule, subject=""):
            return {"message": message, "file": file_path, "line": line, "severity": severity,
                    "rule": rule, "subject": subject}

        if not self.addon:
            return []

        kodi_path = ""
        if hasattr(self.addon, 'settings') and self.addon.settings:
            kodi_path = (self.addon.settings.get("kodi_path") or "").strip()

        if kodi_path and not os.path.isdir(kodi_path):
            return [row(f"Kodi path not found: {kodi_path}", rule="fonts.kodi-path-missing", subject=kodi_path)]

        skin_fonts_dir = os.path.join(self.addon.path, "fonts")
        core_dirs = []

        if kodi_path:
            core_dirs = [
                os.path.join(kodi_path, "media", "Fonts"),
                os.path.join(kodi_path, "media", "fonts"),
            ]

        core_files_maps = [(d, {f.casefold(): f for f in folder_entries(d)}) for d in core_dirs]

        issues = []

        for folder in getattr(self.addon, "xml_folders", []):
            folder_path = os.path.join(self.addon.path, folder)
            actual = miscased_name(folder_path, "Font.xml")
            if actual:
                issues.append(row(f"{actual} must be named Font.xml; Kodi does not load it on Linux",
                                  os.path.join(folder_path, actual), 1, rule="fonts.misnamed-font-xml", subject=actual))

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

                    if filename and not is_dynamic_expression(filename):
                        rel = filename.replace("\\", "/").strip()

                        # a resource:// font lives in another addon
                        if rel.startswith("resource://"):
                            continue

                        rel = "/".join(p for p in rel.split("/") if p and p != ".")
                        base = os.path.basename(rel)

                        actual = self._resolve_font_path(skin_fonts_dir, rel)
                        exists = actual is not None

                        if exists and actual != rel:
                            issues.append(row(f"Case mismatch in font filename '{filename}' (actual '{actual}'), Kodi still loads it", file_src, fn_line, SEVERITY_WARNING,
                                              rule="fonts.file-case-mismatch", subject=filename))

                        if not exists and core_files_maps:
                            for d, cmap in core_files_maps:
                                actual_core = cmap.get(base.casefold())
                                if actual_core:
                                    exists = os.path.isfile(os.path.join(d, actual_core))
                                    if exists and actual_core != base:
                                        issues.append(
                                            row(
                                                f"Case mismatch in core font filename '{filename}' (actual '{actual_core}'), Kodi still loads it",
                                                file_src,
                                                fn_line,
                                                SEVERITY_WARNING,
                                                rule="fonts.core-file-case-mismatch",
                                                subject=filename,
                                            )
                                        )
                                    if exists:
                                        break

                        if not exists and base.lower() not in KODI_FONTS:
                            issues.append(row(f"Missing font file '{filename}' for '{name or '?'}'", file_src, fn_line,
                                              rule="fonts.missing-file", subject=filename))

                        if not base.lower().endswith(".ttf"):
                            issues.append(row(f"Kodi only loads .ttf fonts, so '{name or '?'}' ({filename}) is never "
                                              f"loaded", file_src, fn_line, rule="fonts.not-loaded", subject=name))

        for folder in getattr(self.addon, "xml_folders", []):
            fontsets = self._parse_fontsets(folder)
            if not fontsets:
                continue

            for fs in fontsets:
                if fs["unicode"]:
                    issues.append(row(f"Obsolete unicode attribute on fontset '{fs['id']}', Kodi ignores it",
                                      fs["file"], fs["line"], SEVERITY_WARNING,
                                      rule="fonts.obsolete-unicode", subject=fs["id"]))

            any_font13 = any(any(f["name"] == "font13" for f in fs["fonts"]) for fs in fontsets)
            if not any_font13:
                issues.append(row("Missing required default font 'font13'", fontsets[0]["file"], fontsets[0]["line"],
                                  rule="fonts.missing-font13", subject="font13"))
            else:
                for fs in fontsets:
                    if not any(f["name"] == "font13" for f in fs["fonts"]):
                        issues.append(row(f"Fontset '{fs['id']}' has no font13, which Kodi uses for any font "
                                          f"name the fontset lacks", fs["file"], fs["line"], SEVERITY_WARNING,
                                          rule="fonts.fontset-missing-font13", subject=fs["id"]))

            for fs in fontsets:
                name_to_locs = {}
                for f in fs["fonts"]:
                    nm = (f.get("name") or "").strip()
                    fn = (f.get("filename") or "").strip()
                    sz = (f.get("size") or "").strip()

                    if not nm:
                        issues.append(row("Missing <name> in <font>", f["file"], f["line"],
                                          rule="fonts.missing-name", subject=fn))
                    if not fn:
                        issues.append(row(f"Missing <filename> for font '{nm or '?'}'", f["file"], f["line"],
                                          rule="fonts.missing-filename", subject=nm))

                    if sz and not is_dynamic_expression(sz):
                        try:
                            sz_val = int(sz)
                            if sz_val < 0:
                                issues.append(row(f"Font size must not be negative, got {sz}", f["file"], f["line"],
                                                  rule="fonts.negative-size", subject=nm))
                        except ValueError:
                            issues.append(row(f"Invalid font size '{sz}' for '{nm or '?'}'", f["file"], f["line"],
                                              rule="fonts.invalid-size", subject=nm))

                    if nm:
                        name_to_locs.setdefault(nm, []).append(f)

                for nm, copies in name_to_locs.items():
                    # a conditional copy never becomes the one Kodi keeps
                    first = next((i for i, f in enumerate(copies) if not f["conditional"]), len(copies))
                    if len(copies) - first > 1:
                        for f in copies[first:]:
                            issues.append(row(f"Duplicate font name '{nm}' within fontset '{fs['id']}'", f["file"], f["line"], SEVERITY_WARNING,
                                              rule="fonts.duplicate", subject=nm))

            base = fontsets[0]
            base_names = {f["name"] for f in base["fonts"] if f["name"]}
            for fs in fontsets[1:]:
                names = {f["name"] for f in fs["fonts"] if f["name"]}
                missing = sorted(base_names - names)
                extra = sorted(names - base_names)
                for n in missing:
                    issues.append(row(f"fontset '{fs['id']}' missing font '{n}' compared to '{base['id']}'", fs["file"], fs["line"], SEVERITY_WARNING,
                                      rule="fonts.inconsistent-missing", subject=n))
                for n in extra:
                    issues.append(row(f"fontset '{fs['id']}' has extra font '{n}' not in '{base['id']}'", fs["file"], fs["line"], SEVERITY_WARNING,
                                      rule="fonts.inconsistent-extra", subject=n))

        if getattr(self.addon, "fonts", None) and self._validation_index:
            for folder in self.addon.xml_folders:
                fonts_defined = self._validation_index.get('fonts_defined', {}).get(folder, {})
                fonts_used = self._validation_index.get('fonts_used', {}).get(folder, {})
                used_names = set()

                folded = {n.casefold(): n for n in fonts_defined}
                calls = None
                for font_name, usages in fonts_used.items():
                    first_usage = usages[0] if usages else {}
                    checks = [(font_name, first_usage)]
                    if "$PARAM[" in font_name and any(u.get('include') for u in usages):
                        calls = calls or CallContexts(self.addon, folder)
                        outside = [u for u in usages if not u.get('include')]
                        # each call's params name the font Kodi looks up for it
                        checks = [(font_name, outside[0])] if outside else []
                        checks += [(name, usage) for usage in usages if usage.get('include')
                                   for name in sorted({resolve_param_in_name(font_name, context)
                                                       for context in calls.for_include(usage['include'])})]
                    for name, usage in checks:
                        exact = name in fonts_defined
                        used_names.add(name if exact else folded.get(name.casefold(), name))
                        if is_dynamic_expression(name):
                            continue
                        issue = _undefined_font_issue(name, fonts_defined, folded,
                                                      usage.get('file', ''), usage.get('line', 0),
                                                      self._unloaded_fonts(folder))
                        if issue:
                            issues.append(issue)

                for font_name, font_info in fonts_defined.items():
                    if font_name not in used_names and font_name not in REQUIRED_FONTS:
                        issues.append({
                            "message": f"Unused font definition: '{font_name}'",
                            "file": font_info.get('file', ''),
                            "line": font_info.get('line', 0),
                            "severity": SEVERITY_WARNING,
                            "rule": "fonts.unused",
                            "subject": font_name,
                        })

        # an include pulled into several fontsets reports each of its fonts once per set
        seen = set()
        deduped = []
        for it in issues:
            key = (it.get("message"), it.get("file"), it.get("line"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(it)
        issues = deduped

        error_count = len(issues)
        missing_count = len([i for i in issues if "Missing font file" in i.get("message", "")])
        undefined_count = len([i for i in issues if "not defined in Font.xml" in i.get("message", "")])

        if progress_callback:
            if error_count > 0:
                progress_callback(f"Complete: {error_count} issues ({missing_count} missing files, {undefined_count} undefined)")
            else:
                progress_callback("Complete: No font issues found")

        return issues

    def _unloaded_fonts(self, folder):
        """Casefolded names whose every definition names a file Kodi will not load, as not .ttf."""
        loads, skips = set(), set()
        for font in (getattr(self.addon, "fonts", None) or {}).get(folder, []) or []:
            name = (font.get("name") or "").strip().casefold()
            filename = (font.get("filename") or "").strip()
            if not name or not filename or is_dynamic_expression(filename):
                continue
            # Kodi compares the extension of the lowercased name
            (loads if filename.lower().endswith(".ttf") else skips).add(name)
        return skips - loads

    def _parse_fontsets(self, folder):
        """Parse the folder's fontsets with their fonts, include-supplied ones too."""
        out = []
        candidates = [
            os.path.join(self.addon.path, folder, "Font.xml"),
            os.path.join(self.addon.path, folder, "font.xml"),
        ]
        path = next((p for p in candidates if os.path.isfile(p)), None)
        if not path:
            return out

        root = get_root_from_file(path)
        if root is None:
            return out

        if self._resolve_include and file_needs_expansion(path):
            root = self._resolve_include(root, folder=folder)

        def add_font_from_node(fnode, src_file):
            nm = (fnode.findtext("name") or "").strip()
            fn = (fnode.findtext("filename") or "").strip()
            sz = (fnode.findtext("size") or "").strip()
            ln = getattr(fnode, "sourceline", 0) or 0
            src_file = fnode.get("_kdk_inc_file") or src_file
            return {"name": nm, "filename": fn, "size": sz, "file": src_file, "line": ln,
                    "conditional": fnode.get("_kdk_inc_cond") == "1"}

        for fs in root.findall(".//fontset"):
            fs_id = fs.attrib.get("id") or fs.attrib.get("name") or "fontset"
            unicode_flag = "unicode" in fs.attrib
            fs_line = getattr(fs, "sourceline", 0) or 0

            fonts = [add_font_from_node(f, path) for f in fs.findall("font")]

            out.append({"id": fs_id, "unicode": unicode_flag, "file": path, "line": fs_line, "fonts": fonts})
        return out
