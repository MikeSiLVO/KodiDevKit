"""File-level checks: BOM, line endings, 16-bit PNGs, and files Kodi repo review rejects."""

from __future__ import annotations

import os
import re
import logging
import subprocess

from ..utils.files import check_bom, eol_info_from_path_patterns
from .constants import SEVERITY_ERROR, SEVERITY_WARNING

logger = logging.getLogger(__name__)

_LEFTOVER = re.compile(r"(?i)(\.(bak|orig|tmp|old|swp|psd|xcf)$|~$|^(thumbs\.db|\.ds_store|desktop\.ini)$"
                       r"| - (copy|kopie)\b)")


class ValidationFileCheck:
    """Validates file encoding (BOM) and line endings."""

    def __init__(self, addon):
        self.addon = addon

    def check(self, progress_callback=None):
        issues = []

        if not self.addon:
            return issues

        # Text types only: binaries such as PNGs routinely contain 0D 0A and
        # would otherwise be reported as having Windows line endings.
        result = eol_info_from_path_patterns(
            [self.addon.path],
            recursive=True,
            includes=['.xml', '.po', '.txt', '.py', '.md'],
            excludes=['.svn', '.git'],
        )

        if progress_callback:
            progress_callback(f"Checking {len(result)} files for BOM and line endings...")

        for path, _eol in result:
            if check_bom(path):
                issues.append({
                    "message": f"found BOM. File: {os.path.basename(path)}",
                    "file": path,
                    "line": 1,
                    "severity": SEVERITY_ERROR,
                })

        for path, eol in result:
            if eol == '\r\n':
                issues.append({
                    "message": f"Windows Line Endings detected in {os.path.basename(path)}",
                    "file": path,
                    "line": 0,
                    "severity": SEVERITY_ERROR,
                })
            elif eol == '\r':
                issues.append({
                    "message": f"MAC Line Endings detected in {os.path.basename(path)}",
                    "file": path,
                    "line": 0,
                    "severity": SEVERITY_ERROR,
                })

        issues.extend(self._sixteen_bit_pngs())
        issues.extend(self._repo_file_issues())

        if progress_callback:
            progress_callback(f"Complete: {len(issues)} file encoding issues found")

        return issues


    def _sixteen_bit_pngs(self):
        """PNGs TexturePacker would pack whose IHDR says 16 bits per channel."""
        issues = []
        for folder in ("media", "themes"):
            for dirpath, _dirs, files in os.walk(os.path.join(self.addon.path, folder)):
                for name in files:
                    if not name.lower().endswith(".png"):
                        continue
                    path = os.path.join(dirpath, name)
                    try:
                        with open(path, "rb") as f:
                            header = f.read(25)
                    except OSError:
                        continue
                    # bit depth follows the signature and the IHDR length, type, width and height
                    if len(header) == 25 and header[12:16] == b"IHDR" and header[24] == 16:
                        issues.append({
                            "message": f"16-bit PNG {name}: TexturePacker cannot pack it, save it as 8-bit",
                            "file": path,
                            "line": 0,
                            "severity": SEVERITY_ERROR,
                        })
        return issues


    def _repo_file_issues(self):
        """Files Kodi repo review rejects, plus names that clash on case-insensitive systems."""
        issues = []

        def add(rel, message, severity=SEVERITY_WARNING):
            issues.append({"message": message, "file": os.path.join(self.addon.path, rel), "line": 0,
                           "severity": severity})

        files = shipped_files(self.addon.path)
        by_folded = {}
        for rel, executable in files:
            name = rel.rsplit("/", 1)[-1]
            lower = name.lower()
            by_folded.setdefault(rel.casefold(), []).append(rel)
            if executable:
                add(rel, f"Kodi repo: {name} is marked executable")
            if not rel.isascii():
                add(rel, f"Kodi repo: {rel} has a non-ASCII name")
            if lower.endswith(".py"):
                add(rel, f"Kodi repo: skins may not ship python scripts ({name})")
            elif rel.lower().startswith("keymaps/") or _is_keymap(os.path.join(self.addon.path, rel)):
                add(rel, f"Kodi repo: skins may not ship keymaps ({name})")
            if _LEFTOVER.search(name):
                add(rel, f"Kodi repo: {name} looks like a leftover, not a skin file")
        for paths in by_folded.values():
            if len(paths) > 1:
                for rel in paths:
                    others = ", ".join(p for p in paths if p != rel)
                    add(rel, f"{rel} differs from {others} only by case; one overwrites the other on Windows "
                             f"and macOS", SEVERITY_ERROR)
        addon_xml = os.path.join(self.addon.path, "addon.xml")
        try:
            with open(addon_xml, encoding="utf-8", errors="replace") as f:
                if 'point="kodi.context.item"' in f.read():
                    add("addon.xml", "Kodi repo: skins may not add context menu items (kodi.context.item)")
        except OSError:
            pass
        return issues


def shipped_files(root):
    """Relative paths with their executable bit: git's index in a checkout, else the folder."""
    if os.path.exists(os.path.join(root, ".git")):
        try:
            # on Windows a console program opens a window that takes focus from the editor
            out = subprocess.run(["git", "-C", root, "ls-files", "-s", "-z"], capture_output=True, check=True,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                                 ).stdout.decode("utf-8", "replace")
            # a PR ships what git tracks, with the mode git records
            return [(entry.split("\t", 1)[1], entry.startswith("100755")) for entry in out.split("\0") if "\t" in entry]
        except (OSError, subprocess.CalledProcessError):
            pass
    files = []
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".git"]
        files.extend((os.path.relpath(os.path.join(dirpath, n), root).replace("\\", "/"), False) for n in names)
    return files


def _is_keymap(path):
    """Whether an xml file's root element is <keymap>."""
    if not path.lower().endswith(".xml"):
        return False
    try:
        with open(path, "rb") as f:
            head = f.read(512)
    except OSError:
        return False
    return re.search(rb"^\s*(?:<\?xml[^>]*>\s*)?(?:<!--.*?-->\s*)*<keymap\b", head, re.S) is not None
