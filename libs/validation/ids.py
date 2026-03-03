"""
ID validation for Kodi skins.

Validates control and window ID references against their definitions,
using resolved-tree ID extraction for accurate parameterized ID handling.
"""

from __future__ import annotations

import os
import re
import logging
from lxml import etree as ET

from .. import utils
from .constants import SEVERITY_ERROR

logger = logging.getLogger(__name__)

class ValidationIds:
    """Validates control and window IDs in Kodi skins."""

    def __init__(self, addon, window_ids, window_names, resolve_include_fn=None, validation_index=None):
        """
        Args:
            addon: Addon/Skin instance with xml_folders, path, window_files, includes
            window_ids: List of valid Kodi window IDs
            window_names: List of Kodi window names (parallel to window_ids)
            resolve_include_fn: Callable to resolve include content (optional, slow path)
            validation_index: Pre-built validation index for performance (optional)
        """
        self.addon = addon
        self.window_ids = window_ids
        self.window_names = window_names
        self._resolve_include = resolve_include_fn
        self._validation_index = validation_index

    def check(self, progress_callback=None):
        """
        Check undefined or invalid control/window IDs.
        Returns list of {"message": str, "file": str, "line": int}.
        """
        if self._validation_index:
            total_ids = sum(len(ids) for ids in self._validation_index.get('ids_defined', {}).values())
            total_files = sum(len(files) for files in self._validation_index.get('window_includes', {}).values())
        else:
            total_ids = 0
            total_files = 0

        if progress_callback:
            progress_callback(f"Checking {total_ids} control/window IDs in {total_files} files...")

        listitems = []

        if self._validation_index:
            for folder in self.addon.xml_folders:
                window_ids_in_skin = self._validation_index.get('window_ids', {}).get(folder, [])
                ids_referenced = self._validation_index.get('ids_referenced', {}).get(folder, {})

                window_expanded_ids = self._validation_index.get('window_expanded_ids', {}).get(folder, {})
                window_base_ids = self._validation_index.get('window_base_ids', {}).get(folder, {})

                window_to_ids = {}
                for window_file in window_expanded_ids:
                    expanded_ids = window_expanded_ids.get(window_file, set())
                    if expanded_ids:
                        window_to_ids[window_file] = set(expanded_ids)
                    else:
                        # Fall back to raw base IDs if resolution produced nothing
                        window_to_ids[window_file] = set(window_base_ids.get(window_file, set()))

                for ref_id, usages in ids_referenced.items():
                    for usage in usages:
                        usage_type = usage.get('type', 'control')
                        usage_file = usage.get('file', '')

                        if usage_type == 'window':
                            if ref_id in window_ids_in_skin:
                                continue  # Valid - window ID defined in this skin
                            elif ref_id in self.window_ids:
                                # Window ID is from Kodi core - suggest using name instead
                                if "script-skinshortcuts-includes.xml" not in usage_file.replace("\\", "/").lower():
                                    windowname = self.window_names[self.window_ids.index(ref_id)]
                                    listitems.append({
                                        "message": f"Window id: Please use {windowname} instead of {ref_id}",
                                        "file": usage_file,
                                        "line": usage.get('line', 0),
                                        "severity": SEVERITY_ERROR,
                                    })
                            else:
                                listitems.append({
                                    "message": f"Window ID not defined: {ref_id}",
                                    "file": usage_file,
                                    "line": usage.get('line', 0),
                                    "severity": SEVERITY_ERROR,
                                })
                        else:
                            if not ref_id:
                                continue

                            usage_basename = os.path.basename(usage_file)

                            # Shared files have no window scope — skip
                            include_files_list = self._validation_index.get('include_files', {}).get(folder, [])
                            is_shared_file = usage_basename in include_files_list

                            if is_shared_file:
                                continue

                            window_file = usage_basename
                            window_ids_set = window_to_ids.get(window_file, set())

                            if ref_id not in window_ids_set:
                                builtin_controls = self._validation_index.get('builtin_controls', {})
                                builtin_filename_map = self._validation_index.get('builtin_filename_map', {})

                                window_name = builtin_filename_map.get(window_file.lower())

                                is_builtin = False
                                if window_name and window_name in builtin_controls:
                                    if ref_id in builtin_controls[window_name]:
                                        is_builtin = True

                                usage_context = usage.get('context')
                                is_global_scope = usage_context in ('Control.IsVisible', 'Control.HasFocus')
                                is_view_detection = False
                                if is_global_scope:
                                    all_view_ids = set()
                                    for folder_views in self._validation_index.get('view_ids', {}).values():
                                        all_view_ids.update(folder_views)
                                    if ref_id in all_view_ids:
                                        is_view_detection = True

                                if not is_builtin and not is_view_detection:
                                    listitems.append({
                                        "message": f"Control ID {ref_id} not defined in {window_file}'s scope",
                                        "file": usage_file,
                                        "line": usage.get('line', 0),
                                        "severity": SEVERITY_ERROR,
                                    })

            return utils.deduplicate_issues(listitems)

        window_regex = (
            r"(?:Dialog.Close|Window.IsActive|Window.IsVisible|Window)\(([0-9]+)\)"
        )
        control_regex = (
            r"^(?!.*IsActive)(?!.*Window.IsVisible)(?!.*Dialog.Close)"
            r"(?!.*Window)(?!.*Row)(?!.*Column).*"
            r"(?<!ListItem)(?<!ListItemAbsolute)(?<!ListItemPosition)(?<!ListItemNoWrap)"
            r"\(([0-9]*?)\)"
        )

        control_tags = {
            "button", "togglebutton", "radiobutton", "edit", "image", "label", "fadelabel",
            "textbox", "progress", "slider", "spincontrol", "spincontrolex", "list",
            "fixedlist", "panel", "wraplist", "group", "grouplist", "multiimage",
            "scrollbar", "visualisation", "videowindow", "gamewindow", "mover", "resize",
            "rss", "epggrid", "ranges", "sliderex", "panelcontainer"
        }

        for folder in self.addon.xml_folders:
            window_ids = []
            window_refs = []
            control_refs = []
            defines = []
            for xml_file in self.addon.window_files[folder]:
                path = os.path.join(self.addon.path, folder, xml_file)
                root = utils.get_root_from_file(path)
                if root is None:
                    continue

                # Expand includes and $PARAM if resolver available
                if self._resolve_include and utils.file_needs_expansion(path):
                    try:
                        root = self._resolve_include(root, folder=folder)
                    except Exception:
                        pass

                if "id" in root.attrib:
                    window_ids.append(root.attrib["id"])

                for node in root.iter():
                    tag = node.tag.lower()
                    if "id" in node.attrib:
                        if tag in control_tags:
                            defines.append(
                                {
                                    "name": node.attrib["id"],
                                    "type": tag,
                                    "file": path,
                                    "line": node.sourceline,
                                }
                            )
                        elif tag == "control" and "type" in node.attrib:
                            control_type = node.attrib["type"].lower()
                            if control_type in control_tags:
                                defines.append(
                                    {
                                        "name": node.attrib["id"],
                                        "type": control_type,
                                        "file": path,
                                        "line": node.sourceline,
                                    }
                                )

                for include_node in root.xpath(".//include[@content]"):
                    include_name = include_node.attrib.get("content")
                    if not include_name or include_name.startswith("$"):
                        continue

                    include_def = None
                    if folder in self.addon.include_map and include_name in self.addon.include_map[folder]:
                        node_or_obj, _params, file_path = self.addon.include_map[folder][include_name]
                        if hasattr(node_or_obj, 'tag'):
                            from ..skin.include import SkinInclude
                            definition = node_or_obj.find("definition")
                            include_body = definition if definition is not None else node_or_obj
                            include_def = SkinInclude(node=include_body, file=file_path)
                        else:
                            include_def = node_or_obj

                    if not include_def:
                        continue

                    params_used_as_ids = utils.get_param_names_in_context(
                        include_def.node, ".//@id"
                    )

                    for param_node in include_node.findall("param"):
                        param_name = param_node.attrib.get("name", "")
                        param_value = (param_node.text or "").strip()

                        if (param_name in params_used_as_ids and
                            param_value and
                            not param_value.startswith("$")):

                            defines.append(
                                {
                                    "name": param_value,
                                    "type": "control",
                                    "file": path,
                                    "line": param_node.sourceline,
                                }
                            )

                for node in root.xpath(".//*[@condition]"):
                    for match in re.finditer(control_regex, node.attrib["condition"], re.IGNORECASE):
                        control_refs.append(
                            {
                                "name": match.group(1),
                                "type": node.tag,
                                "file": path,
                                "line": node.sourceline,
                            }
                        )
                    for match in re.finditer(window_regex, node.attrib["condition"], re.IGNORECASE):
                        window_refs.append(
                            {
                                "name": match.group(1),
                                "type": node.tag,
                                "file": path,
                                "line": node.sourceline,
                            }
                        )

                bracket_tags = [
                    "visible", "enable", "usealttexture",
                    "selected", "onclick", "onback",
                ]
                for node in root.xpath(".//" + " | .//".join(bracket_tags)):
                    if not node.text:
                        continue
                    for match in re.finditer(control_regex, node.text, re.IGNORECASE):
                        control_refs.append(
                            {
                                "name": match.group(1),
                                "type": node.tag,
                                "file": path,
                                "line": node.sourceline,
                            }
                        )
                    for match in re.finditer(window_regex, node.text, re.IGNORECASE):
                        window_refs.append(
                            {
                                "name": match.group(1),
                                "type": node.tag,
                                "file": path,
                                "line": node.sourceline,
                            }
                        )

            define_list = [d["name"] for d in defines]
            for inc in self.addon.includes.get(folder, []):
                content = utils.resolve_include_content(inc, None)
                if not content:
                    continue
                try:
                    root_inc = ET.fromstring(f"<root>{content}</root>")
                    for ctrl in root_inc.xpath(".//*[@id]"):
                        define_list.append(ctrl.attrib["id"])
                except ET.XMLSyntaxError:
                    continue

            for item in window_refs:
                if item["name"] in window_ids:
                    continue
                elif item["name"] in self.window_ids:
                    if "script-skinshortcuts-includes.xml" not in item["file"].replace("\\", "/").lower():
                        windowname = self.window_names[self.window_ids.index(item["name"])]
                        item["message"] = f"Window id: Please use {windowname} instead of {item['name']}"
                        item["severity"] = SEVERITY_ERROR
                        listitems.append(item)
                else:
                    item["message"] = f"Window ID not defined: {item['name']}"
                    item["severity"] = SEVERITY_ERROR
                    listitems.append(item)

            for item in control_refs:
                if not item["name"] or item["name"] in define_list:
                    continue
                item["message"] = f"Control / Item ID not defined: {item['name']}"
                item["severity"] = SEVERITY_ERROR
                listitems.append(item)

        error_count = len(listitems)
        undefined_count = len([i for i in listitems if "not defined" in i.get("message", "")])

        if progress_callback:
            progress_callback(f"Complete: {error_count} issues ({undefined_count} undefined)")

        return utils.deduplicate_issues(listitems)


def check(addon, validation_index):
    """Module-level check function for ID validation."""
    checker = ValidationIds(addon, window_ids=[], window_names=[], validation_index=validation_index)
    return checker.check()
