"""
Progress scratch view helper for long-running operations.

Provides a reusable scratch view that shows real-time progress updates
for validation, report generation, and other lengthy operations.
"""

import re
import sublime
import time


class ProgressScratchView:
    """
    Thread-safe progress scratch view for showing real-time operation progress.

    Usage:
        progress = ProgressScratchView(window, "Validation Progress", icon="🔍")

        progress.update("Initializing...")
        progress.update("[1/100] Checking file.xml...")

        progress.finalize("Complete: 23 issues found", close=True)
        progress.finalize("✅ No issues found", close=False)
    """

    def __init__(self, window, title, icon="📊"):
        """
        Create and display a progress scratch view.

        Args:
            window: Sublime window to create view in
            title: Title for the scratch view tab
            icon: Optional emoji icon for the tab name
        """
        self.window = window
        self.title = title
        self.icon = icon
        self._view = None
        self._create_view()

    def _create_view(self):
        """Create the scratch view (must run on main thread)."""
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
        """
        Add a progress message to the view (thread-safe).

        Args:
            message: Progress message to append
        """
        def append_message():
            if self._view and self._view.is_valid():
                self._view.set_read_only(False)
                self._view.run_command('append', {'characters': message + "\n"})
                self._view.set_read_only(True)
                self._view.show(self._view.size())

        sublime.set_timeout(append_message, 0)

    def replace_content(self, content):
        """
        Replace entire view content (for in-place updates).

        Args:
            content: New content to display
        """
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

    def finalize(self, message, close=False):
        """
        Show final message and optionally close the view.

        Args:
            message: Final status message
            close: If True, close the view after showing message
                   If False, keep view open with message
        """
        self.update(message)

        if close:
            # Brief delay before closing so user sees final message
            sublime.set_timeout(self.close, 500)
        else:
            self.update("\nYou can close this tab.")

    def is_valid(self):
        """Check if the view is still valid."""
        return self._view is not None and self._view.is_valid()


class ValidationProgressView(ProgressScratchView):
    """
    Specialized progress view for validation operations.

    Provides helpers for common validation progress patterns.
    """

    def __init__(self, window, check_type):
        """
        Create validation progress view.

        Args:
            window: Sublime window
            check_type: Type of validation (general, font, label, etc.)
        """
        super().__init__(window, f"Validation Progress - {check_type}", icon="🔍")
        self.check_type = check_type
        self._created_at = time.time()
        self._min_display_ms = 1500  # Minimum time to display before opening quick panel
        self._spinner_cycle = 0
        self._spinner_frames = ['|', '/', '-', '\\']
        self._animation_timer = None
        self._current_progress = None  # Store current progress state for animation

    def show_file_progress(self, filename, current, total):
        """
        Show progress for file-based validation (in-place update).

        Args:
            filename: Name of file being checked
            current: Current file number (1-indexed)
            total: Total number of files
        """
        self._current_progress = ('file', filename, current, total)

        if self._animation_timer is None:
            self._start_animation()

        self._update_display()

    def update(self, message):
        """
        Override update to support animated message-based progress.

        Args:
            message: Progress message to display
        """
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

            spinner_char = self._spinner_frames[self._spinner_cycle % len(self._spinner_frames)]
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

            spinner_char = self._spinner_frames[self._spinner_cycle % len(self._spinner_frames)]
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

    def _start_animation(self):
        """Start the animation timer for spinner."""
        self._animation_timer = True  # Mark as started
        sublime.set_timeout(self._animate_spinner, 200)

    def _animate_spinner(self):
        """Animate spinner to show active processing."""
        if not self.is_valid() or not self._current_progress:
            self._animation_timer = None
            return

        self._spinner_cycle += 1

        self._update_display()

        sublime.set_timeout(self._animate_spinner, 200)

    def show_completion(self, issue_count, close_on_issues=True):
        """
        Show fancy completion screen with Enter-to-close.

        Args:
            issue_count: Number of issues found
            close_on_issues: If True, auto-close after showing completion
                           If False, keep view open

        Returns:
            int: Delay in milliseconds before view will close (useful for timing quick panel)
        """
        self._animation_timer = None
        self._current_progress = None

        elapsed_ms = (time.time() - self._created_at) * 1000

        # Ensure minimum display time before closing (when issues found)
        if issue_count > 0 and close_on_issues:
            remaining_ms = max(0, self._min_display_ms - elapsed_ms)
            close_delay = int(remaining_ms + 300)  # Add 300ms after minimum time
        else:
            close_delay = 300

        if issue_count > 0:
            self._show_fancy_completion(
                status="✓ VALIDATION COMPLETE",
                result=f"{issue_count} issue{'s' if issue_count != 1 else ''} found",
                footer="Press ENTER to see results",
                icon="⚠",
                auto_close=close_on_issues,
                close_delay=close_delay
            )
        else:
            self._show_fancy_completion(
                status="VALIDATION COMPLETE",
                result="No issues found",
                footer="Press ENTER to close",
                icon="✅",
                auto_close=close_on_issues,
                close_delay=close_delay
            )

        return close_delay

    def _show_fancy_completion(self, status, result, footer, icon, auto_close=True, close_delay=300):
        """
        Display styled completion screen.

        Args:
            status: Status header text
            result: Result message
            footer: Footer text (instruction or status)
            icon: Emoji icon
            auto_close: If True, close view after delay
            close_delay: Milliseconds to wait before closing
        """
        content = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║  {icon}  {status:<70} ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

  {result}


  ──────────────────────────────────────────────────────────────────────────────

  {footer}
"""

        self.replace_content(content)

        def mark_completion():
            if self._view and self._view.is_valid():
                self._view.settings().set('kodidevkit_completion_view', True)
                window = self._view.window()
                if window:
                    window.focus_view(self._view)

        sublime.set_timeout(mark_completion, 0)

        if auto_close:
            sublime.set_timeout(self.close, close_delay)


class ReportProgressView(ProgressScratchView):
    """
    Specialized progress view for report generation with progress bar.

    Displays a visual progress bar and step-by-step status updates.
    Automatically animates dots when a step takes more than 2 seconds.
    """

    def __init__(self, window):
        """Create report generation progress view."""
        super().__init__(window, "Generating Validation Report", icon="⚙")
        self._current_step = 0
        self._total_steps = 0
        self._last_update_time = 0
        self._min_update_interval = 0.1  # Minimum 100ms between UI updates (prevent spam)
        self._pending_message = None
        self._base_message = ""  # Current message
        self._spinner_cycle = 0  # Cycles through spinner frames continuously
        self._spinner_frames = ['|', '/', '-', '\\']  # Classic spinner animation
        self._animation_timer = None  # Timer handle for animation

    def set_total_steps(self, total):
        """Set total number of steps for progress bar."""
        self._total_steps = total
        self._current_step = 0

    def update_step(self, step, message):
        """
        Update progress with step number and message (throttled to prevent UI spam).

        Args:
            step: Current step number (1-indexed)
            message: Description of current step
        """
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
        """Actually perform the UI update (internal method)."""
        progress_pct = int((step / self._total_steps) * 100) if self._total_steps > 0 else 0
        bar_width = 50
        filled = int(bar_width * step / self._total_steps) if self._total_steps > 0 else 0
        bar = '█' * filled + '░' * (bar_width - filled)

        spinner_char = self._spinner_frames[self._spinner_cycle % len(self._spinner_frames)]
        spinner_display = f"  {spinner_char}"

        count_match = re.search(r'\((\d+)/(\d+)(?:\s+done)?\)(?:\.\.\.)?$', message)
        if count_match:
            base_msg = re.sub(r'\s*\(\d+/\d+(?:\s+done)?\)(?:\.\.\.)?$', '', message)
            count_str = f"File ({count_match.group(1)}/{count_match.group(2)})"

            step_label = f"  Step {step} of {self._total_steps}:"
            total_width = 13 + bar_width + 1  # Width up to and including ']'
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

    def _start_animation(self):
        """Start the animation timer for active processing indication."""
        self._animation_timer = True  # Mark as started
        sublime.set_timeout(self._animate_spinner, 200)  # Start animating immediately

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
        self._animation_timer = None  # Stop animation
        super().close()
