"""Sublime-side log handlers and the results display panel."""

import sublime
import logging


class SublimeLogHandler(logging.StreamHandler):
    """Logging handler that routes records to console / output panel / dialogs."""

    def __init__(self):
        super().__init__()
        formatter = logging.Formatter('[KodiDevKit] %(asctime)s: %(message)s',
                                      datefmt='%Y-%m-%d %H:%M:%S')
        self.setFormatter(formatter)

    def emit(self, record):
        levels = {
            logging.CRITICAL: self.message,
            logging.ERROR: self.info,
            logging.WARNING: self.info,
            logging.INFO: self.debug,
            logging.DEBUG: self.debug,
            logging.NOTSET: self.debug,
        }
        log = levels[record.levelno]
        log(record)

    def flush(self):
        pass

    def debug(self, record):
        print(self.format(record))

    def info(self, record):
        wnd = sublime.active_window()
        wnd.run_command("kodidevkit_log", {"label": self.format(record).strip()})

    @staticmethod
    def message(record):
        """Show `record.msg` in a Sublime message dialog."""
        sublime.message_dialog(record.msg)


class ResultsDisplayPanel:
    """Output panel / scratch view for displaying JSON-RPC results and similar dicts."""

    def __init__(self, panel_name="kodidevkit"):
        """`panel_name` is the output-panel name without the `output.` prefix."""
        self.panel_name = panel_name
        self._window = None
        self._panel = None

    @property
    def window(self):
        """Cached active window."""
        if self._window is None or not self._window.is_valid():
            self._window = sublime.active_window()
        return self._window

    @property
    def panel(self):
        """Lazily-created output panel for this instance."""
        if self._panel is None:
            self._panel = self.window.create_output_panel(self.panel_name)
        return self._panel

    def clear(self):
        """Empty the output panel."""
        self.panel.run_command('select_all')
        self.panel.run_command('left_delete')

    def show_panel(self):
        """Reveal the output panel."""
        self.window.run_command('show_panel', {"panel": f"output.{self.panel_name}"})

    def append_msg(self, msg):
        """Append `msg` and reveal the panel."""
        self.panel.run_command("append", {"characters": f'{msg}\n'})
        self.show_panel()

    def info(self, msg):
        """Append `msg` to the panel and log at INFO."""
        self.append_msg(msg)
        logging.info(msg)

    def warning(self, msg):
        """Append `msg` to the panel and log at WARNING."""
        self.append_msg(msg)
        logging.warning(msg)

    def _format_dict_items(self, data, key_order=None, indent=""):
        """Render `data` as a list of lines, respecting `key_order` if given."""
        lines = []

        if key_order:
            for key in key_order:
                if key in data:
                    lines.append(f"{indent}{key}")
                    lines.append(f"{indent}→ {data[key]}")
                    lines.append("")
        else:
            for key, value in data.items():
                lines.append(f"{indent}{key}")
                lines.append(f"{indent}→ {value}")
                lines.append("")

        return lines

    def display_dict(self, data, clear_first=True, key_order=None):
        """Display `data` in the output panel as plain key/value lines."""
        if clear_first:
            self.clear()

        lines = self._format_dict_items(data, key_order)
        output = "\n".join(lines)
        self.panel.run_command("append", {"characters": output})

        self.panel.set_viewport_position((0, 0), animate=False)  # type: ignore[attr-defined]
        self.show_panel()

    def display_dict_as_scratch_view(self, data, title, window=None, key_order=None):
        """Display `data` in a new scratch view with a header box; returns the view."""
        if window is None:
            window = sublime.active_window()

        view = window.new_file()
        view.set_scratch(True)  # type: ignore[attr-defined]
        view.set_name(f"📊 {title}")  # type: ignore[attr-defined]
        view.set_read_only(False)  # type: ignore[attr-defined]

        lines = []
        lines.append("╔" + "═" * 78 + "╗")
        lines.append("║" + " " * 78 + "║")
        lines.append("║  " + title.ljust(76) + "║")
        lines.append("║" + " " * 78 + "║")
        lines.append("╚" + "═" * 78 + "╝")
        lines.append("")

        lines.extend(self._format_dict_items(data, key_order, indent="  "))

        lines.append("╚" + "═" * 78 + "╝")

        output = "\n".join(lines)

        view.run_command('append', {'characters': output})
        view.set_read_only(True)  # type: ignore[attr-defined]

        return view

    def display_results(self, data, title, mode, window=None, key_order=None):
        """Show `data` in either a scratch view or the output panel.

        `mode` is either "scratch_view" or anything else (treated as panel).
        """
        if mode == "scratch_view":
            self.display_dict_as_scratch_view(
                data=data,
                title=title,
                window=window,
                key_order=key_order
            )
        else:
            self.display_dict(data=data, clear_first=True, key_order=key_order)

    def display_error(self, error_message, mode, window=None):
        """Show `error_message` in either a scratch view or the output panel."""
        if mode == "scratch_view":
            if window is None:
                window = sublime.active_window()

            view = window.new_file()
            view.set_scratch(True)  # type: ignore[attr-defined]
            view.set_name("⚠ Kodi Connection Error")  # type: ignore[attr-defined]
            view.run_command('append', {'characters': error_message})
            view.set_read_only(True)  # type: ignore[attr-defined]
        else:
            self.clear()
            for line in error_message.split('\n'):
                if line:
                    self.append_msg(line)


def config():
    """Replace the root logger's handlers with our SublimeLogHandler."""
    logger = logging.getLogger()
    for hdlr in logger.handlers:
        logger.removeHandler(hdlr)
    logger.addHandler(SublimeLogHandler())
    logger.setLevel(logging.INFO)


def enable_file_logging(log_file_path=None):
    """Attach a rotating file handler at DEBUG level and return the log path.

    Defaults to `<cache>/KodiDevKit/logs/kodidevkit_debug.log`. Rotates at 5 MB
    per file, keeping 5 backups (~30 MB total).
    """
    import os
    from logging.handlers import RotatingFileHandler

    if log_file_path is None:
        cache_path = sublime.cache_path()  # type: ignore[attr-defined]
        log_dir = os.path.join(cache_path, "KodiDevKit", "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file_path = os.path.join(log_dir, "kodidevkit_debug.log")

    file_handler = RotatingFileHandler(
        log_file_path,
        mode='a',
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )

    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)-8s [%(name)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    logger = logging.getLogger()
    logger.addHandler(file_handler)
    logger.setLevel(logging.DEBUG)

    logger.info("=" * 80)
    logger.info("KodiDevKit file logging enabled")
    logger.info(f"Log file: {log_file_path}")
    logger.info("Rotation: 5MB per file, 5 backups (30MB total)")
    logger.info("=" * 80)

    return log_file_path
