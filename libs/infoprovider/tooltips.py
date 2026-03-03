"""
Tooltip and popup content mixin for InfoProvider.
"""

from __future__ import annotations

import os
import string
import logging
from .. import utils
from ..kodi import kodi
try:
    from ..utils import images as imageparser
except (ImportError, ModuleNotFoundError):
    imageparser = None
from ..validation.constants import POS_TAGS

from typing import Any

logger = logging.getLogger(__name__)


class TooltipMixin:
    """Provides tooltip/popup content for the editor."""

    addon: Any
    settings: dict
    kodi: Any
    kodi_path: str | None

    def return_label(self, selection):
        """
        Return formatted label for id in *selection.
        """
        tooltips = ""
        if not selection.isdigit():
            return ""
        seen_labels = set()
        for po_file in self.get_po_files():
            hit = po_file.find("#" + selection, by="msgctxt")
            if not hit:
                continue
            language = po_file.language.replace("resource.language.", "")

            source_label = ""
            if hasattr(po_file, 'fpath') and po_file.fpath:
                fpath = str(po_file.fpath)
                if self.addon and self.addon.path and fpath.startswith(self.addon.path):
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
        """
        Return formatted label for addon string $ADDON[addon.id label_id].
        """
        from .. import polib

        if not label_id.isdigit():
            return ""

        kodi_path = self.settings.get("kodi_path", "")
        if not kodi_path:
            return ""

        portable = self.settings.get("portable_mode", False)
        if portable:
            addon_path = os.path.join(kodi_path, "portable_data", "addons", addon_id)
        else:
            addon_path = os.path.join(kodi_path, "addons", addon_id)

        if not os.path.exists(addon_path):
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
        """
        Aggregate active PO files from kodi module, live instance, and addon.
        """
        po_files = []
        seen = set()

        try:
            from ..kodi import kodi as kodi_mod
            if getattr(kodi_mod, "po_files", None):
                for po in kodi_mod.po_files:
                    po_id = id(po)
                    if po_id not in seen:
                        seen.add(po_id)
                        po_files.append(po)
        except Exception:
            pass

        if self.kodi and hasattr(self.kodi, "po_files"):
            for po in self.kodi.po_files:  # type: ignore[attr-defined]
                po_id = id(po)
                if po_id not in seen:
                    seen.add(po_id)
                    po_files.append(po)

        if self.addon and hasattr(self.addon, "po_files"):
            for po in self.addon.po_files:
                po_id = id(po)
                if po_id not in seen:
                    seen.add(po_id)
                    po_files.append(po)

        return po_files

    def get_colors(self):
        """
        get list of all colors (core + addon)
        """
        colors = []
        if kodi.colors:
            colors.extend(kodi.colors)
        if self.addon and self.addon.colors:
            colors.extend(self.addon.colors)
        return colors

    def get_color_labels(self):
        return self.addon.color_labels if self.addon else set()

    def get_color_info_html(self, color_string):
        """
        Build a small HTML swatch + info for a color value or name.
        """
        color_info = ""
        colors = self.addon.colors if self.addon else []
        for item in colors:
            if item["name"] == color_string:
                color_hex = "#" + item["content"][2:]
                cont_color = utils.get_contrast_color(color_hex)
                alpha_percent = round(
                    int(item["content"][:2], 16) / (16 * 16) * 100
                )
                color_info += (
                    '%s&nbsp;<a href="test" style="background-color:%s;color:%s">'
                    "%s</a> %d %% alpha<br>"
                    % (
                        os.path.basename(item["file"]),
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
            cont_color = utils.get_contrast_color(color_hex)
            alpha_percent = round(int(color_string[:2], 16) / (16 * 16) * 100)
            return '<a href="test" style="background-color:%s;color:%s">%d %% alpha</a>' % (
                color_hex,
                cont_color,
                alpha_percent,
            )

    def build_translate_label(self, label_id, view):
        """
        Return the correct localize expression based on scope.
        """
        if not self.addon:
            return str(label_id)

        scope_name = view.scope_name(view.sel()[0].b)
        if (
            "text.xml.kodi" in scope_name
            and self.addon.type == "python"
            and 32000 <= label_id <= 33000
        ):
            return "$ADDON[%s %i]" % (self.addon.name, label_id)
        elif "text.xml.kodi" in scope_name:
            return "$LOCALIZE[%i]" % label_id
        elif "source.python" in scope_name and 32000 <= label_id <= 33000:
            return "ADDON.getLocalizedString(%i)" % label_id
        elif "source.python" in scope_name:
            return "xbmc.getLocalizedString(%i)" % label_id
        else:
            return str(label_id)

    def get_image_info(self, path):
        """
        Return a small HTML snippet with image properties.
        """
        if not imageparser or not self.addon:
            return ""
        imagepath = self.addon.translate_path(path)
        if not os.path.exists(imagepath) or os.path.isdir(imagepath):
            return ""
        info = imageparser.get_image_info(imagepath)
        text = ["<b>%s</b>: %s" % (k, v) for k, v in info]
        return "<br>".join(text)

    @staticmethod
    def get_ancestor_info(element):
        """
        Collect position-ish attributes from ancestors for a quick summary.
        """
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
