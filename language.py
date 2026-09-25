"""Language file operations: reload, move labels to PO."""

from __future__ import annotations

import difflib
import logging

import sublime
import sublime_plugin

logger = logging.getLogger("KodiDevKit.language")

SETTINGS_FILE = 'kodidevkit.sublime-settings'


def _infos():
    from .kodidevkit import INFOS
    return INFOS


class KodidevkitReloadKodiLanguageFilesCommand(sublime_plugin.WindowCommand):
    """Command to manually reload language files."""

    def run(self):
        from .libs.kodi.jsonrpc import kodi
        infos = _infos()
        if infos:
            load_settings = getattr(infos, "load_settings", None)
            if load_settings:
                load_settings(sublime.load_settings(SETTINGS_FILE))
        kodi.update_labels()
        if infos:
            addon = getattr(infos, "addon", None)
            if addon:
                addon.update_labels()


class KodidevkitMoveToLanguageFileCommand(sublime_plugin.TextCommand):
    """Move selected text to default .po file (or create .po file if not existing)."""

    def is_visible(self):
        scope_name = self.view.scope_name(self.view.sel()[0].b)
        infos = _infos()
        if not infos:
            return False
        addon = getattr(infos, "addon", None)
        if addon and addon.po_files:
            if "text.xml.kodi" in scope_name or "source.python" in scope_name:
                return self.view.sel()[0].b != self.view.sel()[0].a
        return False

    def run(self, edit):
        infos = _infos()
        if not infos:
            return None
        get_po_files = getattr(infos, "get_po_files", None)
        if not get_po_files:
            return None
        region = self.view.sel()[0]
        if region.begin() == region.end():
            logger.critical("Please select the complete label")
            return False
        addon = getattr(infos, "addon", None)
        own = {id(po) for po in addon.po_files} if addon else set()
        own_name = "Skin" if addon and addon.type == "skin" else "Add-on"
        by_text = {}
        for po_file in get_po_files():
            source = own_name if id(po_file) in own else "Kodi"
            for entry in po_file:
                if entry.msgid:
                    by_text.setdefault(entry.msgid.lower(), []).append((entry, source))

        key = self.view.substr(region).lower()
        similar = difflib.get_close_matches(key, list(by_text), n=10, cutoff=0.75)
        ranked = [(key, "exact")] + [(text, "similar") for text in similar if text != key]
        self.label_ids = []
        self.labels = []
        for text, kind in ranked:
            for entry, source in by_text.get(text, []):
                if entry.msgctxt not in self.label_ids:
                    self.label_ids.append(entry.msgctxt)
                    self.labels.append([entry.msgid, f"{source} {entry.msgctxt}, {kind}"])
        create = ["Create new label", "Add the selected text to the language file"]
        if key in by_text:
            self.label_ids.append(None)
            self.labels.append(create)
        else:
            self.label_ids.insert(0, None)
            self.labels.insert(0, create)
        sublime.active_window().show_quick_panel(items=self.labels,
                                                 on_select=lambda s: self.on_done(s, region),
                                                 selected_index=0)

    def on_done(self, index, region):
        if index == -1:
            return None
        infos = _infos()
        if not infos:
            return None
        addon = getattr(infos, "addon", None)
        if not addon or not addon.path:
            return None
        region = self.view.sel()[0]
        file_name = self.view.file_name()
        if not file_name:
            return None
        rel_path = file_name.replace(addon.path, "").replace("\\", "/")
        if self.label_ids[index] is None:
            create_new_label = getattr(addon, "create_new_label", None)
            if not create_new_label:
                return None
            label_id = create_new_label(word=self.view.substr(region),
                                       filepath=rel_path)
            if label_id is None:
                return None
        else:
            label_id = self.label_ids[index][1:]
            attach_occurrence = getattr(addon, "attach_occurrence_to_label", None)
            if attach_occurrence:
                attach_occurrence(label_id, rel_path)
        self.view.run_command("kodidevkit_replace_text", {"label_id": label_id})


class KodidevkitReplaceTextCommand(sublime_plugin.TextCommand):
    """Replace selected text with label from `label_id`."""

    def run(self, edit, label_id):
        infos = _infos()
        if not infos:
            return None
        build_translate_label = getattr(infos, "build_translate_label", None)
        if not build_translate_label:
            return None
        for region in self.view.sel():
            new = build_translate_label(int(label_id), self.view)
            self.view.replace(edit, region, new)
