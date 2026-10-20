"""File-level checks: BOM, line endings, 16-bit PNGs, broken strings.po and rejected files."""

from __future__ import annotations

import os
import re
import logging
import subprocess
import sys

from ..addon.translations import strings_po_faults
from ..utils.files import check_bom, eol_info_from_path_patterns
from .constants import SEVERITY_ERROR, SEVERITY_WARNING

logger = logging.getLogger(__name__)

_LEFTOVER = re.compile(r"(?i)(\.(bak|orig|tmp|old|swp|psd|xcf)$|~$|^(thumbs\.db|\.ds_store|desktop\.ini)$"
                       r"| - (copy|kopie)\b)")


class ValidationFileCheck:
    """Checker for BOMs, line endings, 16-bit PNGs, broken strings.po and rejected files."""

    def __init__(self, addon):
        self.addon = addon

    def check(self, progress_callback=None):
        """Check the skin's files, one issue row per problem found."""
        issues = []

        if not self.addon:
            return issues

        # text only: a PNG holding 0D 0A would read as Windows line endings
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
                    "message": "File starts with a UTF-8 BOM, which Kodi repo review rejects; save it without one",
                    "file": path,
                    "line": 1,
                    "severity": SEVERITY_ERROR,
                    "rule": "files.bom",
                    "subject": "",
                })

        for path, eol in result:
            if eol == '\r\n':
                issues.append({
                    "message": "Windows line endings (CRLF), which Kodi repo review rejects; save the file with LF",
                    "file": path,
                    "line": 0,
                    "severity": SEVERITY_ERROR,
                    "rule": "files.line-endings",
                    "subject": "",
                })
            elif eol == '\r':
                issues.append({
                    "message": "Mac line endings (CR), which Kodi repo review rejects; save the file with LF",
                    "file": path,
                    "line": 0,
                    "severity": SEVERITY_ERROR,
                    "rule": "files.line-endings",
                    "subject": "",
                })

        issues.extend(self._sixteen_bit_pngs())
        issues.extend(self._repo_file_issues())
        issues.extend(self._po_syntax_issues())

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
                            "rule": "files.sixteen-bit-png",
                            "subject": "",
                        })
        return issues


    def _po_syntax_issues(self):
        """Broken strings.po strings Kodi does not misread; the misread ones are label issues."""
        issues = []
        for path, line, string_id, problem, effect in strings_po_faults(self.addon.path):
            if effect:
                continue
            where = f"string {string_id}" if string_id else "the header"
            if problem == "unclosed":
                message = (f"A string in {where} does not close on this line, so Weblate and gettext "
                           f"tools cannot load the file; Kodi still reads it")
                rule, severity = "files.po-unclosed", SEVERITY_ERROR
            else:
                message = (f"Text after the closing quote in {where}, such as an unescaped \", which "
                           f"msgfmt rejects; Kodi and Weblate still read it")
                rule, severity = "files.po-trailing-text", SEVERITY_WARNING
            issues.append({"message": message, "file": path, "line": line, "severity": severity,
                           "rule": rule, "subject": string_id or ""})
        return issues


    def _repo_file_issues(self):
        """Files Kodi repo review rejects, plus names that clash on case-insensitive systems."""
        issues = []

        def add(rel, rule, message, severity=SEVERITY_WARNING):
            issues.append({"message": message, "file": os.path.join(self.addon.path, rel), "line": 0,
                           "severity": severity, "rule": rule, "subject": ""})

        files = shipped_files(self.addon.path)
        by_folded = {}
        for rel, executable in files:
            name = rel.rsplit("/", 1)[-1]
            lower = name.lower()
            by_folded.setdefault(rel.casefold(), []).append(rel)
            if executable:
                add(rel, "files.executable", f"Kodi repo: {name} is marked executable")
            if not rel.isascii():
                add(rel, "files.non-ascii-name", f"Kodi repo: {rel} has a non-ASCII name")
            if lower.endswith(".py"):
                add(rel, "files.python-script", f"Kodi repo: skins may not ship python scripts ({name})")
            elif rel.lower().startswith("keymaps/") or _is_keymap(os.path.join(self.addon.path, rel)):
                add(rel, "files.keymap", f"Kodi repo: skins may not ship keymaps ({name})")
            if _LEFTOVER.search(name):
                add(rel, "files.leftover", f"Kodi repo: {name} looks like a leftover, not a skin file")
        for paths in by_folded.values():
            if len(paths) > 1:
                for rel in paths:
                    others = ", ".join(p for p in paths if p != rel)
                    add(rel, "files.case-clash", f"{rel} differs from {others} only by case; one overwrites the other on Windows "
                             f"and macOS", SEVERITY_ERROR)
        addon_xml = os.path.join(self.addon.path, "addon.xml")
        try:
            with open(addon_xml, encoding="utf-8", errors="replace") as f:
                if 'point="kodi.context.item"' in f.read():
                    add("addon.xml", "files.context-item", "Kodi repo: skins may not add context menu items (kodi.context.item)")
        except OSError:
            pass
        return issues


def shipped_files(root):
    """Relative paths with their executable bit, leaving out the add-ons nested inside this one."""
    files = _tracked_files(root)
    nested = _nested(files)
    return [entry for entry in files if not any(entry[0].startswith(folder + "/") for folder in nested)]


def nested_addons(root):
    """Outermost folders inside the add-on that hold their own addon.xml, each a separate add-on."""
    return _nested(_tracked_files(root))


def _nested(files):
    """Outermost folders in the listing that hold an addon.xml of their own."""
    folders = sorted({os.path.dirname(rel) for rel, _executable in files
                      if os.path.basename(rel) == "addon.xml" and os.path.dirname(rel)})
    return [f for f in folders if not any(f.startswith(other + "/") for other in folders)]


def _tracked_files(root):
    """Relative paths with their executable bit: git's index in a checkout, else the folder."""
    if os.path.exists(os.path.join(root, ".git")):
        try:
            # a skin's .git/config can name an fsmonitor command, which ls-files would run
            cmd = ["git", "-c", "core.fsmonitor=false", "-C", root, "ls-files", "-s", "-z"]
            # on Windows a console program opens a window that takes focus from the editor
            out = subprocess.run(cmd, capture_output=True, check=True,
                                 creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
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
