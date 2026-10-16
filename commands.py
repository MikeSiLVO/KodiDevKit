"""General commands: Kodi logs and queries, control help, XML editing helpers and the report."""

import re
import glob
import webbrowser
import os
import logging
from lxml import etree as ET

import sublime
import sublime_plugin

from .libs.utils.files import check_paths, get_sublime_path
from .libs.addon.translations import get_po_file
from .libs.utils.decorators import run_async
from .libs.utils.expressions import split_top_level_commas
from .libs.kodi.jsonrpc import kodi

import subprocess

APP_NAME = "Kodi"
SETTINGS_FILE = 'kodidevkit.sublime-settings'
SUBLIME_PATH = get_sublime_path()

FILE_ERROR_PATTERN = re.compile(r'File "(.*?)", line (\d*), in .*')
TUPLE_ERROR_PATTERN = re.compile(r"', \('(.*?)', (\d+), (\d+), ")


class KodidevkitOpenKodiLogCommand(sublime_plugin.WindowCommand):
    """Command opening kodi.log from Kodi's usual log locations."""

    def run(self):
        """Open the first kodi.log found, or say which places were checked."""
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

        self.log = check_paths(paths)
        if self.log:
            self.window.open_file(self.log)
        else:
            sublime.error_message(
                f"Could not find Kodi log file: {filename}\n\n"
                f"Checked locations:\n" + "\n".join(f"  • {p}" for p in paths)
            )


class KodidevkitOpenAltKodiLogCommand(sublime_plugin.WindowCommand):
    """Command opening kodi.log from %APPDATA%\\Kodi, for Windows portable mode."""

    def is_visible(self):
        """True on Windows with portable mode set."""
        settings = sublime.load_settings(SETTINGS_FILE)
        return sublime.platform() == "windows" and settings.get("portable_mode")

    def run(self):
        """Open kodi.log from %APPDATA%\\Kodi, or say it is not there."""
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


class KodidevkitOpenSourceFromLogCommand(sublime_plugin.TextCommand):
    """Command jumping from a Python traceback line in the log to its source file and line."""

    def run(self, edit):
        """Open the file and line named on the traceback line holding the caret or selection."""
        for region in self.view.sel():
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


class KodidevkitGoToOnlineHelpCommand(sublime_plugin.TextCommand):
    """Command opening the Kodi doxygen page for the control under the cursor."""

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
        """True on a <control> line of a Kodi XML file."""
        region = self.view.sel()[0]
        line_contents = self.view.substr(self.view.line(region))
        scope_name = self.view.scope_name(region.b)
        return "text.xml.kodi" in scope_name and "<control " in line_contents

    def run(self, edit):
        """Open the help page for the type of the control on the caret's line."""
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
        """Go to the control type's doxygen page in the browser."""
        webbrowser.open_new(self.CONTROLS[word])


class KodidevkitCreateElementRowCommand(sublime_plugin.WindowCommand):
    """Command asking for a count, then repeating the selection that many times."""

    def run(self):
        """Ask for how many copies to make."""
        self.window.show_input_panel("Enter number of items to generate",
                                     "1",
                                     on_done=self.generate_items,
                                     on_change=None,
                                     on_cancel=None)

    def generate_items(self, num_items):
        """Generate the copies through the replace command."""
        self.window.run_command("kodidevkit_replace_xml_elements", {"num_items": num_items})


class KodidevkitReplaceXmlElementsCommand(sublime_plugin.TextCommand):
    """Command repeating the selection, numbering any [n] placeholder upward from n."""

    def run(self, edit, num_items):
        """Replace the first selection with the copies; a non-numeric count does nothing."""
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


class KodidevkitEvaluateMathExpressionPromptCommand(sublime_plugin.WindowCommand):
    """Command asking for an equation, x standing for each selected number."""

    def run(self):
        """Ask for the equation, starting from x."""
        self.window.show_input_panel("Write Equation (x = selected int)",
                                     "x",
                                     self.evaluate,
                                     None,
                                     None)

    def evaluate(self, equation):
        """Evaluate the equation over every selection through the math command."""
        self.window.run_command("kodidevkit_evaluate_math_expression", {'equation': equation})


class KodidevkitEvaluateMathExpressionCommand(sublime_plugin.TextCommand):
    """Command replacing each selection with an equation's result, x its number and i its index."""

    def run(self, edit, equation):
        """Replace each selection with the result, every ".0" removed from it."""
        for i, region in enumerate(self.view.sel()):
            text = self.view.substr(region)
            temp_equation = equation.replace("i", str(i))
            if text.replace('-', '').isdigit():
                temp_equation = temp_equation.replace("x", text)
            self.view.replace(edit, region, str(eval(temp_equation)).replace(".0", ""))


class KodidevkitColorPickerCommand(sublime_plugin.WindowCommand):
    """Command inserting a color from ColorPicker in Kodi's AARRGGBB format."""

    def is_visible(self):
        """True when the ColorPicker package answers its availability check."""
        settings = sublime.load_settings('KodiColorPicker.sublime-settings')
        settings.set('color_pick_return', None)
        self.window.run_command('color_pick_api_is_available',
                                {'settings': 'KodiColorPicker.sublime-settings'})
        return bool(settings.get('color_pick_return', False))

    def run(self):
        """Pick a color and insert it as FF plus its RGB hex."""
        settings = sublime.load_settings('KodiColorPicker.sublime-settings')
        settings.set('color_pick_return', None)
        self.window.run_command('color_pick_api_get_color',
                                {'settings': 'KodiColorPicker.sublime-settings',
                                 'default_color': '#ff0000'})
        color = settings.get('color_pick_return')
        view = self.window.active_view()
        if color and view:
            view.run_command("insert", {"characters": "FF" + color[1:]})


class KodidevkitSetKodiFolderCommand(sublime_plugin.WindowCommand):
    """Command asking for the Kodi installation folder and saving it to the settings."""

    def run(self):
        """Ask for the Kodi folder, starting from the platform's usual location."""
        plat = sublime.platform()
        if plat == "linux":
            preset_path = "/usr/share/%s/" % APP_NAME.lower()
        elif plat == "windows":
            preset_path = "C:/%s/" % APP_NAME.lower()
        elif plat == "osx":
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
        """Set and save the folder as kodi_path when it exists, else log an error."""
        if os.path.exists(path):
            sublime.load_settings(SETTINGS_FILE).set("kodi_path", path)
            sublime.save_settings(SETTINGS_FILE)
        else:
            logger.critical("Folder %s does not exist.", path)


class KodidevkitExecuteBuiltinPromptCommand(sublime_plugin.WindowCommand):
    """Command asking for a Kodi builtin and running it through the builtin command."""

    def run(self):
        """Ask for the builtin, starting from the last one."""
        self.settings = sublime.load_settings(SETTINGS_FILE)
        self.window.show_input_panel("Execute builtin",
                                     self.settings.get("prev_json_builtin", ""),
                                     self.execute_builtin,
                                     None,
                                     None)

    def execute_builtin(self, builtin):
        """Execute the builtin through the builtin command and remember it."""
        self.settings.set("prev_json_builtin", builtin)
        self.window.run_command("kodidevkit_execute_builtin", {"builtin": builtin})


class KodidevkitExecuteBuiltinCommand(sublime_plugin.WindowCommand):
    """Command running a Kodi builtin through the script.toolbox JSON-RPC bridge."""

    def run(self, builtin):
        """Execute the builtin in Kodi through script.toolbox."""
        params = {"addonid": "script.toolbox",
                  "params": {"info": "builtin",
                             "id": builtin}}
        kodi.request_async(method="Addons.ExecuteAddon",
                           params=params)


class _KodiQueryPromptMixin:
    """Mixin querying Kodi with comma-separated values and showing the answers."""
    _prompt = ""
    _settings_key = ""
    _method = ""
    _param_key = ""
    _panel_name = ""
    _title = ""
    _error_subject = ""
    window: sublime.Window
    settings: sublime.Settings

    def run(self):
        """Ask for the values, starting from the last ones."""
        self.settings = sublime.load_settings(SETTINGS_FILE)
        self.window.show_input_panel(self._prompt,
                                     self.settings.get(self._settings_key, ""),
                                     self._on_input,
                                     None,
                                     None)

    @run_async
    def _on_input(self, input_string):
        """Query Kodi for the values, remember them, and show the answers or what to check."""
        from .libs.sublime.logging import ResultsDisplayPanel

        self.settings.set(self._settings_key, input_string)
        words = split_top_level_commas(input_string)

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


class KodidevkitGetInfoLabelsPromptCommand(_KodiQueryPromptMixin, sublime_plugin.WindowCommand):
    """Command asking Kodi for the values of comma-separated infolabels."""
    _prompt = "Get InfoLabels (comma-separated)"
    _settings_key = "prev_infolabel"
    _method = "XBMC.GetInfoLabels"
    _param_key = "labels"
    _panel_name = "kodi_infolabels"
    _title = "KODI INFOLABELS"
    _error_subject = "InfoLabels"


class KodidevkitBrowseKodiVfsCommand(sublime_plugin.WindowCommand):
    """Command browsing the Kodi VFS over JSON-RPC."""

    def run(self):
        """Offer the video and music libraries to browse."""
        self.nodes = [["video", "library://video"],
                      ["music", "library://music"]]
        self.window.show_quick_panel(items=self.nodes,
                                     on_select=self.on_done,
                                     selected_index=0)

    @run_async
    def on_done(self, index):
        """List the picked folder's contents to browse further."""
        if index == -1:
            return None
        node = self.nodes[index]
        data = kodi.request(method="Files.GetDirectory",
                            params={"directory": node[1], "media": "files"})
        self.nodes = [[item["label"], item["file"]] for item in data["result"]["files"]]
        self.window.show_quick_panel(items=self.nodes,
                                     on_select=self.on_done,
                                     selected_index=0)


class KodidevkitGetInfoBooleansPromptCommand(_KodiQueryPromptMixin, sublime_plugin.WindowCommand):
    """Command asking Kodi for the values of comma-separated boolean conditions."""
    _prompt = "Get boolean values (comma-separated)"
    _settings_key = "prev_boolean"
    _method = "XBMC.GetInfoBooleans"
    _param_key = "booleans"
    _panel_name = "kodi_booleans"
    _title = "KODI BOOLEAN CONDITIONS"
    _error_subject = "Boolean conditions"


class KodidevkitOpenKodiAddonCommand(sublime_plugin.WindowCommand):
    """Command opening one of Kodi's add-on folders in a new Sublime Text window."""

    def run(self):
        """List the add-ons in Kodi's userdata folder."""
        self.nodes = kodi.get_userdata_addons()
        self.window.show_quick_panel(items=self.nodes,
                                     on_select=self.on_done,
                                     selected_index=0)

    def on_done(self, index):
        """Open the picked add-on's folder in a new Sublime window."""
        if index == -1:
            return None
        if not kodi.userdata_folder:
            logging.error("Cannot open addon: userdata_folder not configured")
            return None
        path = os.path.join(kodi.userdata_folder, "addons", self.nodes[index])
        if SUBLIME_PATH:
            subprocess.Popen([SUBLIME_PATH, "-n", "-a", path])


class ValidationRunner:
    """Runner for every validation check, calling back with a step and message as it goes."""

    def __init__(self, provider, update_progress):
        self.provider = provider
        self.update_progress = update_progress
        self.all_issues = {}

    def _run_check(self, step, name, check_method):
        """Run one check, reporting progress under its step and name."""
        def progress_callback(message):
            self.update_progress(step, f"{name}: {message}")

        self.update_progress(step, f"Checking {name.lower()}...")
        self.all_issues[name] = check_method(progress_callback=progress_callback)

    def run_all(self):
        """Run every check in order and return {check_name: [issues]}."""
        self.update_progress(0, "Starting validation checks...")

        self._run_check(1, "Variables", self.provider.check_variables)
        self._run_check(2, "Includes", self.provider.check_includes)
        self._run_check(3, "Maps", self.provider.check_maps)
        self._run_check(4, "Labels", self.provider.check_labels)
        self._run_check(5, "Fonts", self.provider.check_fonts)
        self._run_check(6, "IDs", self.provider.check_ids)
        self._run_check(7, "Images", self.provider.check_images)
        self._run_check(8, "XML Validation", self.provider.check_values)
        self._run_check(9, "File Integrity", self.provider.check_file_integrity)
        self._run_check(10, "Kodi Repo", self.provider.check_repo)

        return self.all_issues


class ReportGenerator:
    """Paths for report files and cleanup of old ones."""

    @staticmethod
    def get_report_path(skin_name):
        """Get the timestamped report path, its folder, made if missing, and the safe skin name."""
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
        """Clean up the skin's earlier reports; the new one replaces them."""
        try:
            import glob
            old_reports = glob.glob(os.path.join(report_dir, f"{safe_skin_name}_*.html"))
            for old_report in old_reports:
                try:
                    os.remove(old_report)
                except OSError:
                    pass
        except Exception:
            pass


class KodidevkitShowValidationReportCommand(sublime_plugin.WindowCommand):
    """Command running every check and opening the HTML report in a browser."""

    def run(self):
        """Re-init the project, run every check off the main thread and open the report."""
        from .libs.infoprovider.provider import InfoProvider
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

        # re-init each run; entries a broken include once left would linger in the maps
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
        progress.set_total_steps(11)

        def update_progress(step, message):
            progress.update_step(step, message)

        def clear_progress():
            progress.close()

        def run_checks():
            try:
                runner = ValidationRunner(provider, update_progress)
                all_issues = runner.run_all()

                total_issues = sum(len(issues) for issues in all_issues.values())
                update_progress(11, f"Generating report... ({total_issues} issues found)")

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
                    """Warn the user if report generation seems stuck."""
                    while not last_update['stop_heartbeat']:
                        time.sleep(5)
                        if last_update['stop_heartbeat']:
                            break

                        elapsed = time.time() - last_update['time']

                        if elapsed > 30:
                            update_progress(11,
                                f"⚠ Report generation taking longer than expected ({int(elapsed)}s)... "
                                f"If stuck, close this view and check console for errors.")
                        elif elapsed > 10:
                            update_progress(11,
                                f"Still working on report generation... ({int(elapsed)}s elapsed)")

                import threading
                heartbeat_thread = threading.Thread(target=heartbeat_monitor, daemon=True)
                heartbeat_thread.start()

                def report_progress(message):
                    """Status callback the report generator calls during build."""
                    last_update['time'] = time.time()
                    update_progress(11, f"Report: {message}")

                try:
                    hide_inc = sublime.load_settings(SETTINGS_FILE).get("hide_include_warnings", True)
                    report_path = report_generator.generate_html_report(
                        all_issues=all_issues,
                        skin_name=skin_name,
                        skin_path=addon_path,
                        output_path=report_path,
                        server_port=server_port,
                        progress_callback=report_progress,
                        hide_include_warnings=hide_inc
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


def _report_entry(report_path):
    """Picker entry for a report: skin name and date from its file name, else its modified time."""
    from datetime import datetime

    stem = os.path.basename(report_path)[:-len(".html")]
    parts = stem.rsplit("_", 2)
    try:
        timestamp = datetime.strptime("_".join(parts[1:]), "%Y%m%d_%H%M%S")
        skin_name = parts[0].replace("_", " ")
    except ValueError:
        timestamp = datetime.fromtimestamp(os.path.getmtime(report_path))
        skin_name = stem
    return {"path": report_path, "skin_name": skin_name,
            "date": timestamp.strftime("%Y-%m-%d %H:%M:%S"), "timestamp": timestamp}


class KodidevkitOpenValidationReportCommand(sublime_plugin.WindowCommand):
    """Command opening an existing validation report from the report folder."""

    def _open_folder_and_notify(self, folder_path, created=False):
        """Open the folder in the system file manager and say it was just created or is empty."""
        import subprocess

        try:
            plat = sublime.platform()
            if plat == 'windows':
                subprocess.Popen(['explorer', folder_path])
            elif plat == 'osx':
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
        """Show saved reports in a quick panel and open the pick, else open the report folder."""
        import glob
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

        reports = [_report_entry(report_path) for report_path in report_files]
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
    """Command logging where language files are expected and which ones are found."""
    def run(self) -> None:
        """Log Kodi's language folders and strings.po files, then the add-on's."""
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

            from .libs.addon.addon import Addon
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
                po = get_po_file(core_candidates[0])
                log.info("[probe] parse core candidate ok=%s", bool(po))
            else:
                log.info("[probe] no core .po candidates to parse")

        except Exception as exc:
            log.info("[probe] unexpected-error: %s", exc)
