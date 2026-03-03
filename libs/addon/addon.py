"""
KodiDevKit is a plugin to assist with Kodi skinning / scripting
using Sublime Text 4
"""

from __future__ import annotations

import os
import logging
from typing import Any

from .. import utils
from .. import polib

logger = logging.getLogger(__name__)
if not logger.handlers:
    # Avoid duplicate handlers after reloads; defer to root if present.
    logger.addHandler(logging.NullHandler())
logger.propagate = True

SETTINGS_FILE = 'kodidevkit.sublime-settings'


class Addon(object):
    """
    Represents a kodi addon with path *project_path and *settings
    """

    RELEASES = [{"gui_version": '5.17.0',
                 "python_version": "3.0.1",
                 "name": "omega"},
                {"gui_version": '5.18.0',
                 "python_version": "3.0.1",
                 "name": "piers"}]

    LANG_START_ID = 32000
    LANG_OFFSET = 2

    def __init__(self, *args, **kwargs):
        self.type = "python"
        self.po_files = []
        self.colors = []
        self.color_labels = set()
        self.fonts = {}
        self.xml_folders = []
        self.window_files = {}
        self.include_files = {}
        self.font_file = None
        self.includes = {}
        self.api_version = None

        settings = kwargs.get("settings")
        if settings is None:
            try:
                import sublime
                self.settings: dict | Any = sublime.load_settings(SETTINGS_FILE)
            except Exception:
                self.settings = {}
        else:
            self.settings = settings

        # Accept both legacy and new kwarg names
        path = kwargs.get("path") or kwargs.get("project_path")
        if not path or not isinstance(path, str):
            raise ValueError("Addon requires 'path' or 'project_path' argument as string")
        self.path: str = path

        self.xml_file = os.path.join(self.path, "addon.xml")
        root = utils.get_root_from_file(self.xml_file)
        if root is None:
            raise ValueError(f"Failed to parse addon.xml at {self.xml_file}")
        self.root = root

        # Determine API name from xbmc.python import
        api_import = self.root.find(".//import[@addon='xbmc.python']")
        if api_import is not None:
            api_version = api_import.attrib.get("version")
            parsed_api_version = self._safe_version_tuple(api_version)
            if parsed_api_version is not None:
                for item in self.RELEASES:
                    target_version = self._safe_version_tuple(item["python_version"])
                    if target_version is None:
                        continue
                    if parsed_api_version <= target_version:
                        self.api_version = item["name"]
                        break

        # Basic metadata
        self.version = self.root.attrib.get("version")
        for item in self.root.xpath("/addon[@id]"):
            self.name = item.attrib["id"]
            break

        self.load_xml_folders()
        self.update_xml_files()
        self.update_labels()

    @property
    def default_xml_folder(self):
        """
        returns the fallback xml folder as a string
        """
        return self.xml_folders[0]

    def load_xml_folders(self):
        """
        find and load skin xml folder if existing
        """
        paths = [os.path.join(self.path, "resources", "skins", "Default", "720p"),
                 os.path.join(self.path, "resources", "skins", "Default", "1080i")]
        folder = utils.check_paths(paths)
        if folder:
            self.xml_folders.append(folder)

    @property
    def lang_path(self):
        """
        returns the add-on language folder path
        """
        return os.path.join(self.path, "resources", "language")

    @property
    def changelog_path(self):
        """
        returns the add-on language folder path
        """
        return os.path.join(self.path, "changelog.txt")

    @property
    def primary_lang_folder(self):
        """
        returns default language folder (first one from settings file)
        """
        lang_folders = self.settings.get("language_folders")
        if not lang_folders:
            lang_folders = ["resource.language.en_gb"]
        lang_folder = lang_folders[0]
        lang_path = os.path.join(self.path, "resources", "language", lang_folder)
        if not os.path.exists(lang_path):
            os.makedirs(lang_path)
        return lang_path

    @property
    def media_path(self):
        """
        returns the add-on media folder path
        """
        return os.path.join(self.path, "resources", "skins", "Default", "media")

    @staticmethod
    def by_project(project_path, settings):
        """
        factory, return proper instance based on addon.xml
        """
        xml_file = os.path.join(project_path, "addon.xml")
        root = utils.get_root_from_file(xml_file)
        if root is None or root.find(".//import[@addon='xbmc.python']") is None:
            from .. import skin
            return skin.Skin(project_path=project_path,
                             settings=settings)
        else:
            return Addon(project_path=project_path,
                         settings=settings)
            # TODO: parse all python skin folders correctly

    def update_labels(self):
        """
        get addon po files and update po files list
        """
        self.po_files = self.get_po_files(self.lang_path)

    def get_po_files(self, folder):
        """
        Return PO files from Kodi language add-ons under `folder`.
        Only resource.language.* is considered. No 'English' fallback.
        """
        po_files = []

        # Resolve preferred language to resource.language.<code>
        lang = (self.settings.get("language") or "").strip()
        if lang and not lang.startswith("resource.language."):
            lang = lang.lower().replace("-", "_")
            lang = f"resource.language.{lang}"
        if not lang:
            lang = "resource.language.en_gb"

        for item in [lang]:
            path = utils.check_paths([
                os.path.join(folder, item, "resources", "strings.po"),
                os.path.join(folder, item, "strings.po"),
            ])
            if path:
                po = utils.get_po_file(path)
                if po:
                    po.language = item  # type: ignore[attr-defined]
                    po_files.append(po)

        return po_files

    def update_xml_files(self):
        """
        update list of all include and window xmls
        """
        self.window_files = {}
        for path in self.xml_folders:
            xml_folder = os.path.join(self.path, path)
            self.window_files[path] = []
            if not os.path.exists(xml_folder):
                return []
            for xml_file in os.listdir(xml_folder):
                filename = os.path.basename(xml_file)
                if not filename.endswith(".xml"):
                    continue
                if filename.lower() not in ["font.xml"]:
                    self.window_files[path].append(xml_file)

    def create_new_label(self, word, filepath):
        """
        adds a label to the first pofile from settings (or creates new one if non-existing)
        """
        if not self.po_files:
            po_file = utils.create_new_po_file(os.path.join(self.primary_lang_folder, "strings.po"))
            po_file.save()
            self.po_files.append(po_file)
            logger.critical("New language file created")
        else:
            po_file = self.po_files[0]
        string_ids = []
        for entry in po_file:
            try:
                string_ids.append(int(entry.msgctxt[1:]))
            except Exception:
                string_ids.append(entry.msgctxt)
        label_id = self.LANG_START_ID
        for label_id in range(self.LANG_START_ID, self.LANG_START_ID + 1000):
            if label_id not in string_ids:
                break
        entry = polib.POEntry(msgid=word,
                              msgstr="",
                              msgctxt="#%s" % label_id,
                              occurrences=[(filepath, None)])
        po_file.insert(index=int(label_id) - self.LANG_START_ID + self.LANG_OFFSET,
                       entry=entry)
        po_file.save()
        self.update_labels()
        return label_id

    def attach_occurrence_to_label(self, label_id, rel_path):
        """
        add *rel_path to label with *label id as a file comment
        """
        if 31000 <= int(label_id[1:]) < 33000:
            entry = self.po_files[0].find(label_id, by="msgctxt")
            entry.occurrences.append((rel_path, None))
            self.po_files[0].save()

    def translate_path(self, path):
        """
        return translated path for textures
        """
        if path.startswith("special://skin/"):
            return os.path.join(self.path, path.replace("special://skin/", ""))
        else:
            return os.path.join(self.media_path, path)

    def return_node(self, keyword=None, folder=False):
        """
        get value from include list

        Supports lookups with parameters like "MyVar,(prefix,suffix)"
        by extracting just the variable/include name before the first comma.
        """
        if not keyword or not folder:
            return None

        # e.g., "MyVar,(prefix,suffix)" -> "MyVar"
        lookup_name = keyword.split(',')[0] if ',' in keyword else keyword

        if folder in self.fonts:
            for node in self.fonts[folder]:
                if node["name"] == lookup_name:
                    return node
        if folder in self.includes:
            for node in self.includes[folder]:
                if node["name"] == lookup_name:
                    return node
        return None

    def reload(self, path):
        """
        update include, color and font infos (not needed yet for python)
        """
        pass

    def get_xml_files(self):
        """
        yields absolute paths of all window files
        """
        if self.xml_folders:
            for folder in self.xml_folders:
                for xml_file in self.window_files[folder]:
                    yield os.path.join(self.path, folder, xml_file)

    def bump_version(self, version):
        """
        bump addon.xml version and create changelog entry
        """
        self.root.attrib["version"] = version
        utils.save_xml(self.xml_file, self.root)
        with open(self.changelog_path, "r") as f:
            contents = f.readlines()
        contents = [version, "", "-", "-", "", ""] + contents
        with open(self.changelog_path, "w") as changelog_file:
            changelog_file.write("\n".join(contents))

    def get_constants(self, folder):
        """
        returns empty list because Kodi python add-ons do not support constants yet
        """
        return []

    @staticmethod
    def _safe_version_tuple(text):
        """
        Return a comparable tuple for dotted version strings.
        Non-numeric segments terminate parsing; invalid inputs return None.
        """
        if not text:
            return None
        parts = []
        for item in str(text).split("."):
            if not item:
                parts.append(0)
                continue
            num = ""
            for ch in item:
                if ch.isdigit():
                    num += ch
                else:
                    break
            if not num:
                break
            parts.append(int(num))
        return tuple(parts) if parts else None
