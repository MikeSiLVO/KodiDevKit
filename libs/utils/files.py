"""File helpers: line endings, BOMs, zipping an addon, fetching the Kodi addon list."""

from __future__ import annotations

import codecs
import logging
import os
import re
import time
import zipfile
from typing import Optional
from urllib.request import urlopen
from lxml import etree as ET

from .xml import PARSER

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.propagate = True

REPORT_NAME = "validation_report.html"


def line_ending(path: str) -> Optional[str]:
    """Line ending, CRLF if any line uses it; "" for none, None if binary or unreadable."""
    try:
        with open(path, 'rb') as f:
            head = f.read(8000)
            # a NUL byte marks a binary file, the test git uses
            if b'\0' in head:
                return None
            data = head + f.read()
    except OSError as e:
        logger.warning("Could not read %s for its line endings: %s", path, e)
        return None
    for eol in ('\r\n', '\n', '\r'):
        if eol.encode() in data:
            return eol
    return ""


def get_platform() -> str:
    """Get `'linux'`, `'windows'` or `'osx'`, from the stdlib outside Sublime."""
    try:
        import sublime
        return sublime.platform()
    except ImportError:
        # imported this way so the addon checker does not read it as a top-level import
        from importlib import import_module
        _plat = import_module("platform")
        return {"Darwin": "osx", "Linux": "linux"}.get(_plat.system(), "windows")


def get_absolute_file_paths(directory: str):
    """Get the absolute path of every file under the directory, one at a time."""
    for dirpath, _, filenames in os.walk(directory):
        for filename in filenames:
            yield os.path.abspath(os.path.join(dirpath, filename))


def make_archive(folderpath: str, archive: str, root: str, leave_out: tuple[str, ...] = ()) -> None:
    """Make the zip in one top folder, minus loose media, themes, hidden, build and listed files."""
    archive_path = os.path.abspath(archive)
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for addon_file in get_absolute_file_paths(folderpath):
            rel_path = os.path.relpath(addon_file, folderpath)
            parts = re.split(r'[\\/]', rel_path)
            if os.path.abspath(addon_file) == archive_path or "/".join(parts) in leave_out:
                continue
            if parts[0] == "media" and not rel_path.lower().endswith(".xbt"):
                continue
            if parts[0] == "themes":
                continue
            if addon_file.lower().endswith(('.pyc', '.pyo', '.zip')):
                continue
            if any(part.startswith('.') for part in parts):
                continue
            zip_file.write(addon_file, os.path.join(root, rel_path))
            logger.info("zipped %s", rel_path)


def check_bom(filepath: str) -> bool:
    """True when the file starts with a UTF-8 BOM."""
    file_bytes = min(32, os.path.getsize(filepath))
    with open(filepath, 'rb') as f:
        raw = f.read(file_bytes)
    return raw.startswith(codecs.BOM_UTF8)


def read_xbt_names(path: str) -> Optional[set[str]]:
    """Lowercased paths packed in an .xbt, read from its index."""
    try:
        with open(path, "rb") as f:
            if f.read(4) != b"XBTF" or f.read(1) < b"2":
                return None
            count = int.from_bytes(f.read(4), "little")
            names = set()
            for _ in range(count):
                raw = f.read(256)
                f.seek(4, 1)
                frames = int.from_bytes(f.read(4), "little")
                # width, height, format, packed and unpacked size, duration, offset
                f.seek(frames * 40, 1)
                names.add(raw.split(b"\0", 1)[0].decode("utf-8", "replace").replace("\\", "/").lower())
            return names
    except OSError:
        return None


def check_paths(paths: list[str]) -> Optional[str]:
    """The first path that exists, or None."""
    for path in paths:
        if os.path.exists(path):
            return path
    return None


def xml_folder_paths(skin_path: str, folder: str, default_folder: Optional[str], *names: str) -> list[str]:
    """Paths of the files in the xml folder, then in the default one, to try in that order."""
    folders = [folder] + ([default_folder] if default_folder is not None and default_folder != folder else [])
    return [os.path.join(skin_path, f, name) for f in folders for name in names]


def is_inside(path: str, root: str) -> bool:
    """True when the path, links followed, lies within the root folder."""
    root = os.path.realpath(root)
    try:
        return os.path.commonpath([os.path.realpath(path), root]) == root
    except ValueError:
        return False


_entry_cache: dict[str, tuple[float, tuple[str, ...]]] = {}


def folder_entries(folder: str) -> tuple[str, ...]:
    """Names in the folder, reread whenever its mtime moves; empty when it cannot be read."""
    try:
        stamp = os.stat(folder).st_mtime
    except OSError:
        return ()
    cached = _entry_cache.get(folder)
    if cached and cached[0] == stamp:
        return cached[1]
    try:
        listing = tuple(os.listdir(folder))
    except OSError:
        return ()
    _entry_cache[folder] = (stamp, listing)
    return listing


def miscased_name(folder: str, name: str) -> Optional[str]:
    """On-disk name of the file in the folder when it differs from the name only by case."""
    for entry in folder_entries(folder):
        if entry != name and entry.casefold() == name.casefold():
            return entry
    return None


def get_addons(reponame: str, *, timeout: int = 15, max_retries: int = 3) -> dict[str, str]:
    """Get {addon id: version} from the Kodi mirror, retrying with backoff; empty when it fails."""
    repo_url = f"https://mirrors.kodi.tv/addons/{reponame}/addons.xml"
    logger.info("Downloading %s addon list", reponame)

    backoff = [0.5, 1.0, 2.0]
    for attempt in range(max_retries):
        try:
            with urlopen(repo_url, timeout=timeout) as resp:
                root = ET.parse(resp, parser=PARSER)
            addons = {item.get("id"): item.get("version") for item in root.iter("addon")}
            return addons
        except Exception as e:
            wait = backoff[attempt] if attempt < len(backoff) else backoff[-1]
            logger.warning(
                "Attempt %d/%d failed fetching %s: %s; retrying in %.2fs",
                attempt + 1,
                max_retries,
                repo_url,
                e,
                wait,
            )
            time.sleep(wait)

    logger.error(
        "Failed to download addons.xml from %s after %d attempts",
        repo_url,
        max_retries,
        exc_info=True,
    )
    return {}
