"""Kodi addon model shared by the skin and python-addon paths."""

from __future__ import annotations

import os
import re
import logging
from typing import Any

from ..utils.files import check_paths, is_inside
from .translations import create_new_po_file, get_po_file
from ..utils.xml import get_root_from_file
from ..polib import polib

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.propagate = True

SETTINGS_FILE = 'kodidevkit.sublime-settings'


class Addon:
    """A Kodi addon: addon.xml metadata, language files, xml folders."""

    # github_ref syntax is parsed by scripts/refresh.py _resolve_ref
    RELEASES = [
        {"name": "omega", "gui_version": "5.17.0", "gui_abi": "5.17.0", "github_ref": "release:21.*-Omega"},
        {"name": "piers", "gui_version": "5.18.0", "gui_abi": "5.17.0", "github_ref": "branch:master"},
    ]

    LANG_START_ID = 32000
    LANG_OFFSET = 2

    def __init__(self, *, path=None, settings=None):
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
        self.validation_index = None
        self.notices: list[str] = []
        self._index_builder = None

        self.settings: dict | Any = settings or {}

        if not path or not isinstance(path, str):
            raise ValueError("Addon requires 'path' argument as string")
        self.path: str = path

        self.xml_file = os.path.join(self.path, "addon.xml")
        root = get_root_from_file(self.xml_file)
        if root is None:
            raise ValueError(f"Failed to parse addon.xml at {self.xml_file}")
        self.root = root

        self.api_version = self._resolve_release()

        self.version = self.root.get("version")
        self.name = self.root.get("id")

        self.load_xml_folders()
        self.update_xml_files()
        self.update_labels()

    def _release_from_addon_xml(self) -> str | None:
        """Release addon.xml implies; None here, only a skin's xbmc.gui version can tell."""
        return None

    def _resolve_release(self) -> str:
        """Kodi release to target: the setting, else addon.xml, else newest; a bad setting noted."""
        override = str(self.settings.get("kodi_release") or "").strip().lower()
        if override and any(item["name"] == override for item in self.RELEASES):
            return override
        release = self._release_from_addon_xml() or self.RELEASES[-1]["name"]
        if override:
            self.add_notice(f"Unknown kodi_release '{override}', checked against {release} instead; "
                            f"known: {', '.join(item['name'] for item in self.RELEASES)}")
        return release

    def add_notice(self, message):
        """Add and log a notice of something weakening this run's results, skipping repeats."""
        if message not in self.notices:
            self.notices.append(message)
            logger.warning(message)

    @property
    def default_xml_folder(self):
        """The first xml folder found, used as the fallback."""
        return self.xml_folders[0]

    def load_xml_folders(self):
        """Load the Default/720p or 1080i skin folder when the addon has one."""
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
        """Build a `Skin` or plain `Addon` for the project, by its first non-metadata extension."""
        root = get_root_from_file(os.path.join(path, "addon.xml"))
        points = [] if root is None else [
            ext.get("point") for ext in root.findall("extension")
            if ext.get("point") not in ("xbmc.addon.metadata", "kodi.addon.metadata")]
        if not points or points[0] == "xbmc.gui.skin":
            from ..skin.skin import Skin
            return Skin(path=path, settings=settings)
        return Addon(path=path, settings=settings)

    def update_labels(self):
        """Update `po_files` from the language folder."""
        self.po_files = self.get_po_files(self.lang_path)

    def get_po_files(self, folder):
        """Get the PO files of the configured resource.language.* add-on, no English fallback."""
        po_files = []

        lang = (self.settings.get("language") or "").strip()
        if lang and not lang.startswith("resource.language."):
            lang = lang.lower().replace("-", "_")
            lang = f"resource.language.{lang}"
        if not lang:
            lang = "resource.language.en_gb"

        path = check_paths([
            os.path.join(folder, lang, "resources", "strings.po"),
            os.path.join(folder, lang, "strings.po"),
        ])
        if path:
            po = get_po_file(path)
            if po:
                po.language = lang  # type: ignore[attr-defined]
                po_files.append(po)

        return po_files

    @property
    def index_builder(self):
        """The index builder over every window, built on first use."""
        if self._index_builder is None:
            from ..skin.index import SkinIndex
            self._index_builder = SkinIndex(self)
        return self._index_builder

    def update_xml_files(self):
        """Update `window_files`: every .xml under each folder but Font.xml, dropping the index."""
        self.validation_index = None
        self.window_files = {}
        for path in self.xml_folders:
            xml_folder = os.path.join(self.path, path)
            self.window_files[path] = []
            for dirpath, dirnames, filenames in os.walk(xml_folder):
                dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
                for name in sorted(filenames):
                    rel = os.path.relpath(os.path.join(dirpath, name), xml_folder)
                    if name.endswith(".xml") and rel.lower() != "font.xml":
                        self.window_files[path].append(rel)

    def xml_folder_of(self, path):
        """The xml folder holding the file at any depth, else the name of its parent folder."""
        for folder in self.xml_folders:
            if is_inside(path, os.path.join(self.path, folder)):
                return folder
        return os.path.basename(os.path.dirname(path))

    def create_new_label(self, word, filepath):
        """Add a label to the first PO file, creating it when none exists; None when ids run out."""
        if not self.po_files:
            po_file = create_new_po_file(os.path.join(self.primary_lang_folder, "strings.po"))
            po_file.save()
            self.po_files.append(po_file)
            logger.critical("New language file created")
        else:
            po_file = self.po_files[0]
        used = {entry.msgctxt for entry in po_file}
        last_id = self.LANG_START_ID + 999
        label_id = next((i for i in range(self.LANG_START_ID, last_id + 1) if f"#{i}" not in used),
                        None)
        if label_id is None:
            logger.critical(f"No label added: every id from {self.LANG_START_ID} to {last_id} "
                            f"is taken in {po_file.fpath}")
            return None
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
        """Attach the file as an occurrence to the label, if the add-on's own PO file defines it."""
        if not self.po_files:
            return
        entry = self.po_files[0].find(f"#{label_id}", by="msgctxt")
        if entry is None or any(path == rel_path for path, _ in entry.occurrences):
            return
        entry.occurrences.append((rel_path, None))
        self.po_files[0].save()

    def translate_path(self, path):
        """Translate a texture path to absolute, via special://skin/ or the media folder."""
        if path.startswith("special://skin/"):
            return os.path.join(self.path, path.replace("special://skin/", ""))
        else:
            return os.path.join(self.media_path, path)

    def return_node(self, keyword=None, folder=None):
        """Look up a font or include by name in the folder, ignoring any param tail."""
        if not keyword or not folder:
            return None

        lookup_name = keyword.split(',')[0]

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
        for folder in self.xml_folders:
            for xml_file in self.window_files[folder]:
                yield os.path.join(self.path, folder, xml_file)

    def bump_version(self, version) -> list[tuple[str, int, int]]:
        """Bump the version in addon.xml and add a blank news entry, plus a changelog.txt one."""
        with open(self.xml_file, encoding="utf-8", newline="") as f:
            text = f.read()
        nl = "\r\n" if "\r\n" in text else "\n"
        text, count = re.subn(r'(<addon\b[^>]*?\bversion=")[^"]*"',
                              lambda m: f'{m.group(1)}{version}"', text, count=1)
        if not count:
            logger.critical(f"No version attribute on <addon> in {self.xml_file}")
            return []
        self.version = version
        self.root.set("version", version)

        spots = []
        if os.path.exists(self.changelog_path):
            with open(self.changelog_path, encoding="utf-8", newline="") as f:
                changelog = f.read()
            with open(self.changelog_path, "w", encoding="utf-8", newline="") as f:
                f.write(f"{version}{nl}- {nl}{nl}{changelog}")
            spots.append((self.changelog_path, 2, 3))

        news = text.find("<news>")
        if news >= 0:
            start = news + len("<news>")
            rest = text[start:]
            if rest.startswith("</news>"):
                entry = f"{version}{nl}- "
            elif rest.startswith(nl):
                entry = f"{nl}{version}{nl}- {nl}"
            else:
                entry = f"{version}{nl}- {nl}{nl}"
        else:
            meta = re.search(r'<extension\s+point="xbmc\.addon\.metadata"[^>]*>', text)
            close = text.find("</extension>", meta.end()) if meta else -1
            if meta is None or close < 0:
                logger.warning("No xbmc.addon.metadata extension in %s for a news entry",
                               self.xml_file)
                self._write_text(self.xml_file, text)
                return spots
            start = text.rfind(nl, 0, close) + len(nl)
            if text[start:close].strip():
                start = close
            children = re.findall(r"\n([ \t]+)<", text[meta.end():close])
            indent = children[-1] if children else "\t\t"
            entry = f"{indent}<news>{nl}{version}{nl}- {nl}{indent}</news>{nl}"
        text = text[:start] + entry + text[start:]
        dash = start + entry.index(f"{nl}- ") + len(nl)
        self._write_text(self.xml_file, text)
        spots.append((self.xml_file, text.count("\n", 0, dash) + 1, 3))
        return spots

    @staticmethod
    def _write_text(path, text):
        """Write the text back as UTF-8, line endings untouched."""
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)

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
