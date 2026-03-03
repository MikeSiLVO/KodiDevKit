"""
Skin-related commands: search, navigation, validation quick panel.
"""

from __future__ import annotations

import os
import re
import logging
import threading
import webbrowser
from xml.sax.saxutils import escape

import sublime
import sublime_plugin

from .libs import utils

logger = logging.getLogger("KodiDevKit.skin_commands")


def _infos():
    from .kodidevkit import INFOS
    return INFOS


def _validation_commands():
    from .kodidevkit import _validation_commands
    return _validation_commands


SETTINGS_FILE = 'kodidevkit.sublime-settings'


class QuickPanelCommand(sublime_plugin.WindowCommand):
    """Parent class with callbacks to show location and select text."""

    nodes: list[dict[str, str | int]]

    def is_visible(self):
        infos = _infos()
        if not infos:
            return False
        return bool(getattr(infos, "addon", None))

    def on_done(self, index):
        if index == -1:
            return None
        node = self.nodes[index]
        view = self.window.open_file("%s:%i" % (node["file"], node["line"]),
                                     sublime.ENCODED_POSITION)
        self.select_text(view, node)

    def show_preview(self, index):
        if index >= 0:
            node = self.nodes[index]
            self.window.open_file(
                "%s:%i" % (node["file"], node["line"]),
                sublime.ENCODED_POSITION | sublime.TRANSIENT
            )

    @staticmethod
    def select_text(view, node, retry_count=0):
        """Select text in view. Uses non-blocking retry via set_timeout if view still loading."""
        if view.is_loading():
            if retry_count >= 50:
                logger.warning("Timeout waiting for view to load: %s", node.get("file", "unknown"))
                return False
            sublime.set_timeout(lambda: QuickPanelCommand.select_text(view, node, retry_count + 1), 100)
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


class ShowFontRefsCommand(QuickPanelCommand):
    def run(self):
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
        folder = file_name.split(os.sep)[-2]

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


class SearchFileForLabelsCommand(QuickPanelCommand):
    def run(self):
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


class CheckVariablesCommand(QuickPanelCommand):
    """Start skin check with *check_type and show results in QuickPanel."""
    def run(self, check_type):
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
        """Run validation in background thread, then update UI on main thread."""
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
                nodes = (check_file(filename) if check_file else []) or []
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
        """Show validation results (must run on main thread)."""
        self.nodes = nodes
        self.window.status_message(f"Validation complete: {len(nodes)} issues found")

        is_placeholder = (
            len(self.nodes) == 1
            and isinstance(self.nodes[0], dict)
            and str(self.nodes[0].get("message", "")).lower().startswith("no ")
        )

        if self.nodes and not is_placeholder:
            listitems = [
                [str(i.get("message", "")), "%s: %s" % (os.path.basename(str(i.get("file", ""))), i.get("line", 0))]
                for i in self.nodes
            ]

            self.window.settings().set('kodidevkit_validation_pending', {
                'listitems': listitems,
                'window_id': self.window.id()
            })
            logger.debug(f"CheckVariablesCommand: Stored {len(listitems)} items for window {self.window.id()}")

            vc = _validation_commands()
            vc[self.window.id()] = self
            logger.debug("CheckVariablesCommand: Stored command instance in _validation_commands")

            self.progress.show_completion(len(self.nodes), close_on_issues=False)
        else:
            self.progress.show_completion(0, close_on_issues=False)
            self.window.status_message("✅ Validation complete: No issues found")

    def on_done(self, index):
        if index == -1:
            return

        item = self.nodes[index]
        path = (item.get("file") or "").strip()
        line = int(item.get("line") or 0)

        if not path:
            sublime.message_dialog(item.get("message") or "No issues")
            return

        if not os.path.isfile(path):
            return

        self.window.open_file("%s:%d" % (path, line), sublime.ENCODED_POSITION)


class CloseKodidevkitCompletionViewCommand(sublime_plugin.TextCommand):
    """Close the validation completion view (triggered by Enter key)."""

    def run(self, edit):
        """Close the current view and show quick panel if validation results are pending."""
        window = self.view.window()
        if not window:
            self.view.close()
            return

        validation_data = window.settings().get('kodidevkit_validation_pending')

        if validation_data:
            window_id = validation_data.get('window_id')
            listitems = validation_data.get('listitems', [])

            vc = _validation_commands()
            command = vc.get(window_id)

            if command and listitems:
                window.settings().erase('kodidevkit_validation_pending')
                vc.pop(window_id, None)

                self.view.close()

                window.show_quick_panel(
                    items=listitems,
                    on_select=command.on_done,
                    selected_index=0,
                    on_highlight=command.show_preview,
                )
                return

        self.view.close()

    def is_enabled(self):
        """Only enable in completion views."""
        return self.view.settings().get("kodidevkit_completion_view", False)


class SearchForLabelCommand(sublime_plugin.WindowCommand):
    """Search through all core / addon labels and insert selected entry."""

    def is_visible(self):
        infos = _infos()
        if not infos:
            return False
        addon = getattr(infos, "addon", None)
        get_po_files = getattr(infos, "get_po_files", None)
        return bool(addon) and bool(get_po_files and get_po_files())

    def run(self):
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


class _SearchAndInsertCommand(sublime_plugin.WindowCommand):
    """Base for commands that show a list from InfoProvider and insert the selection."""
    _data_attr = ""  # override in subclass

    def run(self):
        infos = _infos()
        if not infos:
            return None
        self._items = getattr(infos, self._data_attr, [])
        listitems = [[item[0], item[1]] for item in self._items]
        self.window.show_quick_panel(items=listitems,
                                     on_select=self._on_done,
                                     selected_index=0)

    def _on_done(self, index):
        if index == -1:
            return None
        view = self.window.active_view()
        if not view:
            return None
        view.run_command("insert", {"characters": self._items[index][0]})


class SearchForBuiltinCommand(_SearchAndInsertCommand):
    _data_attr = "builtins"


class SearchForVisibleConditionCommand(_SearchAndInsertCommand):
    _data_attr = "conditions"


class SearchForJsonCommand(sublime_plugin.WindowCommand):
    """Search through JSONRPC Introspect results."""
    @utils.run_async
    def run(self):
        from .libs.kodi import kodi
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
        if index == -1:
            return None
        view = self.window.active_view()
        if not view:
            return None
        view.run_command("insert", {"characters": str(self.listitems[index][0])})


class SearchForImageCommand(sublime_plugin.TextCommand):
    """Search through all files in media folder via QuickPanel."""
    def is_visible(self):
        infos = _infos()
        if not infos:
            return False
        addon = getattr(infos, "addon", None)
        return bool(addon and addon.media_path)

    def run(self, edit):
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
        items = ["Insert path", "Open Image"]
        if index >= 0:
            sublime.active_window().show_quick_panel(items=items,
                                                     on_select=lambda s: self.insert_char(s, index),
                                                     selected_index=0)
        else:
            sublime.active_window().focus_view(self.view)

    def insert_char(self, index, fileindex):
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
        if index >= 0:
            infos = _infos()
            if not infos:
                return
            addon = getattr(infos, "addon", None)
            if not addon or not addon.media_path:
                return
            file_path = os.path.join(addon.media_path, self.files[index])
            sublime.active_window().open_file(file_path, sublime.TRANSIENT)


class SearchForFontCommand(sublime_plugin.TextCommand):
    """Search through all fonts from Fonts.xml via QuickPanel."""

    def is_visible(self):
        infos = _infos()
        if not infos:
            return False
        addon = getattr(infos, "addon", None)
        return bool(addon and addon.fonts)

    def run(self, edit):
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
        folder = file_name.split(os.sep)[-2]
        self.fonts = [
            [i["name"], "%s  -  %s" % (i["size"], i["filename"])]
            for i in addon.fonts[folder]
        ]
        sublime.active_window().show_quick_panel(items=self.fonts,
                                                 on_select=self.on_done,
                                                 selected_index=0)

    def on_done(self, index):
        if index >= 0:
            self.view.run_command("insert", {"characters": self.fonts[index][0]})
        sublime.active_window().focus_view(self.view)


class GoToTagCommand(sublime_plugin.WindowCommand):
    """Jump to include/font/etc."""

    def run(self):
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
        position = go_to_tag(keyword=utils.get_node_content(view, flags),
                            folder=file_name.split(os.sep)[-2])
        if position:
            self.window.open_file(position, sublime.ENCODED_POSITION)


class OpenSkinImageCommand(sublime_plugin.WindowCommand):
    """Open image with default OS image tool."""

    def is_visible(self):
        infos = _infos()
        if not infos:
            return False
        addon = getattr(infos, "addon", None)
        if not addon or not addon.media_path:
            return False
        view = self.window.active_view()
        if not view:
            return False
        content = utils.get_node_content(view=view,
                                         flags=sublime.CLASS_WORD_START | sublime.CLASS_WORD_END)
        if not content or ("/" not in content and "\\" not in content):
            return False
        translate_path = getattr(addon, "translate_path", None)
        if not translate_path:
            return False
        return os.path.exists(translate_path(content))

    @utils.run_async
    def run(self, pack_textures=True):
        infos = _infos()
        if not infos:
            return None
        addon = getattr(infos, "addon", None)
        if not addon:
            return None
        path = utils.get_node_content(view=self.window.active_view(),
                                      flags=sublime.CLASS_WORD_START | sublime.CLASS_WORD_END)
        translate_path = getattr(addon, "translate_path", None)
        if not translate_path:
            return None
        imagepath = translate_path(path)
        if not os.path.exists(imagepath):
            return None
        webbrowser.open(imagepath)


class PreviewImageCommand(sublime_plugin.TextCommand):
    """Show image preview of selected text inside SublimeText."""
    def is_visible(self):
        infos = _infos()
        if not infos:
            return False
        addon = getattr(infos, "addon", None)
        if not addon or not addon.media_path:
            return False
        flags = sublime.CLASS_WORD_START | sublime.CLASS_WORD_END
        content = utils.get_node_content(self.view, flags)
        if not content:
            return False
        return "/" in content or "\\" in content

    def run(self, edit):
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
        path = utils.get_node_content(self.view, flags)
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
        sublime.active_window().focus_view(self.view)

    def show_preview(self, index):
        if index >= 0:
            file_path = self.files[index]
            sublime.active_window().open_file(file_path, sublime.TRANSIENT)


class OpenActiveWindowXmlFromRemoteCommand(sublime_plugin.WindowCommand):
    """Checks currently active window via JSON and opens corresponding XML file."""
    @utils.run_async
    def run(self):
        from .libs.kodi import kodi
        view = self.window.active_view()
        if not view:
            return
        file_name = view.file_name()
        if not file_name:
            return

        try:
            folder = file_name.split(os.sep)[-2]
        except Exception:
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


class SwitchXmlFolderCommand(QuickPanelCommand):
    """Switch to same file in different XML folder if available."""

    def is_visible(self):
        infos = _infos()
        if not infos:
            return False
        addon = getattr(infos, "addon", None)
        return bool(addon) and len(addon.xml_folders) > 1

    def run(self):
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
        filename = os.path.basename(file_name)
        for folder in addon.xml_folders:
            node = {"file": os.path.join(addon.path, folder, filename),
                    "line": line + 1}
            self.nodes.append(node)
        self.window.show_quick_panel(items=list(addon.xml_folders),
                                     on_select=self.on_done,
                                     selected_index=0,
                                     on_highlight=self.show_preview)

    def on_done(self, index):
        if index == -1:
            return None
        node = self.nodes[index]
        self.window.open_file("%s:%i" % (node["file"], node["line"]),
                              sublime.ENCODED_POSITION)


class ShowDependenciesCommand(sublime_plugin.WindowCommand):
    """Show all possible dependencies for open addon."""
    def is_visible(self):
        infos = _infos()
        if not infos:
            return False
        return bool(getattr(infos, "addon", None))

    def run(self):
        infos = _infos()
        if not infos:
            return None
        addon = getattr(infos, "addon", None)
        if not addon:
            return None
        api_version = getattr(addon, "api_version", None)
        if not api_version:
            return None
        addons = utils.get_addons(api_version)
        self.ids = list(addons.keys())
        items = [[aid, addons[aid]] for aid in self.ids]
        self.window.show_quick_panel(
            items=items,
            on_select=self.on_done,
            selected_index=0
        )

    def on_done(self, index):
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
