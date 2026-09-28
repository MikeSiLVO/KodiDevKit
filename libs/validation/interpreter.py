"""
Context-aware XML interpreter for Kodi skin validation.

Walks a resolved lxml tree depth-first with a context stack, validating
that each element appears in a structurally valid location.

Operates on the RESOLVED tree (after include expansion, constant/expression
resolution, and default application), so it sees exactly what Kodi sees.
"""

from __future__ import annotations

import logging
from enum import Enum, auto

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
    NOOP_TAGS,
    LABEL_READ_TAGS,
    REPEATABLE_TAGS,
    is_read_copy,
    ALLOWED_MULTI,
    ALLOWED_VALUES,
    CASE_INSENSITIVE_ENUMS,
    INCLUDE_DEFINITION_TAGS,
)

# Use canonical checks from utils to avoid drift
from ..utils.expressions import (
    is_dynamic_expression as _is_dynamic,
    contains_dynamic_expression as _contains_dynamic,
    is_number as _is_number,
    unclosed_label_block,
)
from ..utils.xml import check_brackets as _check_brackets
from ..utils.colors import is_kodi_hex as _is_kodi_hex

logger = logging.getLogger(__name__)


class Context(Enum):
    """Nesting context matching Kodi's loading hierarchy."""
    WINDOW = auto()
    CONTROLS = auto()
    CONTROL = auto()
    GROUP_CONTROL = auto()
    CONTAINER = auto()
    LAYOUT = auto()
    CONTENT = auto()
    COORDINATES = auto()
    FONTS = auto()
    FONTSET = auto()
    FONT = auto()
    INCLUDES = auto()
    VARIABLE = auto()
    MAP = auto()


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


class XmlInterpreter:
    """
    Walks a resolved XML tree and validates structural correctness at each level.

    Each walk method mirrors a Kodi loading function. Issues carry provenance
    info from stamped attributes so errors point back to the source line
    the skinner can fix.
    """

    def __init__(
        self,
        template_attribs: dict | None = None,
        template_values: dict | None = None,
        file_path: str = "",
        color_labels: set | None = None,
    ):
        self.template_attribs = template_attribs or {}
        self.template_values = template_values or {}
        self.file_path = file_path
        self.color_labels = color_labels or set()
        self.issues: list[dict] = []
        self._context_stack: list[Context] = []

    def interpret(self, root) -> list[dict]:
        """Entry point: detect root tag type and dispatch."""
        if root is None:
            return []

        self.issues = []
        self._context_stack = []

        tag = root.tag
        if tag == "window":
            self._walk_window(root)
        elif tag == "includes":
            self._walk_includes(root)
        elif tag == "fonts":
            self._walk_fonts(root)
        else:
            pass

        return self.issues

    def _walk_window(self, node):
        """Validate direct children of <window>. (GUIWindow.cpp:186-268)"""
        self._context_stack.append(Context.WINDOW)
        for child in node:
            tag = child.tag
            if tag == "controls":
                self._walk_controls(child)
            elif tag == "coordinates":
                self._walk_coordinates(child)
            elif tag == "include":
                # An unresolved include here is reported by the unexpanded pass.
                pass
            elif tag not in WINDOW_CHILDREN:
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"<{tag}> is not a valid child of <window>",
                )
        self._check_default_control(node)
        for group in node.iter("control"):
            if (group.get("type") or "").lower() in GROUP_TYPES:
                self._check_default_control(group)
        self._context_stack.pop()

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
            self._add_issue(default, SEVERITY_ERROR, f"defaultcontrol {target} is {why}")

    def _walk_controls(self, node):
        """Validate <controls> children. (GUIWindow.cpp:258-268)"""
        self._context_stack.append(Context.CONTROLS)
        for child in node:
            tag = child.tag
            if tag == "control":
                self._walk_control(child, inside_layout=False)
            elif tag == "include":
                pass
            elif tag not in CONTROLS_CHILDREN:
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"<{tag}> is not valid inside <controls> (only <control>)",
                )
        self._context_stack.pop()

    def _walk_coordinates(self, node):
        """Validate <coordinates> children. (GUIWindow.cpp:234-250)"""
        self._context_stack.append(Context.COORDINATES)
        for child in node:
            if child.tag not in COORDINATES_CHILDREN:
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"<{child.tag}> is not valid inside <coordinates>",
                )
        self._context_stack.pop()

    def _walk_control(self, node, *, inside_layout: bool):
        """Dispatch a <control> based on its type (group / container / leaf)."""
        control_type = (node.attrib.get("type") or "").lower().strip()

        if control_type in GROUP_TYPES:
            self._walk_group_control(node, control_type, inside_layout=inside_layout)
        elif control_type in CONTAINER_TYPES:
            self._walk_container(node, control_type, inside_layout=inside_layout)
        elif control_type:
            self._validate_control_children(node, control_type, inside_layout=inside_layout)
        # No type attribute; skip (invalid control type is caught by the unexpanded pass).

    def _walk_group_control(self, node, control_type: str, *, inside_layout: bool):
        """
        Validate group control. (GUIWindow.cpp:302)
        Group controls load child <control> elements recursively.
        """
        self._context_stack.append(Context.GROUP_CONTROL)
        self._validate_control_children(node, control_type, inside_layout=inside_layout)
        for child in node:
            if child.tag == "control":
                self._walk_control(child, inside_layout=inside_layout)
        self._context_stack.pop()

    def _walk_container(self, node, control_type: str, *, inside_layout: bool):
        """
        Validate container control. (GUIBaseContainer.cpp:1317-1334)
        Containers expect layout tags + content + standard control children.
        """
        self._context_stack.append(Context.CONTAINER)
        self._validate_control_children(node, control_type, inside_layout=inside_layout)

        valid_layouts = EPG_LAYOUT_TAGS if control_type == "epggrid" else STANDARD_LAYOUT_TAGS

        for child in node:
            tag = child.tag
            if tag in ALL_LAYOUT_TAGS:
                if tag not in valid_layouts:
                    self._add_issue(
                        child, SEVERITY_WARNING,
                        f"<{tag}> is not valid for <control type=\"{control_type}\">",
                    )
                else:
                    self._walk_layout(child)
            elif tag == "content":
                self._walk_content(child)

        self._context_stack.pop()

    def _walk_layout(self, node):
        """Validate layout children: only <control> elements. (CGUIListItemLayout)"""
        self._context_stack.append(Context.LAYOUT)
        for child in node:
            tag = child.tag
            if tag == "control":
                self._walk_control(child, inside_layout=True)
            elif tag == "include":
                pass
            elif tag not in LAYOUT_CHILDREN:
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"<{tag}> is not valid inside <{node.tag}> (only <control>)",
                )
        self._context_stack.pop()

    def _walk_content(self, node):
        """Validate <content> children: <item> or <include>. (StaticProvider.cpp:20-34)"""
        self._context_stack.append(Context.CONTENT)
        for child in node:
            if child.tag not in CONTENT_CHILDREN:
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"<{child.tag}> is not valid inside <content> (only <item>)",
                )
        self._context_stack.pop()

    def _validate_control_children(self, node, control_type: str, *, inside_layout: bool):
        """
        Validate each child tag/attribute/value against template schema.
        Mirrors the per-control checks in InfoProvider.check_file().
        """
        subnodes = self.template_attribs.get(control_type)
        if subnodes is None:
            return

        values = self.template_values.get(control_type, {})
        first_singletons = {}

        for child in node:
            tag = child.tag

            # Default-appended children are validated at their source in
            # _walk_default; skip them here so a Defaults.xml error isn't
            # reported again on every control that inherits the default.
            if (child.get("_kdk_inc_name") or "").startswith("default type="):
                continue
            if tag in INCLUDE_DEFINITION_TAGS:
                continue
            if tag == "include":
                continue
            if tag == "control":
                continue
            if tag in ALL_LAYOUT_TAGS:
                continue
            if tag == "content":
                continue

            if tag not in subnodes:
                label = f"{node.tag} type={control_type}"
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"invalid tag for <{label}>: <{tag}>",
                )
                continue

            tmpl_val = values.get(tag)
            if child.text and tmpl_val:
                self._validate_enum_value(child, child.text, tmpl_val)

            if tag in NOOP_TAGS:
                text = (child.text or "").strip()
                if not text and len(child) == 0:
                    self._add_issue(
                        child, SEVERITY_ERROR,
                        f"Use 'noop' for empty calls <{node.tag}>",
                    )

            if tag in BRACKET_TAGS:
                text = (child.text or "").strip()
                if text or tag not in NOOP_TAGS:
                    self._validate_brackets(child, text)

            if tag.lower() in LABEL_READ_TAGS or tag.lower() in ("label2", "altlabel"):
                self._validate_label_brackets(child)

            tag_low = tag.lower()
            allowed_multi = ALLOWED_MULTI.get(
                (node.tag.lower(), control_type), set()
            )
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
                        f"invalid attribute for <{tag}>: {attr_name}",
                    )
                    continue
                if _is_dynamic(attr_value) or _contains_dynamic(attr_value):
                    continue
                value_type = subnodes[tag].get(attr_name)
                if value_type:
                    self._validate_typed_attr(child, attr_name, attr_value, value_type)

        self._report_default_repeats(node, control_type)

    def _report_default_repeats(self, control, control_type: str):
        """Report own tags that set exactly what the control type's <default> would supply."""
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
            if _same_value(others[0], defaults[0]):
                self._add_issue(others[0], SEVERITY_WARNING,
                                f"Redundant <{tag}>: same value as <default type=\"{control_type}\">")

    def _report_duplicate(self, control, first, later):
        """Report a copy of a read-once tag that Kodi drops because an earlier copy wins."""
        message = f"Invalid multiple tags for {control.tag}: <{later.tag}>"
        first_inc = first.get("_kdk_inc_name")
        if later.get("_kdk_inc_name") is not None:
            # own value beating an include's is an intended override, like a <default>
            if first_inc is not None or later.get("_kdk_inc_cond") == "1":
                self._add_issue(later, SEVERITY_WARNING, message)
        elif first_inc is None:
            self._add_issue(later, SEVERITY_ERROR, message)
        elif (later.text or "").strip() == (first.text or "").strip():
            self._add_issue(later, SEVERITY_WARNING, f"{message}, include '{first_inc}' already sets it")
        else:
            self._add_issue(later, SEVERITY_ERROR, f"{message}, ignored because include '{first_inc}' sets it first")

    def _validate_enum_value(self, node, value: str, value_type: str):
        """Validate an enum value against ALLOWED_VALUES."""
        if value_type not in ALLOWED_VALUES:
            return
        if _is_dynamic(value):
            return

        if value_type in CASE_INSENSITIVE_ENUMS:
            if value.lower() not in ALLOWED_VALUES[value_type]:
                allowed = ", ".join(sorted(ALLOWED_VALUES[value_type]))
                self._add_issue(
                    node, SEVERITY_ERROR,
                    f"invalid value for {node.tag}: {value} (allowed: {allowed})",
                )
        else:
            if value not in ALLOWED_VALUES[value_type]:
                if value.lower() in ALLOWED_VALUES[value_type]:
                    detail = "must be lowercase"
                else:
                    detail = "allowed: " + ", ".join(sorted(ALLOWED_VALUES[value_type]))
                self._add_issue(
                    node, SEVERITY_ERROR,
                    f"invalid value for {node.tag}: {value} ({detail})",
                )

    def _validate_label_brackets(self, node):
        """Report a label block whose ']' is missing, as CGUIInfoLabel::Parse logs it."""
        prefix = unclosed_label_block(node.text or "")
        if prefix:
            # the $INFO family ends the label there (GUIInfoLabel.cpp:429), the rest stay as text
            effect = ("Kodi drops the rest of the label" if prefix.rstrip("[") in _LABEL_ENDING
                      else "Kodi shows it as plain text")
            self._add_issue(node, SEVERITY_ERROR, f"Missing ']' after {prefix} in <{node.tag}>: {effect}")

    def _validate_brackets(self, node, text: str):
        """Validate bracket matching in conditions."""
        if not text:
            self._add_issue(node, SEVERITY_ERROR, f"Empty condition: {node.tag}")
            return
        if _is_dynamic(text):
            return
        if not _check_brackets(text):
            condition = text.replace("  ", "").replace("\t", "")
            self._add_issue(
                node, SEVERITY_ERROR,
                f"Brackets do not match: {condition}",
            )

    @staticmethod
    def _looks_like_unresolved(value: str) -> bool:
        """True when the value reads as an unresolved constant or variable name, not a number."""
        return bool(value) and not _is_number(value) and all(c.isalnum() or c in "_-." for c in value)

    def _validate_typed_attr(self, node, attr_name: str, value: str, value_type: str):
        """Validate typed attribute values (int, color, enum)."""
        if not (value or "").strip():
            return

        if value_type in ("int", "position"):
            check_val = value.rstrip("%r") if value_type == "position" else value
            if not _is_number(check_val):
                # Skip values that look like unresolved constants (e.g. from script.skinvariables)
                if self._looks_like_unresolved(check_val):
                    return
                self._add_issue(
                    node, SEVERITY_ERROR,
                    f"invalid integer value for {attr_name}: {value}",
                )
        elif value_type == "color":
            if not _is_kodi_hex(value) and value not in self.color_labels:
                self._add_issue(
                    node, SEVERITY_ERROR,
                    f"Invalid color for {attr_name}: {value}",
                )
        elif value_type in ALLOWED_VALUES:
            self._validate_enum_value(node, value, value_type)

    def _walk_includes(self, node):
        """Validate <includes> root children. (GUIIncludes.cpp:88-99)"""
        self._context_stack.append(Context.INCLUDES)
        for child in node:
            if child.tag not in INCLUDES_CHILDREN:
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"<{child.tag}> is not valid inside <includes>",
                )
            elif child.tag == "variable":
                self._walk_variable(child)
            elif child.tag == "map":
                self._walk_map(child)
            elif child.tag == "default":
                self._walk_default(child)
            elif child.tag == "include":
                self._walk_include_definition(child)
        self._context_stack.pop()

    def _walk_include_definition(self, node):
        """Report text beside a <definition>, which Kodi drops (GUIIncludes.cpp:211-213)."""
        children = list(node)
        if not any(c.tag == "definition" for c in children):
            return
        texts = [(node.text, children[0])]
        texts += [(c.tail, children[i + 1] if i + 1 < len(children) else c) for i, c in enumerate(children)]
        for text, anchor in texts:
            if text and text.strip():
                self._add_issue(
                    anchor, SEVERITY_WARNING,
                    f"Text outside <definition> in include '{node.get('name')}' is ignored: {text.strip()[:40]}",
                )

    def _walk_default(self, node):
        """Validate a <default type="X"> block as a control of type X, at its
        own source. Defaults are the skin's own file, not reusable include
        content, so errors are reported here (not stamped as include warnings)."""
        control_type = (node.attrib.get("type") or "").lower().strip()
        if control_type in self.template_attribs:
            self._validate_control_children(node, control_type, inside_layout=False)

    def _walk_variable(self, node):
        """Validate <variable> children: only <value>. (GUIIncludes.cpp:160-168)"""
        self._context_stack.append(Context.VARIABLE)
        for child in node:
            if child.tag not in VARIABLE_CHILDREN:
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"<{child.tag}> is not valid inside <variable> (only <value>)",
                )
            else:
                self._validate_label_brackets(child)
        self._context_stack.pop()

    def _walk_map(self, node):
        """Validate <map> children: only <entry>. (SkinMapManager.cpp:22-40)"""
        self._context_stack.append(Context.MAP)
        for child in node:
            if child.tag not in MAP_CHILDREN:
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"<{child.tag}> is not valid inside <map> (only <entry>)",
                )
        self._context_stack.pop()

    def _walk_fonts(self, node):
        """Validate <fonts> root children. (GUIFontManager.cpp:67)"""
        self._context_stack.append(Context.FONTS)
        for child in node:
            if child.tag not in FONTS_CHILDREN:
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"<{child.tag}> is not valid inside <fonts> (only <fontset>)",
                )
            else:
                self._walk_fontset(child)
        self._context_stack.pop()

    def _walk_fontset(self, node):
        """Validate <fontset> children. (GUIFontManager.cpp:426-445)"""
        self._context_stack.append(Context.FONTSET)
        for child in node:
            if child.tag not in FONTSET_CHILDREN:
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"<{child.tag}> is not valid inside <fontset> (only <font>)",
                )
            else:
                self._walk_font(child)
        self._context_stack.pop()

    def _walk_font(self, node):
        """Validate <font> children. (GUIFontManager.cpp:482-510)"""
        self._context_stack.append(Context.FONT)
        for child in node:
            if child.tag not in FONT_CHILDREN:
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"<{child.tag}> is not valid inside <font>",
                )
        self._context_stack.pop()

    def _add_issue(self, node, severity: str, message: str):
        """
        Record a validation issue with include provenance chain.

        For issues from include expansion, reports both the call site
        (where to find the <include> in the window) and the source
        location (the actual line in the include definition to fix).
        """
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
        }

        # Include source location so the report can link to the actual line to fix
        if inc_name:
            issue["include_name"] = inc_name
            issue["include_line"] = node.sourceline or 0
            if inc_file:
                issue["include_file"] = inc_file

        call_file = node.get("_kdk_call_file") or ""
        if call_file:
            issue["call_file"] = call_file

        self.issues.append(issue)


__all__ = [
    "Context",
    "XmlInterpreter",
]
