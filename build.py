"""Commands that zip the add-on, build theme bundles and bump the version."""

from __future__ import annotations

import os
import re
import webbrowser
import logging

import sublime
import sublime_plugin

from .libs.addon.addon import Addon
from .libs.utils.files import make_archive
from .libs.utils.decorators import run_async
from .libs.skin.textures import texturepacker
from .libs.reporting.html import REPORT_NAME

logger = logging.getLogger("KodiDevKit.build")

SETTINGS_FILE = 'kodidevkit.sublime-settings'


def _infos():
    """Look up the plugin's shared InfoProvider at call time."""
    from .kodidevkit import INFOS
    return INFOS


class KodidevkitBuildAddonCommand(sublime_plugin.WindowCommand):
    """Command building an installable zip of the loaded skin."""

    def is_visible(self):
        """True when a skin is loaded."""
        infos = _infos()
        if not infos:
            return False
        addon = getattr(infos, "addon", None)
        return bool(addon) and addon.type == "skin"

    def run(self, pack_textures=True):
        """Ask where to save the zip, opening in the add-on folder, named by its id and version."""
        infos = _infos()
        if not infos:
            return None
        addon = getattr(infos, "addon", None)
        if not addon:
            return None

        def build(archive):
            if archive:
                self._build_async(addon, archive, pack_textures)

        sublime.save_dialog(build, file_types=[("Zip archive", ["zip"])], directory=addon.path,
                            name=f"{addon.name}-{addon.version}.zip", extension="zip")

    @run_async
    def _build_async(self, addon, archive, pack_textures):
        """Pack textures if asked, zip the add-on unless packing failed, then offer its folder."""
        if pack_textures and not texturepacker(media_path=addon.media_path,
                                               settings=sublime.load_settings(SETTINGS_FILE)):
            sublime.set_timeout(lambda: sublime.error_message(
                "TexturePacker did not finish, so no zip was made. Check texturepacker_path in the "
                "KodiDevKit settings, and the console for its output."), 0)
            return
        make_archive(folderpath=addon.path, archive=archive, root=addon.name, leave_out=(REPORT_NAME,))
        sublime.set_timeout(lambda: self._offer_folder(archive), 0)

    def _offer_folder(self, archive):
        """Say the zip is made and offer to open its folder in the file browser."""
        if sublime.ok_cancel_dialog(f"{os.path.basename(archive)} created.\n"
                                    "Do you want to show it with a file browser?"):
            webbrowser.open(os.path.dirname(archive))


class KodidevkitBuildThemeCommand(sublime_plugin.WindowCommand):
    """Command building one of the skin's themes into its texture bundle."""

    def is_visible(self):
        """True for a skin with a themes folder."""
        infos = _infos()
        if not infos:
            return False
        addon = getattr(infos, "addon", None)
        if not addon:
            return False
        theme_path = getattr(addon, "theme_path", None)
        return addon.type == "skin" and theme_path and os.path.exists(theme_path)

    def run(self):
        """Show the skin's themes in a quick panel."""
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
        """Build the picked theme in the background."""
        if index == -1:
            return
        self._build_theme_async(index)

    @run_async
    def _build_theme_async(self, index: int) -> None:
        """Build the theme's images into media/<theme>.xbt and offer to open the media folder."""
        infos = _infos()
        if not infos:
            return
        addon = getattr(infos, "addon", None)
        if not addon:
            return
        theme_path = getattr(addon, "theme_path", None)
        if not theme_path:
            return
        theme = self.themes[index]
        if not texturepacker(media_path=os.path.join(theme_path, theme),
                             settings=sublime.load_settings(SETTINGS_FILE),
                             output_path=os.path.join(addon.media_path, theme + ".xbt")):
            sublime.set_timeout(lambda: sublime.error_message(
                "TexturePacker did not finish. Check texturepacker_path in the "
                "KodiDevKit settings, and the console for its output."), 0)
            return
        if sublime.ok_cancel_dialog(
                f"{theme}.xbt created in the media folder.\n"
                "Do you want to show it with a file browser?"):
            webbrowser.open(addon.media_path)


def _next_versions(version):
    """Next major, minor and bugfix versions, led by the next numbered suffix when there is one."""
    m = re.match(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?(.*)$", version or "")
    if not m:
        return []
    x, y, z = (int(g or 0) for g in m.group(1, 2, 3))
    options = [("Major", f"{x + 1}.0.0"), ("Minor", f"{x}.{y + 1}.0"),
               ("Bugfix", f"{x}.{y}.{z + 1}")]
    pre = re.match(r"(.*?)(\d+)$", m.group(4))
    if pre:
        label = f"Next {pre.group(1).strip('~+.-') or 'build'}"
        options.insert(0, (label, f"{x}.{y}.{z}{pre.group(1)}{int(pre.group(2)) + 1}"))
    return options


class KodidevkitBumpVersionCommand(sublime_plugin.WindowCommand):
    """Command bumping the add-on version, with blank news and changelog entries to fill."""

    addon: Addon
    options: list[tuple[str, str]]

    def is_visible(self):
        """True when an add-on is loaded."""
        infos = _infos()
        return bool(infos and getattr(infos, "addon", None))

    def run(self):
        """Offer the next versions and a custom one in a quick panel."""
        infos = _infos()
        addon = getattr(infos, "addon", None) if infos else None
        if not addon:
            return
        self.addon = addon
        current = self.addon.version or ""
        self.options = _next_versions(current) + [("Custom", "")]
        items = [[label, f"{current} -> {version}" if version else "Type a version"]
                 for label, version in self.options]
        self.window.show_quick_panel(items=items, on_select=self.on_done, selected_index=0)

    def on_done(self, index):
        """Bump to the picked version, or ask for one when Custom is picked."""
        if index == -1:
            return
        version = self.options[index][1]
        if version:
            self._bump(version)
        else:
            self.window.show_input_panel("New version:", self.addon.version or "",
                                         self._bump, None, None)

    def _bump(self, version):
        """Bump to the version and open each blank entry at its dash."""
        version = version.strip()
        if not version:
            return
        for path, line, col in self.addon.bump_version(version):
            self.window.open_file(f"{path}:{line}:{col}", sublime.ENCODED_POSITION)
