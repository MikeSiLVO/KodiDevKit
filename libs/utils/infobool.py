"""Boolean-condition checks, offline against Kodi's condition grammar and live over JSON-RPC."""

from __future__ import annotations

import itertools
import re

from .expressions import expression_references, split_top_level_commas

STATE_TRUE = "true"
STATE_FALSE = "false"
STATE_INVALID = "invalid"
STATE_NEEDS_CONTEXT = "needs_context"
STATE_OFFLINE = "offline"

_OPERATORS = "[]!+|"

# answered by the JSON-RPC permission layer, not the condition
_PERMISSION_GATED = frozenset({
    "system.canshutdown",
    "system.canpowerdown",
    "system.cansuspend",
    "system.canhibernate",
    "system.canreboot",
})

# substituted before parsing, case-sensitively; `$Localize[` stays
_PRESUBSTITUTED = re.compile(r"\$(?:LOCALIZE|NUMBER)\[")

# label macros nothing expands in a condition; Kodi rejects the whole expression
_LABEL_MACRO = re.compile(r"\$(VAR|ESCVAR|INFO|ESCINFO|MAP|ESCMAP|ADDON)\[", re.IGNORECASE)

_PARAM = re.compile(r"\$PARAM\[", re.IGNORECASE)
_CASED_KEYWORD = re.compile(r"\$(?:localize|number)\[", re.IGNORECASE)


def _drop_presubstituted(text: str) -> tuple[str, bool]:
    """Swap `$LOCALIZE[..]` / `$NUMBER[..]` for an operand; also whether one is left unclosed."""
    out = []
    pos = 0
    unclosed = False
    while True:
        match = _PRESUBSTITUTED.search(text, pos)
        if not match:
            break
        depth = 1
        i = match.end()
        while i < len(text) and depth:
            if text[i] == "[":
                depth += 1
            elif text[i] == "]":
                depth -= 1
            i += 1
        if depth:
            unclosed = True
            break
        out.append(text[pos:match.start()])
        out.append("_")
        pos = i
    out.append(text[pos:])
    return "".join(out), unclosed


def _has_miscased_keyword(text: str) -> bool:
    """True when `$LOCALIZE[` / `$NUMBER[` appears in a case Kodi won't match."""
    return any(m.group(0) != m.group(0).upper() for m in _CASED_KEYWORD.finditer(text))


def check_syntax(condition: str) -> str | None:
    """Why Kodi cannot parse the condition, or None; names are unchecked."""
    text, unclosed = _drop_presubstituted(condition)
    if unclosed:
        return "missing ']' in $LOCALIZE / $NUMBER"
    text = text.strip()
    if not text:
        return "empty condition"

    after_binary = True
    brackets = 0
    i = 0
    n = len(text)
    while i < n:
        char = text[i]
        i += 1
        if char not in _OPERATORS:
            after_binary = False
            continue

        if (not after_binary and char in "![") or (after_binary and char in "]+|"):
            reason = f"misplaced '{char}'"
            if char == "[" and _has_miscased_keyword(condition):
                reason += " ($LOCALIZE / $NUMBER must be uppercase)"
            return reason
        if char == "[":
            brackets += 1
        elif char == "]":
            if brackets == 0:
                return "unmatched ']'"
            brackets -= 1
        if char in "+|":
            after_binary = True
        while i < n and text[i].isspace():
            i += 1

    if brackets:
        return "unmatched '['"
    if after_binary:
        return "missing operand"
    return None


def check_condition(condition: str) -> tuple[str, str] | None:
    """The (state, reason) blocking the condition, or None; expects `$EXP` already flattened."""
    if _PARAM.search(condition):
        return STATE_NEEDS_CONTEXT, "unresolved $PARAM"

    unknown = next(expression_references(condition), None)
    if unknown:
        return STATE_INVALID, f"unknown expression {unknown[2]}"

    macro = _LABEL_MACRO.search(condition)
    if macro:
        return STATE_INVALID, f"${macro.group(1).upper()}[] is not valid inside a boolean condition"

    reason = check_syntax(condition)
    if reason:
        return STATE_INVALID, reason
    return None


def static_value(condition: str) -> bool | None:
    """True or False when the condition reads the same in any state, else None."""
    tokens = _tokens(condition)
    return None if tokens is None else _value(tokens, {})


def condition_states(conditions: list[str], limit: int = 10) -> list[dict[str, bool]] | None:
    """Each condition's value per operand state; None if one won't parse or there are too many."""
    parsed = {}
    for condition in set(conditions):
        tokens = _tokens(condition)
        if tokens is None:
            return None
        parsed[condition] = tokens
    names = sorted({t for tokens in parsed.values() for t in tokens
                    if t not in _OPERATORS and t.lower() not in _LITERALS})
    if len(names) > limit:
        return None
    states = []
    for combo in itertools.product((False, True), repeat=len(names)):
        values = dict(zip(names, combo))
        state = {condition: _value(tokens, values) for condition, tokens in parsed.items()}
        if None in state.values():
            return None
        states.append(state)
    return states


def _tokens(condition: str) -> list[str] | None:
    """The condition cut into operands and operators, or None when Kodi cannot parse it."""
    text, unclosed = _drop_presubstituted(condition)
    if unclosed or check_syntax(condition):
        return None
    return [t.strip() for t in re.split(r"([\[\]!+|])", text) if t.strip()]


def _value(tokens: list[str], values: dict[str, bool]) -> bool | None:
    """True or False for the parsed condition with the operands given, None where it cannot tell."""
    pos = 0

    def any_of():
        nonlocal pos
        values = [all_of()]
        while pos < len(tokens) and tokens[pos] == "|":
            pos += 1
            values.append(all_of())
        return True if True in values else False if all(v is False for v in values) else None

    def all_of():
        nonlocal pos
        values = [single()]
        while pos < len(tokens) and tokens[pos] == "+":
            pos += 1
            values.append(single())
        return False if False in values else True if all(values) else None

    def single():
        nonlocal pos
        token = tokens[pos]
        pos += 1
        if token == "!":
            value = single()
            return None if value is None else not value
        if token == "[":
            value = any_of()
            pos += 1
            return value
        return _LITERALS.get(token.lower(), values.get(token))

    return any_of()


_LITERALS = {"false": False, "no": False, "true": True, "yes": True}


def info_name_sets(raw: dict) -> dict:
    """An infonames.json table with its name lists as sets, the shape `is_known_info` reads."""
    return {**raw, "categories": {c: set(v) for c, v in raw["categories"].items()},
            "listitem_aliases": set(raw["listitem_aliases"]), "platforms": set(raw["platforms"]),
            "players": {p: set(v) for p, v in raw["players"].items()}}


def split_info(operand: str) -> list[tuple[str, str]]:
    """Split an operand into lowercased `(name, params)` parts at top-level dots."""
    parts = []
    name, params, depth = "", "", 0
    for char in operand:
        if char == "(":
            depth += 1
            if depth == 1:
                continue
        elif char == ")" and depth:
            depth -= 1
            if not depth:
                continue
        elif char == "." and not depth:
            if name:
                parts.append((name.lower(), params))
            name, params = "", ""
            continue
        if depth:
            params += char
        else:
            name += char
    if name:
        parts.append((name.lower(), params))
    return parts


def operands(condition: str) -> list[str]:
    """Trimmed operands of a condition, cut at every operator."""
    return [op.strip() for op in re.split(r"[\[\]!+|]", condition) if op.strip()]


def is_known_info(operand: str, names: dict) -> bool:
    """Whether Kodi gives the operand an info id, params unchecked."""
    parts = [name for name, _ in split_info(operand)]
    if len(parts) == 1:
        return parts[0] in ("true", "false", "yes", "no")
    categories = names["categories"]
    if len(parts) == 2:
        category = "listitem" if parts[0] in names["listitem_aliases"] else parts[0]
        return parts[1] in categories.get(category, ())
    if len(parts) in (3, 4):
        first, second, third = parts[:3]
        if first == "system" and second == "platform":
            return third in names["platforms"]
        if first in names["players"] and second in ("position", "offset"):
            return third in names["players"][first]
        if first == "container" and (second == "listitem" or second in names["listitem_aliases"]):
            return third in categories["listitem"]
        if first == "control":
            return second in categories["control"]
    return False


_MACRO = re.compile(r"\$[A-Za-z]+\[[^\[\]]*\]")


def _blank_macros(condition: str) -> str:
    """Blank each macro, nested ones included, down to a bare `$`."""
    while True:
        blanked = _MACRO.sub("$", condition)
        if blanked == condition:
            return condition
        condition = blanked


def unknown_infos(condition: str, names: dict) -> list[str]:
    """Operands Kodi registers as info 0, which always read false; macro ones are left alone."""
    return [op for op in operands(_blank_macros(condition)) if "$" not in op and not is_known_info(op, names)]


def unknown_info_arguments(condition: str, names: dict) -> list[tuple[str, str]]:
    """Test and argument per String or Integer argument Kodi reads as an info it does not know."""
    found = []
    for op in operands(_blank_macros(condition)):
        parts = split_info(op)
        if len(parts) != 2 or parts[1][0] not in names["categories"].get(parts[0][0], ()):
            continue
        (category, _), (test, params) = parts
        args = [a[1:-1] if len(a) > 1 and a[0] == a[-1] == '"' else a for a in split_top_level_commas(params)]
        if category == "string":
            read = args[:1] if test == "isempty" or len(args) == 2 else []
        elif category == "integer" and test != "valueof":
            # a leading number is the value itself, anything else names an info
            read = [a for a in args[:2] if not re.match(r"-?\d", a)]
        else:
            continue
        found += [(op.split("(", 1)[0].strip(), a) for a in read
                  if a and "$" not in a and not is_known_info(a, names)]
    return found


def negation_of(condition: str) -> str:
    """The bracketed negation Kodi evaluates alongside `condition`."""
    return f"![{condition}]"


def probe_booleans(condition: str) -> list[str]:
    """The pair to send as `XBMC.GetInfoBooleans` params for `condition`."""
    return [condition, negation_of(condition)]


def read_probe(result, condition: str) -> str:
    """Turn a probe response into one of the STATE_* verdicts."""
    # both halves false: Kodi replaced a parse failure with false
    values = (result or {}).get("result")
    if not isinstance(values, dict):
        return STATE_OFFLINE

    direct = values.get(condition)
    if direct is None:
        return STATE_OFFLINE

    # these can disagree with their negation; the direct value is the one to trust
    if condition.strip().lower() in _PERMISSION_GATED:
        return STATE_TRUE if direct else STATE_FALSE

    negated = values.get(negation_of(condition))
    if negated is None:
        return STATE_OFFLINE
    if direct:
        return STATE_TRUE
    return STATE_FALSE if negated else STATE_INVALID
