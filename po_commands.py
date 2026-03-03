"""
Language file operations: reload, convert, move labels to PO.
"""

from __future__ import annotations

import os
import logging

import sublime
import sublime_plugin

from .libs import utils

logger = logging.getLogger("KodiDevKit.po_commands")

SETTINGS_FILE = 'kodidevkit.sublime-settings'


def _infos():
    from .kodidevkit import INFOS
    return INFOS


class ReloadKodiLanguageFilesCommand(sublime_plugin.WindowCommand):
    """Command to manually reload language files."""

    def run(self):
        from .libs.kodi import kodi
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


class ConvertXmlToPoCommand(sublime_plugin.WindowCommand):
    """Convert legacy .xml language files to .po format."""

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
        primary_lang_folder = getattr(addon, "primary_lang_folder", None)
        if not primary_lang_folder:
            return None
        for item in os.listdir(primary_lang_folder):
            if item.endswith(".xml"):
                path = os.path.join(primary_lang_folder, item)
                utils.convert_xml_to_po(path)


class MoveToLanguageFileCommand(sublime_plugin.TextCommand):
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
        self.label_ids = []
        self.labels = []
        region = self.view.sel()[0]
        if region.begin() == region.end():
            logger.critical("Please select the complete label")
            return False
        word = self.view.substr(region)
        for po_file in get_po_files():
            for entry in po_file:
                if entry.msgid.lower() == word.lower() and entry.msgctxt not in self.label_ids:
                    self.label_ids.append(entry.msgctxt)
                    self.labels.append(["%s (%s)" % (entry.msgid, entry.msgctxt), entry.comment])
        self.labels.append("Create new label")
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
        if self.labels[index] == "Create new label":
            create_new_label = getattr(addon, "create_new_label", None)
            if not create_new_label:
                return None
            label_id = create_new_label(word=self.view.substr(region),
                                       filepath=rel_path)
        else:
            label_id = self.label_ids[index][1:]
            attach_occurrence = getattr(addon, "attach_occurrence_to_label", None)
            if attach_occurrence:
                attach_occurrence(label_id, rel_path)
        self.view.run_command("replace_text", {"label_id": label_id})


class ReplaceTextCommand(sublime_plugin.TextCommand):
    """Replace selected text with label from *label_id."""

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
