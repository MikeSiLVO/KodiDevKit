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

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.propagate = True

PARSER = ET.XMLParser(remove_blank_text=True, remove_comments=True)


def eol_info_from_path_patterns(
    paths: list[str],
    *,
    recursive: bool = True,
    includes: list[str] | None = None,
    excludes: list[str] | None = None
) -> list[tuple[str, str | None]]:
    """Line ending of each matching file, or None where it has no newline."""
    # an exclude matches anywhere in the path, an include matches its end
    includes = includes or []
    excludes = excludes or []

    def _skip(path):
        p = path.replace('\\', '/')
        return (
            any(x and x in p for x in excludes)
            or (includes and not any(p.endswith(x) for x in includes))
        )

    files = []
    for root_or_file in paths:
        if os.path.isdir(root_or_file):
            if recursive:
                for r, _dirs, fnames in os.walk(root_or_file):
                    for fn in fnames:
                        fp = os.path.join(r, fn)
                        if not _skip(fp):
                            files.append(fp)
            else:
                for fn in os.listdir(root_or_file):
                    fp = os.path.join(root_or_file, fn)
                    if os.path.isfile(fp) and not _skip(fp):
                        files.append(fp)
        else:
            if not _skip(root_or_file):
                files.append(root_or_file)

    out = []
    for fp in files:
        eol = None
        try:
            with open(fp, 'rb') as f:
                chunk = f.read(1 << 15)
                if b'\r\n' in chunk:
                    eol = '\r\n'
                elif b'\n' in chunk:
                    eol = '\n'
                elif b'\r' in chunk:
                    eol = '\r'
        except Exception as e:
            logger.warning(f"Could not read {fp} for EOL detection: {e}")
            eol = None
        out.append((fp, eol))
    return out


def get_platform() -> str:
    """Return `'linux'`, `'windows'`, or `'osx'`; falls back to stdlib outside Sublime."""
    try:
        import sublime
        return sublime.platform()
    except ImportError:
        # imported this way so the addon checker does not read it as a top-level import
        from importlib import import_module
        _plat = import_module("platform")
        return {"Darwin": "osx", "Linux": "linux"}.get(_plat.system(), "windows")


def get_sublime_path() -> str | None:
    """Get the command that starts Sublime Text, or None when it cannot be found."""
    plat = get_platform()
    if plat in ("osx", "linux"):
        return "subl"
    elif os.path.exists(os.path.join(os.getcwd(), "sublime_text.exe")):
        return os.path.join(os.getcwd(), "sublime_text.exe")
    return None


def get_absolute_file_paths(directory: str):
    """Yield the absolute path of every file under the directory."""
    for dirpath, _, filenames in os.walk(directory):
        for filename in filenames:
            yield os.path.abspath(os.path.join(dirpath, filename))


def make_archive(folderpath: str, archive: str) -> None:
    """Create the addon zip, leaving out loose media, themes, hidden and build files."""
    file_list = get_absolute_file_paths(folderpath)
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for addon_file in file_list:
            path_list = re.split(r'[\\/]', addon_file)
            rel_path = os.path.relpath(addon_file, folderpath)
            if ".git" in path_list:
                continue
            if rel_path.startswith("media") and not rel_path.endswith(".xbt"):
                continue
            if rel_path.startswith("themes"):
                continue
            if addon_file.endswith(('.pyc', '.pyo', '.zip')):
                continue
            if any(part.startswith('.') for part in path_list):
                continue
            zip_file.write(addon_file, rel_path)
            logger.info("zipped %s", rel_path)


def check_bom(filepath: str) -> bool:
    """True when the file starts with a UTF-8 BOM."""
    file_bytes = min(32, os.path.getsize(filepath))
    with open(filepath, 'rb') as f:
        raw = f.read(file_bytes)
    return raw.startswith(codecs.BOM_UTF8)


def read_xbt_names(path: str) -> Optional[set[str]]:
    """Lowercased paths packed in an .xbt, read from its index as CXBTFReader::Open does."""
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


def miscased_name(folder: str, name: str) -> Optional[str]:
    """On-disk name of the file in the folder when it differs from the name only by case."""
    try:
        entries = os.listdir(folder)
    except OSError:
        return None
    for entry in entries:
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
