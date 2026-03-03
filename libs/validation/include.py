"""
KodiDevKit is a plugin to assist with Kodi skinning / scripting
using Sublime Text 4
Include validation for Kodi skins.
"""

import os
import re
import logging
import xml.etree.ElementTree as ET

from .. import utils
from .constants import SEVERITY_ERROR

logger = logging.getLogger(__name__)

# Runtime include patterns - includes generated at runtime by addons
RUNTIME_INCLUDE_PATTERNS = [
    re.compile(r'^skinvariables-.*'),           # script.skinvariables
    re.compile(r'^skinshortcuts-.*'),            # script.skinshortcuts
    re.compile(r'^script-.*-includes$'),         # Dynamic script includes
]


class ValidationInclude:
    """Validates include definitions and usage in Kodi skins."""

    def __init__(self, addon):
        """
        Args:
            addon: Addon/Skin instance with xml_folders, path, window_files, includes, include_files
        """
        self.addon = addon
        self.runtime_addons = self._detect_runtime_addons()
        # Cache for parameter resolution: (include_name, frozenset(params)) -> resolved_name
        self._resolution_cache = {}

    def _detect_runtime_addons(self):
        """
        Parse addon.xml to detect runtime content generation addons.

        Returns:
            set: Set of addon IDs that generate runtime content (e.g., {'script.skinvariables'})
        """
        if not self.addon:
            return set()

        addon_xml_path = os.path.join(self.addon.path, 'addon.xml')
        if not os.path.isfile(addon_xml_path):
            return set()

        try:
            tree = ET.parse(addon_xml_path)
            root = tree.getroot()

            runtime_addons = set()
            for import_node in root.findall('.//import'):
                addon_id = import_node.get('addon', '')
                if addon_id in ['script.skinvariables', 'script.skinshortcuts']:
                    runtime_addons.add(addon_id)
                    logger.info(f"Runtime addon detected: {addon_id}")

            return runtime_addons

        except Exception as e:
            logger.warning(f"Failed to parse addon.xml: {e}")
            return set()

    def _is_runtime_include(self, include_name):
        """
        Check if an include name matches runtime-generated patterns.

        Args:
            include_name: Name of the include to check

        Returns:
            bool: True if include appears to be runtime-generated
        """
        if not include_name:
            return False

        for pattern in RUNTIME_INCLUDE_PATTERNS:
            if pattern.match(include_name):
                logger.debug(f"Runtime include pattern match: {include_name}")
                return True

        return False

    def _resolve_include_name_kodi_style(self, name, params=None):
        """
        Resolve $PARAM references in include name using Kodi's approach.

        Kodi replaces undefined params with empty strings (GUIIncludes.cpp:628).
        Example: "Dialog_Background_Blur$PARAM[dialog_size]" with dialog_size undefined
                 becomes "Dialog_Background_Blur" (param replaced with "")

        Args:
            name: Include name that may contain $PARAM references
            params: Dict of available parameters (or None)

        Returns:
            Resolved include name with undefined params replaced by empty strings
        """
        if not name or "$PARAM[" not in name:
            return name

        if params:
            resolved_name, status = utils.resolve_params_in_text(name, params)
            if status in ("ALL_RESOLVED", "NO_PARAMS"):
                return resolved_name
            name = resolved_name  # Use partially resolved name for next step

        # For any remaining $PARAM references, replace with empty string (Kodi behavior)
        param_pattern = re.compile(r"\$PARAM\[\s*(?P<name>[A-Za-z0-9_\-]+)\s*\]", re.IGNORECASE)
        param_names = param_pattern.findall(name)

        if param_names:
            empty_params = {pname: "" for pname in param_names}
            resolved_name, _ = utils.resolve_params_in_text(name, empty_params)
            return resolved_name

        return name

    def _resolve_param_in_include_name(self, inc_name, param_context=None):
        """Resolve $PARAM[...] in include names using parameter values."""
        return utils.resolve_param_in_name(inc_name, param_context, self._resolution_cache)

    def _get_all_parameter_contexts(self, inc_name, inc_file_path, folder):
        """Get all parameter contexts where an include might be used."""
        return utils.get_all_parameter_contexts(self.addon, folder)

    def check(self, progress_callback=None):
        """
        Check undefined/unused includes. Also counts <fontset>/<include> as usage.
        Returns list of {"message": str, "file": str, "line": int}.
        """
        total_includes = sum(len(self.addon.include_map.get(f, {})) for f in self.addon.xml_folders)
        total_files = sum(len(self.addon.window_files.get(f, [])) for f in self.addon.xml_folders)

        if progress_callback:
            progress_callback(f"Scanning {total_files} files for {total_includes} includes...")

        listitems = []

        for folder in self.addon.xml_folders:
            var_refs = []
            file_count = 0
            files_list = self.addon.window_files[folder]

            for xml_file in files_list:
                file_count += 1
                if progress_callback and utils.should_report_progress(file_count, len(files_list)):
                    progress_callback(f"Scanning {xml_file} ({file_count}/{len(files_list)})...")

                path = os.path.join(self.addon.path, folder, xml_file)
                root = utils.get_root_from_file(path)
                if root is None:
                    continue

                for node in root.xpath(".//include"):
                    if node.text:
                        name = node.text
                        if "file" in node.attrib:
                            include_file = os.path.join(
                                self.addon.path, folder, node.attrib["file"]
                            )
                            if include_file not in self.addon.include_files[folder]:
                                self.addon.update_includes(include_file)
                    elif node.attrib.get("content"):
                        name = node.attrib["content"]
                    else:
                        continue

                    resolved_name = self._resolve_include_name_kodi_style(name)

                    if not resolved_name or not resolved_name.strip():
                        continue

                    var_refs.append(
                        {
                            "line": node.sourceline,
                            "type": node.tag,
                            "file": path,
                            "name": resolved_name,
                            "raw_name": name,  # Keep original for context-aware resolution
                        }
                    )

                for include_node in root.xpath(".//include[@content]"):
                    include_name = include_node.attrib.get("content")
                    if not include_name or include_name.startswith("$"):
                        continue

                    resolved_include_name = self._resolve_include_name_kodi_style(include_name)

                    include_def = None
                    params = None  # Initialize for type safety
                    if folder in self.addon.include_map and resolved_include_name in self.addon.include_map[folder]:
                        node_or_obj, params, file_path = self.addon.include_map[folder][resolved_include_name]
                        if hasattr(node_or_obj, 'tag'):  # It's an lxml Element
                            from ..skin.include import SkinInclude
                            definition = node_or_obj.find("definition")
                            include_body = definition if definition is not None else node_or_obj
                            include_def = SkinInclude(node=include_body, file=file_path)
                        else:
                            include_def = node_or_obj  # Already an Include object

                    if not include_def:
                        continue

                    call_params = {}
                    for param_node in include_node.findall("param"):
                        param_name = param_node.attrib.get("name", "")
                        param_value = (param_node.text or "").strip()
                        if param_name and param_value:
                            call_params[param_name] = param_value

                    # Merge with default params from include definition (Kodi behavior)
                    # Passed params take precedence (GUIIncludes.cpp:439-440)
                    default_params = params if params else {}
                    merged_params = {**default_params, **call_params}

                    for inc_tag in include_def.node.findall(".//include"):
                        inc_name = (inc_tag.text or "").strip()
                        if not inc_name and inc_tag.get("content"):
                            inc_name = inc_tag.get("content")

                        if not inc_name or inc_name.startswith("$INFO") or inc_name.startswith("$VAR"):
                            continue  # Skip dynamic expressions

                        resolved_name, status = utils.resolve_params_in_text(inc_name, merged_params)

                        if (status in ("ALL_RESOLVED", "NO_PARAMS") and
                            resolved_name and
                            not resolved_name.startswith("$") and
                            "$PARAM[" not in resolved_name):
                            var_refs.append(
                                {
                                    "line": inc_tag.sourceline,
                                    "type": "include",
                                    "file": path,
                                    "name": resolved_name,
                                }
                            )

            # <fontset>/<include> usage
            # IMPORTANT: Parse Font.xml fresh (bypassing cache) because skin.get_fonts()
            # modifies the cached root in-place by expanding includes.
            # We need the ORIGINAL XML with <include> tags intact to detect usage.
            for fname in ("Font.xml", "font.xml", "Fonts.xml"):
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

            # SkinShortcuts template references (v2: template.xml, v3: templates.xml)
            template_path = utils.find_skinshortcuts_template(self.addon.path)
            if template_path:
                if progress_callback:
                    progress_callback("Checking SkinShortcuts template...")

                known_includes = set(self.addon.include_map.get(folder, {}).keys())

                template_includes = utils.find_includes_in_skinshortcuts_template(
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

            include_definitions = []
            for name, (node_or_obj, params, file_path) in self.addon.include_map.get(folder, {}).items():
                if hasattr(node_or_obj, 'tag'):  # It's an lxml Element
                    from ..skin.include import SkinInclude
                    definition = node_or_obj.find("definition")
                    include_body = definition if definition is not None else node_or_obj
                    include_obj = SkinInclude(node=include_body, file=file_path)
                else:
                    include_obj = node_or_obj  # Already an Include object

                include_definitions.append({
                    "name": name,
                    "type": "include",
                    "file": include_obj.file,
                    "line": getattr(include_obj.node, 'sourceline', 0) or 0
                })

            undefined_includes = []
            defined_include_names = {inc['name'] for inc in include_definitions}

            for inc_ref in var_refs:
                ref_name = inc_ref['name']
                raw_name = inc_ref.get('raw_name', ref_name)

                if ref_name.startswith("$"):
                    continue

                if self._is_runtime_include(ref_name):
                    if self.runtime_addons:
                        logger.debug(f"Runtime include (addon detected): {ref_name}")
                    else:
                        logger.debug(f"Runtime include pattern (no addon.xml dependency): {ref_name}")
                    continue

                if ref_name in defined_include_names:
                    continue  # Include exists

                found_in_context = False  # Initialize for type safety
                if '$PARAM[' in raw_name:
                    contexts = self._get_all_parameter_contexts(raw_name, inc_ref['file'], folder)

                    found_in_context = False
                    for param_context in contexts:
                        resolved_name = self._resolve_param_in_include_name(raw_name, param_context)
                        if resolved_name in defined_include_names:
                            found_in_context = True
                            break

                    if found_in_context:
                        continue  # Include is valid in at least one context

                issue = {
                    'name': ref_name,
                    'type': 'include',
                    'file': inc_ref['file'],
                    'line': inc_ref['line'],
                    'message': f"Include not defined: {raw_name}",
                    'severity': SEVERITY_ERROR,
                }

                if '$PARAM[' in raw_name and not found_in_context:
                    issue['message'] += (
                        " → Note: Include contains $PARAM but doesn't resolve to any defined include "
                        "in any usage context. Check include definitions and parameter names."
                    )

                undefined_includes.append(issue)

            unused_includes = []
            referenced_include_names = set()

            for inc_ref in var_refs:
                ref_name = inc_ref['name']
                raw_name = inc_ref.get('raw_name', ref_name)

                if ref_name.startswith("$") or self._is_runtime_include(ref_name):
                    continue

                referenced_include_names.add(ref_name)

                if '$PARAM[' in raw_name:
                    contexts = self._get_all_parameter_contexts(raw_name, inc_ref['file'], folder)
                    for param_context in contexts:
                        resolved_name = self._resolve_param_in_include_name(raw_name, param_context)
                        if resolved_name:
                            referenced_include_names.add(resolved_name)

            for inc_def in include_definitions:
                if inc_def['name'] not in referenced_include_names:
                    if self._is_runtime_include(inc_def['name']):
                        continue

                    unused_includes.append({
                        'name': inc_def['name'],
                        'type': 'include',
                        'file': inc_def['file'],
                        'line': inc_def['line'],
                        'message': f"Unused include: {inc_def['name']}",
                        'severity': SEVERITY_ERROR,
                    })

            listitems.extend(undefined_includes)
            listitems.extend(unused_includes)

        undefined_count = len([i for i in listitems if "not defined" in i.get("message", "")])
        unused_count = len([i for i in listitems if "Unused" in i.get("message", "")])

        if progress_callback:
            progress_callback(f"Complete: {len(listitems)} issues ({undefined_count} undefined, {unused_count} unused)")

        return utils.deduplicate_issues(listitems)
