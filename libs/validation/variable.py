"""
KodiDevKit is a plugin to assist with Kodi skinning / scripting
using Sublime Text 4
Variable validation for Kodi skins.
"""

import os
import re
import logging
from .. import utils
from .constants import SEVERITY_ERROR

logger = logging.getLogger(__name__)


def strip_xml_comments(content):
    """
    Remove XML comments from content.

    Args:
        content: String containing XML content

    Returns:
        Content with all XML comments (<!-- ... -->) removed
    """
    return re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)


def extract_variable_name_with_nested_brackets(match_text):
    r"""
    Extract variable name from $VAR[...] handling nested brackets like $PARAM[...].

    The simple regex r"\$VAR\[(.*?)\]" fails for nested brackets:
    - Input: $VAR[Label_Title_C$PARAM[id]3]
    - Broken regex captures: Label_Title_C$PARAM[id (stops at first ])
    - This function captures: Label_Title_C$PARAM[id]3 (handles nesting)

    Args:
        match_text: String starting with "$VAR[" or "$ESCVAR["

    Returns:
        Variable name with balanced brackets, or empty string if malformed
    """
    # Find the start position after $VAR[ or $ESCVAR[
    start_pos = match_text.find('[')
    if start_pos == -1:
        return ''

    bracket_count = 0
    for i, char in enumerate(match_text[start_pos:], start=start_pos):
        if char == '[':
            bracket_count += 1
        elif char == ']':
            bracket_count -= 1
            if bracket_count == 0:
                # Found the matching closing bracket
                return match_text[start_pos+1:i]

    # Malformed - no matching closing bracket
    return ''


class ValidationVariable:
    """Validates variable definitions and usage in Kodi skins."""

    def __init__(self, addon):
        """
        Args:
            addon: Addon/Skin instance with xml_folders, path, window_files, includes
        """
        self.addon = addon
        # Cache for parameter resolution: (var_name, frozenset(params)) -> resolved_name
        self._resolution_cache = {}

    def _resolve_param_in_variable_name(self, var_name, param_context=None):
        """Resolve $PARAM[...] in variable names using parameter values."""
        return utils.resolve_param_in_name(var_name, param_context, self._resolution_cache)

    def _get_all_parameter_contexts(self, var_name, var_file_path, folder):
        """Get all parameter contexts where a variable might be used."""
        return utils.get_all_parameter_contexts(self.addon, folder)

    def check(self, progress_callback=None):
        """
        Find undefined or unused variables.
        Returns list of {"message": str, "file": str, "line": int}.
        """
        total_vars = sum(len(vars) for vars in self.addon.variable_map.values()) if hasattr(self.addon, 'variable_map') else 0
        total_files = sum(len(self.addon.window_files.get(f, [])) for f in self.addon.xml_folders)

        if progress_callback:
            progress_callback(f"Scanning {total_files} files for {total_vars} variables...")

        var_start_regex = r"\$(?:ESC)?VAR\["
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
                with open(path, encoding="utf8", errors="ignore") as f:
                    content = f.read()

                # Strip XML comments to avoid counting variables in commented code
                content_without_comments = strip_xml_comments(content)

                for i, line in enumerate(content_without_comments.splitlines(), 1):
                    for match in re.finditer(var_start_regex, line):
                        match_text = line[match.start():]
                        raw_name = extract_variable_name_with_nested_brackets(match_text)

                        if not raw_name:
                            continue  # Malformed variable reference

                        # Handle fallback syntax: $VAR[Name,fallback]
                        raw_name = raw_name.split(",")[0]

                        # Resolve $PARAM[...] with empty string as default (Kodi's behavior)
                        # Later we'll try with actual parameter contexts
                        resolved_name = self._resolve_param_in_variable_name(raw_name)

                        var_refs.append(
                            {
                                "line": i,
                                "type": "variable",
                                "file": path,
                                "name": resolved_name,
                                "raw_name": raw_name,  # Keep original for debugging
                            }
                        )

            # SkinShortcuts template references (v2: template.xml, v3: templates.xml)
            template_path = utils.find_skinshortcuts_template(self.addon.path)
            if template_path:
                if progress_callback:
                    progress_callback("Checking SkinShortcuts template...")

                known_variables = set(self.addon.variable_map.get(folder, {}).keys())

                template_variables = utils.find_variables_in_skinshortcuts_template(
                    template_path, known_variables
                )

                for var_name in template_variables:
                    var_refs.append(
                        {
                            "line": 0,
                            "type": "variable",
                            "file": template_path,
                            "name": var_name,
                        }
                    )

            var_definitions = [
                {
                    "name": name,
                    "type": "variable",
                    "file": file_path,  # Extract from tuple
                    "line": node.sourceline if hasattr(node, 'sourceline') else 0
                }
                for name, (node, file_path) in self.addon.variable_map.get(folder, {}).items()
            ]

            # Variables defined inside SkinShortcuts templates are generated at
            # runtime -- treat them as defined so $VAR[] refs aren't flagged.
            template_defined_vars = set()
            if template_path:
                template_defined_vars = utils.find_variable_definitions_in_skinshortcuts_template(
                    template_path
                )

            undefined_vars = []
            defined_var_names = {v['name'] for v in var_definitions} | template_defined_vars

            for var_ref in var_refs:
                ref_name = var_ref['name']
                raw_name = var_ref.get('raw_name', ref_name)

                if ref_name in defined_var_names:
                    continue  # Variable exists

                found_in_context = False
                if '$PARAM[' in raw_name:
                    contexts = self._get_all_parameter_contexts(raw_name, var_ref['file'], folder)

                    found_in_context = False
                    for param_context in contexts:
                        resolved_name = self._resolve_param_in_variable_name(raw_name, param_context)
                        if resolved_name in defined_var_names:
                            found_in_context = True
                            break

                    if found_in_context:
                        continue  # Variable is valid in at least one context

                issue = {
                    'name': ref_name,
                    'type': 'variable',
                    'file': var_ref['file'],
                    'line': var_ref['line'],
                    'message': f"Variable not defined: {raw_name}",
                    'severity': SEVERITY_ERROR,
                }

                if '$PARAM[' in raw_name and not found_in_context:
                    issue['message'] += (
                        " → Note: Variable contains $PARAM but doesn't resolve to any defined variable "
                        "in any usage context. Check variable definitions and parameter names."
                    )

                undefined_vars.append(issue)

            unused_vars = []
            referenced_var_names = set()

            for var_ref in var_refs:
                ref_name = var_ref['name']
                raw_name = var_ref.get('raw_name', ref_name)

                referenced_var_names.add(ref_name)

                if '$PARAM[' in raw_name:
                    contexts = self._get_all_parameter_contexts(raw_name, var_ref['file'], folder)
                    for param_context in contexts:
                        resolved_name = self._resolve_param_in_variable_name(raw_name, param_context)
                        if resolved_name:
                            referenced_var_names.add(resolved_name)

            for var_def in var_definitions:
                if var_def['name'] not in referenced_var_names:
                    unused_vars.append({
                        'name': var_def['name'],
                        'type': 'variable',
                        'file': var_def['file'],
                        'line': var_def['line'],
                        'message': f"Unused variable: {var_def['name']}",
                        'severity': SEVERITY_ERROR,
                    })

            listitems.extend(undefined_vars)
            listitems.extend(unused_vars)

        error_count = len(listitems)
        undefined_count = len([i for i in listitems if "not defined" in i.get("message", "")])
        unused_count = len([i for i in listitems if "Unused" in i.get("message", "")])

        if progress_callback:
            progress_callback(f"Complete: {error_count} issues ({undefined_count} undefined, {unused_count} unused)")

        return listitems
