"""
Validation and check orchestration mixin for InfoProvider.
"""

from __future__ import annotations

import os
import copy
import logging
from typing import TYPE_CHECKING
from .. import utils
from ..validation import ValidationFont
from ..validation import ValidationImage
from ..validation import ValidationIds
from ..validation import ValidationLabel
from ..validation import ValidationInclude
from ..validation import ValidationVariable
from ..validation import ValidationFileCheck
from ..validation.interpreter import XmlInterpreter
from ..validation.constants import (
    BRACKET_TAGS,
    INCLUDE_DEFINITION_TAGS,
    NOOP_TAGS,
    SINGLETON_TAGS,
    ALLOWED_MULTI,
    ALLOWED_VALUES,
    CASE_INSENSITIVE_ENUMS,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
)

from typing import Any

logger = logging.getLogger(__name__)


class CheckerMixin:
    """All validation: dispatching, per-file checks, reporting."""

    addon: Any
    template_attribs: dict
    template_values: dict
    settings: dict
    WINDOW_IDS: list
    WINDOW_NAMES: list
    _variable_cache: dict

    if TYPE_CHECKING:
        def get_po_files(self) -> list: ...
        def get_color_labels(self) -> set: ...
        def _get_includes_for_folder(self, folder: str) -> list: ...

    def _no_issues(self, kind: str):
        return [{"message": f"No {kind} issues found", "file": "", "line": 0}]

    def resolve_xml(self, path_or_root, *, folder=None, strict=False):
        """
        Return XML root with includes, constants, expressions, and defaults resolved.
        Uses Kodi-aligned kodi_resolve() method for accurate window-based resolution.

        Args:
            path_or_root: File path (str) or parsed root (lxml.Element)
            folder: Override include folder; auto-detect from path or addon default
            strict: Raise on parse errors when True, else return original root

        Returns:
            Resolved lxml.Element tree (deep copy with all transformations applied)
        """
        from ..skin import Skin

        if hasattr(path_or_root, "tag"):
            root = path_or_root
            src_path = None
        else:
            src_path = str(path_or_root)
            root = utils.get_root_from_file(src_path)
            if root is None:
                if strict:
                    raise RuntimeError(f"XML parse failed: {src_path}")
                return None

        f = folder
        if not f and src_path:
            f = os.path.basename(os.path.dirname(src_path)) or None
        if not f and self.addon and getattr(self.addon, "default_xml_folder", None):
            f = self.addon.default_xml_folder
        if not f and self.addon and getattr(self.addon, "xml_folders", None):
            f = next(iter(self.addon.xml_folders), None)

        if not f:
            # No folder context → nothing to expand
            return root

        # 3) Get Skin instance (with 5-map structure for Kodi-aligned resolution)
        sk = getattr(self, "addon", None)
        if not sk or not isinstance(sk, Skin):
            # Non-Skin addon or no addon - cannot resolve includes
            return root

        try:
            # Make deep copy to avoid modifying cached/original tree
            # (kodi_resolve modifies tree in-place per Kodi's CGUIIncludes::Resolve)
            resolved_root = copy.deepcopy(root)

            # Apply Kodi-exact resolution: defaults → constants → expressions → includes → recurse
            sk.resolver.resolve(resolved_root, f)

            return resolved_root
        except Exception:
            if strict:
                raise
            # Fall back to unexpanded tree for display use-cases
            return root

    def get_check_listitems(self, check_type, progress_callback=None):
        """
        Dispatch skin checks by type and return a list of rows:
        {"message": str, "file": str, "line": int}

        Args:
            check_type: Type of check to run
            progress_callback: Optional callback for progress updates (for checks that support it)
        """
        checks_with_progress = {
            "general": lambda: self.check_values(progress_callback=progress_callback),
            "file": lambda: self.check_values(progress_callback=progress_callback),
        }

        checks_simple = {
            "variable": self.check_variables,
            "include": self.check_includes,
            "font": self.check_fonts,
            "label": self.check_labels,
            "id": self.check_ids,
            # keep while image checker is under active development
            "image": getattr(
                self,
                "check_images",
                lambda: [{"message": "No image issues found", "file": "", "line": 0}],
            ),
            "filecheck": self.check_file_integrity,
        }

        fn = checks_with_progress.get(check_type)
        if fn:
            rows = fn() or []
        else:
            fn = checks_simple.get(check_type)
            if not fn:
                logger.info("[checks] handler missing type=%s", check_type)
                return [{"message": "Unknown check type", "file": "", "line": 0}]
            rows = fn() or []

        filtered_rows = [
            row for row in rows
            if not utils.is_runtime_generated_file(row.get("file", ""))
        ]

        return filtered_rows

    def get_validation_index(self, progress_callback=None):
        """
        Get or build the validation index.
        The index is built once and cached for performance.

        Args:
            progress_callback: Optional callback function(message: str) for progress updates

        Returns:
            dict: Validation index with fonts, labels, IDs, etc.
        """
        if not self.addon:
            return None

        # Check if addon supports validation index (real Skin class does, test mocks might not)
        if not hasattr(self.addon, 'validation_index'):
            return None
        if not hasattr(self.addon, 'index_builder'):
            return None

        if self.addon.validation_index is None:  # type: ignore[attr-defined]
            self.addon.validation_index = self.addon.index_builder.build_validation_index(progress_callback=progress_callback)  # type: ignore[attr-defined]

        return self.addon.validation_index  # type: ignore[attr-defined]

    def check_variables(self, progress_callback=None):
        """Find undefined or unused variables."""
        if not self.addon:
            return self._no_issues("variable")

        checker = ValidationVariable(self.addon)
        return checker.check(progress_callback=progress_callback)

    def check_includes(self, progress_callback=None):
        """Check undefined/unused includes."""
        if not self.addon:
            return self._no_issues("include")

        checker = ValidationInclude(self.addon)
        return checker.check(progress_callback=progress_callback)

    def check_fonts(self, progress_callback=None):
        """Validate fonts declared by the current skin.

        Args:
            progress_callback: Optional callback function(message: str) for progress updates
        """
        if not self.addon:
            return self._no_issues("font")

        index = self.get_validation_index(progress_callback=progress_callback)
        if index:
            checker = ValidationFont(self.addon, resolve_include_fn=self.resolve_xml, validation_index=index)
        else:
            checker = ValidationFont(self.addon, resolve_include_fn=self.resolve_xml)
        return checker.check(progress_callback=progress_callback)

    def check_ids(self, progress_callback=None):
        """Check undefined or invalid control/window IDs.

        Args:
            progress_callback: Optional callback function(message: str) for progress updates
        """
        if not self.addon:
            return self._no_issues("id")

        index = self.get_validation_index(progress_callback=progress_callback)
        if index:
            checker = ValidationIds(self.addon, self.WINDOW_IDS, self.WINDOW_NAMES, resolve_include_fn=self.resolve_xml, validation_index=index)
        else:
            checker = ValidationIds(self.addon, self.WINDOW_IDS, self.WINDOW_NAMES, resolve_include_fn=self.resolve_xml)
        return checker.check(progress_callback=progress_callback)

    def check_labels(self, progress_callback=None):
        """Find untranslated/undefined labels.

        Args:
            progress_callback: Optional callback function(message: str) for progress updates
        """
        if not self.addon:
            return self._no_issues("label")

        index = self.get_validation_index(progress_callback=progress_callback)
        if index:
            checker = ValidationLabel(self.addon, self.get_po_files, resolve_include_fn=self.resolve_xml, validation_index=index)
        else:
            checker = ValidationLabel(self.addon, self.get_po_files, resolve_include_fn=self.resolve_xml)
        return checker.check(progress_callback=progress_callback)

    def check_file_integrity(self, progress_callback=None):
        """Check for BOM and wrong line endings."""
        checker = ValidationFileCheck(self.addon)
        return checker.check(progress_callback=progress_callback)

    def check_images(self, progress_callback=None):
        """Validate image references used by the current skin."""
        if not self.addon:
            return self._no_issues("image")

        index = self.get_validation_index(progress_callback=progress_callback)
        checker = ValidationImage(self.addon, validation_index=index)
        return checker.check(progress_callback=progress_callback)


    def check_values(self, progress_callback=None):
        """
        Apply check_file to all XML files in the addon.
        Validates what the skin author actually wrote (unexpanded source).

        Args:
            progress_callback: Optional function to call with progress updates (message: str)
        """
        if not self.addon:
            return []

        listitems = []
        xml_files = list(self.addon.get_xml_files())  # Convert generator to list for len()
        total_files = len(xml_files)

        if progress_callback:
            progress_callback(f"Validating {total_files} XML files...")

        for index, path in enumerate(xml_files, 1):
            if progress_callback:
                filename = os.path.basename(path)
                if index <= 10:
                    progress_callback(f"Validating {filename} ({index}/{total_files})...")
                elif total_files > 100 and index % 10 == 0:
                    progress_callback(f"Validating {filename} ({index}/{total_files})...")
                elif index % 3 == 0:
                    progress_callback(f"Validating {filename} ({index}/{total_files})...")
            result = self.check_file(path)
            if result:
                listitems.extend(result)

        error_count = len(listitems)
        if progress_callback:
            progress_callback(f"Complete: {error_count} XML validation issues found")

        return listitems

    def _add_issue(self, listitems, node, message, identifier="", severity=SEVERITY_WARNING):
        """Helper to create and append validation issue dict from XML node."""
        issue = utils.create_issue(
            message=message,
            file="",  # File added later in check_file()
            line=node.sourceline,
            type=node.tag,
            identifier=identifier or node.tag
        )
        issue["severity"] = severity
        listitems.append(issue)

    def _validate_brackets(self, listitems, node, text):
        """Helper to validate bracket matching in conditions."""
        if not text:
            self._add_issue(listitems, node, f"Empty condition: {node.tag}", severity=SEVERITY_ERROR)
            return False
        if utils.is_dynamic_expression(text):
            return True
        if not utils.check_brackets(text):
            condition = text.replace("  ", "").replace("\t", "")
            self._add_issue(listitems, node, f"Brackets do not match: {condition}", condition, severity=SEVERITY_ERROR)
            return False
        return True

    def _validate_enum_value(self, listitems, node, value, value_type, attr_name=None):
        """Helper to validate enum values against ALLOWED_VALUES."""
        if value_type not in ALLOWED_VALUES:
            return True
        if utils.is_dynamic_expression(value):
            return True

        # Check if this enum type should be validated case-insensitively
        # (matches Kodi behavior: GUIControlFactory.cpp line 1124 for orientation,
        #  XMLUtils::GetBoolean for bool types)
        if value_type in CASE_INSENSITIVE_ENUMS:
            normalized_value = value.lower()
            if normalized_value not in ALLOWED_VALUES[value_type]:
                location = f"{attr_name} attribute" if attr_name else node.tag
                allowed = ", ".join(sorted(ALLOWED_VALUES[value_type]))
                self._add_issue(listitems, node, f"invalid value for {location}: {value} (allowed: {allowed})", value, severity=SEVERITY_ERROR)
                return False
        else:
            if value not in ALLOWED_VALUES[value_type]:
                location = f"{attr_name} attribute" if attr_name else node.tag
                self._add_issue(listitems, node, f"invalid value for {location}: {value} (must be lowercase)", value, severity=SEVERITY_ERROR)
                return False
        return True

    def _validate_variable_values(self, listitems, node, var_text, value_type, folder, tag_name=None):
        """
        Validate that all values in a variable definition match the expected type.

        Args:
            listitems: List to add issues to
            node: XML node where variable is used
            var_text: Text containing variable reference (e.g., "$VAR[HighlightColor]")
            value_type: Expected type (e.g., "color", "int", "enum_name")
            folder: XML folder for include lookup
            tag_name: Name of tag or attribute where variable is used (for error messages)

        Returns:
            True if all values are valid or validation skipped, False if any invalid
        """
        var_name = utils.extract_variable_name(var_text)
        if not var_name:
            return True  # Not a variable expression

        # PERFORMANCE FIX: Use pre-built cache (O(1) lookup instead of O(m) iteration)
        # The cache is built once per file in check_file() for fast lookups
        var_def = getattr(self, '_variable_cache', {}).get(var_name)

        if not var_def or var_def.get("node") is None:
            return True  # Variable not found or no XML node - different check handles this

        var_node = var_def.get("node")
        value_nodes = var_node.findall("value")

        if not value_nodes:
            return True  # No values to check

        all_valid = True
        for value_node in value_nodes:
            value_text = (value_node.text or "").strip()
            if not value_text:
                continue  # Skip empty values

            if utils.is_dynamic_expression(value_text):
                continue

            is_valid = True
            if value_type == "color" and getattr(self.addon, "type", None) == "skin":
                is_valid = value_text in self.get_color_labels() or utils.is_kodi_hex(value_text)
                if not is_valid:
                    location = tag_name if tag_name else node.tag
                    self._add_issue(
                        listitems, node,
                        f"Variable ${var_name} used in <{location}> has invalid color value: {value_text}",
                        value_text
                    )
            elif value_type in ["int", "position"]:
                check_val = value_text.rstrip("%r") if value_type == "position" else value_text
                number_value = utils.extract_number_value(value_text)
                if number_value:
                    check_val = number_value
                is_valid = utils.is_number(check_val) or (self.addon and value_text in self.addon.get_constants(folder))
                if not is_valid:
                    location = tag_name if tag_name else node.tag
                    self._add_issue(
                        listitems, node,
                        f"Variable ${var_name} used in <{location}> has invalid integer value: {value_text}",
                        value_text
                    )
            elif value_type in ALLOWED_VALUES:
                is_valid = value_text in ALLOWED_VALUES[value_type]
                if not is_valid:
                    location = tag_name if tag_name else node.tag
                    self._add_issue(
                        listitems, node,
                        f"Variable ${var_name} used in <{location}> has invalid value: {value_text}",
                        value_text
                    )

            if not is_valid:
                all_valid = False

        return all_valid

    def _can_resolve(self) -> bool:
        """Check if addon is a Skin with populated include maps."""
        from ..skin import Skin
        return isinstance(self.addon, Skin) and hasattr(self.addon, "resolver")

    def _check_file_resolved(self, root, path: str, folder: str) -> list[dict]:
        """
        Validate the resolved (include-expanded) tree using XmlInterpreter.

        Deep-copies root, resolves via SkinResolution, then walks the
        resolved tree checking structural correctness at every nesting level.
        Skips the expensive deepcopy+resolve for files without includes.
        """
        from ..skin import Skin

        sk = self.addon
        if not isinstance(sk, Skin):
            return []

        # Skip expensive deepcopy+resolve for static files
        if utils.tree_needs_expansion(root):
            try:
                walk_root = copy.deepcopy(root)
                sk.resolver.resolve(walk_root, folder, source_file=path)
            except Exception:
                logger.debug("Resolution failed for %s, skipping resolved pass", path, exc_info=True)
                return []
        else:
            walk_root = root

        interpreter = XmlInterpreter(
            template_attribs=self.template_attribs,
            template_values=self.template_values,
            file_path=path,
            color_labels=self.get_color_labels(),
        )
        issues = interpreter.interpret(walk_root)

        for item in issues:
            item["filename"] = os.path.basename(path)
            item["file"] = path

        return issues

    def check_file(self, path):
        """
        Validate original (unexpanded) XML file for errors.
        This checks what the skin author actually wrote, before include expansion.

        For skin addons, also runs the resolved-tree interpreter and merges
        issues with deduplication by (line, message).
        """
        # Skip excluded paths from settings (returns None, not [])
        exclude = set(self.settings.get("validation_exclude", ["shortcuts"]))
        path_parts = set(path.replace("\\", "/").split("/"))
        if exclude & path_parts:
            return None

        root = utils.get_root_from_file(path)
        if root is None:
            return []

        folder = path.split(os.sep)[-2] if os.sep in path else ""
        listitems = []

        self._variable_cache = {}
        for item in self._get_includes_for_folder(folder):
            if item.get("type") == "variable":
                var_name = item.get("name")
                if var_name:
                    self._variable_cache[var_name] = item

        nodes_invalid_type = []
        if self.template_attribs:
            all_typed_controls = root.xpath(".//control[@type]")
            allowed_types_lower = {ct.lower() for ct in self.template_attribs.keys()}
            for node in all_typed_controls:
                ctrl_type = node.get("type", "").strip()
                if ctrl_type and ctrl_type.lower() not in allowed_types_lower:
                    if not utils.is_dynamic_expression(ctrl_type):
                        nodes_invalid_type.append(node)

        for node in nodes_invalid_type:
            listitems.append(
                {
                    "line": node.sourceline,
                    "type": node.tag,
                    "identifier": node.attrib.get("type"),
                    "message": "invalid control type: %s"
                    % (node.attrib.get("type")),
                    "severity": SEVERITY_ERROR,
                }
            )

        # When interpreter handles resolved tree, skip value checks here to avoid
        # false positives from $PARAM/$VAR/$CONST in unresolved XML
        skip_value_checks = self._can_resolve()

        seen_singletons = {}

        def _seen_for(parent):
            k = id(parent)
            s = seen_singletons.get(k)
            if s is None:
                s = set()
                seen_singletons[k] = s
            return s

        for c_type, subnodes, node, subnode in self.file_control_checks(root, file_path=path):

            if subnode.tag in INCLUDE_DEFINITION_TAGS:
                continue

            if subnode.tag not in subnodes:
                label = (
                    node.tag
                    if "type" not in node.attrib
                    else "%s type=%s" % (node.tag, node.attrib.get("type"))
                )
                listitems.append(
                    {
                        "line": subnode.sourceline,
                        "type": subnode.tag,
                        "identifier": subnode.tag,
                        "message": "invalid tag for <%s>: <%s>" % (label, subnode.tag),
                        "severity": SEVERITY_WARNING,
                    }
                )
                continue

            tmpl_val = self.template_values[c_type].get(subnode.tag)
            if subnode.text and tmpl_val:
                if not skip_value_checks:
                    self._validate_enum_value(listitems, subnode, subnode.text, tmpl_val)
                if utils.is_dynamic_expression(subnode.text):
                    self._validate_variable_values(listitems, subnode, subnode.text, tmpl_val, folder)

            if not skip_value_checks:
                if subnode.tag in NOOP_TAGS:
                    text = (subnode.text or "").strip()
                    if not text and len(subnode) == 0:
                        self._add_issue(listitems, subnode, f"Use 'noop' for empty calls <{node.tag}>", severity=SEVERITY_ERROR)

                if subnode.tag in BRACKET_TAGS:
                    text = (subnode.text or "").strip()
                    if not self._validate_brackets(listitems, subnode, text):
                        continue

                parent = node
                tag_low = subnode.tag.lower()
                allowed_multi = ALLOWED_MULTI.get(
                    (parent.tag.lower(), parent.attrib.get("type", "").lower()), set()
                )
                tag_text = (subnode.text or "").strip()
                has_dynamic_content = utils.is_dynamic_expression(tag_text)

                if (
                    len(subnode) == 0
                    and tag_low in SINGLETON_TAGS
                    and tag_low not in allowed_multi
                    and not has_dynamic_content
                ):
                    seen = _seen_for(parent)
                    if tag_low in seen:
                        self._add_issue(listitems, subnode, f"Invalid multiple tags for {parent.tag}: <{subnode.tag}>")
                    else:
                        seen.add(tag_low)

            # Attribute checks — structural (invalid name) always runs,
            # value checks gated by skip_value_checks
            for k, v in subnode.attrib.items():
                if k == "description":
                    continue
                if k not in subnodes[subnode.tag]:
                    self._add_issue(listitems, subnode, f"invalid attribute for <{subnode.tag}>: {k}", k)
                    continue
                if utils.is_dynamic_expression(v):
                    value_type = subnodes[subnode.tag].get(k)
                    if value_type:
                        self._validate_variable_values(listitems, subnode, v, value_type, folder, tag_name=k)
                    continue
                if utils.contains_dynamic_expression(v):
                    continue
                if (v or "").strip() == "" and k in ("target", "sortby", "sortorder", "limit"):
                    continue
                value_type = subnodes[subnode.tag][k]
                if value_type in ["int", "position"]:
                    vv = v.rstrip("%r") if value_type == "position" else v
                    number_value = utils.extract_number_value(v)
                    if number_value:
                        vv = number_value
                    if not utils.is_number(vv) and not (self.addon and v in self.addon.get_constants(folder)):
                        self._add_issue(listitems, subnode, f"invalid integer value for {k}: {v}", v, severity=SEVERITY_ERROR)
                elif value_type == "color":
                    if getattr(self.addon, "type", None) == "skin" and v not in self.get_color_labels() and not utils.is_kodi_hex(v):
                        self._add_issue(listitems, subnode, f"Invalid color for {k}: {v}", v, severity=SEVERITY_ERROR)
                elif not skip_value_checks:
                    self._validate_enum_value(listitems, subnode, v, value_type, attr_name=k)

                if not skip_value_checks and k == "condition" and v:
                    self._validate_brackets(listitems, subnode, v)


        for item in listitems:
            item["filename"] = os.path.basename(path)
            item["file"] = path

        if self._can_resolve():
            resolved_issues = self._check_file_resolved(root, path, folder)
            if resolved_issues:
                # Deduplicate by (line, message) — raw pass issues take priority
                seen = {(item["line"], item["message"]) for item in listitems}
                for item in resolved_issues:
                    key = (item["line"], item["message"])
                    if key not in seen:
                        listitems.append(item)
                        seen.add(key)

        return listitems

    def file_control_checks(self, root, *, file_path=None):
        """
        Yield (control_type, allowed_subnodes, control_node, child_node).

        Optimized to run ONE xpath query per file instead of N queries per control type.
        """
        if file_path:
            logger.debug("Running file_control_checks for %s", os.path.basename(file_path))

        all_controls = root.xpath(".//control[@type]")

        for node in all_controls:
            c_type_raw = node.attrib.get("type", "")
            if not c_type_raw:
                continue
            c_type = c_type_raw.lower()

            subnodes = self.template_attribs.get(c_type)
            if subnodes is None:
                continue

            for subnode in node.iterchildren():
                yield (c_type, subnodes, node, subnode)
