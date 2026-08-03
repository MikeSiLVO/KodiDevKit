"""`kdk-ignore` comments, so a skin can mute findings it has already judged."""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

# Matches <!-- kdk-ignore --> and <!-- kdk-ignore-file: labels, images -->
DIRECTIVE = re.compile(r"<!--\s*kdk-ignore(-file)?\s*(?::([^>]*?))?\s*-->", re.IGNORECASE)

# A bare directive with no category list mutes every check.
ALL = "*"


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


def _key(path):
    """Compare paths the way the host filesystem does."""
    return os.path.normcase(os.path.abspath(str(path)))


class Suppressions:
    """Which categories a file, or a single line of it, has opted out of."""

    def __init__(self):
        self.files = {}
        self.lines = {}

    def add_file(self, path, categories):
        self.files.setdefault(_key(path), set()).update(categories)

    def add_line(self, path, line, categories):
        self.lines.setdefault((_key(path), line), set()).update(categories)

    def __bool__(self):
        return bool(self.files or self.lines)

    def muted(self, category, path, line):
        """True if `category` is muted for this file, or for this line of it."""
        if not path:
            return False
        wanted = normalize(category)
        key = _key(path)

        for scope in (self.files.get(key), self.lines.get((key, line))):
            if scope and (ALL in scope or wanted in scope):
                return True
        return False

    def filter(self, category, issues):
        """Drop the issues in `category` that a directive mutes."""
        if not self:
            return issues
        return [i for i in issues if not self.muted(category, i.get("file"), i.get("line") or 0)]


def scan(paths):
    """Collect every directive found in `paths`."""
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

            # Nothing is ever reported against a comment, so a directive with no
            # markup beside it must mean the line below
            alone = not DIRECTIVE.sub("", line).strip()

            for match in matches:
                categories = _categories(match.group(2))
                if match.group(1):
                    found.add_file(path, categories)
                else:
                    found.add_line(path, number + 1 if alone else number, categories)

    return found


def scan_skin(addon):
    """Every directive in the skin's XML folders, Font.xml included."""
    paths = []
    for folder in getattr(addon, "xml_folders", []) or []:
        directory = os.path.join(addon.path, folder)
        try:
            entries = os.listdir(directory)
        except OSError:
            continue
        paths.extend(
            os.path.join(directory, name) for name in entries if name.lower().endswith(".xml")
        )
    return scan(paths)
