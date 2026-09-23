"""Helpers that read or act on the Sublime view: the text at the caret and tooltip links."""


def get_node_content(view, flags):
    """Get the text around the first selection, out to the nearest bracket or quote."""
    for region in view.sel():
        try:
            bracket_region = view.expand_by_class(region, flags, '<>"[]')
            return view.substr(bracket_region)
        except Exception:
            return ""


def jump_to_label_declaration(view, label_id):
    """Insert the label id at the cursor and close the tooltip its link sat in."""
    view.run_command("insert", {"characters": label_id})
    try:
        if view and view.settings().get("kodidevkit.popup_kind") == "tooltip":
            view.hide_popup()
            view.settings().erase("kodidevkit.popup_kind")
    except Exception:
        pass
