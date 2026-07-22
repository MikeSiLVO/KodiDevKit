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
_LABEL_MACRO = re.compile(r"\$(VAR|ESCVAR|INFO|ESCINFO|ADDON)\[", re.IGNORECASE)

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


def negation_of(condition: str) -> str:
    """The bracketed negation Kodi evaluates alongside `condition`."""
    return f"![{condition}]"


def probe_booleans(condition: str) -> list[str]:
    """The pair to send as `XBMC.GetInfoBooleans` params for `condition`."""
    return [condition, negation_of(condition)]


def read_probe(result, condition: str) -> str:
    """Turn a probe response into one of the STATE_* verdicts.

    Both halves false means Kodi replaced a failed parse with a constant false
    (InfoExpression.cpp:34-42), the only way to see a parse error over JSON-RPC.
    """
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
