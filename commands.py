# -*- coding: utf8 -*-

# Copyright (C) 2015 - Philipp Temminghoff <phil65@kodi.tv>
# This program is Free Software see LICENSE file for details

"""
KodiDevKit is a plugin to assist with Kodi skinning / scripting using Sublime Text 3
"""

import re
import webbrowser
import platform
import os
import logging
from lxml import etree as ET

import sublime
import sublime_plugin

from .libs import utils
from .libs.kodi import kodi

import subprocess

APP_NAME = "Kodi"
SETTINGS_FILE = 'kodidevkit.sublime-settings'
SUBLIME_PATH = utils.get_sublime_path()


class OpenKodiLogCommand(sublime_plugin.WindowCommand):

    """
    open kodi log from its default location
    """

    def run(self):
        filename = "%s.log" % APP_NAME.lower()
        self.log = utils.check_paths([os.path.join(kodi.userdata_folder, filename),
                                      os.path.join(kodi.userdata_folder, "temp", filename),
                                      os.path.join(os.path.expanduser("~"), "Library", "Logs", filename)])
        self.window.open_file(self.log)


class OpenAltKodiLogCommand(sublime_plugin.WindowCommand):

    """
    open alternative kodi log from its default location
    (visible for windows portable mode)
    """

    def visible(self):
        return platform.system() == "Windows" and self.settings.get("portable_mode")

    def run(self):
        filename = "%s.log" % APP_NAME.lower()
        self.log = os.path.join(os.getenv('APPDATA'), APP_NAME, filename)
        self.window.open_file(self.log)


class OpenSourceFromLog(sublime_plugin.TextCommand):

    """
    open file from exception description and jump to according place in code
    """

    def run(self, edit):
        for region in self.view.sel():
            if not region.empty():
                self.view.insert(edit, region.begin(), self.view.substr(region))
                continue
            line_contents = self.view.substr(self.view.line(region))
            match = re.search(r'File "(.*?)", line (\d*), in .*', line_contents)
            if match:
                sublime.active_window().open_file("{}:{}".format(os.path.realpath(match.group(1)),
                                                                 match.group(2)),
                                                  sublime.ENCODED_POSITION)
                return
            match = re.search(r"', \('(.*?)', (\d+), (\d+), ", line_contents)
            if match:
                sublime.active_window().open_file("{}:{}:{}".format(os.path.realpath(match.group(1)),
                                                                    match.group(2),
                                                                    match.group(3)),
                                                  sublime.ENCODED_POSITION)
                return


class GoToOnlineHelpCommand(sublime_plugin.TextCommand):

    """
    open browser and go to doxygen page
    """

    CONTROLS = {"renderaddon": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/d4/d1e/_addon__rendering_control.html",
                "button": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/dc/df7/skin__button_control.html",
                "colorbutton": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/dc/df7/skin__button_control.html",
                "epggrid": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/dc/d06/_e_p_g_grid_control.html",
                "edit": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/d1/dd3/skin__edit_control.html",
                "fadelabel": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/d2/dd7/_fade__label__control.html",
                "fixedlist": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/dc/d4d/_fixed__list__container.html",
                "gamewindow": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/d0/d29/_game__control.html",
                "gamecontroller": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/da/d5a/_game__controller.html",
                "gamecontrollerlist": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/d9/dea/_game__controller__list.html",
                "group": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/d6/d5c/_group__control.html",
                "grouplist": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/d9/dbd/_group__list__control.html",
                "image": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/d9/d53/_image__control.html",
                "label": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/de/d35/_label__control.html",
                "list": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/d7/d75/_list__container.html",
                "mover": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/dc/d20/_mover__control.html",
                "multiimage": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/db/d1b/_multi_image__control.html",
                "panel": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/d8/d76/_panel__container.html",
                "progress": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/df/d47/_progress__control.html",
                "rss": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/de/dd5/_r_s_s_feed__control.html",
                "ranges": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/d4/dcd/_ranges__control.html",
                "radiobutton": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/d8/d26/_radio_button_control.html",
                "resize": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/dd/d53/_resize__control.html",
                "scrollbar": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/d0/d3d/_scroll__bar__control.html",
                "sliderex": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/d5/dec/_settings__slider__control.html",
                "spincontrolex": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/d9/da3/_settings__spin__control.html",
                "slider": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/d9/dd3/_slider__control.html",
                "spincontrol": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/dd/d4f/_spin__control.html",
                "textbox": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/dc/d90/_text__box.html",
                "togglebutton": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/d1/da9/skin__toggle_button_control.html",
                "videowindow": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/df/d07/_video__control.html",
                "visualisation": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/de/d14/_visualisation__control.html",
                "wraplist": "https://xbmc.github.io/docs.kodi.tv/master/kodi-base/d1/d1c/_wrap__list__container.html"
                }

    def is_visible(self):
        region = self.view.sel()[0]
        line_contents = self.view.substr(self.view.line(region))
        scope_name = self.view.scope_name(region.b)
        return "text.xml" in scope_name and "<control " in line_contents

    def run(self, edit):
        region = self.view.sel()[0]
        line = self.view.line(region)
        line_contents = self.view.substr(line)
        try:
            root = ET.fromstring(line_contents + "</control>")
            control_type = root.attrib["type"]
            self.go_to_help(control_type)
        except Exception:
            logging.info("error when trying to open from %s" % line_contents)

    def go_to_help(self, word):
        """
        open browser and go to wiki page for control with type *word
        """
        webbrowser.open_new(self.CONTROLS[word])


class AppendTextCommand(sublime_plugin.TextCommand):

    """
    append a line of text to the current view
    """

    def run(self, edit, label):
        self.view.insert(edit, self.view.size(), label + "\n")


class LogCommand(sublime_plugin.TextCommand):

    """
    log text into a text panel
    """

    def run(self, edit, label, panel_name='example'):
        if not hasattr(self, "output_view"):
            self.output_view = self.view.window().create_output_panel(panel_name)
        self.output_view.insert(edit, self.output_view.size(), label + '\n')
        self.output_view.show(self.output_view.size())
        self.view.window().run_command("show_panel", {"panel": "output." + panel_name})


class CreateElementRowCommand(sublime_plugin.WindowCommand):

    """
    Creates duplicates based on a template defined by current text selection
    Show input panel for user to enter number of items to generate,
    then execute ReplaceXmlElementsCommand
    """

    def run(self):
        self.window.show_input_panel("Enter number of items to generate",
                                     "1",
                                     on_done=self.generate_items,
                                     on_change=None,
                                     on_cancel=None)

    def generate_items(self, num_items):
        self.window.run_command("replace_xml_elements", {"num_items": num_items})


class ReplaceXmlElementsCommand(sublime_plugin.TextCommand):

    """
    Create *num_items duplicates based on template defined by current text selection
    """

    def run(self, edit, num_items):
        if not num_items.isdigit():
            return None
        selected_text = self.view.substr(self.view.sel()[0])
        text = ""
        reg = re.search(r"\[(-?[0-9]+)\]", selected_text)
        offset = int(reg.group(1)) if reg else 0
        for i in range(int(num_items)):
            text = text + selected_text.replace("[%i]" % offset, str(i + offset)) + "\n"
            i += 1
        for region in self.view.sel():
            self.view.replace(edit, region, text)
            break


class EvaluateMathExpressionPromptCommand(sublime_plugin.WindowCommand):

    """
    Allows calculations for currently selected regions
    Shows an input panel so user can enter equation, then execute EvaluateMathExpressionCommand
    """

    def run(self):
        self.window.show_input_panel("Write Equation (x = selected int)",
                                     "x",
                                     self.evaluate,
                                     None,
                                     None)

    def evaluate(self, equation):
        self.window.run_command("evaluate_math_expression", {'equation': equation})


class EvaluateMathExpressionCommand(sublime_plugin.TextCommand):

    """
    Change currently selected regions based on *equation
    """

    def run(self, edit, equation):
        for i, region in enumerate(self.view.sel()):
            text = self.view.substr(region)
            temp_equation = equation.replace("i", str(i))
            if text.replace('-', '').isdigit():
                temp_equation = temp_equation.replace("x", text)
            self.view.replace(edit, region, str(eval(temp_equation)).replace(".0", ""))


class ColorPickerCommand(sublime_plugin.WindowCommand):

    """
    Launch ColorPicker, return kodi-formatted color string
    """

    def is_visible(self):
        settings = sublime.load_settings('KodiColorPicker.sublime-settings')
        settings.set('color_pick_return', None)
        self.window.run_command('color_pick_api_is_available',
                                {'settings': 'KodiColorPicker.sublime-settings'})
        return bool(settings.get('color_pick_return', False))

    def run(self):
        settings = sublime.load_settings('KodiColorPicker.sublime-settings')
        settings.set('color_pick_return', None)
        self.window.run_command('color_pick_api_get_color',
                                {'settings': 'KodiColorPicker.sublime-settings',
                                 'default_color': '#ff0000'})
        color = settings.get('color_pick_return')
        if color:
            self.window.active_view().run_command("insert",
                                                  {"characters": "FF" + color[1:]})


class SetKodiFolderCommand(sublime_plugin.WindowCommand):

    """
    Show input panel to set kodi folder, set default value according to OS
    """

    def run(self):
        if sublime.platform() == "linux":
            preset_path = "/usr/share/%s/" % APP_NAME.lower()
        elif sublime.platform() == "windows":
            preset_path = "C:/%s/" % APP_NAME.lower()
        elif platform.system() == "Darwin":
            preset_path = os.path.join(os.path.expanduser("~"),
                                       "Applications",
                                       "%s.app" % APP_NAME,
                                       "Contents",
                                       "Resources",
                                       APP_NAME)
        else:
            preset_path = ""
        self.window.show_input_panel("Set Kodi folder",
                                     preset_path,
                                     self.set_kodi_folder,
                                     None,
                                     None)

    @staticmethod
    def set_kodi_folder(path):
        """
        Sets kodi path to *path and saves it if file exists.
        """
        if os.path.exists(path):
            sublime.load_settings(SETTINGS_FILE).set("kodi_path", path)
            sublime.save_settings(SETTINGS_FILE)
        else:
            logging.critical("Folder %s does not exist." % path)


class ExecuteBuiltinPromptCommand(sublime_plugin.WindowCommand):

    """
    Shows an input dialog, then triggers ExecuteBuiltinCommand
    """

    def run(self):
        self.settings = sublime.load_settings(SETTINGS_FILE)
        self.window.show_input_panel("Execute builtin",
                                     self.settings.get("prev_json_builtin", ""),
                                     self.execute_builtin,
                                     None,
                                     None)

    def execute_builtin(self, builtin):
        self.settings.set("prev_json_builtin", builtin)
        self.window.run_command("execute_builtin", {"builtin": builtin})


class ExecuteBuiltinCommand(sublime_plugin.WindowCommand):

    """
    Sends json request to execute a builtin using script.toolbox
    """

    def run(self, builtin):
        params = {"addonid": "script.toolbox",
                  "params": {"info": "builtin",
                             "id": builtin}}
        kodi.request_async(method="Addons.ExecuteAddon",
                           params=params)


class GetInfoLabelsPromptCommand(sublime_plugin.WindowCommand):

    """
    Displays the values of chosen infolabels via output panel
    User chooses infolabels via input panel
    """

    def run(self):
        self.settings = sublime.load_settings(SETTINGS_FILE)
        self.window.show_input_panel("Get InfoLabels (comma-separated)",
                                     self.settings.get("prev_infolabel", ""),
                                     self.show_info_label,
                                     None,
                                     None)

    @utils.run_async
    def show_info_label(self, label_string):
        """
        fetch infolabel with name *label_string from kodi via json and display it.
        """
        self.settings.set("prev_infolabel", label_string)
        words = label_string.split(",")
        logging.warning("send request...")
        result = kodi.request(method="XBMC.GetInfoLabels",
                              params={"labels": words})
        if result:
            logging.warning("Got result:")
            _, value = result["result"].popitem()
            logging.warning(str(value))


class BrowseKodiVfsCommand(sublime_plugin.WindowCommand):

    """
    Allows to browse the Kodi VFS via JSON-RPC
    """

    def run(self):
        self.nodes = [["video", "library://video"],
                      ["music", "library://music"]]
        self.window.show_quick_panel(items=self.nodes,
                                     on_select=self.on_done,
                                     selected_index=0)

    @utils.run_async
    def on_done(self, index):
        if index == -1:
            return None
        node = self.nodes[index]
        data = kodi.request(method="Files.GetDirectory",
                            params={"directory": node[1], "media": "files"})
        self.nodes = [[item["label"], item["file"]] for item in data["result"]["files"]]
        self.window.show_quick_panel(items=self.nodes,
                                     on_select=self.on_done,
                                     selected_index=0)


class GetInfoBooleansPromptCommand(sublime_plugin.WindowCommand):

    """
    Displays the values of chosen booleans via output panel
    User chooses booleans via input panel
    """

    def run(self):
        self.settings = sublime.load_settings(SETTINGS_FILE)
        self.window.show_input_panel("Get boolean values (comma-separated)",
                                     self.settings.get("prev_boolean", ""),
                                     self.resolve_kodi_condition,
                                     None,
                                     None)

    @utils.run_async
    def resolve_kodi_condition(self, condition):
        """
        show OutputPanel with kodi JSON result for b
        """
        self.settings.set("prev_boolean", condition)
        words = condition.split(",")
        logging.warning("send request...")
        result = kodi.request(method="XBMC.GetInfoBooleans",
                              params={"booleans": words})
        if result:
            logging.warning("Got result:")
            _, value = result["result"].popitem()
            logging.warning(str(value))


class OpenKodiAddonCommand(sublime_plugin.WindowCommand):

    """
    Open another SublimeText instance containing the chosen addon
    """

    def run(self):
        self.nodes = kodi.get_userdata_addons()
        self.window.show_quick_panel(items=self.nodes,
                                     on_select=self.on_done,
                                     selected_index=0)

    def on_done(self, index):
        if index == -1:
            return None
        path = os.path.join(kodi.userdata_folder, "addons", self.nodes[index])
        subprocess.Popen([SUBLIME_PATH, "-n", "-a", path])
