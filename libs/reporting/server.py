"""Local HTTP server that opens a report's file:line links in Sublime Text."""

import sublime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading
import logging
import sys
from .text import generate_text_report

logger = logging.getLogger(__name__)

_server = None
_server_port = 48273
_report_data = {}


def _raise_window(window):
    """Raise the window; on Windows, flash its taskbar button when focus is refused."""
    window.bring_to_front()  # type: ignore[attr-defined]

    if sys.platform == 'win32':
        # Windows can refuse focus; the taskbar flash below covers that
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

                    class FLASHWINFO(Structure):
                        _fields_ = [
                            ('cbSize', UINT),
                            ('hwnd', HWND),
                            ('dwFlags', DWORD),
                            ('uCount', UINT),
                            ('dwTimeout', DWORD)
                        ]

                    FLASHW_ALL = 0x00000003
                    FLASHW_TIMERNOFG = 0x0000000C

                    flash_info = FLASHWINFO()
                    flash_info.cbSize = ctypes.sizeof(FLASHWINFO)
                    flash_info.hwnd = hwnd
                    flash_info.dwFlags = FLASHW_ALL | FLASHW_TIMERNOFG
                    flash_info.uCount = 3
                    flash_info.dwTimeout = 0

                    user32.FlashWindowEx(ctypes.byref(flash_info))

                    logger.info("Window focus denied by Windows - flashing taskbar instead")

        except Exception as e:
            logger.warning(f"Could not activate/flash window: {e}")

    elif sys.platform == 'darwin':
        try:
            import subprocess
            subprocess.run(['osascript', '-e', 'tell application "Sublime Text" to activate'],
                           check=False, capture_output=True)
        except Exception as e:
            logger.warning(f"Could not activate window: {e}")
    # Linux relies on bring_to_front, which the window manager may ignore


def _open_at(file_path, line):
    """Open the file at the line in the active window, raising it again once loaded."""
    window = sublime.active_window()
    if not window:
        return
    view = window.open_file(f"{file_path}:{line}:0", sublime.ENCODED_POSITION)

    def focus_view():
        if view and view.is_loading():
            sublime.set_timeout(focus_view, 50)
        elif view:
            window.focus_view(view)
            _raise_window(window)

    _raise_window(window)
    sublime.set_timeout(focus_view, 50)


class FileOpenHandler(BaseHTTPRequestHandler):
    """HTTP request handler for opening files in Sublime Text."""

    def log_message(self, format, *args):
        """Log through the module logger instead of stderr."""
        logger.info(format % args)

    def do_GET(self):
        """Handle the open, ping and export requests."""
        parsed = urlparse(self.path)

        if parsed.path == '/open':
            params = parse_qs(parsed.query)
            file_path = params.get('file', [''])[0]
            line = params.get('line', ['1'])[0]

            if file_path:
                sublime.set_timeout(lambda: _open_at(file_path, line), 0)

                self.send_response(200)
                self.send_header('Content-type', 'text/html')
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
            hide_muted = params.get('hidemuted', ['0'])[0] == '1'

            text_content = generate_text_report(
                _report_data,
                hidden_severities=hidden_severities,
                hide_include_warnings=hide_include_warnings,
                hide_muted=hide_muted,
            )

            self.send_response(200)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.send_header('Content-Disposition', 'attachment; filename="validation_report.txt"')
            self.end_headers()
            self.wfile.write(text_content.encode('utf-8'))

        else:
            self.send_error(404, "Not found")


def set_report_data(all_issues, skin_name, skin_path, timestamp):
    """Set the report data the export endpoint serves."""
    global _report_data
    _report_data = {
        'all_issues': all_issues,
        'skin_name': skin_name,
        'skin_path': skin_path,
        'timestamp': timestamp
    }


def start_server():
    """Start the HTTP server in a background thread."""
    global _server

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
    """Stop the HTTP server and release its port."""
    global _server

    if _server:
        _server.shutdown()
        _server.server_close()
        _server = None
        logger.info("Report server stopped")


def get_server_port():
    """Get the server's port, starting the server if it is down."""
    if _server is None:
        start_server()
    return _server_port
