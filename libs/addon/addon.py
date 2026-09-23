"""Kodi addon model shared by the skin and python-addon paths."""

from __future__ import annotations

import os
import logging
from typing import Any

from ..utils.files import check_paths, save_xml
from .translations import create_new_po_file, get_po_file
from ..utils.xml import get_root_from_file
from ..polib import polib

logger = logging.getLogger(__name__)
if not logger.handlers:
    # Avoid duplicate handlers after reloads; defer to root if present.
    logger.addHandler(logging.NullHandler())
logger.propagate = True

SETTINGS_FILE = 'kodidevkit.sublime-settings'


class Addon(object):
    """A Kodi addon: addon.xml metadata, language files, xml folders."""

    # github_ref syntax is parsed by scripts/refresh.py _resolve_ref
    RELEASES = [
        {"name": "omega", "gui_version": "5.17.0", "github_ref": "release:21.*-Omega"},
        {"name": "piers", "gui_version": "5.18.0", "github_ref": "branch:master"},
    ]

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

        self.settings: dict | Any = kwargs.get("settings") or {}

        path = kwargs.get("path")
        if not path or not isinstance(path, str):
            raise ValueError("Addon requires 'path' argument as string")
        self.path: str = path

        self.xml_file = os.path.join(self.path, "addon.xml")
        root = get_root_from_file(self.xml_file)
        if root is None:
            raise ValueError(f"Failed to parse addon.xml at {self.xml_file}")
        self.root = root

        self.api_version = self._resolve_release()

        self.version = self.root.attrib.get("version")
        for item in self.root.xpath("/addon[@id]"):
            self.name = item.attrib["id"]
            break

        self.load_xml_folders()
        self.update_xml_files()
        self.update_labels()

    def _release_from_addon_xml(self) -> str | None:
        """Release addon.xml implies; None here, only a skin's xbmc.gui version can tell."""
        return None

    def _resolve_release(self) -> str:
        """Kodi release this project targets: the setting, else addon.xml, else the newest."""
        override = str(self.settings.get("kodi_release") or "").strip().lower()
        if override:
            if any(item["name"] == override for item in self.RELEASES):
                return override
            logger.warning("Unknown kodi_release %r; supported: %s", override,
                           ", ".join(item["name"] for item in self.RELEASES))
        return self._release_from_addon_xml() or self.RELEASES[-1]["name"]

    @property
    def default_xml_folder(self):
        """The first xml folder found, used as the fallback."""
        return self.xml_folders[0]

    def load_xml_folders(self):
        """Record the Default/720p or 1080i skin folder when the addon has one."""
        paths = [os.path.join(self.path, "resources", "skins", "Default", "720p"),
                 os.path.join(self.path, "resources", "skins", "Default", "1080i")]
        folder = check_paths(paths)
        if folder:
            self.xml_folders.append(folder)

    @property
    def lang_path(self):
        """The `resources/language` folder."""
        return os.path.join(self.path, "resources", "language")

    @property
    def changelog_path(self):
        """Path to `changelog.txt`."""
        return os.path.join(self.path, "changelog.txt")

    @property
    def primary_lang_folder(self):
        """First language folder from settings, created on disk if missing."""
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
        """The skin's `Default/media` folder."""
        return os.path.join(self.path, "resources", "skins", "Default", "media")

    @staticmethod
    def by_project(path, settings):
        """Build a `Skin` or plain `Addon` for the project, decided by the xbmc.python import."""
        xml_file = os.path.join(path, "addon.xml")
        root = get_root_from_file(xml_file)
        if root is None or root.find(".//import[@addon='xbmc.python']") is None:
            from ..skin.skin import Skin
            return Skin(path=path, settings=settings)
        else:
            return Addon(path=path, settings=settings)

    def update_labels(self):
        """Reload `po_files` from the language folder."""
        self.po_files = self.get_po_files(self.lang_path)

    def get_po_files(self, folder):
        """PO files of the configured resource.language.* add-on, no English fallback."""
        po_files = []

        lang = (self.settings.get("language") or "").strip()
        if lang and not lang.startswith("resource.language."):
            lang = lang.lower().replace("-", "_")
            lang = f"resource.language.{lang}"
        if not lang:
            lang = "resource.language.en_gb"

        for item in [lang]:
            path = check_paths([
                os.path.join(folder, item, "resources", "strings.po"),
                os.path.join(folder, item, "strings.po"),
            ])
            if path:
                po = get_po_file(path)
                if po:
                    po.language = item  # type: ignore[attr-defined]
                    po_files.append(po)

        return po_files

    def update_xml_files(self):
        """Rebuild `window_files`: every .xml per folder except Font.xml."""
        self.window_files = {}
        for path in self.xml_folders:
            xml_folder = os.path.join(self.path, path)
            self.window_files[path] = []
            if not os.path.exists(xml_folder):
                return []
            for xml_file in sorted(os.listdir(xml_folder)):
                filename = os.path.basename(xml_file)
                if not filename.endswith(".xml"):
                    continue
                if filename.lower() not in ["font.xml"]:
                    self.window_files[path].append(xml_file)

    def create_new_label(self, word, filepath):
        """Add a label to the first PO file, creating it when none exists; returns the new id."""
        if not self.po_files:
            po_file = create_new_po_file(os.path.join(self.primary_lang_folder, "strings.po"))
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
        """Record the file as an occurrence on the label's PO entry, skin-range ids only."""
        if 31000 <= int(label_id[1:]) < 33000:
            entry = self.po_files[0].find(label_id, by="msgctxt")
            entry.occurrences.append((rel_path, None))
            self.po_files[0].save()

    def translate_path(self, path):
        """Absolute path of a texture, resolving special://skin/ or the media folder."""
        if path.startswith("special://skin/"):
            return os.path.join(self.path, path.replace("special://skin/", ""))
        else:
            return os.path.join(self.media_path, path)

    def return_node(self, keyword=None, folder=None):
        """Look up a font or include by name in the folder, ignoring any param tail."""
        if not keyword or not folder:
            return None

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
        """No-op for python addons; overridden by Skin."""
        pass

    def get_xml_files(self):
        """Get the absolute path of every window file, yielded one at a time."""
        if self.xml_folders:
            for folder in self.xml_folders:
                for xml_file in self.window_files[folder]:
                    yield os.path.join(self.path, folder, xml_file)

    def bump_version(self, version):
        """Bump the version in addon.xml and open a blank changelog entry for it."""
        self.root.attrib["version"] = version
        save_xml(self.xml_file, self.root)
        with open(self.changelog_path, "r") as f:
            contents = f.readlines()
        contents = [version, "", "-", "-", "", ""] + contents
        with open(self.changelog_path, "w") as changelog_file:
            changelog_file.write("\n".join(contents))

    def get_constants(self, folder):
        """Get constants; always empty, python add-ons have none."""
        return []

    @staticmethod
    def _safe_version_tuple(text):
        """Tuple from a dotted version, cut at the first non-numeric part; None if empty."""
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
