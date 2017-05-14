# -*- coding: utf8 -*-

# Copyright (C) 2015 - Philipp Temminghoff <phil65@kodi.tv>
# This program is Free Software see LICENSE file for details

import os
import platform
from .. import utils
from urllib.request import Request, urlopen
import json
import base64
import logging

APP_NAME = "kodi"


class Kodi(object):

    """
    Class representing a kodi installation
    delivers core language files / paths / JSON answers / installed add-ons
    """

    def __init__(self, settings=None):
        self.settings = settings
        self.po_files = []
        self.colors = []
        self.color_labels = []
        self.json_url = None
        self.kodi_path = None
        self.userdata_folder = None

    @utils.run_async
    def request_async(self, method, params):
        """
        send JSON command *data to Kodi in separate thread,
        also needs *settings for remote ip etc.
        """
        return self.request(method,
                            params)

    def request(self, method, params=None):
        """
        send JSON command *data to Kodi,
        also needs *settings for remote ip etc.
        """
        if not self.json_url:
            return None
        data = {"jsonrpc": "2.0",
                "method": method,
                "id": 1}
        if params:
            data["params"] = params
        credentials = '{}:{}'.format(self.settings.get("kodi_username", "kodi"),
                                     self.settings.get("kodi_password", ""))
        headers = {'Content-Type': 'application/json',
                   'Authorization': b'Basic ' + base64.b64encode(credentials.encode('UTF-8'))}
        request = Request(url=self.json_url + "/jsonrpc",
                          data=json.dumps(data).encode('utf-8'),
                          headers=headers)
        try:
            result = urlopen(request).read()
            result = json.loads(result.decode("utf-8"))
            utils.prettyprint(result)
            return result
        except Exception:
            return None

    def get_colors(self):
        """
        create color list by parsing core color file
        """
        self.colors = []
        if not os.path.exists(self.color_file_path):
            return False
        root = utils.get_root_from_file(self.color_file_path)
        for node in root.findall("color"):
            color = {"name": node.attrib["name"],
                     "line": node.sourceline,
                     "content": node.text,
                     "file": self.color_file_path}
            self.colors.append(color)
        logging.info("found color file %s including %i colors" % (self.color_file_path, len(self.colors)))
        self.color_labels = {i["name"] for i in self.colors}

    def get_userdata_folder(self):
        """
        return userdata folder based on platform and portable setting
        """
        if platform.system() == "Linux":
            return os.path.join(os.path.expanduser("~"), ".%s" % APP_NAME)
        elif platform.system() == "Windows":
            if self.settings.get("portable_mode"):
                return os.path.join(self.kodi_path, "portable_data")
            else:
                return os.path.join(os.getenv('APPDATA'), APP_NAME)
        elif platform.system() == "Darwin":
            return os.path.join(os.path.expanduser("~"), "Application Support", APP_NAME, "userdata")

    @property
    def user_addons_path(self):
        """
        get path to userdata addon dir
        """
        return os.path.join(self.userdata_folder, "addons")

    @property
    def core_addons_path(self):
        """
        get path to core addon dir
        """
        return os.path.join(self.kodi_path, "addons")

    @property
    def color_file_path(self):
        """
        get path to core color xml
        """
        return os.path.join(self.kodi_path, "system", "colors.xml")

    @property
    def default_skin_path(self):
        """
        get path to userdata addon dir
        """
        return os.path.join(self.user_addons_path, "skin.estuary", "xml")

    def get_userdata_addons(self):
        """
        get list of folders from userdata addon dir
        """
        if not os.path.exists(self.user_addons_path):
            return []
        return [f for f in os.listdir(self.user_addons_path) if not os.path.isfile(f)]

    def load_settings(self, settings):
        """
        init instance with *settings
        """
        self.settings = settings
        self.json_url = self.settings.get("kodi_address", "http://localhost:8080")
        self.kodi_path = self.settings.get("kodi_path")
        self.userdata_folder = self.get_userdata_folder()
        self.get_colors()
        self.update_labels()

    def update_labels(self):
        """
        get core po files
        """
        po_files = self.get_po_files(self.user_addons_path)
        languages = {i.language for i in po_files}
        core_po_files = self.get_po_files(self.core_addons_path)
        core_po_files = [i for i in core_po_files if i.language not in languages]
        self.po_files = po_files + core_po_files

    def get_po_files(self, folder):
        """
        get list with pofile objects
        """
        po_files = []
        folders = self.settings.get("language_folders", ["resource.language.en_gb", "English"])
        for item in folders:
            path = utils.check_paths([os.path.join(folder, item, "strings.po"),
                                      os.path.join(folder, item, "resources", "strings.po")])
            if path:
                po_file = utils.get_po_file(path)
                po_file.language = item
                po_files.append(po_file)
        return po_files
