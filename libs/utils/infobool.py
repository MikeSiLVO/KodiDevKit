"""Boolean-condition checking, mirroring Kodi's InfoExpression parser.

Kodi returns `false` from `XBMC.GetInfoBooleans` for a condition it cannot parse,
same as for a genuinely false one (InfoExpression.cpp:34-42). `check_syntax`
catches that offline; the negation probe catches it over the wire.
"""

from __future__ import annotations

import re

STATE_TRUE = "true"
STATE_FALSE = "false"
STATE_INVALID = "invalid"
STATE_NEEDS_CONTEXT = "needs_context"
STATE_OFFLINE = "offline"

_OPERATORS = "[]!+|"

# Answered through the JSON-RPC permission layer, not by evaluating the condition
# (XBMCOperations.cpp:60-69), so the direct value and the negation can disagree.
_PERMISSION_GATED = frozenset({
    "system.canshutdown",
    "system.canpowerdown",
    "system.cansuspend",
    "system.canhibernate",
    "system.canreboot",
})

# Substituted just before parsing by CGUIInfoLabel::ReplaceLocalize
# (GUIInfoManager.cpp:11441), so their brackets never reach the parser.
# Case-sensitive: Kodi matches the literal "$LOCALIZE[" (GUIInfoLabel.cpp:196),
# so `$Localize[1]` keeps its bracket and fails the parse.
_PRESUBSTITUTED = re.compile(r"\$(?:LOCALIZE|NUMBER)\[")

# Label-side macros. Nothing expands them in a boolean condition, so their `[`
# lands after operand characters and Kodi rejects the whole expression.
_LABEL_MACRO = re.compile(r"\$(VAR|ESCVAR|INFO|ESCINFO|MAP|ESCMAP|ADDON)\[", re.IGNORECASE)

_PARAM = re.compile(r"\$PARAM\[", re.IGNORECASE)
_EXP = re.compile(r"\$EXP\[\s*([A-Za-z0-9_\-]+)\s*\]", re.IGNORECASE)
_CASED_KEYWORD = re.compile(r"\$(?:localize|number)\[", re.IGNORECASE)


def _drop_presubstituted(text: str) -> tuple[str, bool]:
    """Swap `$LOCALIZE[..]` / `$NUMBER[..]` for a placeholder operand.

    Returns the text and whether a reference was left unclosed. Kodi stops
    replacing at one and leaves it in (GUIInfoLabel.cpp:214-218), so its `[`
    still reaches the parser.
    """
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
    """Why Kodi cannot parse `condition`, or None when it parses.

    Ports the syntax checks in InfoExpression::Parse (InfoExpression.cpp:206-303).
    Operand names are not checked: Kodi accepts any name and evaluates an unknown
    one as false (GUIInfoManager.cpp:11444), so a bad name is not a parse error.
    """
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
    """The `(state, reason)` blocking `condition`, or None when it can be sent to Kodi.

    Expects `$EXP` already flattened: a leftover reference means the skin never
    defined it, which Kodi erases to nothing at load (GUIIncludes.cpp:663).
    """
    if _PARAM.search(condition):
        return STATE_NEEDS_CONTEXT, "unresolved $PARAM"

    unknown = _EXP.search(condition)
    if unknown:
        return STATE_INVALID, f"unknown expression {unknown.group(1)}"

    macro = _LABEL_MACRO.search(condition)
    if macro:
        return STATE_INVALID, f"${macro.group(1).upper()}[] is not valid inside a boolean condition"

    reason = check_syntax(condition)
    if reason:
        return STATE_INVALID, reason
    return None


def static_value(condition: str) -> bool | None:
    """True or False when the condition reads the same in any state, else None."""
    text, unclosed = _drop_presubstituted(condition)
    if unclosed or check_syntax(condition):
        return None
    tokens = [t.strip() for t in re.split(r"([\[\]!+|])", text) if t.strip()]
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
        return _LITERALS.get(token.lower())

    return any_of()


_LITERALS = {"false": False, "no": False, "true": True, "yes": True}


def info_name_sets(raw: dict) -> dict:
    """An infonames.json table with its name lists as sets, the shape `is_known_info` reads."""
    return {**raw, "categories": {c: set(v) for c, v in raw["categories"].items()},
            "listitem_aliases": set(raw["listitem_aliases"]), "platforms": set(raw["platforms"]),
            "players": {p: set(v) for p, v in raw["players"].items()}}


def split_info(operand: str) -> list[tuple[str, str]]:
    """Cut an operand into `(name, params)` parts at top-level dots (GUIInfoManager.cpp:10983)."""
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
    """Trimmed operands of a condition, cut at every operator as InfoExpression::Parse does."""
    return [op.strip() for op in re.split(r"[\[\]!+|]", condition) if op.strip()]


def is_known_info(operand: str, names: dict) -> bool:
    """Whether Kodi gives `operand` an info id, params unchecked (GUIInfoManager.cpp:11069)."""
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


def unknown_infos(condition: str, names: dict) -> list[str]:
    """Operands Kodi registers as info 0, which always read false; macro ones are left alone."""
    while True:
        blanked = _MACRO.sub("$", condition)
        if blanked == condition:
            break
        condition = blanked
    return [op for op in operands(condition) if "$" not in op and not is_known_info(op, names)]


def negation_of(condition: str) -> str:
    """The bracketed negation Kodi evaluates alongside `condition`."""
    return f"![{condition}]"


def probe_booleans(condition: str) -> list[str]:
    """The pair to send as `XBMC.GetInfoBooleans` params for `condition`."""
    return [condition, negation_of(condition)]


def read_probe(result, condition: str) -> str:
    """Turn a probe response into one of the STATE_* verdicts."""
    # Both halves false means Kodi swapped a failed parse for a constant false
    # (InfoExpression.cpp:34-42), the only way to see a parse error over JSON-RPC.
    values = (result or {}).get("result")
    if not isinstance(values, dict):
        return STATE_OFFLINE

    direct = values.get(condition)
    if direct is None:
        return STATE_OFFLINE

    # The permission-gated five can disagree between the direct key and the
    # negation, so trust the direct value.
    if condition.strip().lower() in _PERMISSION_GATED:
        return STATE_TRUE if direct else STATE_FALSE

    negated = values.get(negation_of(condition))
    if negated is None:
        return STATE_OFFLINE
    if direct:
        return STATE_TRUE
    return STATE_FALSE if negated else STATE_INVALID
