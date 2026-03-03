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
)
from .constants import (
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    BRACKET_TAGS,
    NOOP_TAGS,
    SINGLETON_TAGS,
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
                # Residual unresolved include — skip silently
                pass
            elif tag not in WINDOW_CHILDREN:
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"<{tag}> is not a valid child of <window>",
                )
        self._context_stack.pop()

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
        """
        Dispatch control validation based on type.
        Groups recurse into child <control>s.
        Containers expect layout tags.
        Leaf controls get child-tag validation.
        """
        control_type = (node.attrib.get("type") or "").lower().strip()

        if control_type in GROUP_TYPES:
            self._walk_group_control(node, control_type, inside_layout=inside_layout)
        elif control_type in CONTAINER_TYPES:
            self._walk_container(node, control_type, inside_layout=inside_layout)
        elif control_type:
            self._validate_control_children(node, control_type, inside_layout=inside_layout)
        # No type attribute — skip (invalid control type is caught by raw pass)

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
        """Validate layout children — only <control> elements. (CGUIListItemLayout)"""
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
        """Validate <content> children — <item> or <include>. (StaticProvider.cpp:20-34)"""
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
        seen_singletons: set[str] = set()
        seen_singleton_sources: dict[str, bool] = {}

        for child in node:
            tag = child.tag

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
                self._validate_brackets(child, text)

            tag_low = tag.lower()
            allowed_multi = ALLOWED_MULTI.get(
                (node.tag.lower(), control_type), set()
            )
            tag_text = (child.text or "").strip()
            has_dynamic = _is_dynamic(tag_text)

            if (
                len(child) == 0
                and tag_low in SINGLETON_TAGS
                and tag_low not in allowed_multi
                and not has_dynamic
            ):
                if tag_low in seen_singletons:
                    # Allow overrides between include and window XML (Kodi takes first)
                    current_from_include = child.get("_kdk_inc_name") is not None
                    first_from_include = seen_singleton_sources.get(tag_low, False)
                    if not (current_from_include or first_from_include):
                        self._add_issue(
                            child, SEVERITY_WARNING,
                            f"Invalid multiple tags for {node.tag}: <{tag}>",
                        )
                else:
                    seen_singletons.add(tag_low)
                    seen_singleton_sources[tag_low] = child.get("_kdk_inc_name") is not None

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
                self._add_issue(
                    node, SEVERITY_ERROR,
                    f"invalid value for {node.tag}: {value} (must be lowercase)",
                )

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
        """Check if value looks like an unresolved constant/variable name (e.g. from script.skinvariables)."""
        # Bare alphanumeric + underscore/hyphen, no spaces, not a number
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
        self._context_stack.pop()

    def _walk_variable(self, node):
        """Validate <variable> children — only <value>. (GUIIncludes.cpp:160-168)"""
        self._context_stack.append(Context.VARIABLE)
        for child in node:
            if child.tag not in VARIABLE_CHILDREN:
                self._add_issue(
                    child, SEVERITY_WARNING,
                    f"<{child.tag}> is not valid inside <variable> (only <value>)",
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
