"""
File operation utilities for KodiDevKit.
"""

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

logger = logging.getLogger("KodiDevKit.utils.files")
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
    """
    Return a list of (filepath, eol) where eol is one of:
      '\r\n' (Windows), '\n' (Unix), '\r' (old Mac), or None (no newline found).

    `includes`/`excludes` are simple substring filters on the full path.
    """

    includes = includes or []
    excludes = excludes or []

    def _skip(path):
        p = path.replace('\\', '/')
        return (
            any(x and x in p for x in excludes)
            or (includes and not any(x in p for x in includes))
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
                chunk = f.read(1 << 15)  # 32 KiB is plenty to determine EOL
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


def save_xml(filename: str, root, tab_width: int = 4) -> None:
    """
    Save XML node *root to file *filename.
    Uses lxml pretty_print, then converts leading spaces to tabs.
    """

    xml_bytes = ET.tostring(root, encoding="UTF-8", xml_declaration=True, pretty_print=True)
    text = xml_bytes.decode("utf-8")

    def _detab(line: str) -> str:
        m = re.match(r"^ +", line)
        if not m:
            return line
        spaces = len(m.group(0))
        tabs = "\t" * (spaces // tab_width)
        return tabs + line[spaces:]

    text = "".join(_detab(line) for line in text.splitlines(True))

    with open(filename, "wb") as f:
        f.write(text.encode("utf-8"))


def get_sublime_path() -> str | None:
    """Get command-line path to execute Sublime Text externally."""
    try:
        import sublime
        plat = sublime.platform()
    except ImportError:
        import platform as _plat
        plat = {"Darwin": "osx", "Linux": "linux"}.get(_plat.system(), "windows")
    if plat in ("osx", "linux"):
        return "subl"
    elif os.path.exists(os.path.join(os.getcwd(), "sublime_text.exe")):
        return os.path.join(os.getcwd(), "sublime_text.exe")
    return None


def get_absolute_file_paths(directory: str):
    """Generate absolute file paths for all files in directory (recursive)."""
    for dirpath, _, filenames in os.walk(directory):
        for filename in filenames:
            yield os.path.abspath(os.path.join(dirpath, filename))


def make_archive(folderpath: str, archive: str) -> None:
    """Create zip archive from folder, excluding dev files and hidden files/folders."""
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
    """Check if file has UTF-8 BOM (Byte Order Mark)."""
    file_bytes = min(32, os.path.getsize(filepath))
    with open(filepath, 'rb') as f:
        raw = f.read(file_bytes)
    return raw.startswith(codecs.BOM_UTF8)


def check_paths(paths: list[str]) -> Optional[str]:
    """Return first valid path from list, or None if none exist."""
    for path in paths:
        if os.path.exists(path):
            return path
    return None


def get_addons(reponame: str, *, timeout: int = 15, max_retries: int = 3) -> dict[str, str]:
    """
    Return {addon_id: version} from the Kodi mirror for a given repo name.
    Retries with simple backoff; logs a traceback on final failure.
    """
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
