"""Checks element placement, values and conditions in a resolved skin tree."""

from __future__ import annotations

import logging
import re

from .hierarchy import (
    WINDOW_CHILDREN,
    CONTROLS_CHILDREN,
    COORDINATES_CHILDREN,
    GROUP_TYPES,
    NEVER_FOCUSABLE,
    CONTAINER_TYPES,
    STANDARD_LAYOUT_TAGS,
    EPG_LAYOUT_TAGS,
    ALL_LAYOUT_TAGS,
    LAYOUT_CHILDREN,
    CONTENT_CHILDREN,
    INCLUDES_CHILDREN,
    FONTS_CHILDREN,
    FONTSET_CHILDREN,
    FONT_CHILDREN,
    VARIABLE_CHILDREN,
    MAP_CHILDREN,
)
from .constants import (
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    BRACKET_TAGS,
    CONDITION_TAGS,
    LITERAL_TAGS,
    NOOP_TAGS,
    LABEL_READ_TAGS,
    REPEATABLE_TAGS,
    is_read_copy,
    attribute_bool_problem,
    viewtype_problem,
    ALLOWED_MULTI,
    ALLOWED_VALUES,
    CASE_INSENSITIVE_ENUMS,
    INCLUDE_DEFINITION_TAGS,
)

from ..utils.expressions import (
    is_dynamic_expression as _is_dynamic,
    contains_dynamic_expression as _contains_dynamic,
    RUNTIME_PREFIXES,
    is_number as _is_number,
    extract_number_value,
    info_blocks,
    unclosed_label_block,
)
from ..skin.include import SkinInclude
from ..utils.xml import check_brackets as _check_brackets
from ..utils.infobool import (
    STATE_INVALID,
    check_condition,
    is_known_info,
    static_value,
    unknown_info_arguments,
    unknown_infos,
)
from ..utils.colors import is_kodi_hex as _is_kodi_hex

logger = logging.getLogger(__name__)



_LABEL_ENDING = {"$INFO", "$ESCINFO", "$VAR", "$ESCVAR", "$MAP", "$ESCMAP"}


def _window_controls(scope):
    """Every <control> below the scope that the window owns, leaving out item layouts."""
    for child in scope:
        if child.tag in ALL_LAYOUT_TAGS:
            continue
        if child.tag == "control":
            yield child
        yield from _window_controls(child)


def _can_focus(control) -> bool:
    """Whether any state of the control lets it take focus (CanFocus overrides in guilib)."""
    kind = (control.get("type") or "").lower()
    if kind in NEVER_FOCUSABLE:
        return False
    if kind in GROUP_TYPES:
        children = list(_window_controls(control))
        # an empty group is one Kodi or an addon fills at runtime
        return not children or any(_can_focus(c) for c in children)
    return True


def _same_value(a, b) -> bool:
    """Whether two elements have the same text and the same authored attributes."""
    def attrs(el):
        return {k: v for k, v in el.attrib.items() if not k.startswith("_kdk_")}
    return (a.text or "").strip() == (b.text or "").strip() and attrs(a) == attrs(b)


# control children read by the loader itself rather than listed per type in controls.xml
_STRUCTURAL_TAGS = frozenset({"control", "include", "content"}) | ALL_LAYOUT_TAGS | INCLUDE_DEFINITION_TAGS


class XmlInterpreter:
    """Walker over a resolved tree with one walk per element level."""

    def __init__(
        self,
        template_attribs: dict | None = None,
        template_values: dict | None = None,
        file_path: str = "",
        color_labels: set | None = None,
        runtime_generator: bool = False,
        constants: set | frozenset = frozenset(),
        info_names: dict | None = None,
        expressions: dict | None = None,
        settled_defaults: dict | None = None,
    ):
        self.template_attribs = template_attribs or {}
        self.template_values = template_values or {}
        self.file_path = file_path
        self.color_labels = color_labels or set()
        self.runtime_generator = runtime_generator
        self.constants = constants
        self.info_names = info_names
        self.expressions = expressions or {}
        self.settled_defaults = settled_defaults or {}
        self._condition_cache: dict[str, list[tuple[str, str, str, str]]] = {}
        self.issues: list[dict] = []

    def interpret(self, root) -> list[dict]:
        """Interpret the tree from its root tag, returning the issues found."""
        if root is None:
            return []

        self.issues = []

        tag = root.tag
        if tag == "window":
            self._walk_window(root)
            self._validate_window_conditions(root)
        elif tag == "includes":
            self._walk_includes(root)
        elif tag == "fonts":
            self._walk_fonts(root)
        else:
            pass

        return self.issues

    def _walk_window(self, node):
        """Walk the children of <window> and check its defaultcontrols."""
        for child in node:
            tag = child.tag
            if tag == "controls":
                self._walk_controls(child)
            elif tag == "coordinates":
                self._walk_coordinates(child)
            elif tag == "include":
                # an unresolved include here is reported by the unexpanded pass
                pass
            elif tag not in WINDOW_CHILDREN:
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"<{tag}> is not a valid child of <window>", rule="xml.invalid-tag",
                )
        self._check_default_control(node)
        for group in node.iter("control"):
            if (group.get("type") or "").lower() in GROUP_TYPES:
                self._check_default_control(group)

    def _check_default_control(self, scope):
        """Report a <defaultcontrol> whose every control with that id can never take focus."""
        default = scope.find("defaultcontrol")
        target = (default.text or "").strip() if default is not None else ""
        if not target.isdigit():
            return
        matches = [c for c in _window_controls(scope) if (c.get("id") or "").strip() == target]
        if matches and not any(_can_focus(c) for c in matches):
            kind = (matches[0].get("type") or "").lower()
            why = ("a group with no control that can take focus" if kind in GROUP_TYPES
                   else f"a {kind}, which can never take focus")
            self._add_issue(default, SEVERITY_ERROR, f"defaultcontrol {target} is {why}", rule="xml.unfocusable-default", subject=target)

    def _walk_controls(self, node):
        """Walk the children of <controls>."""
        for child in node:
            tag = child.tag
            if tag == "control":
                self._walk_control(child, inside_layout=False)
            elif tag == "include":
                pass
            elif tag not in CONTROLS_CHILDREN:
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"<{tag}> is not valid inside <controls> (only <control>)", rule="xml.invalid-tag",
                )

    def _walk_coordinates(self, node):
        """Walk the children of <coordinates>."""
        for child in node:
            if child.tag not in COORDINATES_CHILDREN:
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"<{child.tag}> is not valid inside <coordinates>", rule="xml.invalid-tag",
                )

    def _walk_control(self, node, *, inside_layout: bool):
        """Walk a <control> as a group, container or plain control, by its type."""
        written = (node.attrib.get("type") or "").strip()
        control_type = written.lower()
        if written != control_type and "$" not in written:
            self._add_issue(node, SEVERITY_WARNING, f'type="{written}" should be lowercase; Kodi accepts it, '
                                                    f'but a <default> only matches the exact string', rule="xml.type-case", subject=written)

        if control_type in GROUP_TYPES:
            self._walk_group_control(node, control_type, inside_layout=inside_layout)
        elif control_type in CONTAINER_TYPES:
            self._walk_container(node, control_type, inside_layout=inside_layout)
        elif control_type:
            self._validate_control_children(node, control_type, inside_layout=inside_layout)
        # no type attribute: skip, the unexpanded pass reports an invalid type

    def _walk_group_control(self, node, control_type: str, *, inside_layout: bool):
        """Walk a group control and the child controls the window loads with it."""
        self._validate_control_children(node, control_type, inside_layout=inside_layout)
        for child in node:
            if child.tag == "control":
                self._walk_control(child, inside_layout=inside_layout)

    def _walk_container(self, node, control_type: str, *, inside_layout: bool):
        """Walk a container control and its layouts and static content."""
        self._validate_control_children(node, control_type, inside_layout=inside_layout)

        valid_layouts = EPG_LAYOUT_TAGS if control_type == "epggrid" else STANDARD_LAYOUT_TAGS

        for child in node:
            tag = child.tag
            if tag in ALL_LAYOUT_TAGS:
                if tag not in valid_layouts:
                    self._add_issue(
                        child, SEVERITY_WARNING,
                        f"<{tag}> is not valid for <control type=\"{control_type}\">", rule="xml.invalid-tag",
                    )
                else:
                    self._walk_layout(child)
            elif tag == "content":
                self._walk_content(child)


    def _walk_layout(self, node):
        """Walk the children of a layout."""
        for child in node:
            tag = child.tag
            if tag == "control":
                self._walk_control(child, inside_layout=True)
            elif tag == "include":
                pass
            elif tag not in LAYOUT_CHILDREN:
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"<{tag}> is not valid inside <{node.tag}> (only <control>)", rule="xml.invalid-tag",
                )

    def _walk_content(self, node):
        """Walk the children of a static <content> list."""
        for child in node:
            if child.tag not in CONTENT_CHILDREN:
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"<{child.tag}> is not valid inside <content> (only <item>)", rule="xml.invalid-tag",
                )

    def _validate_control_children(self, node, control_type: str, *, inside_layout: bool):
        """Validate each child against the template; flag duplicates and copies of the default."""
        subnodes = self.template_attribs.get(control_type)
        if subnodes is None:
            return

        values = self.template_values.get(control_type, {})
        allowed_multi = ALLOWED_MULTI.get((node.tag.lower(), control_type), set())
        first_singletons = {}

        for child in node:
            tag = child.tag

            # checked at source by _walk_default, else one Defaults.xml error repeats per control
            if (child.get("_kdk_inc_name") or "").startswith("default type="):
                continue
            if tag in _STRUCTURAL_TAGS:
                if tag == "control" and control_type not in GROUP_TYPES:
                    self._add_issue(child, SEVERITY_WARNING, f"<control> inside <control "
                                    f"type={control_type}> is ignored; only groups hold controls", rule="xml.nested-control", subject=control_type)
                continue

            if tag not in subnodes:
                label = f"{node.tag} type={control_type}"
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"invalid tag for <{label}>: <{tag}>", rule="xml.invalid-tag",
                )
                continue

            if tag in LITERAL_TAGS and _contains_dynamic(child.text or "", prefixes=RUNTIME_PREFIXES):
                found = next(p for p in RUNTIME_PREFIXES if p in child.text.casefold())
                self._add_issue(child, SEVERITY_ERROR, f"<{tag}> takes its text as written: Kodi does "
                                                       f"not expand {found.upper()}] in it, and this copy "
                                                       f"still overrides any <default> value", rule="xml.literal-tag")

            tmpl_val = values.get(tag)
            if child.text and tmpl_val in ("int", "position"):
                self._validate_number(child, tag, False, child.text, tmpl_val)
            elif child.text and tmpl_val == "color":
                if not _contains_dynamic(child.text):
                    self._validate_color(child, f"<{tag}>", tag, child.text.strip())
            elif child.text and tmpl_val:
                self._validate_enum_value(child, child.text, tmpl_val)

            if tag in NOOP_TAGS:
                text = (child.text or "").strip()
                if not text and len(child) == 0 and static_value(child.get("condition") or "") is not False:
                    self._add_issue(
                        child, SEVERITY_ERROR,
                        f"Use 'noop' for an empty <{tag}>", rule="xml.empty-action",
                    )

            if tag in BRACKET_TAGS:
                text = (child.text or "").strip()
                if text or tag not in NOOP_TAGS:
                    self._validate_brackets(child, text)

            tag_low = tag.lower()
            if tag_low in LABEL_READ_TAGS or tag_low in ("label2", "altlabel"):
                self._validate_label_brackets(child)
                self._validate_label_infos(child)

            if (
                len(child) == 0
                and tag_low not in REPEATABLE_TAGS
                and tag_low not in allowed_multi
                and is_read_copy(child, tag_low)
            ):
                first = first_singletons.get(tag_low)
                if first is None:
                    # a conditional copy may be absent, so only an unconditional one is sure to win
                    if child.get("_kdk_inc_cond") != "1":
                        first_singletons[tag_low] = child
                else:
                    self._report_duplicate(node, first, child)

            for attr_name, attr_value in child.attrib.items():
                if attr_name == "description":
                    continue
                if attr_name.startswith("_kdk_"):
                    continue
                if attr_name not in subnodes[tag]:
                    self._add_issue(
                        child, SEVERITY_WARNING,
                        f"invalid attribute for <{tag}>: {attr_name}, which <{node.tag} type={control_type}> ignores",
                        rule="xml.invalid-attr", subject=attr_name,
                    )
                    continue
                if _contains_dynamic(attr_value):
                    continue
                value_type = subnodes[tag].get(attr_name)
                if value_type:
                    self._validate_typed_attr(child, attr_name, attr_value, value_type)

        self._report_default_repeats(node, control_type)

    def _report_default_repeats(self, control, control_type: str):
        """Report own tags that set what the control type's <default> supplies in every state."""
        settled = self.settled_defaults.get(control.get("type"))
        copies = {}
        for child in control:
            if not isinstance(child.tag, str) or len(child) or child.tag.lower() in REPEATABLE_TAGS:
                continue
            # without its own posx/posy the control gains the default's left/top family
            if child.tag not in ("posx", "posy"):
                copies.setdefault(child.tag, []).append(child)
        for tag, found in copies.items():
            defaults = [c for c in found if (c.get("_kdk_inc_name") or "").startswith("default type=")]
            others = [c for c in found if c not in defaults]
            if not defaults or len(others) != 1 or others[0].get("_kdk_inc_name") is not None:
                continue
            if settled is not None and tag not in settled:
                continue
            if _same_value(others[0], defaults[0]):
                self._add_issue(others[0], SEVERITY_WARNING,
                                f"Redundant <{tag}>: same value as <default type=\"{control_type}\">", rule="xml.redundant")

    def _report_duplicate(self, control, first, later):
        """Report a copy of a read-once tag that Kodi drops because an earlier copy wins."""
        message = f"Invalid multiple tags for {control.tag}: <{later.tag}>"
        first_inc = first.get("_kdk_inc_name")
        later_inc = later.get("_kdk_inc_name")
        if later_inc is not None:
            # own value beating an include's is an intended override, like a <default>
            if first_inc is not None or later.get("_kdk_inc_cond") == "1":
                self._add_issue(later, SEVERITY_WARNING, f"{message}, this copy is never read",
                                rule="xml.include-duplicate-tag")
        elif first_inc is None:
            self._add_issue(later, SEVERITY_ERROR, message, rule="xml.duplicate-tag")
        elif (later.text or "").strip() == (first.text or "").strip():
            self._add_issue(later, SEVERITY_WARNING, f"{message}, include '{first_inc}' already sets it",
                            rule="xml.include-duplicate-tag")
        else:
            self._add_issue(later, SEVERITY_ERROR, f"{message}, ignored because include '{first_inc}' sets it first", rule="xml.duplicate-tag")

    def _validate_enum_value(self, node, value: str, value_type: str):
        """Validate an enum value against ALLOWED_VALUES."""
        if value_type not in ALLOWED_VALUES:
            return
        if _is_dynamic(value):
            return
        if value_type == "viewtype":
            problem = viewtype_problem(value)
            if problem:
                self._add_issue(node, SEVERITY_WARNING, problem, rule="xml.unknown-viewtype", subject=value)
            return

        if value_type in CASE_INSENSITIVE_ENUMS:
            if value.lower() not in ALLOWED_VALUES[value_type]:
                allowed = ", ".join(sorted(ALLOWED_VALUES[value_type]))
                self._add_issue(
                    node, SEVERITY_ERROR,
                    f"invalid value for {node.tag}: {value} (allowed: {allowed})", rule="xml.invalid-value",
                )
        else:
            if value not in ALLOWED_VALUES[value_type]:
                if value.lower() in ALLOWED_VALUES[value_type]:
                    detail = "must be lowercase"
                else:
                    detail = "allowed: " + ", ".join(sorted(ALLOWED_VALUES[value_type]))
                self._add_issue(
                    node, SEVERITY_ERROR,
                    f"invalid value for {node.tag}: {value} ({detail})", rule="xml.invalid-value",
                )

    def _validate_label_brackets(self, node):
        """Report a label block whose ']' is missing."""
        prefix = unclosed_label_block(node.text or "")
        if prefix:
            effect = ("Kodi drops the rest of the label" if prefix.rstrip("[") in _LABEL_ENDING
                      else "Kodi shows it as plain text")
            self._add_issue(node, SEVERITY_ERROR, f"Missing ']' after {prefix} in <{node.tag}>: {effect}", rule="xml.unclosed-label")

    def _validate_label_infos(self, node):
        """Report an $INFO[] block naming an info Kodi does not know."""
        if not self.info_names:
            return
        for keyword, name, prefix in info_blocks(node.text or ""):
            if name and "$" not in name and not is_known_info(name, self.info_names):
                shows = "shows only its prefix" if prefix else "shows nothing"
                self._add_issue(node, SEVERITY_ERROR, f"Kodi has no info '{name}', so {keyword}[{name}] {shows}",
                                rule="xml.unknown-infolabel", subject=name)

    def _validate_brackets(self, node, text: str):
        """Validate bracket matching in a condition or action, and report an empty one."""
        if not text:
            self._add_issue(node, SEVERITY_ERROR, f"Empty condition: {node.tag}", rule="xml.empty-condition")
            return
        if _is_dynamic(text):
            return
        if not _check_brackets(text):
            condition = text.replace("  ", "").replace("\t", "")
            self._add_issue(
                node, SEVERITY_ERROR,
                f"Brackets do not match: {condition}", rule="xml.bad-brackets", subject=condition,
            )

    def _validate_window_conditions(self, root):
        """Check every condition tag and `condition` attribute in a resolved window."""
        for node in root.iter():
            if not isinstance(node.tag, str):
                continue
            parent = node.getparent()
            if parent is not None and parent.tag == "control":
                taken = self.template_attribs.get((parent.get("type") or "").lower())
                # a tag the control does not take is never read, so neither is its condition
                if taken is not None and node.tag not in taken and node.tag not in _STRUCTURAL_TAGS:
                    continue
            if node.tag in CONDITION_TAGS and node.text and node.text.strip():
                self._validate_condition(node, node.text, resolved=True)
            condition = node.get("condition")
            if condition:
                self._validate_condition(node, condition, resolved=True)

    def _validate_condition(self, node, condition: str, *, resolved: bool):
        """Report unparseable conditions and unknown infos, $EXP faults at their definition."""
        text = condition.strip()
        if not text or "$PARAM" in text.upper() or (not resolved and "$EXP[" in text):
            return
        found = self._condition_problems(text)
        for name in (node.get("_kdk_exp") or "").split("\t") if found else []:
            if name not in self.expressions:
                continue
            exp_text, exp_file, exp_line = self.expressions[name]
            exp_found = self._condition_problems(exp_text)
            for severity, message, rule, subject in exp_found:
                self._add_issue_at(exp_file, exp_line, "expression", severity, message, rule, subject)
            if any(f[1].startswith("Kodi cannot parse") for f in exp_found):
                found = [f for f in found if not f[1].startswith("Kodi cannot parse")]
            found = [f for f in found if f not in exp_found]
        for severity, message, rule, subject in found:
            self._add_issue(node, severity, message, rule, subject)

    def _condition_problems(self, text: str) -> list[tuple[str, str, str, str]]:
        """Severity, message, rule and subject per fault in a balanced condition, cached."""
        if text not in self._condition_cache:
            self._condition_cache[text] = self._read_condition(text)
        return self._condition_cache[text]

    def _read_condition(self, text: str) -> list[tuple[str, str, str, str]]:
        """Read the faults of a balanced condition as severity, message, rule and subject."""
        # unbalanced brackets are already reported by the bracket check
        if not _check_brackets(text):
            return []
        short = text if len(text) <= 60 else text[:60] + "..."
        problem = check_condition(text)
        if problem and problem[0] == STATE_INVALID:
            undefined = problem[1].startswith("unknown expression")
            rule, subject = ("xml.undefined-expression", problem[1].split()[-1]) if undefined else (
                "xml.unparseable-condition", text)
            if self.runtime_generator and undefined:
                return [(SEVERITY_WARNING, f"Condition uses an {problem[1]}, "
                                           f"unless a runtime generator defines it: {short}", rule, subject)]
            return [(SEVERITY_ERROR,
                     f"Kodi cannot parse this condition ({problem[1]}), it always reads false: {short}",
                     rule, subject)]
        if not self.info_names:
            return []
        found = [(SEVERITY_ERROR, f"Kodi has no info '{operand}', it always reads false", "xml.unknown-info", operand)
                 for operand in unknown_infos(text, self.info_names)]
        for test, arg in unknown_info_arguments(text, self.info_names):
            effect = ("always reads true" if test.lower().endswith(".isempty")
                      else "reads it as 0" if test.lower().startswith("integer.") else "reads it as empty text")
            found.append((SEVERITY_ERROR, f"Kodi has no info '{arg}', so {test} {effect}",
                          "xml.unknown-info-argument", arg))
        return found

    def _validate_number(self, node, name: str, is_attr: bool, value: str, value_type: str):
        """Validate a number field, reporting a leftover name or non-numeric attribute text."""
        text = value.strip()
        if not text or _is_number(text.rstrip("%r") if value_type == "position" else text):
            return
        if _contains_dynamic(text) or extract_number_value(text):
            return
        if not is_attr and name in ("width", "height") and text.lower().startswith("auto"):
            return
        where = name if is_attr else f"<{name}>"
        if not self._looks_like_unresolved(text):
            # tag text also takes %, r and comma lists that the value types do not describe
            if is_attr:
                self._add_issue(node, SEVERITY_ERROR, f"invalid integer value for {where}: {text}", rule="xml.invalid-value", subject=name)
        elif name not in (SkinInclude.constant_attribs if is_attr else SkinInclude.constant_nodes):
            self._add_issue(node, SEVERITY_ERROR,
                            f"{where} value {text}: Kodi does not substitute constants in {where}", rule="xml.constant-not-substituted", subject=text)
        elif text in self.constants:
            # a file walked without resolving still carries the name Kodi substitutes
            return
        elif self.runtime_generator:
            self._add_issue(node, SEVERITY_WARNING,
                            f"{where} value {text} is not a defined constant, unless a runtime generator adds it", rule="xml.undefined-constant", subject=text)
        else:
            self._add_issue(node, SEVERITY_ERROR, f"{where} value {text} is not a number or a defined constant", rule="xml.undefined-constant", subject=text)

    @staticmethod
    def _looks_like_unresolved(value: str) -> bool:
        """True when the value reads as a constant name: a letter first, then word characters."""
        return re.match(r"^[A-Za-z_][\w.-]*$", value) is not None and value.lower() != "auto"

    def _validate_color(self, node, where: str, name: str, value: str):
        """Validate a color, reporting one that is no hex value, color name or info."""
        if (not _is_kodi_hex(value) and value not in self.color_labels
                and not (self.info_names and is_known_info(value, self.info_names))):
            self._add_issue(node, SEVERITY_ERROR, f"Invalid color for {where}: {value}", rule="xml.invalid-color",
                            subject=name)

    def _validate_typed_attr(self, node, attr_name: str, value: str, value_type: str):
        """Validate typed attribute values (int, position, color, bool, enum)."""
        if not (value or "").strip():
            return

        if value_type in ("int", "position"):
            self._validate_number(node, attr_name, True, value, value_type)
        elif value_type == "color":
            self._validate_color(node, attr_name, attr_name, value)
        elif value_type == "bool" and (problem := attribute_bool_problem(attr_name, value)):
            self._add_issue(node, SEVERITY_ERROR, problem, rule="xml.misread-bool", subject=attr_name)
        elif value_type in ALLOWED_VALUES:
            self._validate_enum_value(node, value, value_type)

    def _walk_includes(self, node):
        """Walk the children of <includes>."""
        for child in node:
            if child.tag not in INCLUDES_CHILDREN:
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"<{child.tag}> is not valid inside <includes>", rule="xml.invalid-tag",
                )
            elif child.tag == "variable":
                self._walk_variable(child)
            elif child.tag == "map":
                self._walk_map(child)
            elif child.tag == "default":
                self._walk_default(child)
            elif child.tag == "include":
                self._walk_include_definition(child)

    def _walk_include_definition(self, node):
        """Walk an include, reporting text beside its <definition> that Kodi drops."""
        children = list(node)
        if not any(c.tag == "definition" for c in children):
            return
        texts = [(node.text, children[0])]
        texts += [(c.tail, children[i + 1] if i + 1 < len(children) else c) for i, c in enumerate(children)]
        for text, anchor in texts:
            if text and text.strip():
                self._add_issue(
                    anchor, SEVERITY_WARNING,
                    f"Text outside <definition> in include '{node.get('name')}' is ignored: {text.strip()[:40]}", rule="xml.text-outside-definition", subject=node.get("name") or "",
                )

    def _walk_default(self, node):
        """Walk a <default> block as a control of its type, reporting at the block itself."""
        written = (node.attrib.get("type") or "").strip()
        control_type = written.lower()
        # controls match their type in any case, but a default is looked up by the exact string
        if written != control_type and "$" not in written:
            self._add_issue(node, SEVERITY_WARNING, f'<default type="{written}"> applies only to controls '
                                                    f'written type="{written}"; Kodi matches it exactly', rule="xml.default-type-case", subject=written)
        if control_type in self.template_attribs:
            self._validate_control_children(node, control_type, inside_layout=False)

    def _walk_variable(self, node):
        """Walk the children of <variable>."""
        for child in node:
            if child.tag not in VARIABLE_CHILDREN:
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"<{child.tag}> is not valid inside <variable> (only <value>)", rule="xml.invalid-tag",
                )
            else:
                self._validate_label_brackets(child)
                self._validate_label_infos(child)
                condition = child.get("condition")
                if condition:
                    self._validate_condition(child, condition, resolved=False)

    def _walk_map(self, node):
        """Walk the children of <map>."""
        for child in node:
            if child.tag not in MAP_CHILDREN:
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"<{child.tag}> is not valid inside <map> (only <entry>)", rule="xml.invalid-tag",
                )

    def _walk_fonts(self, node):
        """Walk the children of <fonts>."""
        for child in node:
            if child.tag not in FONTS_CHILDREN:
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"<{child.tag}> is not valid inside <fonts> (only <fontset>)", rule="xml.invalid-tag",
                )
            else:
                self._walk_fontset(child)

    def _walk_fontset(self, node):
        """Walk the children of <fontset>."""
        for child in node:
            if child.tag not in FONTSET_CHILDREN:
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"<{child.tag}> is not valid inside <fontset> (only <font>)", rule="xml.invalid-tag",
                )
            else:
                self._walk_font(child)

    def _walk_font(self, node):
        """Walk the children of <font>."""
        for child in node:
            if child.tag not in FONT_CHILDREN:
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"<{child.tag}> is not valid inside <font>", rule="xml.invalid-tag",
                )

    def _add_issue(self, node, severity: str, message: str, rule: str, subject: str | None = None):
        """Add an issue, with the call site and source line when it came from an include."""
        call_line = node.get("_kdk_call_line")
        inc_name = node.get("_kdk_inc_name")
        inc_file = node.get("_kdk_inc_file")

        if call_line is not None:
            line = int(call_line)
            message = f"{message} (from include '{inc_name}')" if inc_name else message
        else:
            line = node.sourceline or 0

        issue = {
            "line": line,
            "type": node.tag,
            "identifier": node.tag,
            "message": message,
            "severity": severity,
            "rule": rule,
            "subject": node.tag if subject is None else subject,
        }

        # so the report can link to the line to fix
        if inc_name:
            issue["include_name"] = inc_name
            issue["include_line"] = node.sourceline or 0
            if inc_file:
                issue["include_file"] = inc_file

        call_file = node.get("_kdk_call_file") or ""
        if call_file:
            issue["call_file"] = call_file

        self.issues.append(issue)

    def _add_issue_at(self, file: str, line: int, tag: str, severity: str, message: str, rule: str,
                      subject: str):
        """Add an issue at a line in another file, once however many usages lead to it."""
        issue = {"file": file, "line": line, "type": tag, "identifier": tag,
                 "message": message, "severity": severity, "rule": rule, "subject": subject}
        if issue not in self.issues:
            self.issues.append(issue)


__all__ = [
    "XmlInterpreter",
]
