"""Skin commands: label, font, image and builtin search, jump to definitions and the checks."""

from __future__ import annotations

import os
import re
import logging
import threading
import webbrowser
from xml.sax.saxutils import escape

import sublime
import sublime_plugin

from .libs.utils.files import get_addons
from .libs.sublime.view import get_node_content
from .libs.utils.decorators import run_async

logger = logging.getLogger("KodiDevKit.skin")


def _infos():
    """Look up the plugin's shared InfoProvider at call time."""
    from .kodidevkit import INFOS
    return INFOS


SETTINGS_FILE = 'kodidevkit.sublime-settings'

CHECK_LABELS = {
    "general": "General",
    "file": "File",
    "variable": "Variables",
    "include": "Includes",
    "map": "Maps",
    "image": "Images",
    "font": "Fonts",
    "label": "Labels",
    "id": "IDs",
    "filecheck": "File Integrity",
    "repo": "Kodi Repo",
}

RESULT_FILE_REGEX = r"^(\S.*\.[A-Za-z0-9]+)\s*$"
RESULT_LINE_REGEX = r"^\s+([0-9]+)\s"


def _rel_path(file_path, base_dir):
    """Path relative to the skin root when it sits inside it, else as-is."""
    if base_dir:
        try:
            candidate = os.path.relpath(file_path, base_dir)
            if not candidate.startswith(".."):
                return candidate
        except (ValueError, OSError):
            pass
    return file_path


def _as_int(value):
    """The value as an int, 0 when it is not one."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _results_body(nodes, base_dir):
    """Results view body: issues under their file headers, pathless ones last as plain text."""
    by_file = {}
    pathless = []
    for issue in nodes:
        file_path = str(issue.get("file", ""))
        if file_path:
            by_file.setdefault(file_path, []).append(issue)
        else:
            pathless.append(issue)

    blocks = []
    for file_path in sorted(by_file):
        rows = sorted(by_file[file_path], key=lambda i: _as_int(i.get("line", 0)))
        lines = "\n".join(
            f"{_as_int(i.get('line', 0)):>7}  {str(i.get('message', ''))}" for i in rows
        )
        blocks.append(f"{_rel_path(file_path, base_dir)}\n{lines}")

    if pathless:
        lines = "\n".join(f"         {str(i.get('message', ''))}" for i in pathless)
        blocks.append(f"Skin-wide\n{lines}")

    return "\n\n".join(blocks)


class _QuickPanelMixin:
    """Quick-panel callbacks (open node location, select text); pair with `WindowCommand`."""

    nodes: list[dict[str, str | int]]
    window: sublime.Window

    def is_visible(self):
        """True when an add-on is loaded."""
        infos = _infos()
        if not infos:
            return False
        return bool(getattr(infos, "addon", None))

    def on_done(self, index):
        """Open the picked row's file at its line and select its identifier."""
        if index == -1:
            return None
        node = self.nodes[index]
        view = self.window.open_file("%s:%i" % (node["file"], node["line"]),
                                     sublime.ENCODED_POSITION)
        self.select_text(view, node)

    def show_preview(self, index):
        """Preview the highlighted row's file at its line."""
        if index >= 0:
            node = self.nodes[index]
            self.window.open_file(
                "%s:%i" % (node["file"], node["line"]),
                sublime.ENCODED_POSITION | sublime.TRANSIENT
            )

    @staticmethod
    def select_text(view, node, retry_count=0):
        """Select `node['identifier']` on `node['line']`, retrying while the view loads."""
        if view.is_loading():
            if retry_count >= 50:
                logger.warning("Timeout waiting for view to load: %s", node.get("file", "unknown"))
                return False
            sublime.set_timeout(lambda: _QuickPanelMixin.select_text(view, node, retry_count + 1), 100)
            return None

        view.sel().clear()
        if "identifier" in node:
            text_point = view.text_point(node["line"] - 1, 0)
            line_contents = view.substr(view.line(text_point))
            label = escape(node["identifier"])
            if line_contents.count(label) != 1:
                return False
            line_start = line_contents.find(label)
            line_end = line_start + len(label)
            view.sel().add(sublime.Region(text_point + line_start, text_point + line_end))
        return True


class KodidevkitShowFontRefsCommand(_QuickPanelMixin, sublime_plugin.WindowCommand):
    """Quick panel of the font references in the current file's xml folder."""

    def run(self):
        """Show the folder's font references, previewing each as it is highlighted."""
        self.nodes = []
        view = self.window.active_view()
        if not view:
            return None
        file_name = view.file_name()
        if not file_name:
            return None
        infos = _infos()
        if not infos:
            return None
        addon = getattr(infos, "addon", None)
        if not addon:
            return None
        font_refs = addon.resource_loader.get_font_references(addon.window_files)
        if not font_refs:
            return None
        folder = addon.xml_folder_of(file_name)

        self.nodes = font_refs.get(folder, [])

        if not self.nodes:
            logger.critical("No references found")
            return

        items = [
            [n.get("name", ""), f"{os.path.basename(str(n.get('file','')))}: {n.get('line', 0)}"]
            for n in self.nodes
        ]
        self.window.show_quick_panel(
            items=items,
            on_select=self.on_done,
            selected_index=0,
            on_highlight=self.show_preview,
        )


class KodidevkitSearchFileForLabelsCommand(_QuickPanelMixin, sublime_plugin.WindowCommand):
    """Quick panel of the labels the current file uses, with their text."""

    def run(self):
        """Show each label the file uses with its text, previewing each as it is highlighted."""
        self.nodes = []
        items = []

        view = self.window.active_view()
        if not view:
            return None
        path = view.file_name()
        if not path:
            return None

        infos = _infos()
        if not infos:
            return None
        get_po_files = getattr(infos, "get_po_files", None)
        if not get_po_files:
            return None

        labels = []
        label_ids = []
        regexs = [
            r"\$LOCALIZE\[([0-9].*?)\]",
            r"\$ADDON\[.*?([0-9].*?)\]",
            r"(?:label|property|altlabel|label2)>([0-9].*?)<",
        ]

        for po_file in get_po_files():
            labels += [s.msgid for s in po_file]
            label_ids += [s.msgctxt for s in po_file]

        with open(path, encoding="utf8") as text_file:
            for i, line in enumerate(text_file.readlines(), start=1):
                for regex in regexs:
                    for match in re.finditer(regex, line):
                        label_id = "#" + match.group(1)
                        if label_id in label_ids:
                            idx = label_ids.index(label_id)
                            msg = "%s (%s)" % (labels[idx], label_id)
                            self.nodes.append({"file": path, "line": i})
                            items.append([msg, f"{os.path.basename(path)}: {i}"])

        if not items:
            logger.critical("No references found")
            return

        self.window.show_quick_panel(
            items=items,
            on_select=self.on_done,
            selected_index=0,
            on_highlight=self.show_preview,
        )


class KodidevkitCheckVariablesCommand(_QuickPanelMixin, sublime_plugin.WindowCommand):
    """Command running one skin check and showing its issues in a results view."""

    def run(self, check_type):
        """Open a progress view and run the check in the background."""
        from .libs.sublime.scratch import ValidationProgressView
        self.progress = ValidationProgressView(self.window, check_type)

        if check_type == "file":
            view = self.window.active_view()
            if not view:
                return None
            filename = view.file_name()
            if not filename:
                return None
            self.progress.update(f"Validating {os.path.basename(filename)}...\n")
        else:
            self.progress.update(f"Running {check_type} validation...\n")

        thread = threading.Thread(
            target=self._run_validation_async,
            args=(check_type,)
        )
        thread.daemon = True
        thread.start()

    def _run_validation_async(self, check_type):
        """Run the check off the main thread, then hand the issues back to the main thread."""
        def progress_callback(*args):
            if len(args) == 3:
                path, current, total = args
                self.progress.show_file_progress(os.path.basename(path), current, total)
            elif len(args) == 1:
                message = args[0]
                self.progress.update(message)
            else:
                logger.warning(f"Unexpected progress_callback signature: {len(args)} args")

        try:
            infos = _infos()
            if check_type == "file":
                view = self.window.active_view()
                if not view:
                    return
                filename = view.file_name()
                if not filename:
                    return
                logger.info("[checks] start type=file path=%s", filename)
                self.progress.update(f"Checking file: {os.path.basename(filename)}")
                if not infos:
                    return
                check_file = getattr(infos, "check_file", None)
                nodes = [n for n in (check_file(filename) if check_file else None) or [] if not n.get("muted")]
                logger.info("[checks] done type=file issues=%d", len(nodes))
            else:
                logger.info("[checks] start type=%s", check_type)
                self.progress.update("Initializing validation...")

                if not infos:
                    return
                get_check_listitems = getattr(infos, "get_check_listitems", None)
                nodes = get_check_listitems(check_type, progress_callback=progress_callback) if get_check_listitems else []
                logger.info("[checks] done type=%s issues=%d", check_type, len(nodes))

        except Exception as exc:
            logger.exception("[checks] unexpected error type=%s", check_type)
            error_msg = str(exc)
            self.progress.update(f"\n❌ ERROR: {error_msg}")
            sublime.set_timeout(
                lambda: sublime.message_dialog(f"Check failed: {check_type}\n{error_msg}"),
                0
            )
            return

        sublime.set_timeout(lambda: self._show_results(nodes, check_type), 0)

    def _show_results(self, nodes, check_type):
        """Show the results on the main thread: a dialog when clean, else a results view."""
        self.nodes = nodes
        label = CHECK_LABELS.get(check_type, "Validation")

        no_issues = (
            not nodes
            or (
                len(nodes) == 1
                and isinstance(nodes[0], dict)
                and str(nodes[0].get("message", "")).lower().startswith("no ")
            )
        )

        if no_issues:
            self.window.status_message(f"✅ {label}: No issues found")

            def reveal_clean():
                self.progress.close_sync()
                sublime.message_dialog(f"{label}: No issues found")

            sublime.set_timeout(reveal_clean, self.progress.remaining_min_display_ms())
            return

        self.window.status_message(
            f"{label}: {len(nodes)} issue{'s' if len(nodes) != 1 else ''} found"
        )

        addon = getattr(_infos(), "addon", None)
        base_dir = getattr(addon, "path", "") or "" if addon is not None else ""

        file_count = len({str(i.get("file", "")) for i in nodes if i.get("file")})
        n = len(nodes)
        summary = f"{n} issue{'s' if n != 1 else ''}"
        if file_count:
            summary += f" in {file_count} file{'s' if file_count != 1 else ''}"
        header = (
            f"{label} validation  -  {summary}\n"
            "Double-click a line to open  -  F4 / Shift+F4 to step through\n"
            f"{chr(0x2500) * 60}\n\n"
        )

        def reveal():
            self.progress.to_results_view(
                name=f"🔍 {label}",
                content=header + _results_body(nodes, base_dir) + "\n",
                file_regex=RESULT_FILE_REGEX,
                line_regex=RESULT_LINE_REGEX,
                base_dir=base_dir,
            )

        sublime.set_timeout(reveal, self.progress.remaining_min_display_ms())


class KodidevkitSearchForLabelCommand(sublime_plugin.WindowCommand):
    """Quick-panel label search; inserts the pick as a localize expression shaped for its scope."""

    def is_visible(self):
        """True when an add-on with language files is loaded."""
        infos = _infos()
        if not infos:
            return False
        addon = getattr(infos, "addon", None)
        get_po_files = getattr(infos, "get_po_files", None)
        return bool(addon) and bool(get_po_files and get_po_files())

    def run(self):
        """Show every label, once per id, in a quick panel."""
        infos = _infos()
        if not infos:
            return None
        get_po_files = getattr(infos, "get_po_files", None)
        if not get_po_files:
            return None
        listitems = []
        self.ids = []
        for po_file in get_po_files():
            for entry in po_file:
                if entry.msgctxt not in self.ids:
                    self.ids.append(entry.msgctxt)
                    listitems.append(["%s (%s)" % (entry.msgid, entry.msgctxt), entry.comment])
        self.window.show_quick_panel(items=listitems,
                                     on_select=self.label_search_ondone_action,
                                     selected_index=0)

    def label_search_ondone_action(self, index):
        """Insert the picked label's localize expression at the caret."""
        if index == -1:
            return None
        infos = _infos()
        view = self.window.active_view()
        if not view or not infos:
            return None
        label_id = int(self.ids[index][1:])
        build_translate_label = getattr(infos, "build_translate_label", None)
        if not build_translate_label:
            return None
        view.run_command("insert",
                         {"characters": build_translate_label(label_id, view)})


class _SearchAndInsertMixin:
    """Quick-panel search of the `InfoProvider` list a subclass names; inserts the pick."""

    _data_attr = ""
    window: sublime.Window

    def run(self):
        """Show the subclass's list in a quick panel."""
        infos = _infos()
        if not infos:
            return None
        self._items = getattr(infos, self._data_attr, [])
        listitems = [[item[0], item[1]] for item in self._items]
        self.window.show_quick_panel(items=listitems,
                                     on_select=self._on_done,
                                     selected_index=0)

    def _on_done(self, index):
        """Insert the picked entry at the caret."""
        if index == -1:
            return None
        view = self.window.active_view()
        if not view:
            return None
        view.run_command("insert", {"characters": self._items[index][0]})


class KodidevkitSearchForBuiltinCommand(_SearchAndInsertMixin, sublime_plugin.WindowCommand):
    """Quick-panel search of Kodi's builtins; inserts the pick at the caret."""

    _data_attr = "builtins"


class KodidevkitSearchForVisibleConditionCommand(_SearchAndInsertMixin, sublime_plugin.WindowCommand):
    """Quick-panel search of Kodi's boolean conditions; inserts the pick at the caret."""

    _data_attr = "conditions"


class KodidevkitSearchForJsonCommand(sublime_plugin.WindowCommand):
    """Quick-panel search of a running Kodi's JSON-RPC types, methods and notifications."""

    @run_async
    def run(self):
        """Ask Kodi for its JSON-RPC schema and list every name in a quick panel."""
        from .libs.kodi.jsonrpc import kodi
        result = kodi.request(method="JSONRPC.Introspect")

        if not result or "result" not in result:
            logger.warning("JSONRPC.Introspect returned no result")
            return

        self.listitems = [[k, str(v)] for k, v in result["result"]["types"].items()]
        self.listitems += [[k, str(v)] for k, v in result["result"]["methods"].items()]
        self.listitems += [[k, str(v)] for k, v in result["result"]["notifications"].items()]
        self.window.show_quick_panel(items=self.listitems,
                                     on_select=self.builtin_search_on_done,
                                     selected_index=0)

    def builtin_search_on_done(self, index):
        """Insert the picked name at the caret."""
        if index == -1:
            return None
        view = self.window.active_view()
        if not view:
            return None
        view.run_command("insert", {"characters": str(self.listitems[index][0])})


class KodidevkitSearchForImageCommand(sublime_plugin.TextCommand):
    """Quick-panel browse of the media files; inserts the path or opens the image."""

    def is_visible(self):
        """True when the add-on has a media folder."""
        infos = _infos()
        if not infos:
            return False
        addon = getattr(infos, "addon", None)
        return bool(addon and addon.media_path)

    def run(self, edit):
        """List the media files, previewing each as it is highlighted."""
        infos = _infos()
        if not infos:
            return None
        addon = getattr(infos, "addon", None)
        if not addon:
            return None
        self.files = [i for i in addon.resource_loader.load_media_files(addon.media_path)]
        sublime.active_window().show_quick_panel(items=self.files,
                                                 on_select=self.on_done,
                                                 selected_index=0,
                                                 on_highlight=self.show_preview)

    def on_done(self, index):
        """Offer to insert the picked file's path or open it; refocus the view on cancel."""
        items = ["Insert path", "Open Image"]
        if index >= 0:
            sublime.active_window().show_quick_panel(items=items,
                                                     on_select=lambda s: self.insert_char(s, index),
                                                     selected_index=0)
        else:
            sublime.active_window().focus_view(self.view)

    def insert_char(self, index, fileindex):
        """Insert the picked file's path, or open it in the system viewer."""
        if index == 0:
            self.view.run_command("insert", {"characters": self.files[fileindex]})
        elif index == 1:
            infos = _infos()
            if not infos:
                return
            addon = getattr(infos, "addon", None)
            if not addon or not addon.media_path:
                return
            full = os.path.join(addon.media_path, self.files[fileindex])
            if os.name == "nt":
                if hasattr(os, 'startfile'):
                    os.startfile(full)  # type: ignore[attr-defined]
            else:
                webbrowser.open(full)
        sublime.active_window().focus_view(self.view)

    def show_preview(self, index):
        """Preview the highlighted media file in a transient view."""
        if index >= 0:
            infos = _infos()
            if not infos:
                return
            addon = getattr(infos, "addon", None)
            if not addon or not addon.media_path:
                return
            file_path = os.path.join(addon.media_path, self.files[index])
            sublime.active_window().open_file(file_path, sublime.TRANSIENT)


class KodidevkitSearchForFontCommand(sublime_plugin.TextCommand):
    """Quick-panel pick from Font.xml; inserts the chosen font name."""

    def is_visible(self):
        """True when the add-on has fonts."""
        infos = _infos()
        if not infos:
            return False
        addon = getattr(infos, "addon", None)
        return bool(addon and addon.fonts)

    def run(self, edit):
        """List the fonts of the current file's xml folder with their size and file."""
        infos = _infos()
        if not infos:
            return None
        addon = getattr(infos, "addon", None)
        if not addon or not addon.fonts:
            return None
        file_name = self.view.file_name()
        if not file_name:
            return None
        self.fonts = []
        folder = addon.xml_folder_of(file_name)
        self.fonts = [
            [i["name"], "%s  -  %s" % (i["size"], i["filename"])]
            for i in addon.fonts[folder]
        ]
        sublime.active_window().show_quick_panel(items=self.fonts,
                                                 on_select=self.on_done,
                                                 selected_index=0)

    def on_done(self, index):
        """Insert the picked font name and refocus the view."""
        if index >= 0:
            self.view.run_command("insert", {"characters": self.fonts[index][0]})
        sublime.active_window().focus_view(self.view)


_REFERENCE_KINDS = (
    (re.compile(r"\$(?:ESC)?VAR\[[^\[\]]*$"), ("variable",)),
    (re.compile(r"\$(?:ESC)?MAP\[[^\[\]]*$"), ("map",)),
    (re.compile(r"\$EXP\[[^\[\]]*$"), ("expression",)),
    (re.compile(r'<include\b(?:[^>]*\bcontent="[^"]*|[^>]*>[^<]*)$'), ("include",)),
    (re.compile(r"<font>[^<]*$"), ("font",)),
)


def _reference_kinds(view):
    """Definition kinds the reference under the caret can name, or None when it could be any."""
    point = view.sel()[0].b
    before = view.substr(sublime.Region(view.line(point).begin(), point))
    return next((kinds for pattern, kinds in _REFERENCE_KINDS if pattern.search(before)), None)


class KodidevkitGoToTagCommand(sublime_plugin.WindowCommand):
    """Command jumping to the definition of the include, font, color or label under the cursor."""

    def run(self):
        """Jump to where the word under the cursor is defined, looked up in its xml folder."""
        infos = _infos()
        if not infos:
            return None
        go_to_tag = getattr(infos, "go_to_tag", None)
        if not go_to_tag:
            return None
        flags = sublime.CLASS_WORD_START | sublime.CLASS_WORD_END
        view = self.window.active_view()
        if not view:
            return None
        file_name = view.file_name()
        if not file_name:
            return None
        addon = getattr(infos, "addon", None)
        if not addon:
            return None
        position = go_to_tag(keyword=get_node_content(view, flags),
                             folder=addon.xml_folder_of(file_name), kinds=_reference_kinds(view))
        if position:
            self.window.open_file(position, sublime.ENCODED_POSITION)


class KodidevkitOpenSkinImageCommand(sublime_plugin.WindowCommand):
    """Command opening the image path under the cursor in the system's default viewer."""

    def is_visible(self):
        """True when the path under the cursor names an existing file of the skin."""
        infos = _infos()
        if not infos:
            return False
        addon = getattr(infos, "addon", None)
        if not addon or not addon.media_path:
            return False
        view = self.window.active_view()
        if not view:
            return False
        content = get_node_content(view=view,
                                   flags=sublime.CLASS_WORD_START | sublime.CLASS_WORD_END)
        if not content or ("/" not in content and "\\" not in content):
            return False
        translate_path = getattr(addon, "translate_path", None)
        if not translate_path:
            return False
        return os.path.exists(translate_path(content))

    @run_async
    def run(self, pack_textures=True):
        """Open the image under the cursor in the system's default viewer."""
        infos = _infos()
        if not infos:
            return None
        addon = getattr(infos, "addon", None)
        if not addon:
            return None
        path = get_node_content(view=self.window.active_view(),
                                flags=sublime.CLASS_WORD_START | sublime.CLASS_WORD_END)
        translate_path = getattr(addon, "translate_path", None)
        if not translate_path:
            return None
        imagepath = translate_path(path)
        if not os.path.exists(imagepath):
            return None
        webbrowser.open(imagepath)


class KodidevkitPreviewImageCommand(sublime_plugin.TextCommand):
    """Command previewing the image path under the cursor in a transient view."""

    def is_visible(self):
        """True when the text under the cursor looks like a path, in a skin with a media folder."""
        infos = _infos()
        if not infos:
            return False
        addon = getattr(infos, "addon", None)
        if not addon or not addon.media_path:
            return False
        flags = sublime.CLASS_WORD_START | sublime.CLASS_WORD_END
        content = get_node_content(self.view, flags)
        if not content:
            return False
        return "/" in content or "\\" in content

    def run(self, edit):
        """List the image, or each image in the folder, previewing each as it is highlighted."""
        infos = _infos()
        if not infos:
            return None
        addon = getattr(infos, "addon", None)
        if not addon:
            return None
        translate_path = getattr(addon, "translate_path", None)
        if not translate_path:
            return None
        flags = sublime.CLASS_WORD_START | sublime.CLASS_WORD_END
        path = get_node_content(self.view, flags)
        imagepath = translate_path(path)
        if not os.path.exists(imagepath):
            return None
        if os.path.isdir(imagepath):
            self.files = []
            for (root, _dirs, filenames) in os.walk(imagepath):
                self.files.extend([os.path.join(root, f) for f in filenames])
                break
        else:
            self.files = [imagepath]
        sublime.active_window().show_quick_panel(items=self.files,
                                                 on_select=self.on_done,
                                                 selected_index=0,
                                                 on_highlight=self.show_preview)

    def on_done(self, index):
        """Refocus the view once the panel closes."""
        sublime.active_window().focus_view(self.view)

    def show_preview(self, index):
        """Preview the highlighted image in a transient view."""
        if index >= 0:
            file_path = self.files[index]
            sublime.active_window().open_file(file_path, sublime.TRANSIENT)


class KodidevkitOpenActiveWindowXmlFromRemoteCommand(sublime_plugin.WindowCommand):
    """Command asking Kodi which window xml is active and opening it locally."""

    @run_async
    def run(self):
        """Open the active window's xml file Kodi names, else the skin's copy, this folder first."""
        from .libs.kodi.jsonrpc import kodi
        view = self.window.active_view()
        if not view:
            return
        file_name = view.file_name()
        if not file_name:
            return

        result = kodi.request(
            method="XBMC.GetInfoLabels",
            params={"labels": ["Window.Property(xmlfile)"]},
        )
        if not result or "result" not in result:
            logger.warning("GetInfoLabels(Window.Property(xmlfile)) returned no result")
            return

        _, value = result["result"].popitem()
        if not value:
            logger.debug("No xmlfile property set on active window")
            return

        if os.path.exists(value):
            self.window.open_file(value)
            return

        infos = _infos()
        if not infos:
            return
        addon = getattr(infos, "addon", None)
        if not addon or not addon.path:
            return

        folder = addon.xml_folder_of(file_name)
        files_in_folder = addon.window_files.get(folder, [])
        for xml_file in files_in_folder:
            if xml_file == value:
                path = os.path.join(addon.path, folder, xml_file)
                self.window.open_file(path)
                return

        for fldr, files in addon.window_files.items():
            if value in files:
                path = os.path.join(addon.path, fldr, value)
                self.window.open_file(path)
                return

        logger.debug("OpenActiveWindowXmlFromRemote: no match for %r in any folder", value)


class KodidevkitSwitchXmlFolderCommand(_QuickPanelMixin, sublime_plugin.WindowCommand):
    """Command opening the same filename in another resolution folder, such as 1080i or 720p."""

    def is_visible(self):
        """True for a skin with more than one xml folder."""
        infos = _infos()
        if not infos:
            return False
        addon = getattr(infos, "addon", None)
        return bool(addon) and len(addon.xml_folders) > 1

    def run(self):
        """List the xml folders, previewing the same file at the same line in each."""
        infos = _infos()
        if not infos:
            return None
        addon = getattr(infos, "addon", None)
        if not addon or not addon.path:
            return None
        view = self.window.active_view()
        if not view:
            return None
        file_name = view.file_name()
        if not file_name:
            return None
        self.nodes = []
        line, _ = view.rowcol(view.sel()[0].b)
        filename = os.path.relpath(file_name, os.path.join(addon.path, addon.xml_folder_of(file_name)))
        for folder in addon.xml_folders:
            node = {"file": os.path.join(addon.path, folder, filename),
                    "line": line + 1}
            self.nodes.append(node)
        self.window.show_quick_panel(items=list(addon.xml_folders),
                                     on_select=self.on_done,
                                     selected_index=0,
                                     on_highlight=self.show_preview)

    def on_done(self, index):
        """Open the file in the picked folder at the same line."""
        if index == -1:
            return None
        node = self.nodes[index]
        self.window.open_file("%s:%i" % (node["file"], node["line"]),
                              sublime.ENCODED_POSITION)


class KodidevkitShowDependenciesCommand(sublime_plugin.WindowCommand):
    """Command listing the Kodi repo's add-ons for this release, with mirror links."""
    def is_visible(self):
        """True when an add-on is loaded."""
        infos = _infos()
        if not infos:
            return False
        return bool(getattr(infos, "addon", None))

    def run(self):
        """List the Kodi repo's add-ons for this release, with their versions."""
        infos = _infos()
        if not infos:
            return None
        addon = getattr(infos, "addon", None)
        if not addon:
            return None
        api_version = getattr(addon, "api_version", None)
        if not api_version:
            return None
        addons = get_addons(api_version)
        self.ids = list(addons.keys())
        items = [[aid, addons[aid]] for aid in self.ids]
        self.window.show_quick_panel(
            items=items,
            on_select=self.on_done,
            selected_index=0
        )

    def on_done(self, index):
        """Open the picked add-on's page on the Kodi mirror."""
        if index == -1:
            return
        infos = _infos()
        if not infos:
            return
        addon = getattr(infos, "addon", None)
        if not addon:
            return
        addon_id = self.ids[index]
        api_version = getattr(addon, "api_version", None)
        repo = (api_version or "omega").strip()
        url = f"https://mirrors.kodi.tv/addons/{repo}/{addon_id}/"
        webbrowser.open(url)
