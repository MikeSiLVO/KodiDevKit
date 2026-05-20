"""Validation utilities for KodiDevKit."""

import os
import re
import logging
from functools import lru_cache

logger = logging.getLogger("KodiDevKit.utils.validation")
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.propagate = True


def is_runtime_generated_file(file_path):
    """True if `file_path` is a script.skinvariables runtime-generated XML."""
    if not file_path:
        return False

    filename = os.path.basename(file_path).lower()

    # Only script-skinvariables-*.xml files (not skinshortcuts per user preference)
    # Examples: script-skinvariables-labels-includes.xml, script-skinvariables-images-includes.xml
    return filename.startswith('script-skinvariables-')


def normalize_control_id(control_id):
    """Strip leading zeros from a numeric control id (Kodi parses ids as ints).

    `"05"` and `"5"` both refer to the same control. Non-numeric ids
    are returned unchanged.
    """
    if not control_id or not isinstance(control_id, str):
        return control_id

    if not control_id.isdigit():
        return control_id

    normalized = control_id.lstrip('0') or '0'
    return normalized


def create_issue(message, file="", line=0, **kwargs):
    """Build a validation-issue dict with the standard fields plus any extras."""
    issue = {
        "message": message,
        "file": file,
        "line": line,
    }
    issue.update(kwargs)
    return issue


_PARAM_PATTERN = re.compile(r'\$PARAM\[([^\]]+)\]')


def resolve_param_in_name(name, param_context=None, cache=None):
    """Replace `$PARAM[name]` in `name` using `param_context` (undefined -> '').

    Optional `cache` dict reuses prior results for the same (name, params) pair.
    """
    if not name or "$PARAM[" not in name:
        return name

    cache_key = None
    if cache is not None:
        cache_key = (name, frozenset(param_context.items()) if param_context else frozenset())
        if cache_key in cache:
            return cache[cache_key]

    def replace_param(match):
        param_name = match.group(1)
        if param_context and param_name in param_context:
            return param_context[param_name]
        return ''

    resolved = _PARAM_PATTERN.sub(replace_param, name)

    if cache is not None and cache_key is not None:
        cache[cache_key] = resolved

    return resolved


def get_all_parameter_contexts(addon, folder):
    """Return every `$PARAM` context that any include in `folder` is called with.

    Used so a `$PARAM`-bearing name can be tested against every concrete
    binding to see if any of them resolves to something defined.
    """
    if not addon._include_usages_built:
        addon.index_builder.build_include_usages()

    all_contexts = []
    for _inc_name, usages in addon.include_usages.get(folder, {}).items():
        for usage in usages:
            all_contexts.append(usage['params'])

    all_contexts.append({})
    return all_contexts


def should_report_progress(count, total):
    """Throttle progress: always first 10, then every 10 (large) or every 3."""
    if count <= 10:
        return True
    if total > 100:
        return count % 10 == 0
    return count % 3 == 0


def deduplicate_issues(issues):
    """Deduplicate validation issues by (file, line, message) key."""
    seen = set()
    result = []
    for issue in issues:
        key = (issue['file'], issue['line'], issue['message'])
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return result


def find_unused_items(definitions, references, item_type, skip_filter=None):
    """Return issue dicts for `definitions` whose name never appears in `references`.

    `skip_filter(node)` lets callers exclude e.g. runtime-generated entries.
    """
    ref_names = {ref["name"] for ref in references}
    unused = []

    for node in definitions:
        if node.get("type") == item_type and node.get("name") not in ref_names:
            if skip_filter and skip_filter(node):
                continue

            unused.append(
                create_issue(
                    f"Unused {item_type}: {node['name']}",
                    file=node.get("file") or "",
                    line=node.get("line") or 0,
                    type=item_type,
                    name=node["name"]
                )
            )

    return unused


def find_undefined_items(references, definitions, item_type, skip_filter=None):
    """Return reference dicts (annotated with a message) whose name has no matching definition."""
    defined_names = {
        node.get("name")
        for node in definitions
        if node.get("type") == item_type and node.get("name")
    }

    undefined = []
    for ref in references:
        if skip_filter and skip_filter(ref):
            continue

        if ref["name"] not in defined_names:
            ref["message"] = f"{item_type.capitalize()} not defined: {ref['name']}"
            undefined.append(ref)

    return undefined


def resolve_include_content(inc, resolve_callback=None):
    """Return `inc`'s XML body with `$PARAM[...]` placeholders substituted."""
    # Import here to avoid circular dependency
    from .expressions import resolve_params_in_text

    if resolve_callback:
        return resolve_callback(inc)

    content = inc.get("content") or "" if hasattr(inc, "get") else getattr(inc, "content", "") or ""
    if not content:
        return ""

    params = getattr(inc, "params", None) or {}
    try:
        resolved_text, _ = resolve_params_in_text(content, params)
        return resolved_text
    except Exception:
        logger.debug("Failed to resolve params for include %s", getattr(inc, "name", "<unknown>"))
        return content


@lru_cache(maxsize=128)
def _get_font_name_pattern(font_name):
    """Cached `<name>font_name</name>` regex used by find_font_line_in_include."""
    return re.compile(r"<name>\s*%s\s*</name>" % re.escape(font_name), re.I)


def find_font_line_in_include(inc, font_name):
    """1-based line of the `<font>` block defining `font_name` inside `inc`'s file.

    Falls back to the include's own line if the font can't be located.
    """
    path = (inc.get("file") or "").strip()
    if not path or not os.path.isfile(path):
        return int(inc.get("line") or 1)

    try:
        with open(path, encoding="utf8", errors="ignore") as f:
            lines = list(f)

        start = max(int(inc.get("line") or 1) - 1, 0)
        pat = _get_font_name_pattern(font_name)  # Use cached pattern

        for i in range(start, len(lines)):
            if pat.search(lines[i]):
                j = i
                while j >= 0 and "<font" not in lines[j].lower():
                    j -= 1
                return (j if j >= 0 else i) + 1
    except Exception:
        pass

    return int(inc.get("line") or 1)


def _is_runtime_placeholder(text):
    """Check if text contains a runtime placeholder that can't be resolved statically."""
    upper = text.upper()
    return "$SKINSHORTCUTS" in upper or "$PROPERTY[" in upper


def find_skinshortcuts_template(addon_path):
    """Path to the SkinShortcuts template (`templates.xml` v3 or `template.xml` v2), or None."""
    shortcuts_dir = os.path.join(addon_path, "shortcuts")
    # v3 first (preferred)
    for filename in ("templates.xml", "template.xml"):
        path = os.path.join(shortcuts_dir, filename)
        if os.path.isfile(path):
            return path
    return None


def find_includes_in_skinshortcuts_template(template_path, known_include_names):
    """Set of skin-include names referenced inside a SkinShortcuts template.

    Scans text bodies plus `content=` / `include=` attributes. References
    that contain `$SKINSHORTCUTS[...]` or `$PROPERTY[...]` are runtime-only
    and skipped.
    """
    from .xml import get_root_from_file

    if not os.path.isfile(template_path):
        return set()

    root = get_root_from_file(template_path)
    if root is None:
        return set()

    referenced = set()

    try:
        # Text content (v2 property values + v3 <include>Name</include>)
        for text in root.xpath(".//text()"):
            text_stripped = text.strip()
            if not text_stripped or _is_runtime_placeholder(text_stripped):
                continue
            for include_name in known_include_names:
                if include_name in text_stripped:
                    referenced.add(include_name)

        # v3: <include content="Name"> and <skinshortcuts include="Name">
        for attr in ("content", "include"):
            for elem in root.xpath(f".//*[@{attr}]"):
                value = elem.get(attr, "")
                if not value or _is_runtime_placeholder(value):
                    continue
                if value in known_include_names:
                    referenced.add(value)

    except Exception:
        logger.exception("Error parsing SkinShortcuts template at %s", template_path)

    return referenced


def find_variables_in_skinshortcuts_template(template_path, known_variable_names):
    """Set of skin-variable names referenced inside a SkinShortcuts template.

    Scans text bodies and attribute values for `$VAR[Name]` / `$ESCVAR[Name]`,
    skipping `$SKINSHORTCUTS[...]` / `$PROPERTY[...]` placeholders.
    """
    from .xml import get_root_from_file

    if not os.path.isfile(template_path):
        return set()

    root = get_root_from_file(template_path)
    if root is None:
        return set()

    referenced = set()
    var_pattern = re.compile(r"\$(?:ESC)?VAR\[(.*?)\]", re.IGNORECASE)

    def _scan(text):
        for match in var_pattern.finditer(text):
            var_name = match.group(1).split(",")[0]
            if _is_runtime_placeholder(var_name):
                continue
            if var_name in known_variable_names:
                referenced.add(var_name)

    try:
        for text in root.xpath(".//text()"):
            text_stripped = text.strip()
            if text_stripped:
                _scan(text_stripped)

        # Attribute values (v3 templates use $VAR[] in attributes like colordiffuse)
        for elem in root.iter():
            for value in elem.attrib.values():
                if "$VAR[" in value.upper() or "$ESCVAR[" in value.upper():
                    _scan(value)

    except Exception:
        logger.exception("Error parsing SkinShortcuts template for variables at %s", template_path)

    return referenced


def find_variable_definitions_in_skinshortcuts_template(template_path):
    """Set of `<variable name="...">` names declared inside a SkinShortcuts template.

    These names must be treated as defined even though the skin's own
    includes don't declare them, since SkinShortcuts emits them into the
    runtime includes file at boot. Names containing runtime placeholders
    are skipped (their real name can't be known statically).
    """
    from .xml import get_root_from_file

    if not os.path.isfile(template_path):
        return set()

    root = get_root_from_file(template_path)
    if root is None:
        return set()

    defined = set()
    try:
        for var_elem in root.iter("variable"):
            name = var_elem.get("name", "").strip()
            if name and not _is_runtime_placeholder(name):
                defined.add(name)
    except Exception:
        logger.exception("Error scanning variable definitions in %s", template_path)

    return defined
