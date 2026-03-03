"""
Data loading and initialization mixin for InfoProvider.
"""

from __future__ import annotations

import os
import json
import copy
import logging
from typing import Any
from lxml import etree as ET

from .. import utils
from ..addon import Addon
from ..kodi import kodi
from ..validation.constants import PARSER

logger = logging.getLogger(__name__)


class LoaderMixin:
    """Handles loading Kodi data, addon initialization, and settings."""

    addon: Any
    template_root: Any
    WINDOW_FILENAMES: list
    WINDOW_NAMES: list
    WINDOW_IDS: list
    builtins: list
    conditions: list
    template_attribs: dict
    template_values: dict
    settings: dict
    kodi_path: str | None
    _fatal_xml_error: str | None

    def load_data(self, kodi_version="omega"):
        """
        Load control templates (controls.xml) and builtins/conditions (data.xml).
        """
        try:
            import sublime  # packaged load via Sublime API

            controls = sublime.load_resource(
                f"Packages/KodiDevKit/data/{kodi_version}/controls.xml"
            )
            self.template_root = ET.fromstring(controls.encode("utf-8"), PARSER)

            data = sublime.load_resource(
                f"Packages/KodiDevKit/data/{kodi_version}/data.xml"
            )
            root = ET.fromstring(data.encode("utf-8"), PARSER)

            WINDOW_MAP = json.loads(
                sublime.load_resource(
                    f"Packages/KodiDevKit/data/{kodi_version}/windows.json"
                )
            )

        except (ImportError, OSError):
            path = os.path.normpath(os.path.abspath(__file__))
            folder = os.path.split(path)[0]

            self.template_root = utils.get_root_from_file(
                os.path.join(folder, "..", "..", "data", kodi_version, "controls.xml")
            )
            root = utils.get_root_from_file(
                os.path.join(folder, "..", "..", "data", kodi_version, "data.xml")
            )
            with open(
                os.path.join(folder, "..", "..", "data", kodi_version, "windows.json"), "r"
            ) as f:
                WINDOW_MAP = json.load(f)

        if root is None:
            raise ValueError(f"Failed to load data.xml for Kodi version {kodi_version}")
        if self.template_root is None:
            raise ValueError(f"Failed to load controls.xml for Kodi version {kodi_version}")

        self.WINDOW_FILENAMES = [item[2] for item in WINDOW_MAP]
        self.WINDOW_NAMES = [item[0] for item in WINDOW_MAP]
        self.WINDOW_IDS = [str(item[1]) for item in WINDOW_MAP]

        builtins_elem = root.find("builtins")
        self.builtins = [
            [i.find("code").text, i.find("help").text] for i in builtins_elem
        ] if builtins_elem is not None else []

        conditions_elem = root.find("conditions")
        self.conditions = [
            [i.find("code").text, i.find("help").text] for i in conditions_elem
        ] if conditions_elem is not None else []

        for include in self.template_root.xpath("//include[@name]"):
            for node in self.template_root.xpath("//include[not(@*)]"):
                if node.text == include.attrib.get("name"):
                    for child in include.getchildren():
                        node.getparent().append(copy.deepcopy(child))
                    node.getparent().remove(node)
            self.template_root.remove(include)

        self.template_attribs = {}
        self.template_values = {}
        for template in self.template_root:
            ctype = template.attrib.get("type")
            if not ctype:
                continue

            attribs = {}
            for k, v in template.attrib.items():
                if k == "type":
                    continue
                attribs[k] = v

            for i in template.iterchildren():
                attribs[i.tag] = i.attrib

            self.template_attribs[ctype] = attribs
            self.template_values[template.attrib.get("type")] = {
                i.tag: i.text for i in template.iterchildren()
            }

    def init_addon(self, path):
        """
        Scan addon folder and parse skin content etc.
        If any XML is broken, stop immediately and set _fatal_xml_error.
        """
        from lxml.etree import XMLSyntaxError

        self.addon = None
        self._fatal_xml_error = None
        addon_xml = os.path.join(path, "addon.xml")
        if not os.path.exists(addon_xml):
            return

        logger.info("Kodi project detected: %s", addon_xml)
        self.addon = Addon.by_project(path, self.settings)

        try:
            kodi_ver = getattr(self.addon, "api_version", "omega")
            self.load_data(kodi_ver)
        except Exception as e:
            logger.warning("Failed to load control schema: %s", e)

        try:
            kodi.load_settings(self.settings, force=True)
            kodi.update_labels()
        except Exception as e:
            logger.warning("Failed to load Kodi core labels: %s", e)
        if not self.addon:
            return

        for xml_path in self.addon.get_xml_files():
            try:
                root = utils.get_root_from_file(xml_path)
                if root is None:
                    raise XMLSyntaxError("Unparseable file", xml_path, 0, 0)
            except XMLSyntaxError:
                logger.error("Unparseable file: %s", os.path.basename(xml_path), exc_info=True)
                self._fatal_xml_error = xml_path
                return

    def load_settings(self, settings):
        """
        Load settings file.
        """
        self.settings = settings
        self.kodi_path = settings.get("kodi_path")
        logger.info("kodi path: %s", self.kodi_path)

