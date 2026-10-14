"""Dynamic expression detection and parameter resolution for Kodi skinning."""

from __future__ import annotations

import logging
import re
from typing import Optional
from xml.sax.saxutils import escape as xml_escape

logger = logging.getLogger(__name__)
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
        "$map[",
        "$escmap[",
    )
)
# the ones a control reads at runtime; $PARAM is substituted into every tag at include load
RUNTIME_PREFIXES = tuple(p for p in _DEFAULT_DYNAMIC_PREFIXES if p != "$param[")


def is_number(text: str) -> bool:
    """True when the text parses as a finite number."""
    try:
        value = float(text)
        return value not in (float('inf'), float('-inf')) and value == value
    except ValueError:
        return False


def extract_number_value(text: str) -> str | None:
    """Numeric value inside `$NUMBER[...]`, or None when `text` is not one."""
    if not isinstance(text, str):
        return None

    match = re.match(r'^\$NUMBER\[([^\]]+)\]$', text.strip(), re.IGNORECASE)
    if not match:
        return None

    value = match.group(1).strip()

    if is_number(value):
        return value

    return None


_LABEL_BLOCKS = re.compile(r"\$(?:LOCALIZE|NUMBER|ADDON|FEATURE|ESCINFO|INFO|ESCVAR|VAR|ESCMAP|MAP)\[")


def unclosed_label_block(text: str):
    """First $INFO[, $VAR[, $LOCALIZE[ or kin whose bracket never closes, or None."""
    for match in _LABEL_BLOCKS.finditer(text):
        depth = 0
        for char in text[match.end() - 1:]:
            depth += (char == "[") - (char == "]")
            if depth == 0:
                break
        else:
            return match.group(0)
    return None


def bracket_body(text: str) -> str:
    """Text inside the first [...], nested brackets included; empty when it never closes."""
    start = text.find('[')
    if start == -1:
        return ''
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '[':
            depth += 1
        elif text[i] == ']':
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
    return ''


def extract_variable_name(text: str) -> str | None:
    """Variable name inside `$VAR[...]` or `$ESCVAR[...]`, or None when `text` is neither."""
    if not isinstance(text, str):
        return None

    text = text.strip()
    if not re.match(r'^\$(ESC)?VAR\[', text, re.IGNORECASE):
        return None

    var_name = bracket_body(text).split(',')[0].strip()
    return var_name if var_name else None


def resolve_params_in_text(text: str, params: Optional[dict[str, str]] = None, *,
                           escape: bool = False) -> tuple[str, str]:
    """Substitute $PARAM names from the params, with a status saying how much resolved."""
    # escape only text that is re-parsed as XML; unknown names stay as written
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
            return xml_escape(val) if escape else val
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
    """True when the text opens with a Kodi runtime expression such as $VAR or $INFO."""
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
    """True when the text opens with a $PARAM reference."""
    return is_dynamic_expression(text, prefixes=("$param[",))


def contains_dynamic_expression(text: str, *, prefixes: Optional[tuple[str, ...]] = None) -> bool:
    """True when a runtime expression appears anywhere, not only at the start."""
    if not isinstance(text, str):
        return False
    if not text:
        return False

    lowered = text.casefold()
    return any(pref in lowered for pref in (prefixes or _DEFAULT_DYNAMIC_PREFIXES))


def split_top_level_commas(text: str) -> list[str]:
    """Split on the commas outside any (...) or [...], dropping empty pieces."""
    # Kodi nests commas inside calls and macros, so a plain split corrupts them
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


def expression_references(text: str):
    """Yield (start, end, name) per upper-case `$EXP[` reference, stopping at an unclosed one."""
    pos = 0
    while (start := text.find("$EXP[", pos)) != -1:
        name = bracket_body(text[start + 4:])
        end = start + len(name) + 6
        if text[end - 1:end] != "]":
            return
        yield start, end, name
        pos = end


def expression_names(text: str) -> list[str]:
    """Names of the `$EXP` references written in the text, nested ones not followed."""
    return [name for _, _, name in expression_references(text or "")]


def flatten_expressions(text: str, expression_map: dict[str, str],
                        _resolved: Optional[list[str]] = None) -> tuple[str, set[str]]:
    """Flatten $EXP references, keeping unknown names for the caller."""
    if not text:
        return text, set()

    resolved = _resolved or []
    unknown: set[str] = set()
    out = []
    pos = 0
    for start, end, name in expression_references(text):
        out.append(text[pos:start])
        pos = end
        if name in resolved:
            logger.error('Skin has a circular expression "%s": %s', resolved[-1], text)
        elif name not in expression_map:
            unknown.add(name)
            out.append(text[start:end])
        else:
            body, nested_unknown = flatten_expressions(
                expression_map[name], expression_map, resolved + [name]
            )
            unknown.update(nested_unknown)
            out.append(body)
    out.append(text[pos:])
    return "".join(out), unknown


_KEYWORD_MACRO_RE = re.compile(
    r"\$(?:LOCALIZE|NUMBER|INFO|ESCINFO|VAR|ESCVAR|MAP|ESCMAP|EXP|ADDON|PARAM)\[",
    re.IGNORECASE,
)


def _kodi_macro_mask(text: str) -> set:
    """Indices that lie inside a $KEYWORD[...] macro."""
    # Kodi replaces these before the boolean parses, so their brackets are never operators
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
    """Smallest Kodi boolean sub-expression around the offset, its leading ! included."""
    # operators are [ ] ! + |; parens hold a call together
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
    """Param names used where the xpath matches, which is what tells a control id from a label."""
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
