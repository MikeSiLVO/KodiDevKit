"""Variable validation for Kodi skins."""

import os
import re
from ..utils.validation import (
    find_skinshortcuts_template,
    find_variable_definitions_in_skinshortcuts_template,
    find_variables_in_skinshortcuts_template,
    reference_issues,
    resolve_param_in_name,
    shadowed_issues,
    should_report_progress,
)
from ..utils.expressions import bracket_body


def strip_xml_comments(content):
    """Remove all `<!-- ... -->` comments from `content`."""
    return re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)



class ValidationVariable:
    """Validates variable definitions and usage in Kodi skins."""

    def __init__(self, addon):
        self.addon = addon

    def check(self, progress_callback=None):
        """Find undefined or unused variables."""
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
                if progress_callback and should_report_progress(file_count, len(files_list)):
                    progress_callback(f"Scanning {xml_file} ({file_count}/{len(files_list)})...")
                path = os.path.join(self.addon.path, folder, xml_file)
                with open(path, encoding="utf8", errors="ignore") as f:
                    content = f.read()

                # Strip XML comments to avoid counting variables in commented code
                content_without_comments = strip_xml_comments(content)

                for i, line in enumerate(content_without_comments.splitlines(), 1):
                    for match in re.finditer(var_start_regex, line):
                        match_text = line[match.start():]
                        raw_name = bracket_body(match_text)

                        if not raw_name:
                            continue  # Malformed variable reference

                        # Handle fallback syntax: $VAR[Name,fallback]
                        raw_name = raw_name.split(",")[0]

                        # Resolve $PARAM[...] with empty string as default (Kodi's behavior)
                        # Later we'll try with actual parameter contexts
                        resolved_name = resolve_param_in_name(raw_name)

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
            template_path = find_skinshortcuts_template(self.addon.path)
            if template_path:
                if progress_callback:
                    progress_callback("Checking SkinShortcuts template...")

                known_variables = set(self.addon.variable_map.get(folder, {}).keys())

                template_variables = find_variables_in_skinshortcuts_template(
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
                template_defined_vars = find_variable_definitions_in_skinshortcuts_template(
                    template_path
                )

            listitems.extend(reference_issues(
                self.addon, folder, "variable", var_refs, var_definitions,
                defined=template_defined_vars))
            listitems.extend(shadowed_issues(self.addon, folder, ("variable",)))

        error_count = len(listitems)
        undefined_count = len([i for i in listitems if "not defined" in i.get("message", "")])
        unused_count = len([i for i in listitems if "Unused" in i.get("message", "")])

        if progress_callback:
            progress_callback(f"Complete: {error_count} issues ({undefined_count} undefined, {unused_count} unused)")

        return listitems
