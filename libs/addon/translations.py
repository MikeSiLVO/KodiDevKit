"""
PO file (gettext translation) utilities for KodiDevKit.
"""

import time
import logging
from .. import polib
from ..polib import pofile

logger = logging.getLogger("KodiDevKit.utils.po_helpers")
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.propagate = True


def get_po_file(po_file_path):
    try:
        return pofile(po_file_path)
    except Exception:
        logger.error("Error in %s", po_file_path, exc_info=True)
        return None


def create_new_po_file(path=None):
    """
    creates a new pofile and returns it (doesnt save yet)
    """
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
    """ convert language xmls inside *path to .po files """
    # Import here to avoid circular dependency
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
