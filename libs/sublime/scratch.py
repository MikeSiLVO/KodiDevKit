"""Progress scratch views for long-running validation and reporting tasks."""

import re
import sublime
import time


class ProgressScratchView:
    """Scratch view showing a long task's progress, safe to update from any thread."""

    def __init__(self, window, title, icon="📊"):
        self.window = window
        self.title = title
        self.icon = icon
        self._view = None
        self._spinner_cycle = 0
        self._animation_timer = None
        self._create_view()

    def _create_view(self):
        """Create the scratch view, retrying on the main thread when it fails."""
        def create():
            self._view = self.window.new_file()
            self._view.set_scratch(True)
            self._view.set_name(f"{self.icon} {self.title}")
            self._view.set_read_only(False)

        try:
            create()
        except Exception:
            sublime.set_timeout(create, 0)

    def update(self, message):
        """Append a progress line to the view (thread-safe)."""
        def append_message():
            if self._view and self._view.is_valid():
                self._view.set_read_only(False)
                self._view.run_command('append', {'characters': message + "\n"})
                self._view.set_read_only(True)
                self._view.show(self._view.size())

        sublime.set_timeout(append_message, 0)

    def replace_content(self, content):
        """Replace the entire view contents (for in-place redraws)."""
        def replace():
            if self._view and self._view.is_valid():
                self._view.set_read_only(False)
                self._view.run_command('select_all')
                self._view.run_command('left_delete')
                self._view.run_command('append', {'characters': content})
                self._view.set_read_only(True)

        sublime.set_timeout(replace, 0)

    def close(self):
        """Close the progress view (thread-safe)."""
        def close_view():
            if self._view and self._view.is_valid():
                self._view.close()

        sublime.set_timeout(close_view, 0)

    def close_sync(self):
        """Close the view now, from the main thread, before a panel or dialog opens over it."""
        if self._view and self._view.is_valid():
            self._view.close()

    def to_results_view(self, name, content, file_regex, line_regex="", base_dir=""):
        """Turn this tab into a read-only results view whose lines open like build output."""
        if not (self._view and self._view.is_valid()):
            return
        view = self._view
        view.set_name(name)
        view.assign_syntax("Packages/KodiDevKit/KodiValidationResults.sublime-syntax")
        settings = view.settings()
        settings.set("result_file_regex", file_regex)
        if line_regex:
            settings.set("result_line_regex", line_regex)
        if base_dir:
            settings.set("result_base_dir", base_dir)
        settings.set("line_numbers", False)
        settings.set("highlight_line", False)
        settings.set("draw_indent_guides", False)
        settings.set("draw_white_space", "none")
        settings.set("rulers", [])
        settings.set("kodidevkit_results", True)
        view.set_read_only(False)
        view.run_command("select_all")
        view.run_command("left_delete")
        view.run_command("append", {"characters": content})
        view.set_read_only(True)
        view.sel().clear()
        view.show(0)

    _SPINNER_FRAMES = ['|', '/', '-', '\\']

    def _spinner_char(self):
        """The spinner frame for the current cycle."""
        return self._SPINNER_FRAMES[self._spinner_cycle % len(self._SPINNER_FRAMES)]

    def _start_animation(self):
        """Start the spinner, which redraws every 200 ms."""
        self._animation_timer = True
        sublime.set_timeout(self._animate_spinner, 200)

    def _animate_spinner(self):
        """Advance the spinner one frame; each progress view redraws itself."""
        raise NotImplementedError

    def is_valid(self):
        """True while the view is still open."""
        return self._view is not None and self._view.is_valid()


class ValidationProgressView(ProgressScratchView):
    """Validation-specific progress view with a spinner and progress bar."""

    def __init__(self, window, check_type):
        super().__init__(window, f"Validation Progress - {check_type}", icon="🔍")
        self.check_type = check_type
        self._created_at = time.time()
        self._min_display_ms = 500
        self._current_progress = None

    def show_file_progress(self, filename, current, total):
        """Render progress for file-by-file validation (e.g. 'File 12 of 50')."""
        self._current_progress = ('file', filename, current, total)

        if self._animation_timer is None:
            self._start_animation()

        self._update_display()

    def update(self, message):
        """Show `message` with the animated spinner."""
        self._current_progress = ('message', message)

        if self._animation_timer is None:
            self._start_animation()

        self._update_display()

    def _update_display(self):
        """Update the progress display with current state and spinner."""
        if not self._current_progress:
            return

        progress_type = self._current_progress[0]

        if progress_type == 'file' and len(self._current_progress) == 4:
            _, filename, current, total = self._current_progress

            progress_pct = int((current / total) * 100) if total > 0 else 0
            bar_width = 50
            filled = int(bar_width * current / total) if total > 0 else 0
            bar = '█' * filled + '░' * (bar_width - filled)

            spinner_char = self._spinner_char()
            spinner_display = f"  {spinner_char}"

            content = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║  🔍  VALIDATION IN PROGRESS                                                  ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

  Progress: [{bar}] {progress_pct}%{spinner_display}

  File {current} of {total}: {filename}


"""
        elif progress_type == 'message' and len(self._current_progress) == 2:
            _, message = self._current_progress

            spinner_char = self._spinner_char()
            spinner_display = f"  {spinner_char}"

            content = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║  🔍  VALIDATION IN PROGRESS                                                  ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

  {spinner_display}  {message}


"""
        else:
            return

        self.replace_content(content)


    def _animate_spinner(self):
        """Animate spinner to show active processing."""
        if not self.is_valid() or not self._current_progress:
            self._animation_timer = None
            return

        self._spinner_cycle += 1

        self._update_display()

        sublime.set_timeout(self._animate_spinner, 200)

    def remaining_min_display_ms(self):
        """Stop the spinner; the ms left before the tab has shown for its minimum time."""
        self._animation_timer = None
        self._current_progress = None
        elapsed_ms = (time.time() - self._created_at) * 1000
        return int(max(0, self._min_display_ms - elapsed_ms))


class ReportProgressView(ProgressScratchView):
    """Progress view for report generation: progress bar, step count, animated spinner."""

    def __init__(self, window):
        super().__init__(window, "Generating Validation Report", icon="⚙")
        self._current_step = 0
        self._total_steps = 0
        self._last_update_time = 0
        self._min_update_interval = 0.1
        self._pending_message = None
        self._base_message = ""

    def set_total_steps(self, total):
        """Set total number of steps for progress bar."""
        self._total_steps = total
        self._current_step = 0

    def update_step(self, step, message):
        """Update to the step and message, throttling how often it redraws."""
        self._current_step = step
        self._pending_message = (step, message)

        if message != self._base_message:
            self._base_message = message
            if self._animation_timer is None:
                self._start_animation()

        current_time = time.time()
        time_since_last = current_time - self._last_update_time

        if time_since_last >= self._min_update_interval:
            self._do_update(step, message)
            self._last_update_time = current_time
        else:
            delay_ms = int((self._min_update_interval - time_since_last) * 1000)
            sublime.set_timeout(self._flush_pending, delay_ms)

    def _flush_pending(self):
        """Flush any pending update (called after throttle delay)."""
        if self._pending_message:
            step, message = self._pending_message
            self._pending_message = None

            current_time = time.time()
            if current_time - self._last_update_time >= self._min_update_interval:
                self._do_update(step, message)
                self._last_update_time = current_time

    def _do_update(self, step, message):
        """Update the view with the progress bar and step line for the step and message."""
        progress_pct = int((step / self._total_steps) * 100) if self._total_steps > 0 else 0
        bar_width = 50
        filled = int(bar_width * step / self._total_steps) if self._total_steps > 0 else 0
        bar = '█' * filled + '░' * (bar_width - filled)

        spinner_char = self._spinner_char()
        spinner_display = f"  {spinner_char}"

        count_match = re.search(r'\((\d+)/(\d+)(?:\s+done)?\)(?:\.\.\.)?$', message)
        if count_match:
            base_msg = re.sub(r'\s*\(\d+/\d+(?:\s+done)?\)(?:\.\.\.)?$', '', message)
            count_str = f"File ({count_match.group(1)}/{count_match.group(2)})"

            step_label = f"  Step {step} of {self._total_steps}:"
            # width of "  Progress: [", the bar and "]"
            total_width = 13 + bar_width + 1
            line1 = f"{step_label}{count_str:>{total_width - len(step_label)}}"

            line2 = f"  {base_msg}"
            formatted_step = f"{line1}\n{line2}"
        else:
            formatted_step = f"  Step {step} of {self._total_steps}: {message}"

        content = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║  ⚙  GENERATING VALIDATION REPORT                                            ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

  Progress: [{bar}] {progress_pct}%{spinner_display}

{formatted_step}


"""

        self.replace_content(content)


    def _animate_spinner(self):
        """Animate spinner near percentage to show active processing."""
        if not self.is_valid():
            self._animation_timer = None
            return

        self._spinner_cycle += 1

        self._do_update(self._current_step, self._base_message)

        sublime.set_timeout(self._animate_spinner, 200)

    def close(self):
        """Close the progress view and stop animation timer."""
        self._animation_timer = None
        super().close()
