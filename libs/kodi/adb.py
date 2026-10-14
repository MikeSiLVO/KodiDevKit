"""ADB helpers for pushing skin files to Android-based Kodi devices."""

from __future__ import annotations

import subprocess
from ..utils.decorators import check_busy, run_async
import os
import logging
import posixpath
import xml.etree.ElementTree as ET

DEFAULT_SETTINGS = {"remote_ip": "localhost"}


def _xml_folders(addon_path):
    """Names of the add-on's xml folders: a skin's res folders, else the script window ones."""
    script_folders = {"1080i", "720p"}
    try:
        root = ET.parse(os.path.join(addon_path, "addon.xml")).getroot()
    except (ET.ParseError, OSError):
        return script_folders
    folders = {os.path.basename(res.get("folder") or "") for res in root.iter("res")} - {""}
    return folders or script_folders


class KodiAdb:
    """ADB client that pushes files to and pulls logs from an Android Kodi device."""

    def __init__(self):
        self.is_busy = False
        self.connected = False
        self.remote_ip = None
        self.userdata_folder = None
        self.settings = None
        self.setup(DEFAULT_SETTINGS)

    def setup(self, settings):
        """Set up the device address and userdata folder from the settings."""
        self.settings = settings
        self.userdata_folder = self.settings.get("remote_userdata_folder")
        self.remote_ip = self.settings.get("remote_ip")

    @property
    def home_folder(self):
        """Kodi's home folder on the device, the parent when the setting names userdata itself."""
        folder = (self.userdata_folder or "").rstrip("/")
        return posixpath.dirname(folder) if posixpath.basename(folder) == "userdata" else folder

    @staticmethod
    def cmd(program, args):
        """Run the program with its args, logging its output; a failure is logged, never raised."""
        command = [program]
        for arg in args:
            command.append(arg)
        logging.warning(" ".join(command))
        try:
            output = subprocess.check_output(command, stderr=subprocess.STDOUT)
            logging.warning(output.decode("utf-8").replace('\r', '').replace('\n', ''))
        except subprocess.CalledProcessError as e:
            logging.warning("%s\nErrorCode: %s" % (e, str(e.returncode)))
        except Exception as e:
            logging.warning(e)

    def adb_connect(self, server_ip):
        """Connect adb to the device and remember its address."""
        self.remote_ip = server_ip
        logging.warning("Connect to remote with server_ip %s" % server_ip)
        self.cmd("adb", ["connect", server_ip])
        self.connected = True

    @check_busy
    def adb_reconnect(self, server_ip=""):
        """Reconnect adb, to the given address or else the saved one."""
        if not server_ip:
            server_ip = self.remote_ip
        self.adb_disconnect()
        self.adb_connect(server_ip)

    @run_async
    def adb_reconnect_async(self, server_ip=""):
        """Background-thread variant of `adb_reconnect()`."""
        self.adb_reconnect(server_ip)

    def adb_disconnect(self):
        """Disconnect adb from every device."""
        logging.warning("Disconnect from remote")
        self.cmd("adb", ["disconnect"])
        self.connected = False

    @check_busy
    def adb_pull(self, path, target):
        """Pull a device path to the local target."""
        self.cmd("adb", ["pull", path, target])

    @run_async
    @check_busy
    def push_to_box(self, addon, all_file=False):
        """Push the add-on's xml folders to the device, or all of its files."""
        logging.warning("push %s to remote" % addon)
        xml_folders = _xml_folders(addon)
        for root, _, files in os.walk(addon):
            if ".git" in root.split(os.sep):
                continue
            if not all_file and os.path.basename(root) not in xml_folders:
                continue
            target = '{}/addons/{}{}'.format(self.home_folder,
                                             os.path.basename(addon),
                                             root.replace(addon, "").replace('\\', '/'))
            self.cmd("adb", ["shell", "mkdir", target])
            for f in files:
                if f.endswith(('.pyc', '.pyo')):
                    continue
                self.cmd("adb", ["push",
                                 os.path.join(root, f).replace('\\', '/'),
                                 target.replace('\\', '/')])
        logging.warning("All files pushed")

    @run_async
    def get_log(self, open_function, target):
        """Get kodi.log from the device and open it."""
        logging.warning("Pull logs from remote")
        self.adb_pull("%s/temp/kodi.log" % self.home_folder, target)
        logging.warning("Finished pulling logs")
        open_function(os.path.join(target, "kodi.log"))

    @run_async
    @check_busy
    def get_screenshot(self, f_open, target):
        """Get a device screenshot and open it."""
        logging.warning("Pull screenshot from remote")
        self.cmd("adb", ["shell", "screencap", "-p", "/sdcard/screen.png"])
        self.cmd("adb", ["pull", "/sdcard/screen.png", target])
        self.cmd("adb", ["shell", "rm", "/sdcard/screen.png"])
        logging.warning("Finished pulling screenshot")
        f_open(os.path.join(target, "screen.png"))

    @run_async
    @check_busy
    def clear_cache(self):
        """Clear the device cache by deleting temp in Kodi's home folder."""
        if not self.userdata_folder:
            logging.warning("remote_userdata_folder not configured")
            return
        self.cmd("adb", ["shell", "rm", "-rf", posixpath.join(self.home_folder, "temp")])

    @run_async
    def reboot(self):
        """Reboot the device."""
        self.cmd("adb", ["reboot"])
