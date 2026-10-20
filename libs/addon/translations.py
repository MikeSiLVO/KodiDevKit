"""PO file helpers for Kodi language folders."""

import os
import re
import time
import logging
from ..polib import polib
from ..polib.polib import pofile

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.propagate = True

_FIELD = re.compile(r'(msgctxt|msgid_plural|msgid|msgstr(?:\[\d+\])?)\s+(.*)$')
_STRING_ID = re.compile(r'msgctxt "#(\d+)')


def strings_po_faults(addon_path):
    """Yield (path, line, string id, problem, effect) per broken string in every strings.po."""
    for base in ("language", os.path.join("resources", "language")):
        base_path = os.path.join(addon_path, base)
        if not os.path.isdir(base_path):
            continue
        for folder in sorted(os.listdir(base_path)):
            path = os.path.join(base_path, folder, "strings.po")
            if not folder.startswith("resource.language.") or not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
            for fault in broken_strings(text, folder.lower() == "resource.language.en_gb"):
                yield (path,) + fault


def _string_fault(value):
    """What breaks a quoted string line: "unclosed", "text" or "spaces" after the quote, or None."""
    i = 0
    while True:
        i += 1
        while i < len(value) and value[i] != '"':
            i += 2 if value[i] == "\\" else 1
        if i >= len(value):
            return "unclosed"
        rest = value[i + 1:]
        following = rest.lstrip()
        if not following:
            return "spaces" if rest else None
        # gettext joins strings written side by side on one line
        if following[0] != '"':
            return "text"
        i = len(value) - len(following)


def broken_strings(text, source):
    """Yield (line, string id, problem, Kodi's effect or None) per broken field in the text."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    entry = []
    for number, line in enumerate(lines + [""], 1):
        if line:
            entry.append((number, line))
            continue
        yield from _entry_faults(entry, source)
        entry = []


def _entry_faults(entry, source):
    """Faults of one blank-line-separated entry, each field reported at its first bad line."""
    string_id = None
    fields = []
    for number, line in entry:
        found = _STRING_ID.match(line)
        if found:
            string_id = found.group(1)
        found = _FIELD.match(line)
        if found:
            # Kodi takes the text after exactly one space as the string
            fields.append((found.group(1), [(number, found.group(2), line[len(found.group(1)) + 1:])]))
        elif line.startswith('"') and fields:
            fields[-1][1].append((number, line, line))
    # Kodi reads msgid for the source language, msgstr and msgid for a translation
    wanted = ("msgid",) if source else ("msgid", "msgstr")
    for name, parts in fields:
        read, stopped = "", string_id is None or name not in wanted
        for number, value, as_kodi in parts:
            problem = _string_fault(value) if value.startswith('"') else "unclosed"
            if not stopped and not (len(as_kodi) > 1 and as_kodi[0] == as_kodi[-1] == '"'):
                stopped = True
                if source:
                    effect = "cut" if read else "empty"
                elif name == "msgstr":
                    effect = "cut" if read else "english"
                else:
                    effect = "english" if read else None
                if effect:
                    yield number, string_id, problem or "spaces", effect
                    break
            if problem not in (None, "spaces"):
                yield number, string_id, problem, None
                break
            if not stopped:
                read += as_kodi[1:-1]


def get_po_file(po_file_path):
    """Get the parsed PO file, or None when it fails to parse."""
    try:
        return pofile(po_file_path)
    except Exception:
        logger.error("Error in %s", po_file_path, exc_info=True)
        return None


def create_new_po_file(path=None):
    """Create an unsaved PO file with a dated gettext header."""
    po_file = polib.POFile(fpath=path)
    mail = ""
    actual_date = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    po_file.metadata = {
        'Project-Id-Version': '1.0',
        'Report-Msgid-Bugs-To': '%s' % mail,
        'POT-Creation-Date': actual_date,
        'PO-Revision-Date': actual_date,
        'Last-Translator': 'you <%s>' % mail,
        'Language-Team': 'English <%s>' % mail,
        'MIME-Version': '1.0',
        'Content-Type': 'text/plain; charset=utf-8',
        'Content-Transfer-Encoding': '8bit',
    }
    return po_file
