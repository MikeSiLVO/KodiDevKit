"""
Sublime Text specific helper utilities for KodiDevKit.
"""

import json
import logging

logger = logging.getLogger("KodiDevKit.utils.sublime_helpers")
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.propagate = True


def find_word(view):
    """
    return selected text or surrounding text for first selection
    """
    for region in view.sel():
        word = view.word(region) if region.begin() == region.end() else region
        return view.substr(word) if not word.empty() else ""


def get_node_content(view, flags):
    """
    return surrounding text for for first selection
    """
    for region in view.sel():
        try:
            bracket_region = view.expand_by_class(region, flags, '<>"[]')
            return view.substr(bracket_region)
        except Exception:
            return ""


def jump_to_label_declaration(view, label_id):
    """
    prints properly formatted output for json objects
    """
    view.run_command("insert", {"characters": label_id})
    # hide only our tooltip
    try:
        if view and view.settings().get("kodidevkit.popup_kind") == "tooltip":
            view.hide_popup()
            view.settings().erase("kodidevkit.popup_kind")
    except Exception:
        pass


def prettyprint(obj) -> None:
    """
    JSON pretty print for debug logs:
    - Stable key order
    - UTF-8 output with replacement for invalid bytes
    - Safe for dict/list/str/bytes/None
    """
    try:
        if isinstance(obj, (bytes, bytearray)):
            try:
                obj = obj.decode("utf-8", "replace")
            except Exception:
                obj = obj.decode("utf-8", "replace")
        text = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)
    except Exception:
        # Fallback: safe repr
        try:
            text = repr(obj)
        except Exception:
            text = "<unprintable>"
    logger.debug(text)


def debug_print(obj) -> None:
    """Console print only when kodidevkit.sublime-settings has debug_mode=true."""
    import sublime
    try:
        if isinstance(obj, (bytes, bytearray)):
            obj = obj.decode("utf-8", "replace")
        text = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)
    except Exception:
        try:
            text = repr(obj)
        except Exception:
            text = "<unprintable>"
    if bool(sublime.load_settings("kodidevkit.sublime-settings").get("debug_mode", False)):
        print(text)
