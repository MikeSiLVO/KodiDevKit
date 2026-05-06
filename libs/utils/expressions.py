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


def split_top_level_commas(text: str) -> list[str]:
    """
    Split *text* on commas that appear outside any `(...)` or `[...]` group.

    Kodi expressions routinely embed commas inside nested calls and macros
    (``String.IsEqual(Label,$LOCALIZE[40211])``, ``$INFO[Label, , - ]``); a
    naive ``str.split(',')`` corrupts them. Empty pieces are dropped so
    callers can pass the result straight to a JSON-RPC ``params`` list.
    """
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in text:
        if ch in "([":
            depth += 1
            buf.append(ch)
        elif ch in ")]":
            if depth > 0:
                depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf).strip())
    return [p for p in parts if p]


_KEYWORD_MACRO_RE = re.compile(
    r"\$(?:LOCALIZE|NUMBER|INFO|ESCINFO|VAR|ESCVAR|EXP|ADDON|PARAM)\[",
    re.IGNORECASE,
)


def _kodi_macro_mask(text: str) -> set:
    """Indices that lie inside a ``$KEYWORD[...]`` macro.

    Kodi's ``Register()`` calls ``ReplaceLocalize`` before parsing booleans
    (GUIInfoManager.cpp:11441 → GUIInfoLabel.cpp:276-282), so ``$LOCALIZE[N]``
    and ``$NUMBER[N]`` are gone by the time ``[`` and ``]`` are interpreted as
    operators. We extend the same masking to ``$INFO``, ``$VAR``, etc. so a
    hover on those forms doesn't get fragmented at their inner brackets.
    """
    masked: set = set()
    pos = 0
    while pos < len(text):
        m = _KEYWORD_MACRO_RE.search(text, pos)
        if not m:
            break
        bracket_open = m.end() - 1
        depth = 1
        j = bracket_open + 1
        while j < len(text) and depth > 0:
            if text[j] == '[':
                depth += 1
            elif text[j] == ']':
                depth -= 1
            j += 1
        end = j if depth == 0 else len(text)
        masked.update(range(m.start(), end))
        pos = end
    return masked


def extract_expression_at_offset(line_text: str, cursor_offset: int) -> str:
    """Return the smallest Kodi boolean sub-expression enclosing *cursor_offset*.

    Implements the grammar from ``InfoExpression.cpp`` — operators are exactly
    ``[ ] ! + |`` (lines 125-139); everything else (including ``( ) , . $``) is
    operand. ``$LOCALIZE[…]`` / ``$NUMBER[…]`` are masked because Kodi resolves
    them before parsing. Parens are tracked as depth so a click anywhere inside
    ``Function(args)`` returns the whole call rather than splitting at an inner
    operator. ``!`` is a unary prefix and stays attached to the operand it
    precedes — without that, the boolean we send to Kodi would have the
    OPPOSITE truth value.
    """
    if not line_text:
        return ""
    n = len(line_text)
    cursor_offset = max(0, min(cursor_offset, n))

    xml_delims = '"<>\n\r'
    enc_left = cursor_offset
    while enc_left > 0 and line_text[enc_left - 1] not in xml_delims:
        enc_left -= 1
    enc_right = cursor_offset
    while enc_right < n and line_text[enc_right] not in xml_delims:
        enc_right += 1

    enc = line_text[enc_left:enc_right]
    cur = cursor_offset - enc_left
    masked = _kodi_macro_mask(enc)

    depths = []
    d = 0
    for i, ch in enumerate(enc):
        depths.append(d)
        if i in masked:
            continue
        if ch == '(':
            d += 1
        elif ch == ')' and d > 0:
            d -= 1

    boundary = set('+|[]')

    def active(i: int) -> bool:
        return i not in masked and depths[i] == 0

    sub_left = 0
    leftmost_bang = None
    for i in range(cur - 1, -1, -1):
        if not active(i):
            continue
        ch = enc[i]
        if ch in boundary:
            sub_left = leftmost_bang if leftmost_bang is not None else i + 1
            break
        if ch == '!':
            leftmost_bang = i
    else:
        if leftmost_bang is not None:
            sub_left = leftmost_bang

    sub_right = len(enc)
    for i in range(cur, len(enc)):
        if active(i) and enc[i] in boundary:
            sub_right = i
            break

    return enc[sub_left:sub_right].strip()


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
