"""Tooltip and popup content mixin for InfoProvider."""

from __future__ import annotations

import os
import string
import logging
from ..utils.colors import get_contrast_color
from ..kodi.jsonrpc import kodi
from ..utils import images as imageparser
from ..validation.constants import POS_TAGS
from .checker import CheckerMixin
from .pystrings import SOURCE_ADDON, WrapperIndex, dependency_roots, label_at

from typing import Any

logger = logging.getLogger(__name__)


def _is_addon_string_id(label_id):
    """True when the id sits in a range Kodi reserves for add-on strings."""
    return 30000 <= label_id <= 30999 or 32000 <= label_id <= 32999


# InfoProvider lists this before CheckerMixin, so super() reaches the engine
class TooltipMixin(CheckerMixin):
    """HTML for the editor's hover popups: labels, colors, images, positions."""

    addon: Any
    settings: dict
    kodi: Any
    kodi_path: str | None
    _python_wrappers: WrapperIndex | None = None

    def python_label_tooltip(self, line, col, path):
        """HTML rows for the string id under the cursor in Python, from the strings it reads."""
        if not self.addon or not self.addon.path:
            return ""
        index = self._python_wrappers
        if index is None or index.root != self.addon.path:
            roots = dependency_roots(self.addon.path)
            index = self._python_wrappers = WrapperIndex(self.addon.path, roots)
        resolver = index.resolver()
        found = label_at(line, col, lambda callee: resolver.source(path, callee))
        if not found:
            return ""
        addon_id, label_id, source = found
        if addon_id and addon_id != self.addon.name:
            return self.return_addon_label(addon_id, label_id)
        if source != SOURCE_ADDON:
            return self.return_label(label_id)
        rows = self.return_label(label_id, addon_only=True)
        return rows or "<i>Not in this add-on's strings.po</i>"

    def return_label(self, selection, addon_only=False):
        """HTML rows of every translation of the id, per language and source, or the add-on's."""
        tooltips = ""
        if not selection.isdigit():
            return ""
        seen_labels = set()
        for po_file in self.get_po_files():
            hit = po_file.find("#" + selection, by="msgctxt")
            if not hit:
                continue
            language = po_file.language.replace("resource.language.", "")
            fpath = str(getattr(po_file, "fpath", "") or "")
            in_addon = bool(self.addon and self.addon.path and fpath.startswith(self.addon.path))
            if addon_only and not in_addon:
                continue

            source_label = ""
            if in_addon:
                source_label = f" <i>({self.addon.type})</i>"
            elif "resource.language." in fpath:
                source_label = " <i>(kodi)</i>"

            label_key = (language, source_label, hit.msgstr if hit.msgstr else hit.msgid)
            if label_key in seen_labels:
                continue
            seen_labels.add(label_key)

            tooltips += "<b>%s%s:</b> %s<br>" % (
                language,
                source_label,
                hit.msgstr if hit.msgstr else hit.msgid,
            )
        return tooltips

    def return_addon_label(self, addon_id, label_id):
        """HTML rows for an $ADDON[id label] string, from the addon alongside or under kodi_path."""
        from ..polib import polib

        if not label_id.isdigit():
            return ""

        candidates = []
        if self.addon and self.addon.path:
            addons_dir = os.path.dirname(os.path.normpath(self.addon.path))
            candidates.append(os.path.join(addons_dir, addon_id))
        kodi_path = self.settings.get("kodi_path", "")
        if kodi_path:
            portable = self.settings.get("portable_mode", False)
            sub = ("portable_data", "addons") if portable else ("addons",)
            candidates.append(os.path.join(kodi_path, *sub, addon_id))

        addon_path = next((p for p in candidates if os.path.isdir(p)), None)
        if not addon_path:
            return f"<i>Addon not found: {addon_id}</i>"

        lang_folders = self.settings.get("language_folders", ["resource.language.en_gb"])
        tooltips = ""

        for lang_folder in lang_folders:
            po_path = os.path.join(addon_path, "resources", "language", lang_folder, "strings.po")
            if not os.path.exists(po_path):
                continue

            try:
                po_file = polib.pofile(po_path)
                hit = po_file.find("#" + label_id, by="msgctxt")
                if hit:
                    language = lang_folder.replace("resource.language.", "")
                    tooltips += "<b>%s <i>(%s)</i>:</b> %s<br>" % (
                        language,
                        addon_id,
                        hit.msgstr if hit.msgstr else hit.msgid,
                    )
            except Exception:
                pass

        return tooltips if tooltips else f"<i>Label {label_id} not found in {addon_id}</i>"

    def get_po_files(self):
        """Get the engine's PO files, with a live Kodi instance's ahead of them."""
        po_files = []
        seen = set()
        live = [po for client in (kodi, self.kodi) for po in getattr(client, "po_files", None) or []]
        for po in live + super().get_po_files():
            if id(po) not in seen:
                seen.add(id(po))
                po_files.append(po)
        return po_files

    def get_colors(self):
        """Get every color the addon knows, Kodi core ones included."""
        return list(self.addon.colors) if self.addon else []

    def get_color_info_html(self, color_string):
        """Get an HTML swatch with alpha for a color name or hex value; None when it is neither."""
        color_info = ""
        colors = self.addon.colors if self.addon else []
        for item in colors:
            if item["name"] == color_string:
                color_hex = "#" + item["content"][2:]
                cont_color = get_contrast_color(color_hex)
                alpha_percent = round(
                    int(item["content"][:2], 16) / 255 * 100
                )
                in_addon = item["file"].startswith(self.addon.path)
                source = self.addon.type if in_addon else "kodi"
                color_info += (
                    '%s <i>(%s)</i>&nbsp;<a href="test" style="background-color:%s;color:%s">'
                    "%s</a> %d %% alpha<br>"
                    % (
                        os.path.basename(item["file"]),
                        source,
                        color_hex,
                        cont_color,
                        item["content"],
                        alpha_percent,
                    )
                )
        if color_info:
            return color_info
        if all(c in string.hexdigits for c in color_string) and len(color_string) == 8:
            color_hex = "#" + color_string[2:]
            cont_color = get_contrast_color(color_hex)
            alpha_percent = round(int(color_string[:2], 16) / 255 * 100)
            return '<a href="test" style="background-color:%s;color:%s">%d %% alpha</a>' % (
                color_hex,
                cont_color,
                alpha_percent,
            )

    def build_translate_label(self, label_id, view):
        """Build the localize expression for the label id, shaped for the scope under the caret."""
        if not self.addon:
            return str(label_id)

        scope_name = view.scope_name(view.sel()[0].b)
        if (
            "text.xml.kodi" in scope_name
            and self.addon.type == "python"
            and _is_addon_string_id(label_id)
        ):
            return "$ADDON[%s %i]" % (self.addon.name, label_id)
        elif "text.xml.kodi" in scope_name:
            return "$LOCALIZE[%i]" % label_id
        elif "source.python" in scope_name and _is_addon_string_id(label_id):
            return "ADDON.getLocalizedString(%i)" % label_id
        elif "source.python" in scope_name:
            return "xbmc.getLocalizedString(%i)" % label_id
        else:
            return str(label_id)

    def get_image_info(self, path):
        """HTML rows of type, dimensions and size for an image path, empty when unreadable."""
        if not self.addon:
            return ""
        imagepath = self.addon.translate_path(path)
        if not os.path.exists(imagepath) or os.path.isdir(imagepath):
            return ""
        info = imageparser.get_image_info(imagepath)
        text = ["<b>%s</b>: %s" % (k, v) for k, v in info]
        return "<br>".join(text)

    @staticmethod
    def get_ancestor_info(element):
        """HTML summary of the position tags found on every ancestor."""
        values = {}
        for anc in element.iterancestors():
            for sib in anc.iterchildren():
                if sib.tag in POS_TAGS:
                    if sib.tag in values:
                        values[sib.tag].append(sib.text)
                    else:
                        values[sib.tag] = [sib.text]
        if not values:
            return ""
        anc_info = ["<b>{}:</b> {}".format(k, v) for k, v in values.items()]
        anc_info = "<br>".join(anc_info)
        return "<b>Absolute position</b><br>{}".format(anc_info)
