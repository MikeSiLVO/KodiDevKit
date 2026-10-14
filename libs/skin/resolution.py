"""Include, constant, expression and default resolution for skin XML."""

from __future__ import annotations
from typing import TYPE_CHECKING
import copy
import re
import logging

from lxml import etree as ET

from ..utils.expressions import expression_names, flatten_expressions, resolve_params_in_text
from ..utils.infobool import static_value
from ..utils.xml import get_params
from ..skin.include import SkinInclude
from ..validation.hierarchy import ALL_LAYOUT_TAGS

if TYPE_CHECKING:
    from .maps import SkinMaps

logger = logging.getLogger(__name__)

_STAMP = re.compile(r'\s_kdk_\w+="[^"]*"')


def _whole_controls(body):
    """True when every element the include body splices is a <control>."""
    tags = [child.tag for child in body if isinstance(child.tag, str)]
    return bool(tags) and all(tag == "control" for tag in tags)


def _splice_key(parent, include_node, name, params):
    """What makes two splices identical: include, params, call body and where they land."""
    body = "".join(ET.tostring(c, encoding="unicode", with_tail=False)
                   for c in include_node if c.tag != "param")
    in_layout = any(e.tag in ALL_LAYOUT_TAGS for e in (parent, *parent.iterancestors()))
    return (name, tuple(sorted(params.items())), _STAMP.sub("", body),
            parent.tag, parent.get("type"), in_layout)


class SkinResolution:
    """Resolver for a skin's includes, constants, expressions and defaults."""

    def __init__(self, include_maps: SkinMaps, skin_path: str):
        self.include_maps = include_maps
        self.skin_path = skin_path

        self.include_map = include_maps.includes
        self.default_map = include_maps.defaults
        self.constant_map = include_maps.constants
        self.variable_map = include_maps.variables
        self.expression_map = include_maps.expressions

    def resolve(self, node, folder: str, *, source_file: str = "", _spliced=None):
        """Resolve defaults, constants, $EXP and includes, then children."""
        if node is None:
            return

        if source_file:
            self._source_file = source_file
        spliced = set() if _spliced is None else _spliced

        self.set_defaults(node, folder)
        self.resolve_constants(node, folder)
        self.resolve_expressions(node, folder)
        self.resolve_includes(node, folder, spliced)

        for child in list(node):
            self.resolve(child, folder, _spliced=spliced)

    def set_defaults(self, node, folder: str):
        """Set defaults: append the control type's default children, minus overridden positions."""
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

            if has_posx and value in ("left", "right", "centerleft", "centerright"):
                skip = True
            if has_posy and value in ("top", "bottom", "centertop", "centerbottom"):
                skip = True

            if not skip:
                cloned = copy.deepcopy(child)
                # stamp so issues point at the control, not Defaults.xml
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
        """Resolve constants in listed tag text, else in listed attributes."""
        if node is None:
            return

        constants_for_folder = self.constant_map.get(folder, {})
        if not constants_for_folder:
            return

        if node.text and node.tag in SkinInclude.constant_nodes:
            node.text = self._resolve_constant_value(node.text, constants_for_folder)
        else:
            for attr_name, attr_value in list(node.attrib.items()):
                if attr_name in SkinInclude.constant_attribs:
                    node.attrib[attr_name] = self._resolve_constant_value(attr_value, constants_for_folder)

    def _resolve_constant_value(self, value: str, constant_map: dict) -> str:
        """Resolve each comma-split piece naming a constant."""
        if not value:
            return value
        pieces = value.split(",")
        pieces = [constant_map.get(p, p) for p in pieces]
        return ",".join(pieces)

    def resolve_expressions(self, node, folder: str):
        """Resolve $EXP in listed tag text, else the condition, recording the names on the node."""
        if node is None:
            return

        expressions_for_folder = self.expression_map.get(folder, {})
        if not expressions_for_folder:
            return

        names = []
        if node.text and node.tag in SkinInclude.exp_nodes:
            names = expression_names(node.text)
            node.text = self._resolve_expression_value(node.text, expressions_for_folder, [])
        else:
            for attr_name, attr_value in list(node.attrib.items()):
                if attr_name in SkinInclude.exp_attribs:
                    names += expression_names(attr_value)
                    node.attrib[attr_name] = self._resolve_expression_value(
                        attr_value, expressions_for_folder, [])
        if names:
            node.set("_kdk_exp", self._PATH_SEP.join(names))

    def _resolve_expression_value(self, value: str, expression_map: dict, resolved: list) -> str:
        """Resolve $EXP[name] references with circular detection."""
        return flatten_expressions(value, expression_map, resolved)[0]

    # tab is attribute-safe and never appears in an include name
    _PATH_SEP = "\t"

    def resolve_includes(self, node, folder: str, spliced=None):
        """Resolve includes, skipping cyclic, always-false and repeated conditional ones."""
        if node is None:
            return

        includes_for_folder = self.include_map.get(folder, {})
        if not includes_for_folder:
            return

        include_node = node.find("include")
        while include_node is not None:
            condition = include_node.get("condition")
            if condition and static_value(condition) is False:
                include_node = next(include_node.itersiblings("include"), None)
                continue

            inc_name = include_node.attrib.get("content")
            if not inc_name and include_node.text:
                inc_name = include_node.text.strip()

            call_params = get_params(include_node, "value")

            # unknown $PARAM names survive our param pass; Kodi's empties them, so empty for lookup
            if inc_name and "$PARAM[" in inc_name:
                resolved_name, status = resolve_params_in_text(inc_name, call_params)
                if status in ("ALL_RESOLVED", "NO_PARAMS"):
                    inc_name = resolved_name
                else:
                    param_pattern = re.compile(r"\$PARAM\[\s*(?P<name>[A-Za-z0-9_\-]+)\s*\]", re.IGNORECASE)
                    param_names = param_pattern.findall(resolved_name)
                    if param_names:
                        empty_params = {pname: "" for pname in param_names}
                        inc_name, _ = resolve_params_in_text(resolved_name, empty_params)
                    else:
                        inc_name = resolved_name

            # cycle check by stamped path; lxml proxy ids are reused
            path_attr = include_node.get("_kdk_inc_path")
            path = path_attr.split(self._PATH_SEP) if path_attr else []

            include_def = includes_for_folder.get(inc_name) if inc_name else None

            if include_def is None or inc_name in path:
                if include_def is None and inc_name:
                    logger.debug("Skin has invalid include: %s", inc_name)
                include_node = next(include_node.itersiblings("include"), None)
                continue

            node_or_obj, default_params, file_path = include_def

            if hasattr(node_or_obj, 'tag'):
                definition = node_or_obj.find("definition")
                include_body = definition if definition is not None else node_or_obj
                include_obj = SkinInclude(node=include_body, file=file_path)
            else:
                include_obj = node_or_obj

            merged_params = dict(default_params)
            merged_params.update(call_params)

            include_element = include_obj.node

            # Kodi splices a conditional include only when its condition holds at load
            conditional = "condition" in include_node.attrib or include_node.get("_kdk_inc_cond") == "1"

            # every branch splices and nesting multiplies them; a repeat adds nothing to check
            if spliced is not None and conditional and _whole_controls(include_element):
                key = _splice_key(node, include_node, inc_name, merged_params)
                if key in spliced:
                    node.remove(include_node)
                    include_node = node.find("include")
                    continue
                spliced.add(key)

            inc_file_for_stamp = include_obj.file or ""
            # nested include: keep the outermost call site in the window file
            existing_stamp = include_node.get("_kdk_call_line")
            if existing_stamp:
                call_line = existing_stamp
                call_file = include_node.get("_kdk_call_file") or ""
            else:
                call_line = str(include_node.sourceline) if include_node.sourceline else ""
                call_file = getattr(self, "_source_file", "")

            # ancestry stamp is what the cycle check reads
            child_path_attr = self._PATH_SEP.join(path + [inc_name])
            for child in include_element:
                cloned_child = copy.deepcopy(child)
                if conditional:
                    for element in cloned_child.iter():
                        element.set("_kdk_inc_cond", "1")

                if call_line and cloned_child.get("_kdk_call_line") is None:
                    cloned_child.set("_kdk_call_line", call_line)
                    cloned_child.set("_kdk_inc_name", inc_name)
                    cloned_child.set("_kdk_inc_file", inc_file_for_stamp)
                    cloned_child.set("_kdk_call_file", call_file)
                    self._stamp_descendants(cloned_child, call_line, inc_name, inc_file_for_stamp, call_file=call_file)

                for nested_inc in cloned_child.iter("include"):
                    if nested_inc.get("_kdk_inc_path") is None:
                        nested_inc.set("_kdk_inc_path", child_path_attr)

                insert_index = list(node).index(include_node)
                node.insert(insert_index, cloned_child)

                self._insert_nested(node, include_node, cloned_child)

                self._resolve_params_for_node(cloned_child, merged_params, include_node)

            node.remove(include_node)
            # rescan from the first include so spliced ones resolve in document order
            include_node = node.find("include")

    def _insert_nested(self, parent_node, include_node, inserted_node):
        """Insert the call's children at the <nested/> marker."""
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
        """Resolve $PARAM through a subtree, dropping a forwarded <param> left undefined."""
        if node is None:
            return

        for attr_name, attr_value in list(node.attrib.items()):
            resolved, status = resolve_params_in_text(attr_value, params)

            # a lone undefined $PARAM forwarded as a param value drops the <param>; default wins
            if (status == "SINGLE_UNDEFINED" and
                node.tag == "param" and
                attr_name == "value" and
                node.getparent() is not None and
                node.getparent().tag == "include"):
                node.getparent().remove(node)
                return

            node.attrib[attr_name] = resolved

        if node.text:
            resolved, status = resolve_params_in_text(node.text, params)

            # same for the text form
            if (status == "SINGLE_UNDEFINED" and
                node.tag == "param" and
                node.getparent() is not None and
                node.getparent().tag == "include"):
                node.getparent().remove(node)
                return

            node.text = resolved

        for child in list(node):
            self._resolve_params_for_node(child, params, include_node)

    @staticmethod
    def _stamp_descendants(node, call_line: str, inc_name: str, inc_file: str = "", *, call_file: str = ""):
        """Stamp every unstamped descendant with the call site and include name."""
        for descendant in node.iter():
            if descendant is node:
                continue
            if descendant.get("_kdk_call_line") is None:
                descendant.set("_kdk_call_line", call_line)
                descendant.set("_kdk_inc_name", inc_name)
                descendant.set("_kdk_inc_file", inc_file)
                descendant.set("_kdk_call_file", call_file)
