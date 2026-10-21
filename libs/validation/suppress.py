"""`kdk-ignore` comments, which let a skin mute warnings it has already judged."""

from __future__ import annotations

import logging
import os
import re

from ..utils.validation import create_issue
from .constants import SEVERITY_ERROR, SEVERITY_WARNING
from .rules import blocks_submission

logger = logging.getLogger(__name__)

DIRECTIVE = re.compile(r"<!--\s*kdk-ignore(-file)?\s*(?::([^;>]*?))?\s*(?:;(.*?))?\s*-->", re.IGNORECASE)

# a bare directive with no category list mutes every check
ALL = "*"

CHECKS = ("Variables", "Maps", "Includes", "Labels", "Fonts", "IDs", "Images", "XML Validation",
          "File Integrity", "Kodi Repo")

FILE_FAULT = ("kdk-ignore-file mutes nothing until it names the checks and gives a reason, "
              "such as <!-- kdk-ignore-file: labels; debug overlay -->")


def normalize(name):
    """Fold a category to its comparison form, so `XML Validation` matches `xml-validation`."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def _categories(raw):
    """Parse the `: a, b` part of a directive; empty means every category."""
    if not raw or not raw.strip():
        return {ALL}
    names = {normalize(part) for part in raw.split(",")}
    names.discard("")
    return names or {ALL}


def _unknown(raw):
    """Names in the `: a, b` part that match no check, as the skin wrote them."""
    known = {normalize(name) for name in CHECKS}
    return [part.strip() for part in (raw or "").split(",") if normalize(part) and normalize(part) not in known]


def _key(path):
    """Key a path so it compares the way the host filesystem does."""
    return os.path.normcase(os.path.abspath(str(path)))


class Suppressions:
    """Which categories a file, or a single line of it, has opted out of."""

    def __init__(self):
        self.files = {}
        self.lines = {}
        self.faults = []

    def add_file(self, path, categories, line=1, reason=""):
        """Add a file-wide mute for the categories, written at that line with that reason."""
        self.files.setdefault(_key(path), []).append((categories, {"line": line, "reason": reason}))

    def add_line(self, path, line, categories, written_at=None, reason=""):
        """Add a one-line mute for the categories, written on that line or the one above."""
        mute = {"line": written_at or line, "reason": reason}
        self.lines.setdefault((_key(path), line), []).append((categories, mute))

    def add_fault(self, path, line, rule, message):
        """Add a warning at the line for a directive that mutes less than it says."""
        self.faults.append(create_issue(message, file=path, line=line, severity=SEVERITY_WARNING,
                                        rule=rule, subject=""))

    def faults_in(self, path=None):
        """Warnings for directives that mute less than they say, in the file or in all of them."""
        if path is None:
            return list(self.faults)
        key = _key(path)
        return [fault for fault in self.faults if _key(fault["file"]) == key]

    def __bool__(self):
        return bool(self.files or self.lines)

    def muted(self, category, path, line):
        """Where and why the category is muted for that line of the file, or None."""
        if not path:
            return None
        wanted = normalize(category)
        key = _key(path)

        for scope in (self.lines.get((key, line)), self.files.get(key)):
            for categories, mute in scope or ():
                if ALL in categories or wanted in categories:
                    return mute
        return None

    def mark(self, category, issues):
        """Mark the category's muted warnings on copies, with the directive's line and reason."""
        if not self:
            return issues
        marked = []
        for issue in issues:
            if issue.get("severity") == SEVERITY_ERROR or blocks_submission(issue.get("rule")):
                marked.append(issue)
                continue
            mute = self.muted(category, issue.get("file"), issue.get("line") or 0)
            marked.append({**issue, "muted": dict(mute)} if mute else issue)
        return marked


def muted_note(issue):
    """Line telling a reviewer where the issue was muted and the reason the skin gives."""
    mute = issue["muted"]
    reason = mute.get("reason")
    if reason:
        return f"Muted by kdk-ignore at line {mute['line']}: {reason}"
    return f"Muted by kdk-ignore at line {mute['line']}, no reason given"


def scan(paths):
    """Scan the files for every directive, noting each that mutes less than it says."""
    found = Suppressions()

    for path in paths:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            logger.debug("Could not scan %s for kdk-ignore: %s", path, e)
            continue

        if "kdk-ignore" not in text.lower():
            continue

        for number, line in enumerate(text.splitlines(), 1):
            matches = list(DIRECTIVE.finditer(line))
            if not matches:
                continue

            # a directive alone covers the line below
            alone = not DIRECTIVE.sub("", line).strip()

            for match in matches:
                categories = _categories(match.group(2))
                reason = (match.group(3) or "").strip()
                unknown = _unknown(match.group(2))
                if unknown:
                    found.add_fault(path, number, "xml.ignore-unknown-check", f"kdk-ignore names a check that does not exist: "
                                                  f"{', '.join(unknown)}. The checks are {', '.join(CHECKS)}")
                    categories -= {normalize(name) for name in unknown}
                if match.group(1) and (ALL in categories or not reason):
                    found.add_fault(path, number, "xml.ignore-file-incomplete", FILE_FAULT)
                elif not categories:
                    continue
                elif match.group(1):
                    found.add_file(path, categories, number, reason)
                else:
                    found.add_line(path, number + 1 if alone else number, categories, number, reason)

    return found


def skin_paths(addon):
    """Every xml file in the skin's xml folders, subfolders and Font.xml included."""
    paths = []
    for folder in getattr(addon, "xml_folders", []) or []:
        for dirpath, dirnames, filenames in os.walk(os.path.join(addon.path, folder)):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            paths.extend(os.path.join(dirpath, name) for name in sorted(filenames) if name.lower().endswith(".xml"))
    return paths


def stamp(paths):
    """Modified time and size of each file, which a scan of them stays valid for."""
    result = []
    for path in paths:
        try:
            info = os.stat(path)
            result.append((path, info.st_mtime_ns, info.st_size))
        except OSError:
            result.append((path, 0, 0))
    return tuple(result)
