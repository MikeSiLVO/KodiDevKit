"""Checks the variables a skin uses and defines."""

import os
import re
from ..utils.validation import (
    find_skinshortcuts_template,
    find_variable_definitions_in_skinshortcuts_template,
    find_variables_in_skinshortcuts_file,
    reference_issues,
    resolve_param_in_name,
    shadowed_issues,
    should_report_progress,
    skinshortcuts_files,
)
from ..utils.expressions import bracket_body, split_top_level_commas
from ..utils.xml import blank_xml_comments


_SET_PROPERTY = re.compile(r"\bSetProperty\(", re.IGNORECASE)


def _set_property_values(line):
    """The value argument of each SetProperty call in the given text."""
    values = []
    for match in _SET_PROPERTY.finditer(line):
        depth, end = 1, match.end()
        while end < len(line) and depth:
            depth += (line[end] == "(") - (line[end] == ")")
            end += 1
        args = split_top_level_commas(line[match.end():end - 1])
        if len(args) > 1:
            values.append(args[1])
    return values


class ValidationVariable:
    """Checker for undefined, unused and shadowed variables."""

    def __init__(self, addon):
        self.addon = addon

    def check(self, progress_callback=None):
        """Check for undefined, unused or shadowed variables."""
        total_vars = sum(len(vars) for vars in self.addon.variable_map.values()) if hasattr(self.addon, 'variable_map') else 0
        total_files = sum(len(self.addon.window_files.get(f, [])) for f in self.addon.xml_folders)

        if progress_callback:
            progress_callback(f"Scanning {total_files} files for {total_vars} variables...")

        var_start_regex = r"\$(?:ESC)?VAR\["
        listitems = []
        for folder in self.addon.xml_folders:
            var_refs = []
            known_variables = set(self.addon.variable_map.get(folder, {}).keys())
            file_count = 0
            files_list = self.addon.window_files[folder]
            for xml_file in files_list:
                file_count += 1
                if progress_callback and should_report_progress(file_count, len(files_list)):
                    progress_callback(f"Scanning {xml_file} ({file_count}/{len(files_list)})...")
                path = os.path.join(self.addon.path, folder, xml_file)
                with open(path, encoding="utf8", errors="ignore") as f:
                    content = f.read()

                for i, line in enumerate(blank_xml_comments(content).splitlines(), 1):
                    for match in re.finditer(var_start_regex, line):
                        match_text = line[match.start():]
                        raw_name = bracket_body(match_text)

                        if not raw_name:
                            continue

                        raw_name = raw_name.split(",")[0]

                        resolved_name = resolve_param_in_name(raw_name)

                        var_refs.append(
                            {
                                "line": i,
                                "type": "variable",
                                "file": path,
                                "name": resolved_name,
                                "raw_name": raw_name,
                            }
                        )

                    # add-ons read a variable named in a property value back as $VAR[name]
                    for value in _set_property_values(line):
                        for name in value.split("|"):
                            if name.strip() in known_variables:
                                var_refs.append({"line": i, "type": "variable", "file": path,
                                                 "name": name.strip()})

            template_path = find_skinshortcuts_template(self.addon.path)
            for shortcuts_path in skinshortcuts_files(self.addon.path):
                for var_name in find_variables_in_skinshortcuts_file(shortcuts_path, known_variables):
                    var_refs.append(
                        {
                            "line": 0,
                            "type": "variable",
                            "file": shortcuts_path,
                            "name": var_name,
                        }
                    )

            var_definitions = [
                {
                    "name": name,
                    "type": "variable",
                    "file": file_path,
                    "line": node.sourceline if hasattr(node, 'sourceline') else 0
                }
                for name, (node, file_path) in self.addon.variable_map.get(folder, {}).items()
            ]

            # template-defined variables exist only at runtime
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
