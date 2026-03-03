"""
KodiDevKit is a plugin to assist with Kodi skinning / scripting
using Sublime Text 4
"""

import sublime
import logging


class SublimeLogHandler(logging.StreamHandler):
    """
    SublimeText Stream handler, outputs stream via console/panels/dialogs
    """

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
        wnd.run_command("log", {"label": self.format(record).strip()})

    @staticmethod
    def message(record):
        """
        shows text in message dialog
        """
        sublime.message_dialog(record.msg)


class ResultsDisplayPanel:
    """
    Helper class for displaying structured data (like JSON-RPC results) in Sublime Text.
    Supports both output panels and scratch views with formatted output.
    """

    def __init__(self, panel_name="kodidevkit"):
        """
        Initialize the panel with a given name.

        Args:
            panel_name: Name of the output panel (without 'output.' prefix)
        """
        self.panel_name = panel_name
        self._window = None
        self._panel = None

    @property
    def window(self):
        """Get the active window, cached."""
        if self._window is None or not self._window.is_valid():
            self._window = sublime.active_window()
        return self._window

    @property
    def panel(self):
        """Get or create the output panel."""
        if self._panel is None:
            self._panel = self.window.create_output_panel(self.panel_name)
        return self._panel

    def clear(self):
        """Clear all content from the panel."""
        self.panel.run_command('select_all')
        self.panel.run_command('left_delete')

    def show_panel(self):
        """Show the output panel."""
        self.window.run_command('show_panel', {"panel": f"output.{self.panel_name}"})

    def append_msg(self, msg):
        """
        Append a message to the panel and show it.

        Args:
            msg: Message to append
        """
        self.panel.run_command("append", {"characters": f'{msg}\n'})
        self.show_panel()

    def info(self, msg):
        """Append info message (also logs to console)."""
        self.append_msg(msg)
        logging.info(msg)

    def warning(self, msg):
        """Append warning message (also logs to console)."""
        self.append_msg(msg)
        logging.warning(msg)

    def _format_dict_items(self, data, key_order=None, indent=""):
        """
        Format dictionary items as lines, preserving key order if specified.

        Args:
            data: Dictionary to format
            key_order: Optional list of keys to control display order
            indent: String to prepend to each line

        Returns:
            List of formatted lines
        """
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
        """
        Display a dictionary in output panel with simple formatting (no headers/borders).

        Args:
            data: Dictionary to display
            clear_first: Whether to clear panel before displaying
            key_order: Optional list of keys to control display order
        """
        if clear_first:
            self.clear()

        lines = self._format_dict_items(data, key_order)
        output = "\n".join(lines)
        self.panel.run_command("append", {"characters": output})

        self.panel.set_viewport_position((0, 0), animate=False)  # type: ignore[attr-defined]
        self.show_panel()

    def display_dict_as_scratch_view(self, data, title, window=None, key_order=None):
        """
        Display a dictionary in a scratch view with fancy formatting (headers, borders).

        Args:
            data: Dictionary to display
            title: Title for the scratch view
            window: Window to create the view in (defaults to active window)
            key_order: Optional list of keys to control display order

        Returns:
            The created scratch view
        """
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
        """
        High-level method to display results in the specified mode.

        Args:
            data: Dictionary of results to display
            title: Title for the display
            mode: Display mode ("scratch_view" or "output_panel")
            window: Window to create view in (for scratch_view mode)
            key_order: Optional list of keys to control display order
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
        """
        Display an error message in the specified mode.

        Args:
            error_message: Error message to display
            mode: Display mode ("scratch_view" or "output_panel")
            window: Window to create view in (for scratch_view mode)
        """
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
                if line:  # Skip empty lines
                    self.append_msg(line)


def config():
    """
    attach Sublime StreamHandler to logger
    """
    logger = logging.getLogger()
    for hdlr in logger.handlers:  # remove all old handlers
        logger.removeHandler(hdlr)
    logger.addHandler(SublimeLogHandler())
    logger.setLevel(logging.INFO)


def enable_file_logging(log_file_path=None):
    """
    Enable logging to file for debugging freeze issues with rotation.

    Uses RotatingFileHandler to prevent log files from getting too large.
    Keeps up to 5 backup files (5MB each = 30MB total) for multi-day debugging.

    Args:
        log_file_path: Path to log file. If None, uses Sublime cache directory.

    Returns:
        Path to the log file
    """
    import os
    from logging.handlers import RotatingFileHandler

    if log_file_path is None:
        cache_path = sublime.cache_path()  # type: ignore[attr-defined]
        log_dir = os.path.join(cache_path, "KodiDevKit", "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file_path = os.path.join(log_dir, "kodidevkit_debug.log")

    # Create rotating file handler
    # maxBytes=5MB per file, backupCount=5 keeps last 5 rotations (30MB total)
    # This gives roughly 3-7 days of logs depending on verbosity
    file_handler = RotatingFileHandler(
        log_file_path,
        mode='a',
        maxBytes=5*1024*1024,  # 5 MB
        backupCount=5,         # Keep .log.1 through .log.5
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
