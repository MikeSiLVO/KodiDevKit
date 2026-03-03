"""
Include resolution engine matching Kodi's CGUIIncludes.cpp behavior.

This module provides the IncludeResolver class that handles all XML resolution
operations: defaults, constants, expressions, and includes with parameter substitution.
"""

from __future__ import annotations
from typing import TYPE_CHECKING
import copy
import re
import logging

from .. import utils
from ..skin.include import SkinInclude

if TYPE_CHECKING:
    from .maps import SkinMaps

logger = logging.getLogger(__name__)


class SkinResolution:
    """
    Resolves includes, constants, expressions, and defaults in Kodi skin XML.
    
    Matches Kodi's CGUIIncludes resolution pipeline exactly.
    """

    def __init__(self, include_maps: SkinMaps, skin_path: str):
        """
        Initialize resolver with include maps.
        
        Args:
            include_maps: SkinMaps instance containing all skin definitions
            skin_path: Path to skin directory (for logging context)
        """
        self.include_maps = include_maps
        self.skin_path = skin_path
        
        self.include_map = include_maps.includes
        self.default_map = include_maps.defaults
        self.constant_map = include_maps.constants
        self.variable_map = include_maps.variables
        self.expression_map = include_maps.expressions

    def resolve(self, node, folder: str, *, source_file: str = ""):
        """
        Main resolution entry point matching Kodi's CGUIIncludes::Resolve (GUIIncludes.cpp:270-287).

        Resolution order:
        1. SetDefaults - Apply control defaults
        2. ResolveConstants - Expand constants
        3. ResolveExpressions - Expand $EXP references (with circular detection)
        4. ResolveIncludes - Splice includes with $PARAM substitution
        5. Recurse to children
        """
        if node is None:
            return

        # Store for provenance stamping in resolve_includes
        if source_file:
            self._source_file = source_file

        self.set_defaults(node, folder)
        self.resolve_constants(node, folder)
        self.resolve_expressions(node, folder)
        self.resolve_includes(node, folder)

        for child in list(node):
            self.resolve(child, folder)

    def set_defaults(self, node, folder: str):
        """
        Apply control defaults. Matches CGUIIncludes::SetDefaults (GUIIncludes.cpp:362-389).

        Only applies to <control type="X"> elements.
        Skips position defaults if control already has posx/posy.
        Appends default children at END of control.
        """
        if node.tag != "control":
            return

        control_type = node.attrib.get("type")
        if not control_type:
            return

        defaults_for_folder = self.default_map.get(folder, {})
        default_tuple = defaults_for_folder.get(control_type)
        if not default_tuple:
            return

        default_node, default_file = default_tuple

        has_posx = node.find("posx") is not None
        has_posy = node.find("posy") is not None

        default_element = default_node

        for child in default_element:
            value = child.tag
            skip = False

            # Skip position defaults if control already has them (Kodi behavior)
            if has_posx and value in ("left", "right", "centerleft", "centerright"):
                skip = True
            if has_posy and value in ("top", "bottom", "centertop", "centerbottom"):
                skip = True

            if not skip:
                # Insert at end (Kodi uses InsertEndChild)
                cloned = copy.deepcopy(child)
                # Stamp provenance so issues trace back to the control, not Defaults.xml
                if cloned.get("_kdk_call_line") is None:
                    call_line = str(node.sourceline) if node.sourceline else ""
                    call_file = getattr(self, "_source_file", "")
                    default_name = "default type=%s" % control_type
                    if call_line:
                        cloned.set("_kdk_call_line", call_line)
                        cloned.set("_kdk_inc_name", default_name)
                        cloned.set("_kdk_inc_file", default_file or "")
                        cloned.set("_kdk_call_file", call_file)
                        self._stamp_descendants(cloned, call_line, default_name, default_file or "", call_file=call_file)
                node.append(cloned)

    def resolve_constants(self, node, folder: str):
        """
        Resolve constants. Matches CGUIIncludes::ResolveConstants (GUIIncludes.cpp:391-410).

        CRITICAL: Only expands in whitelisted attributes and nodes!
        This is what Kodi does - constants are NOT expanded everywhere.
        """
        if node is None:
            return

        constants_for_folder = self.constant_map.get(folder, {})
        if not constants_for_folder:
            return


        if node.text and node.tag in SkinInclude.constant_nodes:
            node.text = self._resolve_constant_value(node.text, constants_for_folder)

        for attr_name, attr_value in list(node.attrib.items()):
            if attr_name in SkinInclude.constant_attribs:
                node.attrib[attr_name] = self._resolve_constant_value(attr_value, constants_for_folder)

    def _resolve_constant_value(self, value: str, constant_map: dict) -> str:
        """
        Resolve constant references in a value. Matches CGUIIncludes::ResolveConstant.

        Parses $CONSTANT[name] syntax and replaces with constant value.
        Only resolves constants using explicit $CONSTANT[] syntax (Kodi spec).
        """
        if not value:
            return value

        pattern = re.compile(r'\$CONSTANT\[\s*([A-Za-z0-9_\-]+)\s*\]', re.IGNORECASE)

        def replacer(match):
            const_name = match.group(1)
            if const_name in constant_map:
                return constant_map[const_name]
            return match.group(0)  # Return unchanged if not found

        result = pattern.sub(replacer, value)
        return result

    def resolve_expressions(self, node, folder: str):
        """
        Resolve expressions. Matches CGUIIncludes::ResolveExpressions (GUIIncludes.cpp:412-431).

        Expands $EXP[name] references in condition attributes and specific node text.
        """
        if node is None:
            return

        expressions_for_folder = self.expression_map.get(folder, {})
        if not expressions_for_folder:
            return


        if node.text and node.tag in SkinInclude.exp_nodes:
            node.text = self._resolve_expression_value(node.text, expressions_for_folder, [])

        for attr_name, attr_value in list(node.attrib.items()):
            if attr_name in SkinInclude.exp_attribs:
                node.attrib[attr_name] = self._resolve_expression_value(attr_value, expressions_for_folder, [])

    def _resolve_expression_value(self, value: str, expression_map: dict, resolved: list) -> str:
        """
        Resolve $EXP[name] references with circular detection.
        Matches CGUIIncludes::FlattenExpression (GUIIncludes.cpp:223-242).
        """
        if not value:
            return value

        pattern = re.compile(r'\$EXP\[\s*([A-Za-z0-9_\-]+)\s*\]', re.IGNORECASE)

        def replacer(match):
            exp_name = match.group(1)

            # Check for circular expression (GUIIncludes.cpp:227-231)
            if exp_name in resolved:
                logger.error("Skin has a circular expression \"%s\": %s", resolved[-1] if resolved else exp_name, value)
                return ""

            if exp_name not in expression_map:
                return match.group(0)

            # Recursively flatten nested expressions
            resolved_copy = resolved + [exp_name]
            exp_value = expression_map[exp_name]
            return self._resolve_expression_value(exp_value, expression_map, resolved_copy)

        return pattern.sub(replacer, value)

    def resolve_includes(self, node, folder: str):
        """
        Resolve includes. Matches CGUIIncludes::ResolveIncludes (GUIIncludes.cpp:368-469).
        """
        if node is None:
            return

        includes_for_folder = self.include_map.get(folder, {})
        if not includes_for_folder:
            return

        # Kodi uses while loop that keeps finding first include until none left
        # (GUIIncludes.cpp:419-468)
        # We use a similar approach but track processed nodes
        processed_nodes = set()  # Track node IDs we've already tried to process

        while True:
            include_nodes = list(node.findall("include"))
            if not include_nodes:
                break

            include_node = None
            for candidate in include_nodes:
                node_id = id(candidate)
                if node_id not in processed_nodes:
                    include_node = candidate
                    break

            if include_node is None:
                break

            inc_name = include_node.attrib.get("content")
            if not inc_name and include_node.text:
                inc_name = include_node.text.strip()

            if not inc_name:
                node.remove(include_node)
                continue

            # Collect call-site parameters BEFORE looking up include
            # (needed to resolve $PARAM in include name - GUIIncludes.cpp:628)
            call_params = {}
            for param in include_node.findall("param"):
                param_name = param.attrib.get("name")
                if not param_name:
                    continue
                param_value = param.attrib.get("value")
                if param_value is None and param.text:
                    param_value = param.text.strip()
                call_params[param_name] = param_value or ""

            # Resolve $PARAM in include name before lookup (matches Kodi GUIIncludes.cpp:628)
            # Kodi replaces undefined params with empty strings
            if "$PARAM[" in inc_name:
                resolved_name, status = utils.resolve_params_in_text(inc_name, call_params)
                if status in ("ALL_RESOLVED", "NO_PARAMS"):
                    inc_name = resolved_name
                else:
                    # Partially resolved - replace remaining undefined params with empty string
                    param_pattern = re.compile(r"\$PARAM\[\s*(?P<name>[A-Za-z0-9_\-]+)\s*\]", re.IGNORECASE)
                    param_names = param_pattern.findall(resolved_name)
                    if param_names:
                        empty_params = {pname: "" for pname in param_names}
                        inc_name, _ = utils.resolve_params_in_text(resolved_name, empty_params)
                    else:
                        inc_name = resolved_name

            include_def = includes_for_folder.get(inc_name)
            if not include_def:
                logger.warning("Skin has invalid include: %s", inc_name)
                processed_nodes.add(id(include_node))
                continue

            node_or_obj, default_params, file_path = include_def

            if hasattr(node_or_obj, 'tag'):  # It's an lxml Element
                definition = node_or_obj.find("definition")
                include_body = definition if definition is not None else node_or_obj
                include_obj = SkinInclude(node=include_body, file=file_path)
            else:
                include_obj = node_or_obj  # Already an Include object

            # Mark this include as processed BEFORE expanding it (prevents circular references)
            # This matches Kodi's behavior - once we start processing an include node,
            # we never process that same node again, even if it appears in nested content
            processed_nodes.add(id(include_node))

            # Merge params: call-site params override defaults (no overwrites of existing)
            # Note: call_params already collected earlier for $PARAM resolution in include name
            merged_params = dict(default_params)
            merged_params.update(call_params)

            include_element = include_obj.node

            inc_file_for_stamp = include_obj.file or ""
            # Nested includes: trace back to outermost call site in the window file
            # include_node.sourceline is from the include definition, not the window
            existing_stamp = include_node.get("_kdk_call_line")
            if existing_stamp:
                call_line = existing_stamp
                call_file = include_node.get("_kdk_call_file") or ""
            else:
                call_line = str(include_node.sourceline) if include_node.sourceline else ""
                call_file = getattr(self, "_source_file", "")
            for child in include_element:
                cloned_child = copy.deepcopy(child)

                if call_line and cloned_child.get("_kdk_call_line") is None:
                    cloned_child.set("_kdk_call_line", call_line)
                    cloned_child.set("_kdk_inc_name", inc_name)
                    cloned_child.set("_kdk_inc_file", inc_file_for_stamp)
                    cloned_child.set("_kdk_call_file", call_file)
                    self._stamp_descendants(cloned_child, call_line, inc_name, inc_file_for_stamp, call_file=call_file)

                insert_index = list(node).index(include_node)
                node.insert(insert_index, cloned_child)

                self._insert_nested(node, include_node, cloned_child)

                self._resolve_params_for_node(cloned_child, merged_params, include_node)

            node.remove(include_node)


    def _insert_nested(self, parent_node, include_node, inserted_node):
        """
        Insert call-site children at <nested /> marker locations.
        Matches CGUIIncludes::InsertNested (GUIIncludes.cpp:471-504).

        Args:
            parent_node: The parent control containing the include call
            include_node: The <include> element being expanded
            inserted_node: The node just inserted from the include definition
        """
        if inserted_node.tag == "nested":
            nested = inserted_node
            target = parent_node
        else:
            nested = inserted_node.find("nested")
            target = inserted_node

        if nested is not None:
            for child in include_node:
                if child.tag != "param":
                    cloned = copy.deepcopy(child)
                    insert_index = list(target).index(nested)
                    target.insert(insert_index, cloned)

            if nested != inserted_node:
                target.remove(nested)
            else:
                parent_node.remove(inserted_node)

    def _resolve_params_for_node(self, node, params: dict, include_node=None):
        """
        Resolve $PARAM[name] in node recursively.
        Matches CGUIIncludes::ResolveParametersForNode (GUIIncludes.cpp:549-606).

        Args:
            node: Node to resolve params in
            params: Parameter dictionary
            include_node: Optional include call node (for undefined param detection)
        """
        if node is None:
            return

        for attr_name, attr_value in list(node.attrib.items()):
            resolved, status = utils.resolve_params_in_text(attr_value, params)

            # Special case: undefined param in <param value="$PARAM[undefined]" />
            # (GUIIncludes.cpp:559-568)
            if (status == "SINGLE_UNDEFINED" and
                node.tag == "param" and
                attr_name == "value" and
                node.getparent() is not None and
                node.getparent().tag == "include"):
                node.getparent().remove(node)
                return

            node.attrib[attr_name] = resolved

        if node.text:
            resolved, status = utils.resolve_params_in_text(node.text, params)

            # Special case: undefined param in <param>$PARAM[undefined]</param>
            # (GUIIncludes.cpp:580-586)
            if (status == "SINGLE_UNDEFINED" and
                node.tag == "param" and
                node.getparent() is not None and
                node.getparent().tag == "include"):
                node.getparent().remove(node)
                return

            node.text = resolved

        # Recurse to children (save next before recursing, as child might be removed)
        # (GUIIncludes.cpp:590-605)
        for child in list(node):
            self._resolve_params_for_node(child, params, include_node)

    @staticmethod
    def _stamp_descendants(node, call_line: str, inc_name: str, inc_file: str = "", *, call_file: str = ""):
        """Propagate provenance attributes to all descendants that don't already have them."""
        for descendant in node.iter():
            if descendant is node:
                continue
            if descendant.get("_kdk_call_line") is None:
                descendant.set("_kdk_call_line", call_line)
                descendant.set("_kdk_inc_name", inc_name)
                descendant.set("_kdk_inc_file", inc_file)
                descendant.set("_kdk_call_file", call_file)
