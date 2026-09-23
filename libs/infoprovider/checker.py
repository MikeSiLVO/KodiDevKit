"""Validation and check orchestration mixin for InfoProvider."""

from __future__ import annotations

import os
import copy
import logging
from ..utils.xml import check_brackets, get_root_from_file, tree_needs_expansion
from ..utils.expressions import (
    contains_dynamic_expression,
    extract_number_value,
    extract_variable_name,
    is_dynamic_expression,
    is_number,
)
from ..utils.validation import create_issue, is_runtime_generated_file
from ..addon.translations import get_po_file
from ..utils.colors import is_kodi_hex
from ..validation.font import ValidationFont
from ..validation.image import ValidationImage
from ..validation.ids import ValidationIds
from ..validation.label import ValidationLabel
from ..validation.include import ValidationInclude
from ..validation.variable import ValidationVariable
from ..validation.skinmap import ValidationMap
from ..validation.filecheck import ValidationFileCheck
from ..validation.include import check_include_file_ref
from ..validation.suppress import scan_skin
from ..validation.interpreter import XmlInterpreter
from ..validation.hierarchy import ALL_LAYOUT_TAGS
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

# every hover re-enters get_po_files; keyed by mtime so a refreshed snapshot reloads
_CORE_PO_CACHE: dict = {}


def _core_po(path):
    """Parsed Kodi-core strings.po at the path, reusing the last parse."""
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        stamp = None
    cached = _CORE_PO_CACHE.get(path)
    if cached and cached[0] == stamp:
        return cached[1]
    po = get_po_file(path)
    if po is not None:
        po.language = "resource.language.en_gb"  # type: ignore[attr-defined]
        _CORE_PO_CACHE[path] = (stamp, po)
    return po


class CheckerMixin:
    """All validation: dispatching, per-file checks, reporting."""

    addon: Any
    template_attribs: dict
    template_values: dict
    settings: dict
    WINDOW_IDS: list
    WINDOW_NAMES: list
    _variable_cache: dict

    def get_po_files(self) -> list:
        """Get the skin's PO files plus Kodi-core strings.po from kodi_path or the snapshot."""
        from ..kodi_refs import kodi_strings_po

        po_files = []
        seen = set()

        def _add(po):
            if po is None or id(po) in seen:
                return
            seen.add(id(po))
            po_files.append(po)

        if self.addon and hasattr(self.addon, "po_files"):
            for po in self.addon.po_files:
                _add(po)

        kodi_path = (self.settings.get("kodi_path") or "").strip() if self.settings else ""
        core_po_path = kodi_strings_po(self.addon, kodi_path or None)
        if core_po_path:
            try:
                _add(_core_po(core_po_path))
            except Exception as e:
                logger.warning("Failed to load Kodi-core strings.po (%s): %s", core_po_path, e)

        return po_files

    def get_color_labels(self) -> set:
        """Get the color names the skin defines, empty without an addon."""
        if self.addon and hasattr(self.addon, "color_labels"):
            return self.addon.color_labels
        return set()

    def _get_includes_for_folder(self, folder: str) -> list:
        """Flatten the folder's include, variable and default maps into one list of rows."""
        if not self.addon:
            return []

        if not hasattr(self.addon, "include_map"):
            return self.addon.includes.get(folder, [])

        from ..skin.include import SkinInclude

        result = []
        for name, (node, params, file_path) in self.addon.include_map.get(folder, {}).items():
            definition = node.find("definition")
            include_body = definition if definition is not None else node
            inc = SkinInclude(node=include_body, file=file_path)
            result.append({
                "name": name, "type": "include",
                "file": inc.file, "line": inc.line,
                "content": inc.content, "node": inc.node,
                "params": params,
            })

        for name, (node, file_path) in self.addon.variable_map.get(folder, {}).items():
            inc = SkinInclude(node=node, file=file_path)
            result.append({
                "name": name, "type": "variable",
                "file": inc.file, "line": inc.line,
                "content": inc.content, "node": inc.node,
            })

        for control_type, (node, file_path) in self.addon.default_map.get(folder, {}).items():
            inc = SkinInclude(node=node, file=file_path)
            result.append({
                "name": control_type, "type": "default",
                "file": inc.file, "line": inc.line,
                "content": inc.content, "node": inc.node,
            })

        return result

    def _no_issues(self, kind: str):
        """Single placeholder row saying the check found nothing."""
        return [{"message": f"No {kind} issues found", "file": "", "line": 0}]

    def resolve_xml(self, path_or_root, *, folder=None, strict=False):
        """Include-resolved copy of a tree or file; without strict, failures fall back."""
        from ..skin.skin import Skin

        if hasattr(path_or_root, "tag"):
            root = path_or_root
            src_path = None
        else:
            src_path = str(path_or_root)
            root = get_root_from_file(src_path)
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
            return root

        sk = getattr(self, "addon", None)
        if not sk or not isinstance(sk, Skin):
            return root

        try:
            # resolve() mutates in place, as CGUIIncludes::Resolve does
            resolved_root = copy.deepcopy(root)
            sk.resolver.resolve(resolved_root, f)
            return resolved_root
        except Exception:
            if strict:
                raise
            return root

    def get_check_listitems(self, check_type, progress_callback=None):
        """Get the rows of the named check, minus those in runtime-generated files."""
        checks_with_progress = {
            "general": lambda: self.check_values(progress_callback=progress_callback),
            "file": lambda: self.check_values(progress_callback=progress_callback),
        }

        checks_simple = {
            "variable": self.check_variables,
            "map": self.check_maps,
            "include": self.check_includes,
            "font": self.check_fonts,
            "label": self.check_labels,
            "id": self.check_ids,
            "image": self.check_images,
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
            if not is_runtime_generated_file(row.get("file", ""))
        ]

        return filtered_rows

    def get_suppressions(self):
        """Cached `kdk-ignore` directives for the current skin; rebuilt when the skin reloads."""
        cached = getattr(self.addon, "_kdk_suppressions", None)
        if cached is None:
            cached = scan_skin(self.addon)
            try:
                self.addon._kdk_suppressions = cached
            except AttributeError:
                pass
        return cached

    def _muted(self, category, issues):
        """Drop the category's issues that a `kdk-ignore` comment mutes."""
        if not self.addon or not issues:
            return issues
        return self.get_suppressions().filter(category, issues)

    def get_validation_index(self, progress_callback=None):
        """Get the cached validation index, building it on first access."""
        if not self.addon:
            return None

        # test mocks may lack the index
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
        return self._muted("Variables", checker.check(progress_callback=progress_callback))

    def check_maps(self, progress_callback=None):
        """Find malformed, undefined, or unused skin maps."""
        if not self.addon:
            return self._no_issues("map")

        checker = ValidationMap(self.addon)
        return self._muted("Maps", checker.check(progress_callback=progress_callback))

    def check_includes(self, progress_callback=None):
        """Check undefined/unused includes."""
        if not self.addon:
            return self._no_issues("include")

        checker = ValidationInclude(self.addon)
        return self._muted("Includes", checker.check(progress_callback=progress_callback))

    def check_fonts(self, progress_callback=None):
        """Validate fonts declared by the current skin."""
        if not self.addon:
            return self._no_issues("font")

        index = self.get_validation_index(progress_callback=progress_callback)
        if index:
            checker = ValidationFont(self.addon, resolve_include_fn=self.resolve_xml, validation_index=index)
        else:
            checker = ValidationFont(self.addon, resolve_include_fn=self.resolve_xml)
        return self._muted("Fonts", checker.check(progress_callback=progress_callback))

    def check_ids(self, progress_callback=None):
        """Check undefined or invalid control/window IDs."""
        if not self.addon:
            return self._no_issues("id")

        index = self.get_validation_index(progress_callback=progress_callback)
        if index:
            checker = ValidationIds(self.addon, self.WINDOW_IDS, self.WINDOW_NAMES, resolve_include_fn=self.resolve_xml, validation_index=index)
        else:
            checker = ValidationIds(self.addon, self.WINDOW_IDS, self.WINDOW_NAMES, resolve_include_fn=self.resolve_xml)
        return self._muted("IDs", checker.check(progress_callback=progress_callback))

    def check_labels(self, progress_callback=None):
        """Find untranslated/undefined labels."""
        if not self.addon:
            return self._no_issues("label")

        index = self.get_validation_index(progress_callback=progress_callback)
        if index:
            checker = ValidationLabel(self.addon, self.get_po_files, resolve_include_fn=self.resolve_xml, validation_index=index)
        else:
            checker = ValidationLabel(self.addon, self.get_po_files, resolve_include_fn=self.resolve_xml)
        return self._muted("Labels", checker.check(progress_callback=progress_callback))

    def check_file_integrity(self, progress_callback=None):
        """Check for BOM and wrong line endings."""
        checker = ValidationFileCheck(self.addon)
        return self._muted("File Integrity", checker.check(progress_callback=progress_callback))

    def check_images(self, progress_callback=None):
        """Validate image references used by the current skin."""
        if not self.addon:
            return self._no_issues("image")

        index = self.get_validation_index(progress_callback=progress_callback)
        checker = ValidationImage(self.addon, validation_index=index)
        return self._muted("Images", checker.check(progress_callback=progress_callback))


    def check_values(self, progress_callback=None):
        """Run check_file over every XML file, on the unexpanded source the author wrote."""
        if not self.addon:
            return []

        listitems = []
        xml_files = list(self.addon.get_xml_files())
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

        listitems = self._muted("XML Validation", listitems)

        if progress_callback:
            progress_callback(f"Complete: {len(listitems)} XML validation issues found")

        return listitems

    def _add_issue(self, listitems, node, message, identifier="", severity=SEVERITY_WARNING):
        """Append an issue at the node's line; check_file fills in the file later."""
        issue = create_issue(
            message=message,
            file="",
            line=node.sourceline,
            type=node.tag,
            identifier=identifier or node.tag
        )
        issue["severity"] = severity
        listitems.append(issue)

    def _validate_brackets(self, listitems, node, text):
        """Report an empty or unbalanced condition; returns whether the text is usable."""
        if not text:
            self._add_issue(listitems, node, f"Empty condition: {node.tag}", severity=SEVERITY_ERROR)
            return False
        if is_dynamic_expression(text):
            return True
        if not check_brackets(text):
            condition = text.replace("  ", "").replace("\t", "")
            self._add_issue(listitems, node, f"Brackets do not match: {condition}", condition, severity=SEVERITY_ERROR)
            return False
        return True

    def _validate_enum_value(self, listitems, node, value, value_type, attr_name=None):
        """Report a value outside ALLOWED_VALUES for its type; returns whether it passed."""
        if value_type not in ALLOWED_VALUES:
            return True
        if is_dynamic_expression(value):
            return True

        # lowercased by Kodi first (GUIControlFactory.cpp orientation, XMLUtils::GetBoolean)
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
                if value.lower() in ALLOWED_VALUES[value_type]:
                    detail = "must be lowercase"
                else:
                    detail = "allowed: " + ", ".join(sorted(ALLOWED_VALUES[value_type]))
                self._add_issue(listitems, node, f"invalid value for {location}: {value} ({detail})", value, severity=SEVERITY_ERROR)
                return False
        return True

    def _validate_variable_values(self, listitems, node, var_text, value_type, folder, tag_name=None):
        """Check every <value> of the $VAR definition against the tag's value type."""
        var_name = extract_variable_name(var_text)
        if not var_name:
            return True

        var_def = getattr(self, '_variable_cache', {}).get(var_name)

        if not var_def or var_def.get("node") is None:
            return True  # undefined vars are the variable check's job

        var_node = var_def.get("node")
        value_nodes = var_node.findall("value")

        if not value_nodes:
            return True

        all_valid = True
        for value_node in value_nodes:
            value_text = (value_node.text or "").strip()
            if not value_text:
                continue

            if is_dynamic_expression(value_text):
                continue

            is_valid = True
            if value_type == "color" and getattr(self.addon, "type", None) == "skin":
                is_valid = value_text in self.get_color_labels() or is_kodi_hex(value_text)
                if not is_valid:
                    location = tag_name if tag_name else node.tag
                    self._add_issue(
                        listitems, node,
                        f"Variable ${var_name} used in <{location}> has invalid color value: {value_text}",
                        value_text
                    )
            elif value_type in ["int", "position"]:
                check_val = value_text.rstrip("%r") if value_type == "position" else value_text
                number_value = extract_number_value(value_text)
                if number_value:
                    check_val = number_value
                is_valid = is_number(check_val) or (self.addon and value_text in self.addon.get_constants(folder))
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
        """Whether the addon is a Skin carrying a resolver."""
        from ..skin.skin import Skin
        return isinstance(self.addon, Skin) and hasattr(self.addon, "resolver")

    def _check_file_resolved(self, root, path: str, folder: str) -> list[dict]:
        """XmlInterpreter issues over the expanded tree; files without includes are walked as-is."""
        from ..skin.skin import Skin

        sk = self.addon
        if not isinstance(sk, Skin):
            return []

        if tree_needs_expansion(root):
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
        """Validate one file as written plus the resolved pass for skins; None when excluded."""
        exclude = set(self.settings.get("validation_exclude", ["shortcuts"]))
        path_parts = set(path.replace("\\", "/").split("/"))
        if exclude & path_parts:
            return None

        root = get_root_from_file(path)
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

        for node in root.xpath(".//include[@file]"):
            issue = check_include_file_ref(self.addon, folder, node.attrib["file"])
            if issue:
                issue["line"] = node.sourceline
                listitems.append(issue)

        nodes_invalid_type = []
        if self.template_attribs:
            all_typed_controls = root.xpath(".//control[@type]")
            allowed_types_lower = {ct.lower() for ct in self.template_attribs.keys()}
            for node in all_typed_controls:
                ctrl_type = node.get("type", "").strip()
                if ctrl_type and ctrl_type.lower() not in allowed_types_lower:
                    if not is_dynamic_expression(ctrl_type):
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

        # resolved pass checks values; unresolved $PARAM, $VAR and constants would false-positive
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
                if is_dynamic_expression(subnode.text):
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
                has_dynamic_content = is_dynamic_expression(tag_text)

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

            # attribute names always checked; values wait for the resolved pass when it runs
            for k, v in subnode.attrib.items():
                if k == "description":
                    continue
                if k not in subnodes[subnode.tag]:
                    self._add_issue(listitems, subnode, f"invalid attribute for <{subnode.tag}>: {k}", k)
                    continue
                if is_dynamic_expression(v):
                    value_type = subnodes[subnode.tag].get(k)
                    if value_type:
                        self._validate_variable_values(listitems, subnode, v, value_type, folder, tag_name=k)
                    continue
                if contains_dynamic_expression(v):
                    continue
                if (v or "").strip() == "" and k in ("target", "sortby", "sortorder", "limit"):
                    continue
                value_type = subnodes[subnode.tag][k]
                if value_type in ["int", "position"]:
                    # CGUIListItemLayout falls back to the container size for a non-numeric size
                    if subnode.tag in ALL_LAYOUT_TAGS and v == "auto":
                        continue
                    vv = v.rstrip("%r") if value_type == "position" else v
                    number_value = extract_number_value(v)
                    if number_value:
                        vv = number_value
                    if not is_number(vv) and not (self.addon and v in self.addon.get_constants(folder)):
                        self._add_issue(listitems, subnode, f"invalid integer value for {k}: {v}", v, severity=SEVERITY_ERROR)
                elif value_type == "color":
                    if getattr(self.addon, "type", None) == "skin" and v not in self.get_color_labels() and not is_kodi_hex(v):
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
                # Source-pass issues take priority on collision.
                seen = {(item["line"], item["message"]) for item in listitems}
                for item in resolved_issues:
                    key = (item["line"], item["message"])
                    if key not in seen:
                        listitems.append(item)
                        seen.add(key)

        return listitems

    def file_control_checks(self, root, *, file_path=None):
        """Yield (control type, allowed tags, control, child) for every child of a typed control."""
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
