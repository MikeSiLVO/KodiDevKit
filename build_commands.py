"""
Build, package, and version management commands.
"""

from __future__ import annotations

import os
import webbrowser
import logging

import sublime
import sublime_plugin

from .libs import utils
from .libs.skin import texturepacker

logger = logging.getLogger("KodiDevKit.build_commands")

SETTINGS_FILE = 'kodidevkit.sublime-settings'


def _infos():
    from .kodidevkit import INFOS
    return INFOS


class BuildAddonCommand(sublime_plugin.WindowCommand):
    """Create an installable zip archive of the currently open addon."""

    def is_visible(self):
        infos = _infos()
        if not infos:
            return False
        addon = getattr(infos, "addon", None)
        return bool(addon) and addon.type == "skin"

    @utils.run_async
    def run(self, pack_textures=True):
        infos = _infos()
        if not infos:
            return None
        addon = getattr(infos, "addon", None)
        if not addon:
            return None
        path = addon.media_path
        if pack_textures:
            texturepacker(media_path=path,
                          settings=sublime.load_settings(SETTINGS_FILE))
        utils.make_archive(folderpath=path,
                           archive=os.path.join(path, os.path.basename(path) + ".zip"))
        if sublime.ok_cancel_dialog(
                "Zip file created!\n"
                "Do you want to show it with a file browser?"):
            webbrowser.open(path)


class BuildThemeCommand(sublime_plugin.WindowCommand):
    """Select and build a theme of the currently open skin."""

    def is_visible(self):
        infos = _infos()
        if not infos:
            return False
        addon = getattr(infos, "addon", None)
        if not addon:
            return False
        theme_path = getattr(addon, "theme_path", None)
        return addon.type == "skin" and theme_path and os.path.exists(theme_path)

    def run(self):
        infos = _infos()
        if not infos:
            return None
        addon = getattr(infos, "addon", None)
        if not addon:
            return None
        get_themes = getattr(addon, "get_themes", None)
        if not get_themes:
            return None
        self.themes = get_themes()
        self.window.show_quick_panel(items=self.themes,
                                     on_select=self.on_done,
                                     selected_index=0)

    def on_done(self, index: int) -> None:
        if index == -1:
            return
        self._build_theme_async(index)

    @utils.run_async
    def _build_theme_async(self, index: int) -> None:
        infos = _infos()
        if not infos:
            return
        addon = getattr(infos, "addon", None)
        if not addon:
            return
        theme_path = getattr(addon, "theme_path", None)
        if not theme_path:
            return
        media_path = os.path.join(theme_path, self.themes[index])
        texturepacker(media_path=media_path,
                      settings=sublime.load_settings(SETTINGS_FILE),
                      xbt_filename=self.themes[index] + ".xbt")
        if sublime.ok_cancel_dialog(
                "Theme file created!\n"
                "Do you want to show it with a file browser?"):
            webbrowser.open(media_path)


class BumpVersionCommand(sublime_plugin.WindowCommand):
    """Bump Addon version by incrementing addon.xml version and adding changelog entry."""

    def run(self):
        self.window.show_quick_panel(items=["Major", "Minor", "Bugfix"],
                                     on_select=self.on_done,
                                     selected_index=0)

    def on_done(self, index):
        if index == -1:
            return None
        infos = _infos()
        if not infos:
            return None
        addon = getattr(infos, "addon", None)
        if not addon:
            return None
        bump_version = getattr(addon, "bump_version", None)
        if bump_version:
            bump_version("9.9.9")
        changelog_path = getattr(addon, "changelog_path", None)
        if changelog_path:
            self.window.open_file(changelog_path)
