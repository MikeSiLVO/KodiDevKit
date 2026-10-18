"""Plugin entry point and the listener behind hovers, completions, phantoms and on-save checks."""

from __future__ import annotations

import sublime_plugin
import sublime

import time
import re
import os
import html
from collections import Counter
from bisect import bisect_right
from urllib.parse import quote, unquote

import logging
from lxml import etree as ET
from threading import Timer
import mdpopups

# quiet mdpopups' markdown logger before the local imports start logging
logging.getLogger('MARKDOWN').setLevel(logging.WARNING)

from .libs.utils.infobool import (  # noqa: E402
    STATE_FALSE,
    STATE_INVALID,
    STATE_NEEDS_CONTEXT,
    STATE_OFFLINE,
    STATE_TRUE,
    check_condition,
    probe_booleans,
    read_probe,
)
from .libs.utils.expressions import (  # noqa: E402
    extract_expression_at_offset, flatten_expressions, split_top_level_commas)
from .libs.utils.xml import get_root_from_file  # noqa: E402
from .libs.utils.validation import (  # noqa: E402
    CallContexts, is_runtime_placeholder, resolve_param_in_name)
from .libs.sublime.view import jump_to_label_declaration  # noqa: E402
from .libs.infoprovider.provider import INFOS  # noqa: E402
from .libs.kodi.jsonrpc import kodi  # noqa: E402

SETTINGS_FILE = 'kodidevkit.sublime-settings'


CONST_ATTRIBUTES = {"x", "y", "width", "height", "center", "max", "min", "w", "h", "time",
                    "acceleration", "delay", "start", "end", "border", "repeat"}


CONST_NODES = {"posx", "posy", "left", "centerleft", "right", "centerright", "top", "centertop",
               "bottom", "centerbottom", "width", "height", "offsetx", "offsety", "textoffsetx",
               "textoffsety", "textwidth", "spinposx", "spinposy", "spinwidth", "spinheight",
               "radioposx", "radioposy", "radiowidth", "radioheight", "markwidth", "markheight",
               "sliderwidth", "sliderheight", "itemgap", "bordersize", "timeperimage", "fadetime",
               "pauseatend", "depth"}

LABEL_TAGS = {"label", "label2", "altlabel", "property", "hinttext"}

VISIBLE_TAGS = {"visible", "enable", "usealttexture", "expression", "autoscroll", "selected"}

# fixed dark background; syntax colors read the same under any theme
POPUP_CSS = """
html, body {
    background-color: #1B2530;
    color: #D8DEE9;
    margin: 0;
    padding: 0;
}
.mdpopups {
    border-left: 3px solid #14A9D5;
    border-top: 1px solid #3E4F5A;
    border-right: 1px solid #3E4F5A;
    border-bottom: 1px solid #3E4F5A;
    border-radius: 0 4px 4px 0;
    background-color: #1B2530;
    color: #D8DEE9;
    padding: 10px 16px;
    margin: 0;
}
.mdpopups div, .mdpopups p {
    background-color: #1B2530;
    color: #D8DEE9;
    margin: 0 0 2px 0;
    padding: 0;
    line-height: 1.5;
}
.mdpopups a {
    color: #14A9D5;
    text-decoration: none;
}
.mdpopups .highlight {
    border-radius: 3px;
    padding: 4px 6px;
    background-color: #1B2530;
}
.mdpopups .kdk-verdict {
    padding: 2px 8px;
    border-radius: 3px;
    font-weight: bold;
}
.mdpopups .kdk-true {
    background-color: #1E4620;
    color: #7CE38B;
}
.mdpopups .kdk-false {
    background-color: #4A1D1D;
    color: #F28B82;
}
.mdpopups .kdk-invalid {
    background-color: #4A3A1D;
    color: #F2C744;
}
.mdpopups .kdk-offline {
    background-color: #2A2F36;
    color: #8A97A5;
}
.mdpopups .kdk-rule {
    border-top: 1px solid #3E4F5A;
    margin: 6px 0;
}
.mdpopups .kdk-sub {
    color: #8A97A5;
    font-size: 0.9em;
}
"""


POPUP_WRAP_COLUMN = 100

# past this a tooltip cannot show the text, and a verdict on unseen text misleads
EXPANSION_LIMIT = 1200

CALL_VARIANT_LIMIT = 6

# color and word, not emoji: emoji fonts differ across platforms
_VERDICT_TEXT = {
    STATE_TRUE: ("kdk-true", "TRUE"),
    STATE_FALSE: ("kdk-false", "FALSE"),
    STATE_INVALID: ("kdk-invalid", "NOT PARSEABLE"),
    STATE_NEEDS_CONTEXT: ("kdk-offline", "NEEDS INCLUDE CONTEXT"),
    STATE_OFFLINE: ("kdk-offline", "KODI UNREACHABLE"),
}

# XML's five predefined entities; conditions carry them as &amp; and quotes
_XML_ENTITIES = {"&quot;": '"', "&apos;": "'", "&lt;": "<", "&gt;": ">", "&amp;": "&"}


def _decode_entities(text):
    """Decode XML's five entities, &amp; last, back to the characters the skin means."""
    for entity, char in _XML_ENTITIES.items():
        if entity != "&amp;":
            text = text.replace(entity, char)
    return text.replace("&amp;", "&")


def _verdict_html(state, detail=""):
    """Verdict pill for a condition, with any detail as a subdued second line."""
    style, label = _VERDICT_TEXT.get(state, ("kdk-offline", "UNKNOWN"))
    body = f'<div><span class="kdk-verdict {style}">{label}</span></div>'
    if detail:
        body += f'<div class="kdk-sub">{html.escape(detail)}</div>'
    return body


# characters that end an operand; hovering one is not on an item
_OPERAND_STOP = set(" \t+|[]<>\"'")


def _on_tag_name(line_text, cursor_offset):
    """True when the caret is on an element's tag name, not an attribute."""
    before = line_text[:cursor_offset]
    if before.rfind("<") <= before.rfind(">"):
        return False
    return bool(re.match(r"</?\s*[\w.-]*$", before[before.rfind("<"):]))


def _operand_clause(line_text, cursor_offset):
    """The single condition item under the caret, or None on an operator or gap."""
    at = line_text[cursor_offset] if 0 <= cursor_offset < len(line_text) else ""
    if not at or at in _OPERAND_STOP:
        return None
    return extract_expression_at_offset(line_text, cursor_offset) or None


def _skin_expressions(view):
    """`$EXP` definitions for the xml folder of the view's file."""
    addon = getattr(INFOS, "addon", None)
    file_name = view.file_name()
    if not addon or not file_name:
        return {}
    folder = addon.xml_folder_of(file_name)
    return (getattr(addon, "expression_map", None) or {}).get(folder, {})


def _enclosing_include(element):
    """Name of the include definition holding the element, or None outside one."""
    if element is None:
        return None
    return next((a.get("name") for a in element.iterancestors("include") if a.get("name")), None)


def evaluate_condition(view, condition, element=None):
    """Popup HTML with a condition's verdict and, for one item, Kodi's help; None if neither."""
    verdict = _condition_verdict(view, condition, _enclosing_include(element))
    help_text = _condition_help_text(_decode_entities(condition or ""))
    if not help_text:
        return verdict
    sentence, values = _help_parts(help_text)
    note = html.escape(sentence) + (f"<br>{html.escape(', '.join(values))}" if values else "")
    rule = '<div class="kdk-rule"></div>' if verdict else ""
    return f'{verdict or ""}{rule}<div class="kdk-sub">{note}</div>'


def _condition_verdict(view, condition, include=None):
    """Popup HTML giving a Kodi boolean condition's verdict, or None if there is none."""
    condition = _decode_entities(condition or "").strip()
    if not condition or not re.search(r"[A-Za-z]", condition):
        return None
    if include and "$PARAM[" in condition:
        return _call_verdicts(view, condition, include)

    # JSON-RPC never sees the skin's expressions; Kodi expands them at load
    flattened, unknown = flatten_expressions(condition, _skin_expressions(view))
    if unknown:
        return _verdict_html(STATE_INVALID, f"undefined expression {sorted(unknown)[0]}")

    expansion = flattened if flattened != condition else ""
    if len(flattened) > EXPANSION_LIMIT:
        return _verdict_html(STATE_OFFLINE, "expression too large to evaluate")

    problem = check_condition(flattened)
    if problem:
        return _verdict_html(*problem)

    if getattr(kodi, "_cooldown_until", 0) > time.time():
        return None
    result = kodi.request(method="XBMC.GetInfoBooleans",
                          params={"booleans": probe_booleans(flattened)})
    state = read_probe(result, flattened)

    body = _verdict_html(state)
    if expansion:
        body += '<div class="kdk-rule"></div><div class="kdk-sub">expands to</div>'
        body += mdpopups.syntax_highlight(
            view=view,
            src=_soft_wrap_source(expansion, POPUP_WRAP_COLUMN),
            language="text",
            allow_code_wrap=True,
        )
    return body


_PARAM_REF = re.compile(r"\$PARAM\[([^\]]+)\]")


def _call_verdicts(view, condition, include):
    """Verdict rows, one per way the include's calls fill the condition's $PARAM, up to a limit."""
    addon = getattr(INFOS, "addon", None)
    file_name = view.file_name()
    if addon is None or not file_name or getattr(addon, "include_usages", None) is None:
        return _verdict_html(STATE_NEEDS_CONTEXT, "unresolved $PARAM")
    contexts = CallContexts(addon, addon.xml_folder_of(file_name)).for_include(include)
    if not contexts:
        return _verdict_html(STATE_NEEDS_CONTEXT, f"nothing calls {include}")

    names = list(dict.fromkeys(_PARAM_REF.findall(condition)))
    variants = {}
    for context in contexts:
        filled = resolve_param_in_name(condition, context)
        if not is_runtime_placeholder(filled):
            values = ", ".join(f"{name}={_shortened(context.get(name, ''))}" for name in names)
            variants.setdefault(filled, values)
    if not variants:
        return _verdict_html(STATE_NEEDS_CONTEXT, f"only runtime placeholders fill {include}'s params")

    rows, probes = [], []
    for filled, values in list(variants.items())[:CALL_VARIANT_LIMIT]:
        flattened, unknown = flatten_expressions(filled, _skin_expressions(view))
        problem = (check_condition(flattened) if not unknown
                   else (STATE_INVALID, f"undefined expression {sorted(unknown)[0]}"))
        if problem:
            rows.append((problem[0], f"{values}: {problem[1]}", None))
        elif len(flattened) > EXPANSION_LIMIT:
            rows.append((STATE_OFFLINE, f"{values}: expression too large to evaluate", None))
        else:
            rows.append((None, values, flattened))
            probes += probe_booleans(flattened)

    result = None
    if probes:
        if getattr(kodi, "_cooldown_until", 0) > time.time():
            return None
        result = kodi.request(method="XBMC.GetInfoBooleans", params={"booleans": probes})
    body = "".join(_verdict_row(state or read_probe(result, flattened), values)
                   for state, values, flattened in rows)
    hidden = len(variants) - CALL_VARIANT_LIMIT
    if hidden > 0:
        body += f'<div class="kdk-sub">and {hidden} more ways the calls fill it</div>'
    return body


def _shortened(value):
    """A param value short enough for one popup row, quoted when empty."""
    if not value:
        return '""'
    return value if len(value) <= 40 else value[:37] + "..."


def _verdict_row(state, detail):
    """Verdict pill with its detail on the same line."""
    style, label = _VERDICT_TEXT.get(state, ("kdk-offline", "UNKNOWN"))
    return (f'<div><span class="kdk-verdict {style}">{label}</span> '
            f'<span class="kdk-sub">{html.escape(detail)}</span></div>')


_WRAP_BREAK_CHARS = ",|+"


_HELP_TAG = re.compile(r"</?(?:b|c|i|em|strong|code)>")
_HELP_VALUE = re.compile(r"\s*-\s*<b>([^<]+)</b>")


def _help_parts(text):
    """Split Kodi's help into its plain sentence and the values it lists, if any."""
    text = text or ""
    values = _HELP_VALUE.findall(text)
    return " ".join(_HELP_TAG.sub("", _HELP_VALUE.sub("", text)).split()), values


def _help_details(text):
    """Kodi's help text for a completion's details line, listed values last, HTML-escaped."""
    sentence, values = _help_parts(text)
    return html.escape(" ".join([sentence] + ([", ".join(values)] if values else [])))


_PARAM_GROUP = re.compile(r"\(([^()]*)\)")


def _info_stem(text):
    """The stem `Foo(50)` and `Foo(id)` share: the info lowercased, every argument emptied."""
    text = text.lower()
    while True:
        emptied = _PARAM_GROUP.sub("\0", text)
        if emptied == text:
            return text.replace("\0", "()")
        text = emptied


def _help_index(entries):
    """Help per lowercased code, and per stem where only one code has it."""
    stems = Counter(_info_stem(code) for code, _help in entries)
    exact = {code.lower(): help_text for code, help_text in entries}
    by_stem = {_info_stem(code): help_text for code, help_text in entries
               if stems[_info_stem(code)] == 1}
    return exact, by_stem


def _condition_help_text(condition):
    """Kodi's help for a condition that is one item, matched exactly, else by its stem."""
    item = condition.strip().lstrip("!").strip()
    depth = 0
    for char in item:
        depth += (char in "([") - (char in ")]")
        if char in "+|" and depth == 0:
            return None
    if not item or item.startswith("["):
        return None
    exact, by_stem = _kodi_derived(getattr(INFOS, "conditions", []), "help", _help_index)
    return exact.get(item.lower()) or by_stem.get(_info_stem(item))


def _value_completions(text_before):
    """Values Kodi's help lists for the condition whose parentheses the caret sits in."""
    call = re.search(r"([\w.]+)\(\w*$", text_before)
    if not call:
        return []
    _exact, by_stem = _kodi_derived(getattr(INFOS, "conditions", []), "help", _help_index)
    _sentence, values = _help_parts(by_stem.get(call.group(1).lower() + "()"))
    return [sublime.CompletionItem(value, annotation="value") for value in values]


def _snippet_escape(text):
    """Escape the characters a Sublime snippet reads as markup."""
    return text.replace("\\", "\\\\").replace("$", "\\$").replace("}", "\\}")


def _completion_snippets(codes):
    """Snippet per code with a field for each parameter, skipping groups another code varies."""
    stems = Counter(code[:a] + "()" + code[b:] for code in codes
                    for a, b in (m.span() for m in _PARAM_GROUP.finditer(code)))
    snippets = []
    for code in codes:
        parts, last, field = [], 0, 0
        for match in _PARAM_GROUP.finditer(code):
            a, b = match.span()
            names = split_top_level_commas(match.group(1))
            if not names or stems[code[:a] + "()" + code[b:]] > 1:
                continue
            fields = []
            for name in names:
                field += 1
                fields.append(f"${{{field}:{_snippet_escape(name)}}}")
            parts += [_snippet_escape(code[last:a + 1]), ",".join(fields)]
            last = b - 1
        snippets.append("".join(parts) + _snippet_escape(code[last:]))
    return snippets


def _completion_items(entries, annotation):
    """Completion items for Kodi's conditions or builtins, with Kodi's help as details."""
    snippets = _completion_snippets([code for code, _help in entries])
    return [sublime.CompletionItem.snippet_completion(
        code, snippet, annotation=annotation, details=_help_details(help_text))
        for (code, help_text), snippet in zip(entries, snippets)]


_derived = {}


def _kodi_derived(entries, key, build):
    """Value built from one of Kodi's loaded lists, rebuilt once a reload replaces that list."""
    cached = _derived.get(key)
    if cached is None or cached[0] is not entries:
        cached = _derived[key] = (entries, build(entries))
    return cached[1]


def _soft_wrap_source(text, max_col):
    """Hard-wrap long lines at `,`, `|` or `+`, giving minihtml break points."""
    if max_col <= 0:
        return text
    out = []
    for line in text.splitlines():
        if len(line) <= max_col:
            out.append(line)
            continue
        m = re.match(r"^[\t ]*", line)
        indent = m.group(0) if m else ""
        cont = indent + "    "
        floor = len(indent) + 1  # don't break inside leading whitespace

        remaining = line
        while len(remaining) > max_col:
            cut = -1
            search_to = min(max_col, len(remaining) - 1)
            for i in range(search_to, floor - 1, -1):
                if remaining[i] in _WRAP_BREAK_CHARS:
                    cut = i + 1
                    break
            if cut < 0:
                break
            out.append(remaining[:cut])
            remaining = cont + remaining[cut:].lstrip()
            floor = len(cont) + 1
        out.append(remaining)
    return "\n".join(out)


def _setup_logging_once():
    """Install one root StreamHandler; safe to call after plugin reloads."""
    root = logging.getLogger()
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        h = logging.StreamHandler()
        h.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s: %(message)s",
                "%H:%M:%S",
            )
        )
        root.addHandler(h)
    # WARNING is the root logger's default and counts as unset
    if root.level in (logging.NOTSET, logging.WARNING):
        root.setLevel(logging.INFO)

    from .libs.sublime.logging import DialogHandler
    pkg = logging.getLogger("KodiDevKit")
    pkg.propagate = True
    pkg.handlers.clear()
    pkg.addHandler(DialogHandler())


_setup_logging_once()

logger = logging.getLogger("KodiDevKit.kodidevkit")


def _apply_debug_level(settings):
    """Point debug_mode at the engine loggers, which are __name__-based under this package."""
    level = logging.DEBUG if bool(settings.get("debug_mode", False)) else logging.INFO
    logging.getLogger(f"{__package__}.libs" if __package__ else "libs").setLevel(level)


def _on_settings_changed():
    """Reload the settings into the plugin, its debug level and the Kodi client."""
    s = sublime.load_settings(SETTINGS_FILE)
    KodiDevKit.settings = s

    # before the INFOS guard: debug output matters most when the provider failed
    try:
        _apply_debug_level(s)
    except Exception:
        pass

    try:
        if not INFOS:
            return
        from .libs.kodi.jsonrpc import KodiJsonrpc
        kodi_client = getattr(INFOS, "kodi", None)
        if kodi_client:
            kodi_client.load_settings(s, force=True)
        else:
            INFOS.kodi = KodiJsonrpc(s)
            INFOS.kodi.load_settings(s, force=True)
        kodi.update_labels()
    except Exception:
        pass

    logger.info("settings reloaded from %s", SETTINGS_FILE)



def _show_fatal_xml_phantom():
    """If init_addon hit a broken XML file, open it and show an error phantom."""
    fatal = getattr(INFOS, "_fatal_xml_error", None)
    if not fatal:
        return
    from .libs.utils.xml import parse_error_issue
    issues = [parse_error_issue(fatal)]
    line_num = issues[0]["line"]

    def _open_and_show():
        window = sublime.active_window()
        if not window:
            return
        view = window.open_file(f"{fatal}:{line_num}", sublime.ENCODED_POSITION)

        def _when_loaded():
            if view.is_loading():
                sublime.set_timeout(_when_loaded, 50)
                return
            KodiDevKit._clear_phantoms(view)
            KodiDevKit._show_validation_phantoms(view, issues)
            point = view.text_point(max(0, line_num - 1), 0)
            view.show_at_center(point)

        _when_loaded()

    sublime.set_timeout(_open_and_show, 0)


def plugin_unloaded():
    """Sublime exit point: stop the report server."""
    import sys
    server = sys.modules.get(f"{__package__}.libs.reporting.server")
    if server:
        server.stop_server()


def plugin_loaded():
    """Sublime entry point: load settings and Kodi's labels, wire reload hooks, sync the project."""
    import sublime

    settings = sublime.load_settings('kodidevkit.sublime-settings')

    # applied now too, or a restart with debug_mode already set logs nothing extra
    try:
        _apply_debug_level(settings)
    except Exception:
        pass

    if settings.get("enable_file_logging", False):
        try:
            from .libs.sublime import logging as sublimelogger
            log_path = sublimelogger.enable_file_logging()
            print(f"[KodiDevKit] File logging enabled: {log_path}")
        except Exception as e:
            print(f"[KodiDevKit] Failed to enable file logging: {e}")

    try:
        KodiDevKit.settings = settings
    except Exception:
        pass

    try:
        settings.add_on_change('kdk_settings_reload', _on_settings_changed)
    except Exception:
        pass
    kodi.update_labels()

    try:
        _sync_project(sublime.active_window())
    except Exception:
        pass


def _in_addon(filename):
    """True when the file sits inside the loaded addon's folder; other files are left alone."""
    path = getattr(getattr(INFOS, "addon", None), "path", None) if INFOS else None
    if not path or not filename:
        return False
    root = os.path.normcase(os.path.abspath(path))
    try:
        return os.path.commonpath([root, os.path.normcase(os.path.abspath(filename))]) == root
    except ValueError:
        return False


_disk_states = {}


def _disk_state(addon):
    """Modified time and size of each xml and po file the add-on's caches read, by path."""
    roots = [os.path.join(addon.path, folder) for folder in addon.xml_folders]
    roots += [os.path.join(addon.path, "colors"), addon.lang_path]
    paths = [addon.xml_file]
    for root in roots:
        for dirpath, _dirnames, filenames in os.walk(root):
            paths += [os.path.join(dirpath, name) for name in filenames
                      if name.lower().endswith((".xml", ".po"))]
    state = {}
    for path in paths:
        try:
            stat = os.stat(path)
        except OSError:
            continue
        state[path] = (stat.st_mtime_ns, stat.st_size)
    return state


def _remember_disk_state():
    """Remember the modified time and size of the loaded add-on's files, for later comparison."""
    addon = getattr(INFOS, "addon", None) if INFOS else None
    if addon:
        _disk_states[addon.path] = _disk_state(addon)


def _pick_up_disk_changes():
    """Pick up files changed outside the editor since the last look, reloading what they affect."""
    infos = INFOS
    addon = getattr(infos, "addon", None) if infos else None
    if not infos or not addon:
        return
    state = _disk_state(addon)
    old = _disk_states.get(addon.path)
    _disk_states[addon.path] = state
    if old is None or old == state:
        return
    changed = sorted(p for p in state.keys() | old.keys() if state.get(p) != old.get(p))
    logger.info("reloading %d file(s) changed outside the editor", len(changed))
    if addon.xml_file in changed:
        infos.init_addon(addon.path)
        _remember_disk_state()
        return
    addon.update_xml_files()
    addon.reload(*[p for p in changed if p.lower().endswith(".xml")])
    if any(p.lower().endswith(".po") for p in changed):
        addon.update_labels()


def _sync_project(window):
    """Sync the loaded addon to the window's folder and reload the Kodi client's settings."""
    if not INFOS or window is None:
        return
    project_folder = window.extract_variables().get("folder")
    if not project_folder:
        return
    addon = getattr(INFOS, "addon", None)
    if not addon or getattr(addon, "path", None) != project_folder:
        logger.info("project change detected: %s", project_folder)
        init_start = time.time()
        load_settings = getattr(INFOS, "load_settings", None)
        init_addon = getattr(INFOS, "init_addon", None)
        if load_settings and init_addon:
            load_settings(KodiDevKit.settings)
            init_addon(project_folder)
            _remember_disk_state()
            _show_fatal_xml_phantom()
        init_elapsed = time.time() - init_start
        if init_elapsed > 1.0:
            logger.warning("init_addon SLOW: %.3fs project=%s", init_elapsed, project_folder)
    try:
        from .libs.kodi.jsonrpc import KodiJsonrpc
        KodiJsonrpc(KodiDevKit.settings).load_settings(KodiDevKit.settings, force=True)
    except Exception:
        pass


class KodiDevKit(sublime_plugin.EventListener):
    """Event listener behind the plugin: hovers, completions, phantoms and the on-save checks."""
    settings: "sublime.Settings | dict" = {}
    _phantom_sets = {}
    _validation_issues = {}
    _media_cache = {}
    _media_cache_timestamp = {}

    def __init__(self):
        super().__init__()
        self.is_modified = False
        self._modified_files = set()
        self._last_phantom_cleanup = 0

        self.settings = KodiDevKit.settings

        self.timer = None
        self._prev_selections = {}

        self.root = None
        self.tree = None
        self._nodes = []
        self._node_lines = []

    def _index_nodes(self):
        """Build sorted parallel lists of elements and their source lines."""
        self._nodes = []
        self._node_lines = []
        if not self.tree:
            return
        for n in self.tree.iter():
            sl = getattr(n, "sourceline", None)
            if sl:
                self._nodes.append(n)
                self._node_lines.append(sl)

    def _element_at_row(self, row_one_based: int):
        """The element starting last on or before the row, rows counted from one."""
        if not self._node_lines:
            return None
        idx = bisect_right(self._node_lines, row_one_based) - 1
        if idx < 0:
            return None
        return self._nodes[idx]

    @staticmethod
    def _issue_in_file(issue: dict, file_path: str) -> bool:
        """True when the issue's call site is in the file, or it has none."""
        call_file = issue.get("call_file")
        if not call_file:
            return True
        return os.path.normpath(call_file) == os.path.normpath(file_path)

    @staticmethod
    def _clear_phantoms(view):
        """Clear validation phantoms and data from a view."""
        view_id = view.id()
        if view_id in KodiDevKit._phantom_sets:
            KodiDevKit._phantom_sets[view_id].update([])
            del KodiDevKit._phantom_sets[view_id]

        KodiDevKit._validation_issues.pop(view_id, None)


    @staticmethod
    def _show_validation_phantoms(view, issues):
        """Show validation issues as inline phantoms, grouped by source line."""
        if not issues:
            return

        view_id = view.id()

        sorted_issues = sorted(issues, key=lambda x: x.get("line", 1))
        total_issues = len(sorted_issues)

        issues_by_line = {}
        for issue in sorted_issues:
            line = issue.get("line", 1)
            if line not in issues_by_line:
                issues_by_line[line] = []
            issues_by_line[line].append(issue)

        sorted_lines = sorted(issues_by_line.keys())
        KodiDevKit._validation_issues[view_id] = sorted_lines

        if view_id not in KodiDevKit._phantom_sets:
            KodiDevKit._phantom_sets[view_id] = sublime.PhantomSet(view, "kodidevkit_validation")

        phantom_set = KodiDevKit._phantom_sets[view_id]
        phantoms = []

        total_lines = len(sorted_lines)

        severity_colors = {
            "error":   "--redish",
            "warning": "--orangish",
        }

        for line_idx, line_num in enumerate(sorted_lines):
            line_issues = issues_by_line[line_num]

            line = max(0, line_num - 1)
            point = view.text_point(line, 0)
            region = sublime.Region(point, point)

            severity_rank = {"error": 0, "warning": 1}
            worst = min(
                (issue.get("severity", "warning") for issue in line_issues),
                key=lambda s: severity_rank.get(s, 1)
            )
            border_color = severity_colors.get(worst, "--orangish")

            issue_items = []
            for issue in line_issues:
                msg = html.escape(issue.get("message", "Unknown issue"))
                issue_type = html.escape(issue.get("type", ""))
                sev = issue.get("severity", "warning")
                sev_color = severity_colors.get(sev, "--orangish")
                badge = f'<span class="sev-badge" style="color: var({sev_color});">[{sev}]</span> '
                source = ""
                if issue.get("include_file") and issue.get("include_line"):
                    target = f"{issue['include_file']}:{issue['include_line']}"
                    name = html.escape(f"{os.path.basename(issue['include_file'])}:{issue['include_line']}")
                    source = f' <a href="open:{quote(target)}">\u2192 {name}</a>'
                issue_items.append(f'<div class="issue-item">{badge}<span class="type">{issue_type}:</span> '
                                   f'{msg}{source}</div>')

            current_position = line_idx + 1
            nav_links = f'<a href="hide">✕ Dismiss</a> | <a href="next">Next Issue \u2192 ({current_position}/{total_lines} lines, {total_issues} total)</a>'

            html_content = f"""
                <body id="kodidevkit-phantom">
                    <style>
                        #kodidevkit-phantom {{
                            background-color: color(var({border_color}) alpha(0.15));
                            border-left: 3px solid var({border_color});
                            padding: 0.4rem 0.6rem;
                            margin: 0.2rem 0;
                        }}
                        #kodidevkit-phantom .issues {{
                            max-height: 20rem;
                            overflow-y: auto;
                        }}
                        #kodidevkit-phantom .issue-item {{
                            margin: 0.2rem 0;
                            font-size: 0.9rem;
                        }}
                        #kodidevkit-phantom .type {{
                            color: var({border_color});
                            font-weight: bold;
                        }}
                        #kodidevkit-phantom .sev-badge {{
                            font-size: 0.8rem;
                            font-weight: bold;
                        }}
                        #kodidevkit-phantom a {{
                            color: var(--bluish);
                            text-decoration: none;
                        }}
                        #kodidevkit-phantom a:hover {{
                            text-decoration: underline;
                        }}
                    </style>
                    <div class="issues">
                        {''.join(issue_items)}
                        <div style="margin-top: 0.3rem;">{nav_links}</div>
                    </div>
                </body>
            """

            phantom = sublime.Phantom(
                region,
                html_content,
                sublime.LAYOUT_BELOW,
                on_navigate=lambda href, v=view: KodiDevKit._on_phantom_navigate(href, v)
            )
            phantoms.append(phantom)

        phantom_set.update(phantoms)


    @staticmethod
    def _on_phantom_navigate(href, view):
        """Phantom link handler: dismiss, open the include line, or jump to the next issue."""
        view_id = view.id()

        if href == "hide":
            KodiDevKit._clear_phantoms(view)
        elif href.startswith("open:"):
            window = view.window()
            if window:
                window.open_file(unquote(href[len("open:"):]), sublime.ENCODED_POSITION)
        elif href == "next":
            if view_id not in KodiDevKit._validation_issues:
                return

            sorted_lines = KodiDevKit._validation_issues[view_id]
            if not sorted_lines:
                return

            visible = view.visible_region()
            visible_end_row = view.rowcol(visible.end())[0] + 1

            next_idx = None
            for i, line in enumerate(sorted_lines):
                if line > visible_end_row:
                    next_idx = i
                    break

            if next_idx is None:
                next_idx = 0

            next_line = sorted_lines[next_idx]
            next_line_idx = max(0, next_line - 1)
            point = view.text_point(next_line_idx, 0)
            view.show_at_center(point)

    @staticmethod
    def _get_media_completions(media_path):
        """Get the media files as completions, cached per media folder for 30 seconds."""
        if not media_path or not os.path.exists(media_path):
            return []

        cache_key = media_path
        current_time = time.time()
        cache_ttl = 30

        if cache_key in KodiDevKit._media_cache:
            cache_age = current_time - KodiDevKit._media_cache_timestamp.get(cache_key, 0)
            if cache_age < cache_ttl:
                return KodiDevKit._media_cache[cache_key]

        logger.debug(f"Rebuilding media cache for {media_path}")
        start_time = time.time()
        media_completions = []

        try:
            for dirpath, _, files in os.walk(media_path):
                rel_dir = os.path.relpath(dirpath, media_path)
                for fname in files:
                    rel_file = os.path.join(rel_dir, fname).lstrip("./").lstrip("\\")
                    rel_file = rel_file.replace("\\", "/")
                    media_completions.append([rel_file, rel_file])
        except Exception as e:
            logger.error(f"Error walking media path {media_path}: {e}")
            return []

        elapsed = time.time() - start_time
        logger.debug(f"Media cache rebuilt: {len(media_completions)} files in {elapsed:.3f}s")

        KodiDevKit._media_cache[cache_key] = media_completions
        KodiDevKit._media_cache_timestamp[cache_key] = current_time

        return media_completions

    @staticmethod
    def _tag_from_buffer(line_text, view, point):
        """Tag name of the nearest line at or above the caret that opens a tag, from the buffer."""
        row, _ = view.rowcol(point)
        m = re.match(r'\s*<(\w+)[\s>]', line_text)
        if m:
            return m.group(1)
        for i in range(row - 1, max(row - 20, -1), -1):
            prev_line = view.substr(view.line(view.text_point(i, 0)))
            m = re.match(r'\s*<(\w+)[\s>]', prev_line)
            if m:
                return m.group(1)
        return None

    def _get_completion_context(self, view, point):
        """Get the completion kind (tag value, attribute value or tag name) and its type."""
        row, col = view.rowcol(point)
        line_text = view.substr(view.line(point))
        text_before = line_text[:col]
        row_1 = row + 1

        node = self._element_at_row(row_1)

        ctrl_type = None
        if node is not None:
            p = node
            while p is not None:
                if p.tag == "control" and "type" in p.attrib:
                    ctrl_type = p.attrib["type"].lower()
                    break
                p = p.getparent()

        attr_match = re.search(r'(\w+)="([^"]*?)$', text_before)
        if attr_match:
            attr_name = attr_match.group(1)
            if ctrl_type and INFOS and node is not None:
                attribs = INFOS.template_attribs.get(ctrl_type, {})
                buf_tag = self._tag_from_buffer(line_text, view, point)
                tag_key = buf_tag or node.tag
                tag_attribs = attribs.get(tag_key, {})
                if isinstance(tag_attribs, dict):
                    attr_type = tag_attribs.get(attr_name)
                    if attr_type:
                        return "attr_value", attr_type
            if attr_name == "condition":
                return "attr_value", "condition"
            if attr_name in ("effect", "type"):
                tag_on_line = re.search(r'<(\w+)', line_text)
                if tag_on_line and tag_on_line.group(1) == "animation":
                    return "attr_value", "effect"
            return "attr_value", None

        if re.search(r'<\w*$', text_before) and ">" not in text_before.split("<")[-1]:
            return "tag_name", ctrl_type

        buf_tag = self._tag_from_buffer(line_text, view, point)

        if ctrl_type and INFOS:
            values = INFOS.template_values.get(ctrl_type, {})
            tag_key = buf_tag or (node.tag if node is not None else None)
            if tag_key:
                value_type = values.get(tag_key)
                if value_type:
                    return "tag_value", value_type

        tag = (buf_tag or (node.tag if node is not None else "")).lower()
        TAG_TYPE_HINTS = {
            "visible": "condition", "enable": "condition",
            "include": "include", "font": "font",
            "colordiffuse": "color", "textcolor": "color",
            "focusedcolor": "color", "disabledcolor": "color",
            "shadowcolor": "color", "selectedcolor": "color",
            "invalidcolor": "color", "hitrectcolor": "color",
            "texture": "path", "texturefocus": "path",
            "texturenofocus": "path", "bordertexture": "path",
            "imagepath": "path",
            "onclick": "builtin", "onfocus": "builtin",
            "onunfocus": "builtin", "onback": "builtin",
            "onup": "builtin", "ondown": "builtin",
            "onleft": "builtin", "onright": "builtin",
            "onnext": "builtin", "onprev": "builtin",
            "oninfo": "builtin", "altclick": "builtin",
            "ontextchange": "builtin",
            "onload": "builtin", "onunload": "builtin",
        }
        hint = TAG_TYPE_HINTS.get(tag)
        if hint:
            return "tag_value", hint

        return None, None

    def _completions_for_type(self, value_type, addon, folder):
        """Build completions for a value type from Kodi's lists and the skin's own files."""
        from .libs.validation.constants import ALLOWED_VALUES

        items = []

        if value_type in ALLOWED_VALUES:
            for val in sorted(ALLOWED_VALUES[value_type]):
                items.append([f"{val}\t{value_type}", val])
            return items

        if value_type == "effect":
            for val in ["fade", "slide", "rotate", "rotatex", "rotatey", "zoom"]:
                items.append([f"{val}\teffect", val])
            return items

        if value_type == "controltype":
            for ct in sorted(getattr(INFOS, "template_attribs", {}).keys()):
                items.append([f"{ct}\tcontrol", ct])
            return items

        if value_type == "color":
            get_colors = getattr(INFOS, "get_colors", None)
            if get_colors:
                seen = set()
                for node in get_colors():
                    name = node.get("name")
                    if name and name not in seen:
                        seen.add(name)
                        items.append([f"{name}\t{node.get('content', 'color')}", name])
            return items

        if value_type == "font":
            if folder in addon.fonts:
                seen = set()
                for node in addon.fonts[folder]:
                    nm = node.get("name")
                    if nm and nm not in seen:
                        seen.add(nm)
                        items.append([f"{nm}\tfont", nm])
            return items

        if value_type == "include":
            inc_map = getattr(addon, "include_map", {}).get(folder, {})
            for nm in sorted(inc_map.keys()):
                items.append([f"{nm}\tinclude", nm])
            return items

        if value_type in ("path", "texture"):
            return self._get_media_completions(addon.media_path)

        if value_type in ("condition", "builtin"):
            entries = getattr(INFOS, value_type + "s", [])
            return _kodi_derived(entries, value_type, lambda e: _completion_items(e, value_type))

        return items

    def on_query_completions(self, view, prefix, locations):
        """Completions for the caret's place in one of the loaded addon's XML files."""
        start = time.time()
        if not INFOS:
            return []
        addon = getattr(INFOS, "addon", None)
        if not addon:
            return []

        filename = view.file_name()
        if not filename or not _in_addon(filename):
            return []

        scope_name = view.scope_name(locations[0])
        if "text.xml.kodi" not in scope_name:
            return []

        folder = addon.xml_folder_of(filename)

        ctx_type, detail = self._get_completion_context(view, locations[0])

        if ctx_type and detail:
            if detail == "condition":
                line_start = view.line(locations[0]).begin()
                values = _value_completions(view.substr(sublime.Region(line_start, locations[0])))
                if values:
                    return (values, sublime.INHIBIT_WORD_COMPLETIONS
                            | sublime.INHIBIT_EXPLICIT_COMPLETIONS)
            items = self._completions_for_type(detail, addon, folder)
            if items:
                elapsed = time.time() - start
                if elapsed > 0.2:
                    logger.warning("on_query_completions SLOW: %.3fs count=%d ctx=%s", elapsed, len(items), detail)
                flags = getattr(sublime, "INHIBIT_WORD_COMPLETIONS", 8)
                return (items, flags)

        return []

    def on_selection_modified_async(self, view):
        """Schedule the tooltip for a moved caret in the add-on's files, after the set delay."""
        if not INFOS:
            return
        addon = getattr(INFOS, "addon", None)
        if not addon:
            return
        # also skips views without filenames (Find Results, scratch buffers, etc.)
        if not _in_addon(view.file_name()):
            return
        sels = view.sel()
        if len(sels) != 1:
            return

        # the selection can change between the length check and the read
        try:
            region = sels[0]
        except IndexError:
            return

        if region.a != region.b:
            return

        view_id = view.id()
        prev = self._prev_selections.get(view_id)
        if prev is not None and region.a == prev.a and region.b == prev.b:
            return
        self._prev_selections[view_id] = region

        delay_ms = self.settings.get("tooltip_delay", 200)
        try:
            delay = int(delay_ms) / 1000.0
        except (TypeError, ValueError):
            delay = 0.2

        if self.timer is not None:
            try:
                if hasattr(self.timer, "cancel"):
                    self.timer.cancel()
                if hasattr(self.timer, "join") and self.timer.is_alive():
                    self.timer.join(timeout=0.05)
            except Exception as e:
                logger.debug("Timer cleanup: %s", e)
            finally:
                self.timer = None

        t = Timer(delay, self.show_tooltip, (view,))
        try:
            t.daemon = True
        except Exception:
            pass
        t.start()
        self.timer = t

    def get_tooltip(self, view):
        """Get the tooltip body for the cursor's current context, None when nothing applies."""
        if not INFOS:
            return None

        sels = view.sel()
        if not sels:
            return None

        region = sels[0]
        scope_name = view.scope_name(region.b)
        line = view.line(region)

        if "source.python" in scope_name:
            python_label_tooltip = getattr(INFOS, "python_label_tooltip", None)
            if not python_label_tooltip:
                return None
            col = region.b - line.begin()
            return python_label_tooltip(view.substr(line), col, view.file_name() or "") or None

        if "text.xml.kodi" not in scope_name:
            return None
        if "comment" in scope_name:
            comment_text = view.substr(view.extract_scope(region.b))
            if not re.search(
                r'\$INFO\[|\$VAR\[|\$ESCINFO\[|\$EXP\[|\$MAP\[|'
                r'Window\.|Control\.|Skin\.|String\.|Player\.|Container\.|ListItem\.|'
                r'\b(?:Is|Has)[A-Za-z_]+',
                comment_text
            ):
                return None

        flags = sublime.CLASS_WORD_START | sublime.CLASS_WORD_END
        scope_content = view.substr(view.extract_scope(region.b))
        label_region = view.expand_by_class(region, flags, '$],')
        row, _ = view.rowcol(region.begin())

        on_attr_name = "entity.other.attribute-name" in scope_name

        line = view.line(region)
        line_text = view.substr(line)
        cursor_offset = region.begin() - line.begin()

        word_at_cursor = view.substr(label_region)

        selected_content = view.substr(
            view.expand_by_class(region, flags, '<>"[]')
        )

        info_type = ""
        info_id = ""
        addon_id = ""
        token = word_at_cursor

        dollar_pos = line_text.rfind("$", 0, cursor_offset + 1)
        if dollar_pos != -1:
            open_bracket = line_text.find("[", dollar_pos)
            if open_bracket != -1 and open_bracket < cursor_offset:
                # block may hold nested [...]
                close_bracket = self.find_end_bracket(line_text, '[', ']', open_bracket + 1)
                if close_bracket != -1 and close_bracket > cursor_offset:
                    token = line_text[dollar_pos:close_bracket + 1]

        if "[" in token:
            head = token.split("[", 1)[0]
            if head in {"INFO", "ESCINFO", "VAR", "ESCVAR", "MAP", "ESCMAP", "EXP", "LOCALIZE", "ADDON", "$INFO", "$ESCINFO", "$VAR", "$ESCVAR", "$MAP", "$ESCMAP", "$EXP", "$LOCALIZE", "$ADDON"}:
                info_type = head.lstrip("$")
                content = token.split("[", 1)[1].rsplit("]", 1)[0]
                if info_type == "ADDON":
                    parts = content.split(None, 1)
                    if len(parts) == 2:
                        addon_id = parts[0].strip()
                        info_id = parts[1].strip()
                    else:
                        info_id = content.strip()
                else:
                    info_id = content.split(",", 1)[0].strip()

        if "constant.other.allcaps" in scope_name:
            window_name = scope_content.lower()[1:-1]
            window_names = getattr(INFOS, "WINDOW_NAMES", [])
            if window_name in window_names:
                window_filenames = getattr(INFOS, "WINDOW_FILENAMES", [])
                window_index = window_names.index(window_name)
                if window_index < len(window_filenames):
                    return window_filenames[window_index]

        if info_type in {"VAR", "ESCVAR"}:
            content = self.get_formatted_include(selected_content, view, kinds=("variable",))
            if content:
                return content

        if info_type in {"MAP", "ESCMAP"}:
            body_start = dollar_pos + token.find("[") + 1
            args = token.split("[", 1)[1].rsplit("]", 1)[0].split(",")
            map_name = args[0].strip()
            # Kodi splits the block on every comma
            arg_index = line_text.count(",", body_start, cursor_offset)
            if arg_index == 0:
                content = self.get_formatted_include(map_name, view, kinds=("map",))
                if content:
                    return content
            elif arg_index == 1 and len(args) > 1:
                preview = self._map_lookup_preview(view, map_name, args[1].strip())
                if preview:
                    return preview

        if info_type in {"INFO", "ESCINFO"}:
            # word after [COLOR is a color name, left to the color lookup
            word_start = label_region.begin() - line.begin()
            if word_at_cursor and word_start >= 7:
                before_word = line_text[word_start - 7:word_start].upper()
                if before_word == "[COLOR ":
                    return None

            if getattr(kodi, '_cooldown_until', 0) > time.time():
                return None
            result = kodi.request(method="XBMC.GetInfoLabels", params={"labels": [info_id]})
            if result:
                _, value = result["result"].popitem()
                if value:
                    return str(value)

        if info_type == "LOCALIZE":
            return_label = getattr(INFOS, "return_label", None)
            if return_label:
                return return_label(info_id)

        if info_type == "ADDON" and addon_id and info_id:
            return_addon_label = getattr(INFOS, "return_addon_label", None)
            if return_addon_label:
                addon_label = return_addon_label(addon_id, info_id)
                if addon_label:
                    return addon_label

        element = self._element_at_row(row + 1) if self.tree else None

        visible_owner = element
        while visible_owner is not None and visible_owner.tag not in VISIBLE_TAGS:
            parent = visible_owner.getparent() if hasattr(visible_owner, "getparent") else None
            if parent is None or getattr(parent, "sourceline", 0) > (row + 1):
                break
            visible_owner = parent

        if element is not None and "condition" in element.attrib:
            if on_attr_name and scope_content.strip() == "condition":
                verdict = evaluate_condition(view, element.attrib["condition"], element)
                if verdict:
                    return verdict

        if "string.quoted.double.xml" in scope_name:
            content = scope_content[1:-1]

            if element is not None and "condition" in element.attrib:
                attr_region = view.find(r'condition\s*=\s*"[^"]*"', view.line(region).begin())
                if attr_region and attr_region.contains(region):
                    # the item at the caret; the whole attribute shows on the `condition` name
                    cond = _operand_clause(line_text, cursor_offset)
                    if cond:
                        verdict = evaluate_condition(view, cond, element)
                        if verdict:
                            return verdict

            if (element is not None
                    and element.tag == "control"
                    and content == (element.attrib.get("type") or "").strip()):
                attr_region = view.find(r'type\s*=\s*"[^"]*"', view.line(region).begin())
                if attr_region and attr_region.contains(region):
                    default_content = self.get_formatted_default(content, view)
                    if default_content:
                        return default_content

            if (content.isdigit()
                    and element is not None
                    and any(k in element.attrib for k in {"fallback", "label"})):
                return_label = getattr(INFOS, "return_label", None)
                if return_label:
                    label_id = return_label(content)
                    if label_id:
                        return label_id
            if content.endswith((".png", ".jpg", ".gif")):
                get_image_info = getattr(INFOS, "get_image_info", None)
                if get_image_info:
                    image_info = get_image_info(content)
                    if image_info:
                        return image_info

        if element is not None and element.tag in ("include", "font"):
            ref_name = None
            sel = selected_content.strip()
            if element.text and sel == element.text.strip():
                ref_name = element.text.strip()
            elif element.tag == "include":
                attr_name = (element.attrib.get("content") or "").strip()
                if attr_name and sel == attr_name:
                    ref_name = attr_name
            if ref_name:
                include_content = self.get_formatted_include(ref_name, view, kinds=(element.tag,))
                if include_content:
                    return include_content

        # read the live buffer, which works before the file is saved
        if element is None or element.tag not in ("include", "font"):
            ref_name = None
            ref_kind = "include"
            attr_match = re.search(
                r'<include[^>]*\bcontent\s*=\s*"([^"]+)"',
                line_text,
            )
            if attr_match:
                ref_name = attr_match.group(1).strip()
            else:
                ref_match = re.search(r'<(include|font)[^>]*>([^<]+)</\1>', line_text)
                if not ref_match:
                    ref_match = re.match(r'\s*<(include|font)[^>]*>(\S+)', line_text)
                if ref_match:
                    ref_kind = ref_match.group(1)
                    ref_name = ref_match.group(2).strip()
            if ref_name and selected_content.strip() in ref_name:
                include_content = self.get_formatted_include(ref_name, view, kinds=(ref_kind,))
                if include_content:
                    return include_content

        if element is not None and element.tag == "param":
            text = extract_expression_at_offset(line_text, cursor_offset) or selected_content.strip()

            # a forwarded $PARAM has nothing to look up
            if "$PARAM[" in text:
                return None

            if "$INFO[" in text:
                info_id = (
                    text.split("$INFO[", 1)[1]
                    .split("]", 1)[0]
                    .split(",", 1)[0]
                    .strip()
                )
                if info_id:
                    if getattr(kodi, '_cooldown_until', 0) > time.time():
                        return None
                    result = kodi.request("XBMC.GetInfoLabels", {"labels": [info_id]})
                    if result:
                        _, value = result["result"].popitem()
                        if value:
                            return str(value)

            text_lower = text.strip().lower()
            if text_lower in {"true", "false", "yes", "no"}:
                return None
            if "[COLOR" in text.upper():
                return None
            has_operators = any(op in text for op in ['|', '+', '!', '[', ']'])
            if (has_operators
                    and "entity.name.tag" not in view.scope_name(region.b)
                    and info_type not in {"INFO", "ESCINFO", "VAR", "ESCVAR", "MAP", "ESCMAP", "EXP"}):
                verdict = evaluate_condition(view, text)
                if verdict:
                    return verdict

            # a bare operand is a condition only where the include uses this param as one
            parent = element.getparent() if hasattr(element, "getparent") else None
            if (parent is not None and parent.tag == "include"
                    and parent.get("content")
                    and re.search(r"[A-Za-z]", text)):
                addon = getattr(INFOS, "addon", None)
                file_name = view.file_name()
                resolver = getattr(addon, "resolve_param_role", None) if addon else None
                if addon and resolver and file_name:
                    folder = addon.xml_folder_of(file_name)
                    inc_name = parent.get("content")
                    param_name = element.get("name") or ""
                    role = resolver(folder, inc_name, param_name)
                    is_condition_role = (
                        isinstance(role, tuple)
                        and (
                            (role[0] == "tag" and role[1] in VISIBLE_TAGS)
                            or (role[0] == "attr" and role[1] == "condition")
                        )
                    )
                    if is_condition_role:
                        # whole body on the param name, a single item inside the body
                        text_before_cursor = line_text[:cursor_offset]
                        in_name_attr = bool(re.search(r'\bname="[^"]*$', text_before_cursor))
                        if in_name_attr:
                            cond = (element.text or "").strip()
                        else:
                            cond = _operand_clause(line_text, cursor_offset)
                        if cond:
                            verdict = evaluate_condition(view, cond)
                            if verdict:
                                return verdict

        owner = (
            visible_owner
            if (visible_owner is not None and visible_owner.tag in VISIBLE_TAGS)
            else element
        )
        if owner is not None and owner.tag in VISIBLE_TAGS:
            # whole condition on the tag name, a single item on an operand, nothing else
            if _on_tag_name(line_text, cursor_offset):
                cond = "".join(owner.itertext() or "").strip()
            elif line_text[:cursor_offset].rfind("<") > line_text[:cursor_offset].rfind(">"):
                return None
            else:
                cond = _operand_clause(line_text, cursor_offset)
                if not cond:
                    return None

            cond = re.sub(r"\s*\+\s*", " + ", cond.strip())
            verdict = evaluate_condition(view, cond, owner)
            if verdict:
                return verdict

        if element is not None and element.tag in LABEL_TAGS:
            if "$PARAM[" in selected_content:
                return None
            return_label = getattr(INFOS, "return_label", None)
            if return_label:
                label = return_label(selected_content)
                if label:
                    return label

        if selected_content.endswith((".png", ".gif", ".jpg")):
            get_image_info = getattr(INFOS, "get_image_info", None)
            if get_image_info:
                image_info = get_image_info(selected_content)
                if image_info:
                    return image_info

        if element is not None and element.tag == "control":
            scope_name = view.scope_name(region.b)
            if "entity.name.tag" in scope_name and "</" not in selected_content:
                control_type = element.get("type", "").lower()
                if control_type in {"group", "grouplist", "list", "panel", "fixedlist", "wraplist"}:
                    get_ancestor_info = getattr(INFOS, "get_ancestor_info", None)
                    if get_ancestor_info:
                        return get_ancestor_info(element)

        get_color_info_html = getattr(INFOS, "get_color_info_html", None)
        if get_color_info_html:
            color = get_color_info_html(selected_content.strip())
            if color:
                return color

        # a bare name can be a constant, expression or variable
        sel = selected_content.strip()
        if sel and re.match(r"^[A-Za-z_][\w\-]*$", sel):
            addon = getattr(INFOS, "addon", None)
            file_name = view.file_name()
            if addon and file_name:
                folder = addon.xml_folder_of(file_name)
                maps = (
                    getattr(addon, "constant_map", {}),
                    getattr(addon, "expression_map", {}),
                    getattr(addon, "variable_map", {}),
                )
                if any(sel in m.get(folder, {}) for m in maps):
                    content = self.get_formatted_include(sel, view, kinds=("constant", "expression", "variable"))
                    if content:
                        return content

        return None

    @staticmethod
    def _map_lookup_preview(view, map_name, infolabel):
        """The infolabel's live value, and what the map turns it into."""
        if not infolabel or getattr(kodi, '_cooldown_until', 0) > time.time():
            return None

        result = kodi.request(method="XBMC.GetInfoLabels", params={"labels": [infolabel]})
        if not result:
            return None
        _, value = result["result"].popitem()
        if not value:
            return None

        raw = str(value)
        addon = getattr(INFOS, "addon", None)
        file_name = view.file_name()
        lookup = getattr(addon, "lookup_skin_map", None) if addon else None
        if not addon or not lookup or not file_name:
            return raw

        folder = addon.xml_folder_of(file_name)
        mapped = lookup(folder, map_name, raw)
        return raw if mapped == raw else f"{raw} -> {mapped}"

    @staticmethod
    def find_end_bracket(text, opener, closer, start_pos=0):
        """Find the closer for an already-opened bracket, nested pairs skipped; -1 when none."""
        blocks = 1
        for i in range(start_pos, len(text)):
            if text[i] == opener:
                blocks += 1
            elif text[i] == closer:
                blocks -= 1
                if blocks == 0:
                    return i
        return -1

    @staticmethod
    def _popup_target(view):
        """The loaded addon and the view's resolution folder, or None."""
        addon = getattr(INFOS, "addon", None) if INFOS else None
        if not addon:
            return None
        file_path = view.file_name()
        if not file_path:
            return None
        folder = addon.xml_folder_of(file_path)
        return (addon, folder) if folder else None

    @staticmethod
    def get_formatted_include(content, view, kinds=None):
        """Get a popup body showing the definition of that name, of any kind or only those given."""
        target = KodiDevKit._popup_target(view)
        if target is None:
            return None
        addon, folder = target

        return_node = getattr(addon, "return_node", None)
        if not return_node:
            return None

        node = return_node(content, folder=folder, kinds=kinds)
        if not node:
            return None

        return KodiDevKit._render_definition(node['content'], view, folder)

    @staticmethod
    def get_formatted_default(control_type, view):
        """Render the `<default type="X">` block a control of that type inherits."""
        target = KodiDevKit._popup_target(view)
        if target is None:
            return None
        addon, folder = target

        entry = getattr(addon, "default_map", {}).get(folder, {}).get(control_type)
        if not entry:
            return None

        return KodiDevKit._render_definition(entry[0], view, folder)

    @staticmethod
    def _render_definition(content_elem, view, folder):
        """Resolve a definition body and syntax-highlight it, plain values verbatim."""
        resolve_xml = getattr(INFOS, "resolve_xml", None)

        # an element for includes, variables and defaults, XML text for fonts, else a value
        if hasattr(content_elem, 'tag'):
            root = content_elem
        else:
            text = content_elem.strip() if isinstance(content_elem, str) else ""
            if not text:
                return None
            if text.startswith("<"):
                try:
                    root = ET.fromstring(text)
                except ET.XMLSyntaxError:
                    root = None
            else:
                root = None
            if root is None:
                return mdpopups.syntax_highlight(
                    view=view,
                    src=text,
                    language="text",
                    allow_code_wrap=True,
                )

        # resolve_xml resolves a copy, leaving root untouched
        if resolve_xml:
            resolved = resolve_xml(root, folder=folder)
            if resolved is not None:
                root = resolved
                for el in root.iter():
                    for attr in [a for a in el.attrib if a.startswith("_kdk_")]:
                        del el.attrib[attr]

        node_content = ET.tostring(root, encoding="unicode", pretty_print=True)
        if not node_content:
            return None
        if len(node_content) >= 50000:
            return "include too big for preview"
        node_content = _soft_wrap_source(node_content, POPUP_WRAP_COLUMN)
        return mdpopups.syntax_highlight(
            view=view,
            src=node_content,
            language="xml",
            allow_code_wrap=True,
        )

    def _is_definition_name_here(self, view, tag_names=("include", "variable", "constant", "expression", "map")) -> bool:
        """True when the caret is inside an opening definition tag (`<include name="...">`)."""
        try:
            pt = view.sel()[0].begin()
        except Exception:
            return False

        line_region = view.line(pt)
        text = view.substr(line_region)
        text_lower = text.lower()

        for tag in tag_names:
            open_pat = f"<{tag}"
            if open_pat not in text_lower:
                continue

            offset = pt - line_region.begin()
            start = text_lower.rfind(open_pat, 0, offset + 1)
            if start == -1:
                continue
            end = text_lower.find(">", start)
            if end == -1:
                continue

            tag_text = text_lower[start:end]
            # body `$EXP[]` on the same line still needs the popup
            if "name=" in tag_text and start <= offset <= end:
                return True

        return False

    def show_tooltip(self, view):
        """Show the mdpopups tooltip for the cursor's current context, if any."""
        if view is None or not view.is_valid():
            return

        window = view.window()
        if window is None or not view.file_name():
            return

        # `expression` left out: its body is a boolean, and hovering the name evaluates it
        if self._is_definition_name_here(view, ("include", "variable", "constant")):
            return

        tooltip = self.get_tooltip(view)
        if not tooltip:
            return

        try:
            mw = self.settings.get("tooltip_width", 1000)
            mh = self.settings.get("tooltip_height", 400)
            sublime.set_timeout(
                lambda v=view, c=tooltip, w=mw, h=mh: (
                    v.settings().set("kodidevkit.popup_kind", "tooltip"),
                    mdpopups.show_popup(
                        view=v,
                        content=c,
                        css=POPUP_CSS,
                        flags=sublime.COOPERATE_WITH_AUTO_COMPLETE,
                        max_width=w,
                        max_height=h,
                        on_navigate=lambda href, vv=v: jump_to_label_declaration(vv, href),
                        on_hide=lambda vv=v: vv.settings().erase("kodidevkit.popup_kind"),
                    )
                ),
                0,
            )
        except Exception as exc:
            try:
                view.settings().erase("kodidevkit.popup_kind")
            except Exception:
                pass
            logger.exception("Failed to show tooltip: %s", exc)

    def _hide_tooltip_only(self, view):
        """Hide our popup without touching popups owned by other plugins."""
        if not view.is_popup_visible():
            return
        try:
            if view.settings().get("kodidevkit.popup_kind") == "tooltip":
                view.hide_popup()
                s = view.settings()
                if s.has("kodidevkit.popup_kind"):
                    s.erase("kodidevkit.popup_kind")
        except Exception:
            # a failed popup teardown must never break editing
            pass

    def on_modified(self, view):
        """Hide the tooltip and clear the view's phantoms once its text changes."""
        start = time.time()
        self._hide_tooltip_only(view)
        if view.id() in KodiDevKit._phantom_sets:
            self._clear_phantoms(view)
            view.erase_status("kodidevkit_validation")
        elapsed = time.time() - start
        if elapsed > 0.1:
            logger.warning("on_modified SLOW: %.3fs view_id=%s", elapsed, view.id())

    def on_selection_modified(self, view):
        """Hide the tooltip as soon as the caret moves."""
        start = time.time()
        self._hide_tooltip_only(view)
        elapsed = time.time() - start
        if elapsed > 0.1:
            logger.warning("on_selection_modified SLOW: %.3fs view_id=%s", elapsed, view.id())

    def on_close(self, view):
        """Forget the closing view's phantoms, issues, selection and popup state."""
        start = time.time()
        view_id = view.id()

        if view_id in KodiDevKit._phantom_sets:
            self._clear_phantoms(view)

        KodiDevKit._validation_issues.pop(view_id, None)

        self._prev_selections.pop(view_id, None)

        try:
            s = view.settings()
            if s.has("kodidevkit.popup_kind"):
                s.erase("kodidevkit.popup_kind")
        except Exception:
            pass

        elapsed = time.time() - start
        if elapsed > 0.1:
            logger.warning("on_close SLOW: %.3fs view_id=%s", elapsed, view_id)

    def _cleanup_orphaned_phantoms(self):
        """Drop phantom sets and stored issues for views that have closed."""
        current_time = time.time()
        if current_time - self._last_phantom_cleanup < 300:
            return

        self._last_phantom_cleanup = current_time
        valid_view_ids = {v.id() for w in sublime.windows() for v in w.views()}
        orphaned = set(KodiDevKit._phantom_sets.keys()) - valid_view_ids
        for view_id in orphaned:
            KodiDevKit._phantom_sets.pop(view_id, None)
            KodiDevKit._validation_issues.pop(view_id, None)
    

    def on_load_async(self, view):
        """Refresh the parse for a newly loaded file."""
        self.check_status()

    def on_load_project_async(self, window):
        """Load the project's folder as the add-on."""
        _sync_project(window)

    def on_query_context(self, view, key, operator, operand, match_all):
        """Answer the `kodidevkit_project` key binding context: a Kodi addon is loaded."""
        if key != "kodidevkit_project":
            return None
        loaded = bool(INFOS and getattr(INFOS, "addon", None))
        if operator == sublime.OP_EQUAL:
            return loaded == operand
        if operator == sublime.OP_NOT_EQUAL:
            return loaded != operand
        return None

    def on_new_window_async(self, window):
        """Load the new window's folder as the add-on."""
        _sync_project(window)

    def on_activated_async(self, view):
        """Reload outside edits, reparse the view and drop the phantoms of closed views."""
        _pick_up_disk_changes()
        self.check_status()
        self._cleanup_orphaned_phantoms()

    def on_deactivated_async(self, view):
        """Hide our tooltip and cancel any pending tooltip timer."""
        self._hide_tooltip_only(view)
        timer = getattr(self, "timer", None)
        if timer:
            try:
                timer.cancel()
            finally:
                self.timer = None

    def on_modified_async(self, view):
        """Track which xml files were edited so post-save knows what to reload."""
        if not hasattr(self, "_modified_files"):
            self._modified_files = set()

        if not INFOS:
            return
        addon = getattr(INFOS, "addon", None)
        if not addon or not addon.path:
            return

        fname = view.file_name()
        if not fname or not _in_addon(fname) or not fname.lower().endswith(".xml"):
            return

        self._modified_files.add(fname)

    def on_post_save_async(self, view):
        """On save: drop an image's media cache, reload po labels, reload and revalidate an xml."""
        import time
        save_start = time.time()

        if not INFOS:
            return None
        addon = getattr(INFOS, "addon", None)
        if not addon:
            return None

        filename_full = view.file_name()
        if not filename_full or not _in_addon(filename_full):
            return None

        logger.debug("on_post_save_async START: file=%s", os.path.basename(filename_full))
        ext = os.path.splitext(filename_full)[1].lower()

        if ext in {'.png', '.jpg', '.jpeg', '.gif', '.webp'} and addon.media_path:
            try:
                if filename_full.startswith(addon.media_path):
                    cache_key = addon.media_path
                    if cache_key in KodiDevKit._media_cache:
                        logger.debug(f"Media file saved, invalidating cache for {cache_key}")
                        del KodiDevKit._media_cache[cache_key]
                        del KodiDevKit._media_cache_timestamp[cache_key]
            except Exception as e:
                logger.debug(f"Error invalidating media cache: {e}")

        if ext == ".xml":
            edited = False
            try:
                edited = filename_full in self._modified_files
                if edited:
                    self._modified_files.discard(filename_full)
            except Exception:
                edited = bool(getattr(self, "is_modified", False))
                self.is_modified = False

            if not edited:
                return

            addon.update_xml_files()

            folder = addon.xml_folder_of(filename_full)
            filename = os.path.relpath(filename_full, os.path.join(addon.path, folder))

            addon.reload(filename_full)
            _remember_disk_state()

            from .libs.utils.xml import parse_error_issue

            self.root = get_root_from_file(filename_full)
            if self.root is None:
                issues = [parse_error_issue(filename_full)]

                def _show_parse_error():
                    self._clear_phantoms(view)
                    self._show_validation_phantoms(view, issues)
                    line_num = issues[0]["line"]
                    point = view.text_point(max(0, line_num - 1), 0)
                    view.show_at_center(point)

                sublime.set_timeout(_show_parse_error, 0)
                return

            self.tree = ET.ElementTree(self.root)
            self._index_nodes()

            needs_reload = (
                folder == "colors"
                or (folder in addon.window_files and filename in addon.window_files[folder])
            )

            if self.settings.get("debug_mode", False):
                log = logging.getLogger("KodiDevKit.save")
                log.debug(
                    "on_post_save: needs_reload=%s | auto_reload_skin=%s | auto_skin_check=%s | file=%s | view_id=%s",
                    needs_reload,
                    self.settings.get("auto_reload_skin", True),
                    self.settings.get("auto_skin_check", True),
                    (view.file_name() or "Untitled"),
                    view.id(),
                )

            window = view.window()

            if needs_reload and window and self.settings.get("auto_reload_skin", True):
                window.run_command("kodidevkit_execute_builtin", {"builtin": "ReloadSkin()"})

            if window and self.settings.get("auto_skin_check", True):
                # an add-on's resources/settings.xml has its own schema; a skin's is checked
                is_addon_settings = (
                    filename.lower() == "settings.xml"
                    and ("resources" in filename_full.replace("\\", "/").lower().split("/"))
                    and folder.lower() not in ["1080i", "720p", "16x9"]
                )

                if not is_addon_settings:
                    check_file = getattr(INFOS, "check_file", None)
                    all_issues = check_file(filename_full) if check_file else []

                    # None means the file is excluded, such as one in the shortcuts folder
                    if all_issues is None:
                        sublime.set_timeout(lambda: self._clear_phantoms(view), 0)
                        return

                    severity_rank = {"error": 0, "warning": 1}
                    min_level = self.settings.get("phantom_severity_level", "warning")
                    max_rank = severity_rank.get(min_level, 1)
                    hide_include_warnings = self.settings.get("hide_include_warnings", True)
                    issues = [
                        i for i in all_issues
                        if severity_rank.get(i.get("severity", "warning"), 1) <= max_rank
                        and not i.get("muted")
                        and self._issue_in_file(i, filename_full)
                        and not (hide_include_warnings
                                 and i.get("include_name")
                                 and i.get("severity") != "error")
                    ]

                    def _show():
                        self._clear_phantoms(view)

                        try:
                            rel = os.path.relpath(filename_full, addon.path) if addon and addon.path else os.path.basename(filename_full)
                        except Exception:
                            rel = os.path.basename(filename_full)

                        if issues:
                            self._show_validation_phantoms(view, issues)
                            first_line = min(issue.get("line", 1) for issue in issues)
                            first_line_idx = max(0, first_line - 1)
                            point = view.text_point(first_line_idx, 0)
                            view.show_at_center(point)

                            errors = sum(1 for i in issues if i.get("severity") == "error")
                            warnings = len(issues) - errors
                            parts = []
                            if errors:
                                parts.append(f"{errors}E")
                            if warnings:
                                parts.append(f"{warnings}W")
                            breakdown = " ".join(parts) if parts else str(len(issues))
                            sublime.status_message(f"⚠ {len(issues)} issue(s) in {rel} [{breakdown}]")
                        else:
                            popup_html = f"""
                                <body style="margin: 0; padding: 0.5rem 0.8rem; background-color: color(var(--greenish) alpha(0.1)); border-left: 3px solid var(--greenish);">
                                    <div style="font-size: 1.1rem; color: var(--greenish); font-weight: bold;">✓ No Issues Found</div>
                                    <div style="margin-top: 0.3rem; font-size: 0.9rem; opacity: 0.9;">in {html.escape(rel)}</div>
                                </body>
                            """
                            view.show_popup(
                                popup_html,
                                flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY,
                                location=-1,
                                max_width=400
                            )

                            def hide_popup():
                                view.hide_popup()
                            sublime.set_timeout(hide_popup, 3000)

                    sublime.set_timeout(_show, 0)

        elif ext == ".po":
            if addon:
                addon.update_labels()
                _remember_disk_state()

        save_duration = time.time() - save_start
        logger.debug("on_post_save_async COMPLETE: file=%s duration=%.3fs", os.path.basename(filename_full), save_duration)

        return None

    def on_pre_save_async(self, view):
        """Record whether this save follows a real edit, for post-save to skip a no-op."""
        self.is_modified = bool(view.is_dirty())

    def check_status(self):
        """Refresh the parsed tree, assign syntax, and re-init the addon if the project changed."""
        start = time.time()
        window = sublime.active_window()
        if window is None:
            return
        _sync_project(window)
        view = window.active_view()
        if view is None:
            return

        self.filename = view.file_name()
        self.root = None
        self.tree = None
        if not self.filename:
            return

        ext = os.path.splitext(self.filename)[1].lower()

        if INFOS and ext == ".xml":
            if _in_addon(self.filename):
                parse_start = time.time()
                self.root = get_root_from_file(self.filename)
                self.tree = ET.ElementTree(self.root)
                self._index_nodes()
                parse_elapsed = time.time() - parse_start
                if parse_elapsed > 0.5:
                    logger.warning("check_status XML parse SLOW: %.3fs file=%s", parse_elapsed, os.path.basename(self.filename))
                view.assign_syntax('Packages/KodiDevKit/KodiSkinXML.sublime-syntax')
        elif ext == ".po":
            view.assign_syntax('Packages/KodiDevKit/Gettext.sublime-syntax')
        elif ext == ".log":
            view.assign_syntax('Packages/KodiDevKit/KodiLog.sublime-syntax')

        total_elapsed = time.time() - start
        if total_elapsed > 1.0:
            logger.warning("check_status SLOW total: %.3fs file=%s", total_elapsed, self.filename)


