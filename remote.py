"""ADB commands for a Kodi device: push the add-on, fetch the log or a screenshot, reboot."""

from __future__ import annotations

import os
import sublime
import sublime_plugin
from .libs.kodi.adb import KodiAdb

REMOTE = KodiAdb()
SETTINGS_FILE = 'kodidevkit.sublime-settings'


def plugin_loaded():
    """Sublime entry point: load the ADB settings."""
    REMOTE.setup(sublime.load_settings(SETTINGS_FILE))


class KodidevkitRemoteActionsCommand(sublime_plugin.WindowCommand):
    """Command showing the ADB actions for the device in a quick panel."""

    settings: sublime.Settings

    def run(self):
        """Show the actions in a quick panel, the saved device first."""
        self.settings = sublime.load_settings(SETTINGS_FILE)
        active_device = "Set device: %s" % self.settings.get("remote_ip", "")
        listitems = [active_device, "Reconnect", "Send this add-on",
                     "Get log", "Get Screenshot", "Clear cache", "Reboot"]
        self.window.show_quick_panel(items=listitems,
                                     on_select=self.on_done,
                                     selected_index=0)

    def on_done(self, index):
        """Run the picked action, or ask for the device address on the first entry."""
        if index == -1:
            return None
        elif index == 0:
            self.window.show_input_panel("Set remote IP",
                                         self.settings.get("remote_ip", "192.168.0.1"),
                                         self.set_ip,
                                         None,
                                         None)
        elif index == 1:
            REMOTE.adb_reconnect_async()
            self.window.run_command("kodidevkit_remote_actions")
        elif index == 2:
            active_view = self.window.active_view()
            if active_view:
                variables = active_view.extract_variables()
                if "folder" in variables:
                    REMOTE.push_to_box(variables["folder"])
        elif index == 3:
            plugin_path = os.path.join(sublime.packages_path(), "KodiDevKit")
            REMOTE.get_log(self.open_file, plugin_path)
        elif index == 4:
            plugin_path = os.path.join(sublime.packages_path(), "KodiDevKit")
            REMOTE.get_screenshot(self.open_file, plugin_path)
        elif index == 5:
            REMOTE.clear_cache()
        elif index == 6:
            REMOTE.reboot()

    def open_file(self, path):
        """Open a pulled file, the log or a screenshot, in the window."""
        self.window.open_file(path)

    def set_ip(self, ip):
        """Set and save the device address, then reopen the actions menu."""
        self.settings.set("remote_ip", ip)
        sublime.save_settings(SETTINGS_FILE)
        self.window.run_command("kodidevkit_remote_actions")
