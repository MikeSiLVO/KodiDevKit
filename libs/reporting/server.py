"""
Local HTTP server for handling file:line navigation from HTML reports.
No system-level installation or protocol registration required.
"""

import sublime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading
import logging
import sys
from .text import generate_text_report

logger = logging.getLogger("KodiDevKit.report_server")

_server = None
_server_port = 48273  # Random high port
_report_data = {}  # Store report data for export


class FileOpenHandler(BaseHTTPRequestHandler):
    """HTTP request handler for opening files in Sublime Text."""

    def log_message(self, format, *args):
        """Override to use our logger instead of stderr."""
        logger.info(format % args)

    def do_GET(self):
        """Handle GET requests to open files."""
        parsed = urlparse(self.path)

        if parsed.path == '/open':
            params = parse_qs(parsed.query)
            file_path = params.get('file', [''])[0]
            line = params.get('line', ['1'])[0]

            if file_path:
                def open_file():
                    window = sublime.active_window()
                    if window:
                        view = window.open_file(f"{file_path}:{line}:0", sublime.ENCODED_POSITION)

                        def activate_window():
                            window.bring_to_front()  # type: ignore[attr-defined]

                            if sys.platform == 'win32':
                                # Windows: Modern Windows prevents focus stealing for security
                                # Instead, flash the taskbar to notify the user
                                try:
                                    import ctypes
                                    from ctypes import Structure
                                    from ctypes.wintypes import DWORD, HWND, UINT

                                    hwnd = window.hwnd()
                                    if hwnd:
                                        user32 = ctypes.windll.user32

                                        SW_RESTORE = 9
                                        user32.ShowWindow(hwnd, SW_RESTORE)
                                        user32.SetForegroundWindow(hwnd)

                                        if user32.GetForegroundWindow() != hwnd:
                                            # We don't have focus - flash the taskbar instead
                                            # This is the proper Windows UX for background notifications

                                            class FLASHWINFO(Structure):
                                                _fields_ = [
                                                    ('cbSize', UINT),
                                                    ('hwnd', HWND),
                                                    ('dwFlags', DWORD),
                                                    ('uCount', UINT),
                                                    ('dwTimeout', DWORD)
                                                ]

                                            FLASHW_ALL = 0x00000003       # Flash both window and taskbar
                                            FLASHW_TIMERNOFG = 0x0000000C  # Flash until window comes to foreground

                                            flash_info = FLASHWINFO()
                                            flash_info.cbSize = ctypes.sizeof(FLASHWINFO)
                                            flash_info.hwnd = hwnd
                                            flash_info.dwFlags = FLASHW_ALL | FLASHW_TIMERNOFG
                                            flash_info.uCount = 3  # Flash 3 times
                                            flash_info.dwTimeout = 0

                                            user32.FlashWindowEx(ctypes.byref(flash_info))

                                            logger.info("Window focus denied by Windows - flashing taskbar instead")

                                except Exception as e:
                                    logger.warning(f"Could not activate/flash window: {e}")

                            elif sys.platform == 'darwin':
                                # macOS: Use osascript to activate
                                try:
                                    import subprocess
                                    subprocess.run(['osascript', '-e', 'tell application "Sublime Text" to activate'],
                                                 check=False, capture_output=True)
                                except Exception as e:
                                    logger.warning(f"Could not activate window: {e}")
                            # Linux: window.bring_to_front() should work, but depends on window manager

                        def focus_view():
                            if view and view.is_loading():
                                sublime.set_timeout(focus_view, 50)
                            elif view:
                                window.focus_view(view)
                                activate_window()

                        activate_window()
                        sublime.set_timeout(focus_view, 50)

                sublime.set_timeout(open_file, 0)

                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'<html><body><h2>Opening in Sublime Text...</h2><script>window.close();</script></body></html>')
            else:
                self.send_error(400, "Missing file parameter")

        elif parsed.path == '/ping':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'OK')

        elif parsed.path == '/export':
            global _report_data

            if not _report_data:
                self.send_error(404, "No report data available")
                return

            params = parse_qs(parsed.query)
            hidden_severities = {
                s for s in params.get('hidesev', [''])[0].split(',') if s
            }
            hide_include_warnings = params.get('hideinc', ['0'])[0] == '1'

            text_content = generate_text_report(
                _report_data,
                hidden_severities=hidden_severities,
                hide_include_warnings=hide_include_warnings,
            )

            self.send_response(200)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.send_header('Content-Disposition', 'attachment; filename="validation_report.txt"')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(text_content.encode('utf-8'))

        else:
            self.send_error(404, "Not found")


def set_report_data(all_issues, skin_name, skin_path, timestamp):
    """Store report data for export."""
    global _report_data
    _report_data = {
        'all_issues': all_issues,
        'skin_name': skin_name,
        'skin_path': skin_path,
        'timestamp': timestamp
    }


def start_server():
    """Start the HTTP server in a background thread."""
    global _server, _server_port

    if _server is not None:
        logger.info("Server already running on port %d", _server_port)
        return _server_port

    try:
        _server = HTTPServer(('localhost', _server_port), FileOpenHandler)
        thread = threading.Thread(target=_server.serve_forever, daemon=True)
        thread.start()
        logger.info("Report server started on http://localhost:%d", _server_port)
        return _server_port
    except Exception as e:
        logger.error("Failed to start report server: %s", e)
        return None


def stop_server():
    """Stop the HTTP server."""
    global _server

    if _server:
        _server.shutdown()
        _server = None
        logger.info("Report server stopped")


def get_server_port():
    """Get the port number of the running server, or start it."""
    global _server_port
    if _server is None:
        start_server()
    return _server_port


start_server()
