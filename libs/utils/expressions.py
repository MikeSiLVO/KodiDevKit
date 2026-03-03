"""
Dynamic expression detection and parameter resolution for Kodi skinning.
"""

from __future__ import annotations

import logging
import re
from typing import Optional
from xml.sax.saxutils import escape as xml_escape

logger = logging.getLogger("KodiDevKit.utils.expressions")
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.propagate = True

_PARAM_PATTERN = re.compile(r"\$PARAM\[\s*(?P<name>[A-Za-z0-9_\-]+)\s*\]", re.IGNORECASE)
_DEFAULT_DYNAMIC_PREFIXES = tuple(
    p.casefold()
    for p in (
        "$param[",
        "$var[",
        "$info[",
        "$addon[",
        "$escvar[",
        "$escinfo[",
    )
)


def is_number(text: str) -> bool:
    """Check if text is a valid finite number."""
    try:
        value = float(text)
        return value not in (float('inf'), float('-inf')) and value == value
    except ValueError:
        return False


def extract_number_value(text: str) -> str | None:
    """
    Extract numeric value from $NUMBER[...] expressions.

    Args:
        text: String that may contain a $NUMBER[value] expression

    Returns:
        The extracted numeric string if valid $NUMBER[] expression, None otherwise

    Examples:
        extract_number_value("$NUMBER[25]") -> "25"
        extract_number_value("$NUMBER[100]") -> "100"
        extract_number_value("25") -> None (not a $NUMBER expression)
        extract_number_value("$NUMBER[abc]") -> None (invalid number)
    """
    if not isinstance(text, str):
        return None

    match = re.match(r'^\$NUMBER\[([^\]]+)\]$', text.strip(), re.IGNORECASE)
    if not match:
        return None

    value = match.group(1).strip()

    if is_number(value):
        return value

    return None


def extract_variable_name(text: str) -> str | None:
    """
    Extract variable name from $VAR[...] or $ESCVAR[...] expressions.

    Args:
        text: String that may contain a $VAR or $ESCVAR expression

    Returns:
        The variable name if valid expression, None otherwise

    Examples:
        extract_variable_name("$VAR[HighlightColor]") -> "HighlightColor"
        extract_variable_name("$ESCVAR[CustomVar]") -> "CustomVar"
        extract_variable_name("$VAR[MyVar,param]") -> "MyVar"
        extract_variable_name("red") -> None (not a variable expression)
    """
    if not isinstance(text, str):
        return None

    match = re.match(r'^\$(ESC)?VAR\[([^\]]+)\]', text.strip(), re.IGNORECASE)
    if not match:
        return None

    var_name = match.group(2).strip()

    if ',' in var_name:
        var_name = var_name.split(',')[0].strip()

    return var_name if var_name else None


def resolve_params_in_text(text: str, params: Optional[dict[str, str]] = None) -> tuple[str, str]:
    """
    Replace $PARAM[name] in *text* using values from *params* dict.
    Missing keys are left unchanged.
    Parameter values are XML-escaped to preserve entities like & < >.

    Returns:
        tuple: (resolved_text, resolution_status) where resolution_status is one of:
            - "NO_PARAMS": No $PARAM references found
            - "ALL_RESOLVED": All $PARAM references were resolved
            - "PARTIAL_RESOLVED": Some $PARAM references were resolved, some not
            - "SINGLE_UNDEFINED": Text contains exactly one $PARAM that was undefined
    """
    if not text or not isinstance(text, str):
        return text, "NO_PARAMS"
    if not params:
        if _PARAM_PATTERN.search(text):
            matches = _PARAM_PATTERN.findall(text)
            if len(matches) == 1:
                return text, "SINGLE_UNDEFINED"
            return text, "PARTIAL_RESOLVED"
        return text, "NO_PARAMS"

    total_params = 0
    undefined_params = 0

    def _sub(m):
        nonlocal total_params, undefined_params
        total_params += 1
        key = m.group("name")
        val = params.get(key)
        if val is not None:
            return xml_escape(val)
        undefined_params += 1
        return m.group(0)

    result = _PARAM_PATTERN.sub(_sub, text)

    if total_params == 0:
        status = "NO_PARAMS"
    elif undefined_params == 0:
        status = "ALL_RESOLVED"
    elif total_params == 1 and undefined_params == 1:
        status = "SINGLE_UNDEFINED"
    else:
        status = "PARTIAL_RESOLVED"

    return result, status


def is_dynamic_expression(text: str, *, prefixes: Optional[tuple[str, ...]] = None) -> bool:
    """
    Return True when *text* starts with a Kodi runtime expression such as
    $PARAM[], $VAR[], $INFO[], etc. Case-insensitive. Leading whitespace ignored.
    """
    if not isinstance(text, str):
        return False
    candidate = text.strip()
    if not candidate:
        return False
    lowered = candidate.casefold()
    if prefixes:
        checks = tuple(p.casefold() for p in prefixes)
    else:
        checks = _DEFAULT_DYNAMIC_PREFIXES
    return any(lowered.startswith(pref) for pref in checks)


def starts_with_param_reference(text: str) -> bool:
    """Check if text starts with a $PARAM[...] expression."""
    return is_dynamic_expression(text, prefixes=("$param[",))


def contains_dynamic_expression(text: str) -> bool:
    """
    Return True when *text* contains a Kodi runtime expression anywhere in the string.

    This differs from is_dynamic_expression() which only checks if the text STARTS with
    a dynamic expression. This function checks if ANY dynamic expression appears in the text,
    such as "800$PARAM[id]", "prefix$VAR[MyVar]suffix", etc.

    Used for validation to skip strict type checking on values that contain dynamic content
    that will be resolved at runtime (see Kodi GUIIncludes.cpp resolution process).

    Examples:
        contains_dynamic_expression("$VAR[Foo]") -> True
        contains_dynamic_expression("800$PARAM[id]") -> True
        contains_dynamic_expression("prefix$INFO[Label]suffix") -> True
        contains_dynamic_expression("normalvalue") -> False
    """
    if not isinstance(text, str):
        return False
    if not text:
        return False

    lowered = text.casefold()
    return any(pref in lowered for pref in _DEFAULT_DYNAMIC_PREFIXES)


def get_param_names_in_context(include_node, xpath_pattern: str) -> set[str]:
    """
    Extract param names used in specific XML contexts within an include definition.

    This helps distinguish between params used for different purposes:
    - Params used in <include> tags are include references
    - Params used in id attributes are control IDs
    - Params used elsewhere could be labels, paths, colors, etc.

    Args:
        include_node: lxml Element node of an include definition
        xpath_pattern: XPath pattern to match specific usages, e.g.:
            - ".//include/text()" - matches <include>$PARAM[foo]</include>
            - ".//@id" - matches any id="$PARAM[foo]" attribute
            - ".//label/text()" - matches <label>$PARAM[foo]</label>

    Returns:
        Set of param names used in the matched contexts

    Examples:
        >>> get_param_names_in_context(node, ".//include/text()")
        {'include', 'content'}

        >>> get_param_names_in_context(node, ".//@id")
        {'id', 'panel_id', 'button_id'}
    """
    if include_node is None:
        return set()

    param_names = set()

    try:
        matches = include_node.xpath(xpath_pattern)

        for match in matches:
            if not match or not isinstance(match, str):
                continue

            for param_match in _PARAM_PATTERN.finditer(match):
                param_name = param_match.group("name")
                if param_name:
                    param_names.add(param_name)

    except Exception:
        logger.exception("Error extracting param names with pattern %s", xpath_pattern)

    return param_names
