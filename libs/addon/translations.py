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
