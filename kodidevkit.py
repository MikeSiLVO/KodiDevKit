"""KodiDevKit Sublime Text plugin — entry point and event handlers."""

from __future__ import annotations

import sublime_plugin
import sublime

import time
import re
import os
import html
from bisect import bisect_right

import logging
from lxml import etree as ET
from threading import Timer
import mdpopups

# Suppress mdpopups verbose logging (must happen before local imports that use logging)
logging.getLogger('MARKDOWN').setLevel(logging.WARNING)

from .libs import utils  # noqa: E402
from .libs import infoprovider  # noqa: E402
from .libs.kodi import kodi  # noqa: E402

INFOS = infoprovider.InfoProvider()
# sublime.log_commands(True)
SETTINGS_FILE = 'kodidevkit.sublime-settings'


CONST_ATTRIBUTES = {"x", "y", "width", "height", "center", "max", "min", "w", "h", "time",
                    "acceleration", "delay", "start", "end", "center", "border", "repeat"}


CONST_NODES = {"posx", "posy", "left", "centerleft", "right", "centerright", "top", "centertop",
               "bottom", "centerbottom", "width", "height", "offsetx", "offsety", "textoffsetx",
               "textoffsety", "textwidth", "spinposx", "spinposy", "spinwidth", "spinheight",
               "radioposx", "radioposy", "radiowidth", "radioheight", "markwidth", "markheight",
               "sliderwidth", "sliderheight", "itemgap", "bordersize", "timeperimage", "fadetime",
               "pauseatend", "depth"}

LABEL_TAGS = {"label", "label2", "altlabel", "property", "hinttext"}

VISIBLE_TAGS = {"visible", "enable", "usealttexture", "expression", "autoscroll", "selected"}

# Attributes on VISIBLE_TAGS that should not be evaluated as conditions
VISIBLE_TAG_ATTRIBUTES = {"allowhiddenfocus", "delay", "time", "repeat"}

# mdpopups CSS — fixed dark background so syntax colors pop regardless of theme
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
"""


POPUP_WRAP_COLUMN = 100


_WRAP_BREAK_CHARS = ",|+"


def _soft_wrap_source(text, max_col):
    """Hard-wrap long lines at `,`, `|`, `+` so minihtml has break points.

    minihtml only wraps on whitespace; long comma chains like
    `RunScript(a,b,c,...)` would otherwise overflow the popup edge. Walks
    each over-long line backward from `max_col` to the latest separator
    and splits there.
    """
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
                    cut = i + 1  # break AFTER the separator
                    break
            if cut < 0:
                break  # no breakable char before max_col
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
    # Prefer INFO unless already configured higher
    if root.level in (logging.NOTSET, logging.WARNING):
        root.setLevel(logging.INFO)

    pkg = logging.getLogger("KodiDevKit")
    pkg.propagate = True
    pkg.handlers.clear()


_setup_logging_once()

logger = logging.getLogger("KodiDevKit.kodidevkit")

# Active validation commands keyed by view id, so the Enter-handler can
# reach their callbacks.
_validation_commands = {}



def _on_settings_changed():
    s = sublime.load_settings(SETTINGS_FILE)
    KodiDevKit.settings = s

    try:
        if not INFOS:
            return
        from .libs.kodi import KodiJsonrpc
        kodi_client = getattr(INFOS, "kodi", None)
        if kodi_client:
            kodi_client.load_settings(s, force=True)
        else:
            INFOS.kodi = KodiJsonrpc(s)
            INFOS.kodi.load_settings(s, force=True)
        kodi.update_labels()
    except Exception:
        pass

    try:
        level = logging.DEBUG if bool(s.get("debug_mode", False)) else logging.INFO
        logging.getLogger("libs.skin").setLevel(level)
    except Exception:
        pass

    logger.info("settings reloaded from %s", SETTINGS_FILE)



def _show_fatal_xml_phantom():
    """If init_addon hit a broken XML file, open it and show an error phantom."""
    fatal = getattr(INFOS, "_fatal_xml_error", None)
    if not fatal:
        return
    from .libs.utils import last_xml_errors
    err = last_xml_errors[0] if last_xml_errors else None
    line_num = err.get("line", 1) if err else 1
    msg = err["message"] if err else "File could not be parsed"
    issues = [{
        "message": f"XML parse error: {msg}",
        "line": line_num,
        "file": fatal,
        "severity": "error",
        "type": "XML",
    }]

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


def plugin_loaded():
    """Sublime entry point: load settings, init INFOS, wire reload hooks."""
    import sublime
    from importlib import import_module

    settings = sublime.load_settings('kodidevkit.sublime-settings')

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

    global INFOS
    if 'INFOS' not in globals():
        try:
            infoprovider = import_module('.libs.infoprovider', __package__)
            INFOS = infoprovider.InfoProvider(settings)
        except Exception:
            INFOS = None

    try:
        if not INFOS:
            return
        if getattr(INFOS, "kodi", None) is None:
            kodi_mod = import_module('.libs.kodi.kodi', __package__)
            INFOS.kodi = kodi_mod.Kodi(settings)
        else:
            kodi_client = getattr(INFOS, "kodi", None)
            if kodi_client:
                kodi_client.load_settings(settings, force=True)
    except Exception:
        pass

    try:
        settings.add_on_change('kdk_settings_reload', _on_settings_changed)
    except Exception:
        pass
    kodi.update_labels()

    try:
        if INFOS:
            window = sublime.active_window()
            if window:
                variables = window.extract_variables()
                project_folder = variables.get("folder")
                if project_folder:
                    load_settings = getattr(INFOS, "load_settings", None)
                    init_addon = getattr(INFOS, "init_addon", None)
                    if load_settings and init_addon:
                        load_settings(settings)
                        init_addon(project_folder)
                        _show_fatal_xml_phantom()
    except Exception:
        pass


class KodiDevKit(sublime_plugin.EventListener):
    settings = {}  # type: ignore[assignment]
    _phantom_sets = {}  # Track PhantomSets by view.id()
    _validation_issues = {}  # Track validation issues by view.id()
    _media_cache = {}  # Cache media file completions per addon path
    _media_cache_timestamp = {}  # Track when media cache was last updated
    def __init__(self):
        super().__init__()
        self.is_modified = False
        self._modified_files = set()
        self._last_phantom_cleanup = 0

        self.settings = sublime.load_settings(SETTINGS_FILE)

        self.timer = None
        self._prev_selections = {}  # per-view selection tracking: {view_id: Region}

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
        """Return the deepest element whose start line <= row_one_based."""
        if not self._node_lines:
            return None
        idx = bisect_right(self._node_lines, row_one_based) - 1
        if idx < 0:
            return None
        return self._nodes[idx]

    @staticmethod
    def _issue_in_file(issue: dict, file_path: str) -> bool:
        """True if `issue`'s call site is in `file_path` (or it has no call site)."""
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
        """Render validation issues as inline phantoms, grouped by source line."""
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
                issue_items.append(f'<div class="issue-item">{badge}<span class="type">{issue_type}:</span> {msg}</div>')

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
        """Phantom link handler — dismiss the phantoms or jump to the next issue line."""
        view_id = view.id()

        if href == "hide":
            KodiDevKit._clear_phantoms(view)
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
        """Cached list of media files for autocomplete (TTL 30s)."""
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
        """Find the enclosing tag name by scanning the live buffer (no parsed tree needed)."""
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
        """Classify the completion site at `point`.

        Returns (kind, detail) where kind is one of:
          "tag_value"  inside <tag>|</tag>; detail = value-type string
          "attr_value" inside attr="|"; detail = value-type string
          "tag_name"   after `<`; detail = enclosing control type
        Returns (None, None) if nothing useful applies.
        """
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
                # Live-buffer tag name when the parsed tree is stale
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

        # Live-buffer tag name (works before the file is saved)
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
            "oninfo": "builtin",
        }
        hint = TAG_TYPE_HINTS.get(tag)
        if hint:
            return "tag_value", hint

        return None, None

    def _completions_for_type(self, value_type, addon, folder):
        """Build [trigger, completion] pairs for the given value type."""
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
            if inc_map:
                for nm in sorted(inc_map.keys()):
                    items.append([f"{nm}\tinclude", nm])
            else:
                for node in addon.includes.get(folder, []):
                    nm = node.get("name")
                    if nm:
                        items.append([f"{nm}\tinclude", nm])
            return items

        if value_type in ("path", "texture"):
            return self._get_media_completions(addon.media_path)

        if value_type == "condition":
            conditions = getattr(INFOS, "conditions", [])
            for nm, desc in conditions:
                items.append([f"{nm}\t{desc or 'condition'}", nm])
            return items

        if value_type == "builtin":
            builtins = getattr(INFOS, "builtins", [])
            for nm, desc in builtins:
                completion = nm
                for i, match in enumerate(re.findall(r"\([a-z,\]\[]+\)", completion)):
                    completion = completion.replace(match, f"(${i + 1})")
                items.append([f"{nm}\t{desc or 'builtin'}", completion])
            return items

        return items

    def on_query_completions(self, view, prefix, locations):
        start = time.time()
        if not INFOS:
            return []
        addon = getattr(INFOS, "addon", None)
        if not addon:
            return []

        filename = view.file_name()
        if not filename:
            return []

        scope_name = view.scope_name(locations[0])
        if "text.xml.kodi" not in scope_name:
            return []

        folder = os.path.basename(os.path.dirname(filename))

        ctx_type, detail = self._get_completion_context(view, locations[0])

        if ctx_type and detail:
            items = self._completions_for_type(detail, addon, folder)
            if items:
                elapsed = time.time() - start
                if elapsed > 0.2:
                    logger.warning("on_query_completions SLOW: %.3fs count=%d ctx=%s", elapsed, len(items), detail)
                flags = getattr(sublime, "INHIBIT_WORD_COMPLETIONS", 8)
                return (items, flags)

        # Generic fallback when no specific value-type was matched: includes + window names.
        items = []

        inc_map = getattr(addon, "include_map", {}).get(folder, {})
        if inc_map:
            for nm in sorted(inc_map.keys()):
                items.append([f"{nm}\tinclude", nm])
        else:
            for node in addon.includes.get(folder, []):
                nm = node.get("name")
                if nm:
                    items.append([f"{nm}\tinclude", nm])

        window_names = getattr(INFOS, "WINDOW_NAMES", [])
        for item in window_names:
            items.append([f"{item}\twindow", item])

        elapsed = time.time() - start
        if elapsed > 0.2:
            logger.warning("on_query_completions SLOW: %.3fs count=%d ctx=fallback", elapsed, len(items))

        return items

    def on_selection_modified_async(self, view):
        if not INFOS:
            return
        addon = getattr(INFOS, "addon", None)
        if not addon:
            return
        # Skip views without filenames (Find Results, scratch buffers, etc.)
        if not view.file_name():
            return
        sels = view.sel()
        if len(sels) != 1:
            return

        # Safely access selection (guard against race conditions)
        try:
            region = sels[0]
        except IndexError:
            return

        # Skip when text is selected (dragging, copy/paste, shift-click)
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
        """Build the tooltip body for the cursor's current context.

        Returns HTML/text to display, or None if nothing useful applies.
        """
        if not INFOS:
            return None

        sels = view.sel()
        if not sels:
            return None

        region = sels[0]
        scope_name = view.scope_name(region.b)
        line = view.line(region)

        if "source.python" in scope_name:
            line_contents = view.substr(line).lower().strip()
            if ("lang" in line_contents
                    or "label" in line_contents
                    or "string" in line_contents):
                word = view.substr(view.word(region))
                return_label = getattr(INFOS, "return_label", None)
                if return_label:
                    text = return_label(word)
                    if text:
                        return text
            return None

        if "text.xml.kodi" not in scope_name:
            return None
        # In XML comments, only fire if the text looks like a real Kodi expression.
        if "comment" in scope_name:
            comment_text = view.substr(view.extract_scope(region.b))
            if not re.search(
                r'\$INFO\[|\$VAR\[|\$ESCINFO\[|\$EXP\[|'
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
                # Match Kodi's bracket logic so nested [...] don't break the parse.
                close_bracket = self.find_end_bracket(line_text, '[', ']', open_bracket + 1)
                if close_bracket != -1 and close_bracket > cursor_offset:
                    token = line_text[dollar_pos:close_bracket + 1]

        if "[" in token:
            head = token.split("[", 1)[0]
            if head in {"INFO", "ESCINFO", "VAR", "ESCVAR", "EXP", "LOCALIZE", "ADDON", "$INFO", "$ESCINFO", "$VAR", "$ESCVAR", "$EXP", "$LOCALIZE", "$ADDON"}:
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

        if info_type in {"VAR", "ESCVAR", "EXP"}:
            content = self.get_formatted_include(selected_content, view)
            if content:
                return content

        if info_type in {"INFO", "ESCINFO"}:
            # If the cursor is inside [COLOR <name>...], let the color lookup handle it
            # instead of asking Kodi for an InfoLabel by that name.
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

        # Evaluate condition="..." attributes by sending them to Kodi.
        if element is not None and "condition" in element.attrib:
            if on_attr_name and scope_content.strip() == "condition":
                cond = element.attrib["condition"].strip()
                if cond and re.search(r"[A-Za-z]", cond):
                    if getattr(kodi, '_cooldown_until', 0) > time.time():
                        return None
                    result = kodi.request(
                        method="XBMC.GetInfoBooleans",
                        params={"booleans": [cond]},
                    )
                    if result:
                        key, value = result["result"].popitem()
                        if value is not None:
                            return "✅ <b>True</b>" if value else "❌ <b>False</b>"

        if "string.quoted.double.xml" in scope_name:
            content = scope_content[1:-1]

            if element is not None and "condition" in element.attrib:
                attr_region = view.find(r'condition\s*=\s*"[^"]*"', view.line(region).begin())
                if attr_region and attr_region.contains(region):
                    cond = utils.extract_expression_at_offset(line_text, cursor_offset) or selected_content.strip()
                    if cond and re.search(r"[A-Za-z]", cond):
                        if getattr(kodi, '_cooldown_until', 0) > time.time():
                            return None
                        result = kodi.request(
                            method="XBMC.GetInfoBooleans",
                            params={"booleans": [cond]},
                        )
                        if result:
                            key, value = result["result"].popitem()
                            if value is not None:
                                return "✅ <b>True</b>" if value else "❌ <b>False</b>"

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
                # Modern <include content="Name"> attribute form.
                attr_name = (element.attrib.get("content") or "").strip()
                if attr_name and sel == attr_name:
                    ref_name = attr_name
            if ref_name:
                include_content = self.get_formatted_include(ref_name, view)
                if include_content:
                    return include_content

        # Live-buffer fallback for <include>Name</include>, <font>Name</font>,
        # and <include content="Name"> (works before the file is saved).
        if element is None or element.tag not in ("include", "font"):
            ref_name = None
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
                    ref_name = ref_match.group(2).strip()
            if ref_name and selected_content.strip() in ref_name:
                include_content = self.get_formatted_include(ref_name, view)
                if include_content:
                    return include_content

        if element is not None and element.tag == "param":
            text = utils.extract_expression_at_offset(line_text, cursor_offset) or selected_content.strip()

            # Unresolved include params like <param name="visible">$PARAM[visible]</param>
            # have nothing meaningful to look up.
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
                    and re.search(r"[A-Za-z]", text)
                    and "entity.name.tag" not in view.scope_name(region.b)
                    and info_type not in {"INFO", "ESCINFO", "VAR", "ESCVAR", "EXP"}):
                if getattr(kodi, '_cooldown_until', 0) > time.time():
                    return None
                cond = text.strip()
                result = kodi.request(
                     method="XBMC.GetInfoBooleans",
                     params={"booleans": [cond]},
                )
                if result:
                    key, value = result["result"].popitem()
                    if value is not None:
                        return "✅ <b>True</b>" if value else "❌ <b>False</b>"

        owner = (
            visible_owner
            if (visible_owner is not None and visible_owner.tag in VISIBLE_TAGS)
            else element
        )
        if owner is not None and owner.tag in VISIBLE_TAGS:
            raw = selected_content.strip()

            if raw.startswith("</") or (raw.startswith("/") and ">" in raw):
                return None

            # Skip if the cursor sits past a closing tag (outside the element).
            text_before_cursor = line_text[:cursor_offset]
            last_close_bracket = text_before_cursor.rfind(">")
            last_open_bracket = text_before_cursor.rfind("<")

            if last_close_bracket > last_open_bracket and last_close_bracket >= 0:
                tag_content = text_before_cursor[last_open_bracket:last_close_bracket + 1]
                if tag_content.startswith("</"):
                    return None

            # Don't evaluate hover on visible-tag attributes like allowhiddenfocus / delay.
            if any(attr in raw.lower() for attr in VISIBLE_TAG_ATTRIBUTES):
                scope_name = view.scope_name(region.b)
                if "meta.attribute-with-value" in scope_name or "entity.other.attribute-name" in scope_name:
                    return None

            owner_tag = owner.tag.lower() if hasattr(owner, "tag") and owner is not None else ""
            if (
                "<" in raw
                or ">" in raw
                or raw.strip("/").lower() in VISIBLE_TAGS
                or raw.lower() == owner_tag
            ):
                cond = "".join(owner.itertext() or "").strip()
            else:
                cond = utils.extract_expression_at_offset(line_text, cursor_offset) or raw

            if "$PARAM[" in cond or cond.startswith("$PARAM"):
                return None

            # Keep [] grouping; only normalize whitespace around `+`.
            cond = cond.strip()
            cond = re.sub(r"\s*\+\s*", " + ", cond)

            if cond and re.search(r"[A-Za-z]", cond):
                result = kodi.request(
                     method="XBMC.GetInfoBooleans",
                     params={"booleans": [cond]},
                )
                if result:
                    key, value = result["result"].popitem()
                    if value is not None:
                        return "✅ <b>True</b>" if value else "❌ <b>False</b>"

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

        # Bare-name reference to a defined constant / expression / variable.
        # Kodi auto-expands these in whitelisted nodes (e.g. <fadetime>Foo</fadetime>)
        # without `$CONSTANT[]` syntax, so we surface their definitions on hover too.
        sel = selected_content.strip()
        if sel and re.match(r"^[A-Za-z_][\w\-]*$", sel):
            addon = getattr(INFOS, "addon", None)
            file_name = view.file_name()
            if addon and file_name:
                folder = os.path.basename(os.path.dirname(file_name))
                maps = (
                    getattr(addon, "constant_map", {}),
                    getattr(addon, "expression_map", {}),
                    getattr(addon, "variable_map", {}),
                )
                if any(sel in m.get(folder, {}) for m in maps):
                    content = self.get_formatted_include(sel, view)
                    if content:
                        return content

        return None

    @staticmethod
    def find_end_bracket(text, opener, closer, start_pos=0):
        """Find the matching closer for an already-opened bracket.

        Mirrors Kodi's StringUtils::FindEndBracket. `start_pos` is the position
        AFTER the opener (the search starts at depth 1). Returns the index of
        the matching closer, or -1 if unbalanced.
        """
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
    def get_formatted_include(content, view):
        """Render `content` (an include/font/variable/constant name) as a popup body.

        Resolves nested includes, constants, and expressions, then returns
        syntax-highlighted HTML. Plain string values (constants, expressions)
        are shown verbatim with no XML highlighting.
        """
        if not INFOS:
            return None
        file_path = view.file_name()
        if not file_path:
            return None

        addon = getattr(INFOS, "addon", None)
        if not addon:
            return None

        folder = os.path.basename(os.path.dirname(file_path))
        return_node = getattr(addon, "return_node", None)
        if not return_node:
            return None

        node = return_node(content, folder=folder)
        if not node:
            return None

        content_elem = node['content']
        resolve_xml = getattr(INFOS, "resolve_xml", None)

        # Normalize whatever return_node returned to a single lxml root.
        # Includes/variables/defaults yield an Element; fonts a serialized XML
        # string; constants/expressions a plain value (handled below).
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

        # resolve_xml deep-copies internally, so `root` isn't mutated.
        if resolve_xml:
            resolved = resolve_xml(root, folder=folder)
            if resolved is not None:
                root = resolved
                # Strip resolver-only `_kdk_*` provenance attribs from the popup output.
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

    def _is_definition_name_here(self, view, tag_names=("include", "variable")) -> bool:
        """True if the caret is inside an opening definition tag (`<include name="...">`).

        Used to suppress the tooltip on the definition itself (since the tooltip
        is meant for usages).
        """
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
            # `name=` distinguishes definitions from usage-only references.
            if "name=" in tag_text:
                return True

        return False

    def show_tooltip(self, view):
        """Show the mdpopups tooltip for the cursor's current context, if any."""
        if view is None or not view.is_valid():
            return

        window = view.window()
        if window is None or not view.file_name():
            return

        if self._is_definition_name_here(view, ("include", "variable")):
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
                        on_navigate=lambda href, vv=v: utils.jump_to_label_declaration(vv, href),
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
            # Editing must never break because popup teardown failed.
            pass

    def on_modified(self, view):
        start = time.time()
        self._hide_tooltip_only(view)
        if view.id() in KodiDevKit._phantom_sets:
            self._clear_phantoms(view)
            view.erase_status("kodidevkit_validation")
        elapsed = time.time() - start
        if elapsed > 0.1:
            logger.warning("on_modified SLOW: %.3fs view_id=%s", elapsed, view.id())

    def on_selection_modified(self, view):
        start = time.time()
        self._hide_tooltip_only(view)
        elapsed = time.time() - start
        if elapsed > 0.1:
            logger.warning("on_selection_modified SLOW: %.3fs view_id=%s", elapsed, view.id())

    def on_close(self, view):
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
        self.check_status()

    def on_activated_async(self, view):
        self.check_status()
        self._cleanup_orphaned_phantoms()

    def on_pre_close_window(self, window):
        """Forget validation commands tied to this window."""
        global _validation_commands
        _validation_commands.pop(window.id(), None)

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
        if not fname or not fname.lower().endswith(".xml"):
            return

        self._modified_files.add(fname)

    def on_post_save_async(self, view):
        """After saving an xml file: reload skin caches and revalidate the file."""
        import time
        save_start = time.time()

        if not INFOS:
            return None
        addon = getattr(INFOS, "addon", None)
        if not addon:
            return None

        filename_full = view.file_name()
        if not filename_full:
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

            filename = os.path.basename(filename_full)
            folder = os.path.basename(os.path.dirname(filename_full))

            addon.reload(filename_full)

            from .libs.utils import last_xml_errors

            self.root = utils.get_root_from_file(filename_full)
            if self.root is None:
                # Parse failed — surface the parse error inline as an error phantom.
                if last_xml_errors:
                    err = last_xml_errors[0]
                    issues = [{
                        "message": f"XML parse error: {err['message']}",
                        "line": err.get("line", 1),
                        "file": filename_full,
                        "severity": "error",
                        "type": "XML",
                    }]
                else:
                    issues = [{
                        "message": f"XML parse error: {os.path.basename(filename_full)} could not be parsed",
                        "line": 1,
                        "file": filename_full,
                        "severity": "error",
                        "type": "XML",
                    }]

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
                window.run_command("execute_builtin", {"builtin": "ReloadSkin()"})

            if window and self.settings.get("auto_skin_check", True):
                # Validate skin Settings.xml (1080i/720p/16x9) but skip addon settings.xml
                # under `resources/`, which has different schema.
                is_addon_settings = (
                    filename.lower() == "settings.xml"
                    and ("resources" in filename_full.replace("\\", "/").lower().split("/"))
                    and folder.lower() not in ["1080i", "720p", "16x9"]
                )

                if not is_addon_settings:
                    check_file = getattr(INFOS, "check_file", None)
                    all_issues = check_file(filename_full) if check_file else []

                    # None signals the file was skipped (e.g. shortcuts folder).
                    if all_issues is None:
                        sublime.set_timeout(lambda: self._clear_phantoms(view), 0)
                        return

                    # Drop issues below the configured severity, those from other
                    # files, and (optionally) include-originated warnings.
                    severity_rank = {"error": 0, "warning": 1}
                    min_level = self.settings.get("phantom_severity_level", "warning")
                    max_rank = severity_rank.get(min_level, 1)
                    hide_include_warnings = self.settings.get("phantom_hide_include_warnings", True)
                    issues = [
                        i for i in all_issues
                        if severity_rank.get(i.get("severity", "warning"), 1) <= max_rank
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

        save_duration = time.time() - save_start
        logger.debug("on_post_save_async COMPLETE: file=%s duration=%.3fs", os.path.basename(filename_full), save_duration)

        return None

    def on_pre_save_async(self, view):
        """Record whether this save follows a real edit (so post-save can skip no-ops)."""
        self.is_modified = bool(view.is_dirty())

    def check_status(self):
        """Refresh the parsed tree, assign syntax, and re-init the addon if the project changed."""
        start = time.time()
        window = sublime.active_window()
        if window is None:
            return
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
            addon = getattr(INFOS, "addon", None)
            if addon:
                parse_start = time.time()
                self.root = utils.get_root_from_file(self.filename)
                self.tree = ET.ElementTree(self.root)
                self._index_nodes()
                parse_elapsed = time.time() - parse_start
                if parse_elapsed > 0.5:
                    logger.warning("check_status XML parse SLOW: %.3fs file=%s", parse_elapsed, os.path.basename(self.filename))
                view.assign_syntax('Packages/KodiDevKit/KodiSkinXML.sublime-syntax')
        elif ext == ".po":
            view.assign_syntax('Packages/KodiDevKit/Gettext.tmLanguage')
        elif ext == ".log":
            view.assign_syntax('Packages/KodiDevKit/KodiLog.sublime-syntax')

        wnd = view.window()
        if wnd is None:
            return
        variables = wnd.extract_variables()
        project_folder = variables.get("folder")

        if INFOS and project_folder:
            addon = getattr(INFOS, "addon", None)
            if not addon or getattr(addon, 'path', None) != project_folder:
                logger.info("project change detected: %s", project_folder)
                init_start = time.time()
                load_settings = getattr(INFOS, "load_settings", None)
                init_addon = getattr(INFOS, "init_addon", None)
                if load_settings and init_addon:
                    load_settings(KodiDevKit.settings)
                    init_addon(project_folder)
                    _show_fatal_xml_phantom()
                init_elapsed = time.time() - init_start
                if init_elapsed > 1.0:
                    logger.warning("check_status init_addon SLOW: %.3fs project=%s", init_elapsed, project_folder)

            try:
                from .libs.kodi import KodiJsonrpc
                KodiJsonrpc(KodiDevKit.settings).load_settings(KodiDevKit.settings, force=True)
            except Exception:
                pass

        total_elapsed = time.time() - start
        if total_elapsed > 1.0:
            logger.warning("check_status SLOW total: %.3fs file=%s", total_elapsed, self.filename)


