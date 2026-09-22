"""Small helpers that touch the Sublime view: selection text, popups, debug output."""

import json
import logging

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.propagate = True


def find_word(view):
    """The first selection's text, or the word under the caret when nothing is selected."""
    for region in view.sel():
        word = view.word(region) if region.begin() == region.end() else region
        return view.substr(word) if not word.empty() else ""


def get_node_content(view, flags):
    """Text around the first selection, out to the nearest bracket or quote."""
    for region in view.sel():
        try:
            bracket_region = view.expand_by_class(region, flags, '<>"[]')
            return view.substr(bracket_region)
        except Exception:
            return ""


def jump_to_label_declaration(view, label_id):
    """Insert `label_id` at the cursor and hide the popup (callback for label tooltip links)."""
    view.run_command("insert", {"characters": label_id})
    try:
        if view and view.settings().get("kodidevkit.popup_kind") == "tooltip":
            view.hide_popup()
            view.settings().erase("kodidevkit.popup_kind")
    except Exception:
        pass


def prettyprint(obj) -> None:
    """Log any value as sorted, readable JSON, falling back to repr."""
    try:
        if isinstance(obj, (bytes, bytearray)):
            try:
                obj = obj.decode("utf-8", "replace")
            except Exception:
                obj = obj.decode("utf-8", "replace")
        text = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)
    except Exception:
        try:
            text = repr(obj)
        except Exception:
            text = "<unprintable>"
    logger.debug(text)


