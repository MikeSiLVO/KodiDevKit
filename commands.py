"""
KodiDevKit is a plugin to assist with Kodi skinning / scripting
using Sublime Text 4
"""

import re
import glob
import webbrowser
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

FILE_ERROR_PATTERN = re.compile(r'File "(.*?)", line (\d*), in .*')
TUPLE_ERROR_PATTERN = re.compile(r"', \('(.*?)', (\d+), (\d+), ")


class OpenKodiLogCommand(sublime_plugin.WindowCommand):

    """
    open kodi log from its default location
    """

    def run(self):
        filename = "%s.log" % APP_NAME.lower()

        if not kodi.userdata_folder:
            kodi.userdata_folder = kodi.get_userdata_folder()

        paths = []
        if kodi.userdata_folder:
            paths.extend([
                os.path.join(kodi.userdata_folder, filename),
                os.path.join(kodi.userdata_folder, "temp", filename)
            ])
        paths.append(os.path.join(os.path.expanduser("~"), "Library", "Logs", filename))

        self.log = utils.check_paths(paths)
        if self.log:
            self.window.open_file(self.log)
        else:
            sublime.error_message(
                f"Could not find Kodi log file: {filename}\n\n"
                f"Checked locations:\n" + "\n".join(f"  • {p}" for p in paths)
            )


class OpenAltKodiLogCommand(sublime_plugin.WindowCommand):

    """
    open alternative kodi log from its default location
    (visible for windows portable mode)
    """

    def is_visible(self):
        settings = sublime.load_settings(SETTINGS_FILE)
        return sublime.platform() == "windows" and settings.get("portable_mode")

    def run(self):
        filename = "%s.log" % APP_NAME.lower()
        appdata = os.getenv('APPDATA')

        if not appdata:
            sublime.error_message("Could not find APPDATA environment variable.")
            return

        self.log = os.path.join(appdata, APP_NAME, filename)

        if os.path.exists(self.log):
            self.window.open_file(self.log)
        else:
            sublime.error_message(
                f"Could not find Kodi log file:\n{self.log}\n\n"
                f"The file may not exist yet."
            )


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
            match = FILE_ERROR_PATTERN.search(line_contents)
            if match:
                sublime.active_window().open_file("{}:{}".format(os.path.realpath(match.group(1)),
                                                                 match.group(2)),
                                                  sublime.ENCODED_POSITION)
                return
            match = TUPLE_ERROR_PATTERN.search(line_contents)
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
        return "text.xml.kodi" in scope_name and "<control " in line_contents

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
        window = self.view.window()
        if not window:
            return
        if not hasattr(self, "output_view"):
            self.output_view = window.create_output_panel(panel_name)
        self.output_view.insert(edit, self.output_view.size(), label + '\n')
        self.output_view.show(self.output_view.size())
        window.run_command("show_panel", {"panel": "output." + panel_name})


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
        view = self.window.active_view()
        if color and view:
            view.run_command("insert", {"characters": "FF" + color[1:]})


class SetKodiFolderCommand(sublime_plugin.WindowCommand):

    """
    Show input panel to set kodi folder, set default value according to OS
    """

    def run(self):
        if sublime.platform() == "linux":
            preset_path = "/usr/share/%s/" % APP_NAME.lower()
        elif sublime.platform() == "windows":
            preset_path = "C:/%s/" % APP_NAME.lower()
        elif sublime.platform() == "osx":
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


class _KodiQueryPromptCommand(sublime_plugin.WindowCommand):
    """Base for commands that prompt for comma-separated values and query Kodi JSON-RPC."""
    _prompt = ""
    _settings_key = ""
    _method = ""
    _param_key = ""
    _panel_name = ""
    _title = ""
    _error_subject = ""

    def run(self):
        self.settings = sublime.load_settings(SETTINGS_FILE)
        self.window.show_input_panel(self._prompt,
                                     self.settings.get(self._settings_key, ""),
                                     self._on_input,
                                     None,
                                     None)

    @utils.run_async
    def _on_input(self, input_string):
        from .libs.sublime.logging import ResultsDisplayPanel

        self.settings.set(self._settings_key, input_string)
        words = [w.strip() for w in input_string.split(",")]

        result = kodi.request(method=self._method,
                              params={self._param_key: words})

        output_mode = self.settings.get("json_rpc_output_mode", "output_panel")

        def show_results():
            panel = ResultsDisplayPanel(panel_name=self._panel_name)

            if result and "result" in result:
                panel.display_results(
                    data=result["result"],
                    title=self._title,
                    mode=output_mode,
                    window=self.window,
                    key_order=words
                )
            else:
                error_msg = (
                    f"ERROR: Failed to get {self._error_subject} from Kodi\n\n"
                    "Please check:\n"
                    "  • Kodi is running\n"
                    "  • JSON-RPC is enabled in Kodi settings\n"
                    "  • Connection settings in KodiDevKit preferences\n"
                )
                panel.display_error(error_msg, output_mode, self.window)

        sublime.set_timeout(show_results, 0)


class GetInfoLabelsPromptCommand(_KodiQueryPromptCommand):
    _prompt = "Get InfoLabels (comma-separated)"
    _settings_key = "prev_infolabel"
    _method = "XBMC.GetInfoLabels"
    _param_key = "labels"
    _panel_name = "kodi_infolabels"
    _title = "KODI INFOLABELS"
    _error_subject = "InfoLabels"


class BrowseKodiVfsCommand(sublime_plugin.WindowCommand):
    """Browse the Kodi VFS via JSON-RPC."""

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


class GetInfoBooleansPromptCommand(_KodiQueryPromptCommand):
    _prompt = "Get boolean values (comma-separated)"
    _settings_key = "prev_boolean"
    _method = "XBMC.GetInfoBooleans"
    _param_key = "booleans"
    _panel_name = "kodi_booleans"
    _title = "KODI BOOLEAN CONDITIONS"
    _error_subject = "Boolean conditions"


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
        if not kodi.userdata_folder:
            logging.error("Cannot open addon: userdata_folder not configured")
            return None
        path = os.path.join(kodi.userdata_folder, "addons", self.nodes[index])
        if SUBLIME_PATH:
            subprocess.Popen([SUBLIME_PATH, "-n", "-a", path])


class ValidationRunner:
    """Encapsulates validation check execution with progress tracking."""

    def __init__(self, provider, update_progress):
        """
        Initialize the validation runner.

        Args:
            provider: InfoProvider instance with check methods
            update_progress: Callback function(step, message) for progress updates
        """
        self.provider = provider
        self.update_progress = update_progress
        self.all_issues = {}

    def _run_check(self, step, name, check_method):
        """
        Run a single validation check with progress tracking.

        Args:
            step: Progress step number (1-7)
            name: Display name of the check
            check_method: Provider method to call (e.g., provider.check_variables)
        """
        def progress_callback(message):
            self.update_progress(step, f"{name}: {message}")

        self.update_progress(step, f"Checking {name.lower()}...")
        self.all_issues[name] = check_method(progress_callback=progress_callback)

    def run_all(self):
        """
        Run all validation checks in sequence.

        Returns:
            dict: All issues collected from all checks
        """
        self.update_progress(0, "Starting validation checks...")

        self._run_check(1, "Variables", self.provider.check_variables)
        self._run_check(2, "Includes", self.provider.check_includes)
        self._run_check(3, "Labels", self.provider.check_labels)
        self._run_check(4, "Fonts", self.provider.check_fonts)
        self._run_check(5, "IDs", self.provider.check_ids)
        self._run_check(6, "Images", self.provider.check_images)
        self._run_check(7, "XML Validation", self.provider.check_values)

        return self.all_issues


class ReportGenerator:
    """Handles report file generation and cleanup."""

    @staticmethod
    def get_report_path(skin_name):
        """
        Determine report directory and filename.

        Args:
            skin_name: Name of the skin being validated

        Returns:
            tuple: (report_path, report_dir, safe_skin_name)
        """
        from datetime import datetime

        settings = sublime.load_settings('kodidevkit.sublime-settings')
        report_dir = settings.get('validation_report_directory', None)

        if not report_dir:
            packages_path = sublime.packages_path()
            report_dir = os.path.join(packages_path, 'User', 'KodiDevKit', 'ValidationReports')

        os.makedirs(report_dir, exist_ok=True)

        safe_skin_name = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in skin_name)
        timestamp_file = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = f"{safe_skin_name}_{timestamp_file}.html"

        return os.path.join(report_dir, report_filename), report_dir, safe_skin_name

    @staticmethod
    def cleanup_old_reports(report_dir, safe_skin_name):
        """
        Remove old reports for the same skin.

        Args:
            report_dir: Directory containing reports
            safe_skin_name: Sanitized skin name for pattern matching
        """
        try:
            import glob
            old_reports = glob.glob(os.path.join(report_dir, f"{safe_skin_name}_*.html"))
            for old_report in old_reports:
                try:
                    os.remove(old_report)
                except OSError:
                    pass  # Ignore if file can't be deleted
        except Exception:
            pass  # Don't fail report generation if cleanup fails


class ShowValidationReportCommand(sublime_plugin.WindowCommand):
    """Command to run all validation checks and display report in browser."""

    def run(self):
        """Run all checks, generate HTML report, and open in browser."""
        from .libs.infoprovider import InfoProvider
        from .libs.reporting import html as report_generator
        from .libs.reporting import server as report_server
        from .libs.sublime.scratch import ReportProgressView

        settings = {}
        try:
            from .kodidevkit import INFOS, KodiDevKit
            provider = INFOS
            settings = getattr(KodiDevKit, 'settings', {})
        except Exception:
            provider = InfoProvider()

        # Always re-initialize for fresh state — stale include maps from
        # previously-broken files would cause false positives otherwise.
        try:
            variables = self.window.extract_variables()
            project_folder = variables.get("folder")
            if project_folder:
                provider.load_settings(settings or provider.settings)
                provider.init_addon(project_folder)
        except Exception:
            pass

        if not provider.addon:
            sublime.error_message(
                "No skin project detected.\n\n"
                "Please open a Kodi skin folder as a project."
            )
            return

        server_port = report_server.get_server_port()

        progress = ReportProgressView(self.window)
        progress.set_total_steps(8)

        def update_progress(step, message):
            """Update progress display."""
            progress.update_step(step, message)

        def clear_progress():
            """Close progress view."""
            progress.close()

        def run_checks():
            try:
                runner = ValidationRunner(provider, update_progress)
                all_issues = runner.run_all()

                total_issues = sum(len(issues) for issues in all_issues.values())
                update_progress(8, f"Generating report... ({total_issues} issues found)")

                if provider.addon and provider.addon.path:
                    skin_name = provider.addon.name if provider.addon.name else os.path.basename(provider.addon.path)
                else:
                    skin_name = "Unknown"

                from datetime import datetime
                import time
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                report_path, report_dir, safe_skin_name = ReportGenerator.get_report_path(skin_name)
                ReportGenerator.cleanup_old_reports(report_dir, safe_skin_name)

                addon_path = provider.addon.path if provider.addon else ""
                report_server.set_report_data(all_issues, skin_name, addon_path, timestamp)

                last_update = {'time': time.time(), 'stop_heartbeat': False}

                def heartbeat_monitor():
                    """Monitor for stuck report generation and show warnings."""
                    while not last_update['stop_heartbeat']:
                        time.sleep(5)
                        if last_update['stop_heartbeat']:
                            break

                        elapsed = time.time() - last_update['time']

                        if elapsed > 30:
                            update_progress(8,
                                f"⚠ Report generation taking longer than expected ({int(elapsed)}s)... "
                                f"If stuck, close this view and check console for errors.")
                        elif elapsed > 10:
                            update_progress(8,
                                f"Still working on report generation... ({int(elapsed)}s elapsed)")

                import threading
                heartbeat_thread = threading.Thread(target=heartbeat_monitor, daemon=True)
                heartbeat_thread.start()

                def report_progress(message):
                    """Called by report generator with status updates."""
                    last_update['time'] = time.time()
                    update_progress(8, f"Report: {message}")

                try:
                    report_path = report_generator.generate_html_report(
                        all_issues=all_issues,
                        skin_name=skin_name,
                        skin_path=addon_path,
                        output_path=report_path,
                        server_port=server_port,
                        progress_callback=report_progress
                    )
                finally:
                    last_update['stop_heartbeat'] = True

                def open_browser():
                    import pathlib
                    file_url = pathlib.Path(report_path).as_uri()
                    webbrowser.open(file_url)
                    clear_progress()

                sublime.set_timeout(open_browser, 0)

            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                error_message = str(e)

                logging.error(f"Validation error: {error_message}\n{error_details}")

                def show_error():
                    clear_progress()
                    sublime.error_message(
                        f"Validation failed with error:\n\n{error_message}\n\n"
                        f"Check the Sublime Text console for details."
                    )

                sublime.set_timeout(show_error, 0)

        import threading
        thread = threading.Thread(target=run_checks)
        thread.daemon = True
        thread.start()


class OpenValidationReportCommand(sublime_plugin.WindowCommand):
    """Command to open an existing validation report from the report directory."""

    def _open_folder_and_notify(self, folder_path, created=False):
        """Open the folder in file manager and show a notification."""
        import subprocess
        import sys

        try:
            if sublime.platform() == 'windows':
                subprocess.Popen(['explorer', folder_path])
            elif sublime.platform() == 'osx':
                subprocess.Popen(['open', folder_path])
            else:
                subprocess.Popen(['xdg-open', folder_path])

            if created:
                sublime.message_dialog(
                    "Validation reports folder created and opened.\n\n"
                    f"Location: {folder_path}\n\n"
                    "No reports exist yet. Generate your first report using:\n"
                    "KodiDevKit: Generate Validation Report"
                )
            else:
                sublime.message_dialog(
                    "Validation reports folder opened.\n\n"
                    f"Location: {folder_path}\n\n"
                    "The folder is currently empty. Generate a report using:\n"
                    "KodiDevKit: Generate Validation Report"
                )

        except Exception as e:
            sublime.error_message(
                f"Could not open folder:\n{folder_path}\n\n"
                f"Error: {e}\n\n"
                "You can navigate to this location manually."
            )

    def run(self):
        """Show list of existing reports and open the selected one."""
        import glob
        from datetime import datetime
        import pathlib

        settings = sublime.load_settings('kodidevkit.sublime-settings')
        report_dir = settings.get('validation_report_directory', None)

        if not report_dir:
            packages_path = sublime.packages_path()
            report_dir = os.path.join(packages_path, 'User', 'KodiDevKit', 'ValidationReports')

        if not os.path.exists(report_dir):
            os.makedirs(report_dir, exist_ok=True)
            self._open_folder_and_notify(report_dir, created=True)
            return

        pattern = os.path.join(report_dir, "*.html")
        report_files = glob.glob(pattern)

        if not report_files:
            self._open_folder_and_notify(report_dir, created=False)
            return

        reports = []
        for report_path in report_files:
            filename = os.path.basename(report_path)

            try:
                name_parts = filename.rsplit('_', 2)
                if len(name_parts) >= 2:
                    skin_name = name_parts[0].replace('_', ' ')
                    timestamp_str = name_parts[1].replace('.html', '')

                    try:
                        timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                        date_display = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        mtime = os.path.getmtime(report_path)
                        timestamp = datetime.fromtimestamp(mtime)
                        date_display = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    # Fallback for non-standard filenames
                    skin_name = filename.replace('.html', '')
                    mtime = os.path.getmtime(report_path)
                    timestamp = datetime.fromtimestamp(mtime)
                    date_display = timestamp.strftime("%Y-%m-%d %H:%M:%S")

                reports.append({
                    'path': report_path,
                    'skin_name': skin_name,
                    'date': date_display,
                    'timestamp': timestamp
                })
            except Exception:
                # If parsing fails, use basic info
                mtime = os.path.getmtime(report_path)
                timestamp = datetime.fromtimestamp(mtime)
                reports.append({
                    'path': report_path,
                    'skin_name': filename.replace('.html', ''),
                    'date': timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    'timestamp': timestamp
                })

        reports.sort(key=lambda x: x['timestamp'], reverse=True)

        items = []
        for report in reports:
            items.append([
                f"{report['skin_name']}",
                f"Generated: {report['date']}"
            ])

        def on_select(index):
            if index == -1:
                return

            report_path = reports[index]['path']
            file_url = pathlib.Path(report_path).as_uri()
            webbrowser.open(file_url)
            self.window.status_message(f"✓ Opened report: {reports[index]['skin_name']}")

        self.window.show_quick_panel(
            items,
            on_select,
            placeholder="Select a validation report to open"
        )


logger = logging.getLogger("KodiDevKit.commands")


class KodidevkitLanguageProbeCommand(sublime_plugin.ApplicationCommand):
    """Logs where language files are expected and what is actually found."""
    def run(self) -> None:
        log = logging.getLogger("KodiDevKit.commands")
        log.setLevel(logging.INFO)

        try:
            s = sublime.load_settings('kodidevkit.sublime-settings')
            kodi_path = (s.get("kodi_path") or "").strip()
            lang_pref = (s.get("language") or "").strip()
            lang_folders = s.get("language_folders") or ["resource.language.en_gb", "English"]

            log.info("[probe] kodi_path=%r", kodi_path)
            log.info("[probe] language=%r language_folders=%r", lang_pref, lang_folders)

            core_addons = os.path.join(kodi_path, "addons") if kodi_path else ""
            log.info("[probe] core_addons=%r exists=%s", core_addons, os.path.isdir(core_addons))

            found_lang_dirs = []
            if os.path.isdir(core_addons):
                for d in os.listdir(core_addons):
                    if d.lower().startswith("resource.language."):
                        found_lang_dirs.append(d)
            log.info("[probe] core language dirs found: %d", len(found_lang_dirs))
            if found_lang_dirs:
                log.info("[probe] sample core lang dirs: %s", ", ".join(found_lang_dirs[:5]))

            def po_candidates(base, lang_dir):
                return glob.glob(
                    os.path.join(base, lang_dir, "resources", "**", "strings.po"),
                    recursive=True,
                )

            core_candidates = []
            for lf in list(dict.fromkeys(lang_folders + ["resource.language.en_gb"])):
                core_candidates.extend(po_candidates(core_addons, lf))
            log.info("[probe] core strings.po candidates: %d", len(core_candidates))
            if core_candidates:
                log.info("[probe] sample core .po: %s", core_candidates[0])

            from .libs.addon import Addon
            try:
                win = sublime.active_window()
                view = win.active_view() if win else None
                fname = view.file_name() if view else None
                active_dir = os.path.dirname(fname) if fname else None
            except Exception:
                active_dir = None

            addon_root = None
            start = active_dir
            for _ in range(8):
                if start and os.path.isfile(os.path.join(start, "addon.xml")):
                    addon_root = start
                    break
                if not start:
                    break
                parent = os.path.dirname(start)
                if parent == start:
                    break
                start = parent

            log.info("[probe] addon_root=%r", addon_root)

            a = None
            if addon_root:
                a = Addon(path=addon_root, settings=s)
                log.info("[probe] primary_lang_folder=%r", getattr(a, "primary_lang_folder", None))
                log.info("[probe] secondary_lang_folders=%r", getattr(a, "secondary_lang_folders", None))

                skin_candidates = []
                if getattr(a, "primary_lang_folder", None):
                    skin_candidates = glob.glob(os.path.join(a.primary_lang_folder, "**", "*.po"), recursive=True)
                log.info("[probe] skin .po candidates: %d", len(skin_candidates))
                if skin_candidates:
                    log.info("[probe] sample skin .po: %s", skin_candidates[0])
                log.info("[probe] po_files loaded by Addon: %d", len(getattr(a, "po_files", [])))

            if core_candidates:
                po = utils.get_po_file(core_candidates[0])
                log.info("[probe] parse core candidate ok=%s", bool(po))
            else:
                log.info("[probe] no core .po candidates to parse")

        except Exception as exc:
            log.info("[probe] unexpected-error: %s", exc)
