"""Checks the includes a skin calls and defines, and the include files it names."""

import os
import re

from ..utils.validation import (
    deduplicate_issues,
    find_includes_in_skinshortcuts_template,
    find_skinshortcuts_template,
    reference_issues,
    shadowed_issues,
    should_report_progress,
)
from ..utils.files import miscased_name
from ..utils.xml import get_params, get_root_from_file
from ..utils.expressions import resolve_params_in_text
from .constants import SEVERITY_ERROR

RUNTIME_INCLUDE_PATTERNS = [
    re.compile(r'^skinvariables-.*'),           # script.skinvariables
    re.compile(r'^skinshortcuts-.*'),            # script.skinshortcuts
    re.compile(r'^script-.*-includes$'),
]

RUNTIME_INCLUDE_FILE = re.compile(r'^script-.*-includes\.xml$', re.I)


_dir_cache = {}


def _entries(directory):
    """List the directory's entries, rereading them whenever its mtime moves."""
    try:
        stamp = os.stat(directory).st_mtime
    except OSError:
        return ()
    cached = _dir_cache.get(directory)
    if cached and cached[0] == stamp:
        return cached[1]
    try:
        listing = tuple(os.listdir(directory))
    except OSError:
        return ()
    _dir_cache[directory] = (stamp, listing)
    return listing


def resolve_include_file(addon, folder, filename):
    """Resolve the path an `<include file>` opens, and the real name when only its case differs."""
    # Kodi opens the joined path, no case fallback (CSkinInfo::GetSkinPath); case matters on Linux
    ordered = [folder] + [f for f in addon.xml_folders if f != folder]
    near = None
    for name in ordered:
        entries = _entries(os.path.join(addon.path, name))
        if filename in entries:
            return os.path.join(addon.path, name, filename), None
        if near is None:
            near = next((e for e in entries if e.lower() == filename.lower()), None)
    return None, near


def check_include_file_ref(addon, folder, ref):
    """Check an `<include file>` Kodi cannot open, as an issue without the caller's location."""
    ref = (ref or "").strip()
    if not ref or "$" in ref or RUNTIME_INCLUDE_FILE.match(ref):
        return None

    path, actual = resolve_include_file(addon, folder, ref)
    if path:
        return None

    if actual:
        message = f"Case mismatch for '{ref}' (actual '{actual}')"
    else:
        message = f"Missing include file '{ref}'"
    return {
        'name': ref,
        'identifier': ref,
        'type': 'include',
        'message': message,
        'severity': SEVERITY_ERROR,
    }


class ValidationInclude:
    """Checker for undefined, unused and shadowed includes, and a misnamed Includes.xml."""

    def __init__(self, addon):
        self.addon = addon

    def _is_runtime_include(self, include_name):
        """True when the name matches a runtime-generated name pattern."""
        if not include_name:
            return False

        for pattern in RUNTIME_INCLUDE_PATTERNS:
            if pattern.match(include_name):
                return True

        return False

    def _resolve_include_name(self, name, params=None):
        """Resolve $PARAM references in an include name, emptying any left undefined."""
        if not name or "$PARAM[" not in name:
            return name

        if params:
            resolved_name, status = resolve_params_in_text(name, params)
            if status in ("ALL_RESOLVED", "NO_PARAMS"):
                return resolved_name
            name = resolved_name

        param_pattern = re.compile(r"\$PARAM\[\s*(?P<name>[A-Za-z0-9_\-]+)\s*\]", re.IGNORECASE)
        param_names = param_pattern.findall(name)

        if param_names:
            empty_params = {pname: "" for pname in param_names}
            resolved_name, _ = resolve_params_in_text(name, empty_params)
            return resolved_name

        return name

    def check(self, progress_callback=None):
        """Check for undefined, unused or shadowed includes and a misnamed Includes.xml."""
        total_includes = sum(len(self.addon.include_map.get(f, {})) for f in self.addon.xml_folders)
        total_files = sum(len(self.addon.window_files.get(f, [])) for f in self.addon.xml_folders)

        if progress_callback:
            progress_callback(f"Scanning {total_files} files for {total_includes} includes...")

        listitems = []

        for folder in self.addon.xml_folders:
            folder_path = os.path.join(self.addon.path, folder)
            actual = miscased_name(folder_path, "Includes.xml")
            if actual:
                listitems.append({
                    'name': actual,
                    'type': 'include',
                    'file': os.path.join(folder_path, actual),
                    'line': 1,
                    'message': f"{actual} must be named Includes.xml; Kodi does not load it on Linux",
                    'severity': SEVERITY_ERROR,
                })

            var_refs = []
            file_count = 0
            files_list = self.addon.window_files[folder]

            for xml_file in files_list:
                file_count += 1
                if progress_callback and should_report_progress(file_count, len(files_list)):
                    progress_callback(f"Scanning {xml_file} ({file_count}/{len(files_list)})...")

                path = os.path.join(self.addon.path, folder, xml_file)
                root = get_root_from_file(path)
                if root is None:
                    continue

                for node in root.xpath(".//include[not(@name)]"):
                    name = node.get("content") or (node.text or "").strip()
                    if not name:
                        continue
                    if "file" in node.attrib:
                        include_file = os.path.join(self.addon.path, folder, node.attrib["file"])
                        if include_file not in self.addon.include_files[folder]:
                            self.addon.update_includes(include_file)

                    resolved_name = self._resolve_include_name(name)

                    if not resolved_name or not resolved_name.strip():
                        continue

                    var_refs.append(
                        {
                            "line": node.sourceline,
                            "type": node.tag,
                            "file": path,
                            "name": resolved_name,
                            "raw_name": name,
                        }
                    )

                for include_node in root.iter("include"):
                    if "name" in include_node.attrib or "file" in include_node.attrib:
                        continue
                    include_name = include_node.get("content") or (include_node.text or "").strip()
                    if not include_name or include_name.startswith("$"):
                        continue

                    resolved_include_name = self._resolve_include_name(include_name)

                    include_def = None
                    params = None
                    if folder in self.addon.include_map and resolved_include_name in self.addon.include_map[folder]:
                        node_or_obj, params, file_path = self.addon.include_map[folder][resolved_include_name]
                        if hasattr(node_or_obj, 'tag'):
                            from ..skin.include import SkinInclude
                            definition = node_or_obj.find("definition")
                            include_body = definition if definition is not None else node_or_obj
                            include_def = SkinInclude(node=include_body, file=file_path)
                        else:
                            include_def = node_or_obj

                    if not include_def:
                        continue

                    call_params = get_params(include_node, "value")

                    default_params = params if params else {}
                    merged_params = {**default_params, **call_params}

                    for inc_tag in include_def.node.findall(".//include"):
                        inc_name = (inc_tag.text or "").strip()
                        if not inc_name and inc_tag.get("content"):
                            inc_name = inc_tag.get("content")

                        if not inc_name or inc_name.startswith("$INFO") or inc_name.startswith("$VAR"):
                            continue

                        resolved_name, status = resolve_params_in_text(inc_name, merged_params)

                        if (status in ("ALL_RESOLVED", "NO_PARAMS") and
                            resolved_name and
                            not resolved_name.startswith("$") and
                            "$PARAM[" not in resolved_name):
                            var_refs.append(
                                {
                                    "line": inc_tag.sourceline,
                                    "type": "include",
                                    "file": include_def.file,
                                    "name": resolved_name,
                                }
                            )

            # parsed fresh: load_fonts() expands the cached root, erasing these <include> tags
            for fname in ("Font.xml", "font.xml"):
                font_path = os.path.join(self.addon.path, folder, fname)
                if not os.path.isfile(font_path):
                    continue

                if progress_callback:
                    progress_callback(f"Checking fontsets in {fname}...")

                try:
                    from lxml import etree as ET
                    root = ET.parse(font_path).getroot()
                except Exception:
                    continue

                for fontset in root.xpath(".//fontset"):
                    for inc_node in fontset.xpath(".//include"):
                        inc_name = (inc_node.text or "").strip()
                        if not inc_name:
                            continue
                        var_refs.append(
                            {
                                "line": getattr(inc_node, "sourceline", 0),
                                "type": "include",
                                "file": font_path,
                                "name": inc_name,
                            }
                        )

            template_path = find_skinshortcuts_template(self.addon.path)
            if template_path:
                if progress_callback:
                    progress_callback("Checking SkinShortcuts template...")

                known_includes = set(self.addon.include_map.get(folder, {}).keys())

                template_includes = find_includes_in_skinshortcuts_template(
                    template_path, known_includes
                )

                for inc_name in template_includes:
                    var_refs.append(
                        {
                            "line": 0,
                            "type": "include",
                            "file": template_path,
                            "name": inc_name,
                        }
                    )

            include_definitions = [
                {"name": name, "type": "include", "file": file_path, "line": node.sourceline or 0}
                for name, (node, _params, file_path) in self.addon.include_map.get(folder, {}).items()
            ]

            listitems.extend(reference_issues(
                self.addon, folder, "include", var_refs, include_definitions,
                skip=lambda name: name.startswith("$") or self._is_runtime_include(name)))
            listitems.extend(shadowed_issues(
                self.addon, folder,
                ("include", "include without definition", "constant", "expression", "default")))

        undefined_count = len([i for i in listitems if "not defined" in i.get("message", "")])
        unused_count = len([i for i in listitems if "Unused" in i.get("message", "")])

        if progress_callback:
            progress_callback(f"Complete: {len(listitems)} issues ({undefined_count} undefined, {unused_count} unused)")

        return deduplicate_issues(listitems)
