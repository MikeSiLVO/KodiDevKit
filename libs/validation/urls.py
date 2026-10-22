"""Checks runtime values in xsp filters and plugin URLs for the URL encoding they need."""

from __future__ import annotations

import re

from ..utils.expressions import bracket_body, builtin_calls
from ..utils.xml import get_root_from_file

_VALUE_KEY = re.compile(r'(?:%22|")value(?:%22|")\s*(?:%3A|:)', re.IGNORECASE)
_VALUE_END = re.compile(r'%5D|%7D|[\]}]', re.IGNORECASE)
_EXPRESSION = re.compile(r'\$(ESC)?(INFO|VAR)\[')
_PLUGIN_QUERY = re.compile(r'plugin://[^\s"\'?]*\?', re.IGNORECASE)
_URL_END = re.compile(r'[\s"\',)]')
# an '&' that starts no key=value pair, or a '|', inside a value
_DATA_SEPARATOR = re.compile(r'&(?![\w.-]+=)|\|')
# the key of the last pair a text opens, as in ?key= or &key=
_PAIR_KEY = re.compile(r'[&?]?([\w.-]*)=[^&?=]*$')
_BETWEEN_PAIRS = re.compile(r'[&?][^=]*$')
# a plugin reads these only to change the URL, never as data
_TOKEN_KEYS = {"reload"}
_ENCODER = re.compile(r'get_encoded_string\b.*?\bwindow_prop=([^&"\s,)]+)', re.IGNORECASE)
_PROPERTY = re.compile(r'window(?:\([^)]*\))?\.property\((.+)\)$', re.IGNORECASE)
_SKIN_STRING = re.compile(r'skin\.string\((.+)\)$', re.IGNORECASE)
_ITEM_PROPERTY = re.compile(r'container\((\d+)\)\.listitem\w*(?:\([^)]*\))?\.property\((.+)\)$', re.IGNORECASE)
# an edit control's text as typed; no other control answers Index(1)
_TYPED = re.compile(r'control\.getlabel\(\s*\d+\s*\)\.index\(\s*1\s*\)$', re.IGNORECASE)
# characters a URL query or a JSON string cannot carry unencoded
_UNSAFE = set('&|+"\\')

_PLAIN_INFOS = frozenset({
    "content", "currentitem", "date", "dateadded", "dbid", "dbtype", "duration", "episode", "imdbnumber",
    "lastplayed", "numitems", "percentplayed", "playcount", "position", "premiered", "rating",
    "sortmethod", "sortorder",
    "season", "setid", "time", "top250", "tvshowdbid", "uniqueid", "userrating", "year",
})

RAW, TYPED, UNTRACED, SAFE = "raw", "typed", "untraced", "safe"
_RANK = {SAFE: 0, UNTRACED: 1, TYPED: 2, RAW: 3}


def _plain(name):
    """True when an info or property name holds a number, a date or a fixed word."""
    parts = [part for part in name.lower().split("(", 1)[0].split(".") if not part.isdigit()]
    last = parts[-1] if parts else ""
    return last in _PLAIN_INFOS or last.endswith(("_id", "dbid"))


def _url_end(text, pos):
    """Index where the URL starting before the position ends: a space, quote, comma or ')'."""
    found = _URL_END.search(text, pos)
    return found.start() if found else len(text)


def _worst(kinds):
    """The kind that matters most among those given; safe when there are none."""
    return max(kinds, key=_RANK.__getitem__, default=SAFE)


def value_sources(paths):
    """Each value the skin stores per property, skin string and static item property, by name."""
    sources = {}
    for path in paths:
        root = get_root_from_file(path)
        if root is None:
            continue
        for element in root.iter():
            if not isinstance(element.tag, str):
                continue
            if element.tag == "property" and element.get("name") and element.getparent().tag == "item":
                control = next(element.iterancestors("control"), None)
                if control is not None and (control.get("id") or "").isdigit():
                    key = f"item:{control.get('id')}:{element.get('name').casefold()}"
                    sources.setdefault(key, []).append(element.text or "")
            for text in [element.text or ""] + list(element.attrib.values()):
                for name, args in builtin_calls(text, ("SetProperty", "Skin.SetString")):
                    if not args or "$" in args[0]:
                        continue
                    if name.lower() == "setproperty":
                        key, value = "property:" + args[0].casefold(), args[1] if len(args) > 1 else ""
                    else:
                        key, value = "skin:" + args[0].casefold(), args[1] if len(args) > 1 else "keyboard"
                    sources.setdefault(key, []).append(value)
                for found in _ENCODER.finditer(text):
                    sources.setdefault("property:" + found.group(1).casefold(), []).append("encoded")
    return sources


class UrlValues:
    """Classifier of the runtime values a skin writes into xsp filters and plugin URLs."""

    def __init__(self, sources, variables):
        self.sources = sources
        self.variables = variables
        self._kinds = {}

    def xsp_faults(self, text):
        """Yield (expression, keyword, kind) per unsafe value in a filter's value lists."""
        for key in _VALUE_KEY.finditer(text):
            pos = key.end()
            while True:
                found = _EXPRESSION.search(text, pos)
                end = _VALUE_END.search(text, pos)
                if not found or (end and end.start() < found.start()):
                    break
                body = bracket_body(text[found.end() - 1:])
                if not body:
                    break
                pos = found.end() + len(body) + 1
                kind = self._expression_kind(found.group(2), body, frozenset())
                if kind != SAFE:
                    yield found.group(0) + body + "]", found.group(0)[:-1], kind

    def plugin_faults(self, text):
        """Yield (expression, keyword, kind, variable) per unsafe plugin query value."""
        for query in _PLUGIN_QUERY.finditer(text):
            # the encoder's own call takes the raw value it encodes
            if "get_encoded_string" not in text[query.start():_url_end(text, query.end())]:
                yield from self._query_faults(text, query.end(), None, None, frozenset())

    def _query_faults(self, text, pos, key, variable, seen):
        """Faults of query text from the position on: values after '=', pairs a $VAR holds."""
        while True:
            found = _EXPRESSION.search(text, pos)
            if not found or _URL_END.search(text, pos, found.start()):
                return
            body = bracket_body(text[found.end() - 1:])
            if not body:
                return
            # an $INFO prefix such as ,&query=, opens its own pair
            prefix = body.split(",")[1] if found.group(2) == "INFO" and "," in body else ""
            for span in (text[pos:found.start()], prefix):
                pair = _PAIR_KEY.search(span)
                if pair:
                    key = pair.group(1)
                elif _BETWEEN_PAIRS.search(span):
                    key = None
            pos = found.end() + len(body) + 1
            expression, keyword, name = found.group(0) + body + "]", found.group(0)[:-1], body.strip()
            if found.group(2) == "VAR" and name in self.variables and name not in seen:
                for value in self.variables[name]:
                    if key and _DATA_SEPARATOR.search(value):
                        yield expression, keyword, RAW, variable
                    yield from self._query_faults(value, 0, key, variable or expression, seen | {name})
            elif key and key.lower() not in _TOKEN_KEYS:
                kind = self._expression_kind(found.group(2), body, frozenset())
                if kind != SAFE:
                    yield expression, keyword, kind, variable

    def _expression_kind(self, keyword, body, seen):
        """Kind of one $INFO[] or $VAR[] body: raw or typed text, an unseen source, or safe."""
        if keyword == "VAR":
            name = body.strip()
            if name in seen or name not in self.variables:
                return SAFE
            return _worst(self._text_kind(value, seen | {name}) for value in self.variables[name])
        info = body.split(",")[0].strip()
        if "$" in info:
            return SAFE
        found = _PROPERTY.search(info)
        if found:
            return self._stored_kind("property:" + found.group(1).strip().casefold(), seen)
        found = _SKIN_STRING.search(info)
        if found:
            return self._stored_kind("skin:" + found.group(1).strip().casefold(), seen)
        found = _ITEM_PROPERTY.search(info)
        if found and f"item:{found.group(1)}:{found.group(2).strip().casefold()}" in self.sources:
            return self._stored_kind(f"item:{found.group(1)}:{found.group(2).strip().casefold()}", seen)
        found = re.search(r"\.property\((.+)\)$", info, re.IGNORECASE)
        if found:
            return SAFE if _plain(found.group(1)) else UNTRACED
        if _TYPED.search(info):
            return TYPED
        return SAFE if _plain(info.rsplit(".", 1)[-1]) else RAW

    def _stored_kind(self, key, seen):
        """Kind of a property, skin string or static item property, from every value it holds."""
        if key in seen:
            return SAFE
        values = self.sources.get(key)
        # an encoder that sets NAME also sets NAME.0, NAME.1 and on
        if not values and key.rsplit(".", 1)[-1].isdigit():
            values = [v for v in self.sources.get(key.rsplit(".", 1)[0], []) if v == "encoded"]
        if not values:
            name = key.split(":", 1)[1]
            return SAFE if "encoded" in name or _plain(name) else UNTRACED
        kinds = []
        for value in values:
            if value == "encoded":
                kinds.append(SAFE)
            elif value == "keyboard":
                kinds.append(RAW)
            else:
                kinds.append(self._text_kind(value, seen | {key}))
        return _worst(kinds)

    def _text_kind(self, text, seen):
        """Kind of a stored or variable value, from its runtime parts and its literal characters."""
        key = (text, seen)
        if key not in self._kinds:
            kinds = []
            literal = text
            for found in _EXPRESSION.finditer(text):
                body = bracket_body(text[found.end() - 1:])
                if body:
                    kinds.append(self._expression_kind(found.group(2), body, seen))
                    literal = literal.replace(found.group(0) + body + "]", "")
            if _UNSAFE & set(literal):
                kinds.append(RAW)
            self._kinds[key] = _worst(kinds)
        return self._kinds[key]
