"""Sublime-side logging: critical records as dialogs, the results panel, the debug log file."""

import sublime
import logging


class DialogHandler(logging.Handler):
    """Log handler showing each critical record in a Sublime message dialog."""

    def __init__(self):
        super().__init__(level=logging.CRITICAL)

    def emit(self, record):
        """Show the record's formatted message in a dialog, from the main thread."""
        message = record.getMessage()
        sublime.set_timeout(lambda: sublime.message_dialog(message), 0)


class ResultsDisplayPanel:
    """Output panel / scratch view for displaying JSON-RPC results and similar dicts."""

    def __init__(self, panel_name="kodidevkit"):
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
        """Append a line and reveal the panel."""
        self.panel.run_command("append", {"characters": f'{msg}\n'})
        self.show_panel()

    def _format_dict_items(self, data, key_order=None, indent=""):
        """Format the dict as key and arrow-value lines, in the given key order if any."""
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
        """Display the dict in the output panel as key and value lines."""
        if clear_first:
            self.clear()

        lines = self._format_dict_items(data, key_order)
        output = "\n".join(lines)
        self.panel.run_command("append", {"characters": output})

        self.panel.set_viewport_position((0, 0), animate=False)  # type: ignore[attr-defined]
        self.show_panel()

    def display_dict_as_scratch_view(self, data, title, window=None, key_order=None):
        """Display the dict in a new scratch view under a header box; returns the view."""
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
        """Display the results in a scratch view, or else the output panel."""
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
        """Display the error in a scratch view, or else the output panel."""
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


def enable_file_logging(log_file_path=None):
    """Enable a rotating DEBUG log file and set the root logger to DEBUG; returns the path."""
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
