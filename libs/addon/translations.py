"""PO file helpers for Kodi language folders."""

import time
import logging
from ..polib import polib
from ..polib.polib import pofile

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.propagate = True


def get_po_file(po_file_path):
    """Parsed PO file, or None when it fails to parse."""
    try:
        return pofile(po_file_path)
    except Exception:
        logger.error("Error in %s", po_file_path, exc_info=True)
        return None


def create_new_po_file(path=None):
    """Create an unsaved PO file with Kodi-style metadata."""
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


def convert_xml_to_po(path):
    """Convert a legacy strings.xml into a saved .po file beside it."""
    from ..utils.xml import get_root_from_file

    po_file = create_new_po_file(path)
    root = get_root_from_file(path)
    if root is None:
        logger.error("convert_xml_to_po: could not parse %s", path)
        return po_file
    for item in root.findall("string"):
        entry = polib.POEntry(
            msgid=item.text or "",
            msgstr="",
            msgctxt="#%s" % item.attrib.get("id", "")
        )
        po_file.append(entry)
    po_file.save()
    return po_file
