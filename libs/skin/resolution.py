"""Include, constant, expression and default resolution for skin XML."""

from __future__ import annotations
from typing import TYPE_CHECKING
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


def _clone(element):
    """Clone an lxml element with its subtree."""
    return element.__deepcopy__(None)


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
        self._ready_defaults_cache = {}
        self._flattened_cache = {}

    def resolve(self, node, folder: str, *, source_file: str = "", _spliced=None):
        """Resolve defaults, constants, $EXP and includes, then children."""
        if node is None or node.get("_kdk_ready") is not None:
            return

        if source_file:
            self._source_file = source_file
        if _spliced is None:
            # rebuilt per window so a reload never leaves stale results behind
            self._ready_defaults_cache = {}
            self._flattened_cache = {}
        spliced = set() if _spliced is None else _spliced

        # each guard repeats its step's own no-op test
        if node.tag == "control":
            self.set_defaults(node, folder)
        if node.text or len(node.attrib):
            self.resolve_constants(node, folder)
            self.resolve_expressions(node, folder)
        if node.find("include") is not None:
            self.resolve_includes(node, folder, spliced)

        for child in list(node):
            self.resolve(child, folder, _spliced=spliced)

    def splice_includes(self, node, folder: str, _spliced=None):
        """Splice includes through the subtree unstamped, leaving defaults, constants and $EXP."""
        if next(node.iter("include"), None) is None:
            return
        spliced = set() if _spliced is None else _spliced
        self.resolve_includes(node, folder, spliced, _stamp=False)
        for child in list(node):
            self.splice_includes(child, folder, spliced)

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

        # stamp so issues point at the control, not Defaults.xml
        call_line = str(node.sourceline) if node.sourceline else ""
        call_file = getattr(self, "_source_file", "")
        default_name = "default type=%s" % control_type
        ready = self._ready_defaults(folder, control_type, default_node, default_file)

        for child, ready_child in zip(default_node, ready):
            value = child.tag
            if has_posx and value in ("left", "right", "centerleft", "centerright"):
                continue
            if has_posy and value in ("top", "bottom", "centertop", "centerbottom"):
                continue

            if ready_child is not None and call_line:
                cloned = _clone(ready_child)
                for element in cloned.iter():
                    element.set("_kdk_call_line", call_line)
                    element.set("_kdk_call_file", call_file)
            else:
                cloned = _clone(child)
                if call_line:
                    cloned.set("_kdk_call_line", call_line)
                    cloned.set("_kdk_inc_name", default_name)
                    cloned.set("_kdk_inc_file", default_file or "")
                    cloned.set("_kdk_call_file", call_file)
                    self._stamp_descendants(cloned, call_line, default_name, default_file or "", call_file=call_file)
            node.append(cloned)

    def _ready_defaults(self, folder: str, control_type: str, default_node, default_file):
        """Default children resolved once per window; None for one with an include or control."""
        cached = self._ready_defaults_cache.get((folder, control_type))
        if cached is not None:
            return cached
        default_name = "default type=%s" % control_type
        ready = []
        for child in default_node:
            # a splice or nested default depends on the window it lands in
            if next(child.iter("include", "control"), None) is not None:
                ready.append(None)
                continue
            ready_child = _clone(child)
            for element in ready_child.iter():
                element.set("_kdk_inc_name", default_name)
                element.set("_kdk_inc_file", default_file or "")
                self.resolve_constants(element, folder)
                self.resolve_expressions(element, folder)
            ready_child.set("_kdk_ready", "1")
            ready.append(ready_child)
        self._ready_defaults_cache[(folder, control_type)] = ready
        return ready

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
            for attr_name in SkinInclude.constant_attribs.intersection(node.attrib):
                node.attrib[attr_name] = self._resolve_constant_value(node.attrib[attr_name], constants_for_folder)

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
            text_names, node.text = self._flattened(folder, node.text, expressions_for_folder)
            names += text_names
        else:
            for attr_name in SkinInclude.exp_attribs.intersection(node.attrib):
                attr_names, node.attrib[attr_name] = self._flattened(folder, node.attrib[attr_name],
                                                                     expressions_for_folder)
                names += attr_names
        if names:
            node.set("_kdk_exp", self._PATH_SEP.join(names))

    def _flattened(self, folder: str, value: str, expression_map: dict):
        """The $EXP names written in the text and the text with them flattened, once per window."""
        key = (folder, value)
        if key not in self._flattened_cache:
            self._flattened_cache[key] = (tuple(expression_names(value)),
                                          flatten_expressions(value, expression_map, [])[0])
        return self._flattened_cache[key]

    # tab is attribute-safe and never appears in an include name
    _PATH_SEP = "\t"

    def resolve_includes(self, node, folder: str, spliced=None, _stamp=True):
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
                cloned_child = _clone(child)
                if conditional:
                    for element in cloned_child.iter():
                        element.set("_kdk_inc_cond", "1")

                if _stamp and call_line and cloned_child.get("_kdk_call_line") is None:
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
                    cloned = _clone(child)
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
            if "$" not in attr_value:
                continue
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

        if node.text and "$" in node.text:
            resolved, status = resolve_params_in_text(node.text, params)

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
        for descendant in node.iterdescendants():
            if "_kdk_call_line" not in descendant.attrib:
                descendant.set("_kdk_call_line", call_line)
                descendant.set("_kdk_inc_name", inc_name)
                descendant.set("_kdk_inc_file", inc_file)
                descendant.set("_kdk_call_file", call_file)
