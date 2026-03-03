import os
import platform
from .. import utils
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import socket
import json
import base64
import time
import logging


logger = logging.getLogger(__name__)

APP_NAME = "kodi"

if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.propagate = True


class KodiJsonrpc:
    """
    Class representing a kodi installation
    delivers core language files / paths / JSON answers / installed add-ons
    """
    def __init__(self, settings=None):
        try:
            import sublime
        except Exception:
            sublime = None

        self.settings = settings or (sublime.load_settings('kodidevkit.sublime-settings') if sublime else {})
        self.po_files = []
        self.colors = []
        self.color_labels = []
        self.json_url = None
        self.kodi_path = None
        self.userdata_folder = None
        self._settings_loaded = False  # <- add this

        try:
            self.load_settings(self.settings)
        except Exception:
            pass

    @utils.run_async
    def request_async(self, method, params):
        """
        send JSON command *data to Kodi in separate thread,
        also needs *settings for remote ip etc.
        """
        return self.request(method,
                            params)

    def request(self, method, params=None):
        """Send JSON-RPC request to Kodi. Returns dict or None."""
        # Refresh connection info from live settings every call
        s = self.settings or {}
        addr = (s.get("kodi_address") or "").strip()
        if addr:
            self.json_url = addr.rstrip("/")
        else:
            scheme = (s.get("kodi_scheme") or "http").strip()
            host = (s.get("kodi_host") or "localhost").strip()
            try:
                port = int(s.get("kodi_port", 8080))
            except Exception:
                port = 8080
            self.json_url = f"{scheme}://{host}:{port}"

        # Cooldown guard after a transport failure
        now = time.time()
        if now < getattr(self, "_cooldown_until", 0.0):
            logger.debug("Kodi request skipped (cooldown active): %s", method)
            return None
        if not self.json_url:
            return None

        data = {"jsonrpc": "2.0", "method": method, "id": 1}
        if params:
            data["params"] = params

        headers = {"Content-Type": "application/json"}

        token = (s.get("token") or "").strip()
        if token:
            headers["Authorization"] = "Bearer " + token
        else:
            user = (s.get("kodi_username", "kodi") or "").strip()
            pwd = (s.get("kodi_password", "") or "").strip()
            credentials = f"{user}:{pwd}"
            b64 = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
            headers["Authorization"] = "Basic " + b64

        req = Request(self.json_url + "/jsonrpc",
                      data=json.dumps(data).encode("utf-8"),
                      headers=headers)

        # Detailed logging for freeze diagnosis
        request_start = time.time()
        logger.debug("Kodi request START: method=%s url=%s", method, self.json_url)

        try:
            # Use 0.5s timeout to prevent UI freezing during network issues (e.g., display disconnection)
            # This is critical for hover tooltips which run on the main thread
            raw = urlopen(req, timeout=0.5).read()
            request_duration = time.time() - request_start
            logger.debug("Kodi request SUCCESS: method=%s duration=%.3fs", method, request_duration)

            result = json.loads(raw.decode("utf-8"))
            debug = bool(s.get("debug_mode", False))

            is_dict = isinstance(result, dict)
            if method == "JSONRPC.Introspect":
                if is_dict and "result" in result:
                    logger.info("JSONRPC.Introspect received from Kodi; payload suppressed")
                else:
                    err = result.get("error") if is_dict else None
                    if isinstance(err, dict):
                        logger.info("JSONRPC.Introspect error %s: %s", err.get("code"), err.get("message"))
                    else:
                        logger.info("JSONRPC.Introspect unexpected response; payload suppressed")
            elif debug:
                utils.prettyprint(result)

            self._cooldown_until = 0.0
            return result

        except (HTTPError, URLError, socket.timeout, OSError, ConnectionError) as exc:
            request_duration = time.time() - request_start
            exc_type = type(exc).__name__
            logger.warning("Kodi request FAILED: method=%s exception=%s duration=%.3fs error=%s",
                          method, exc_type, request_duration, str(exc))

            if bool(s.get("debug_mode", False)):
                logger.info("RPC transport error for %s: %s", method, exc)

            # After timeout/network error, prevent further requests for 2 seconds
            # This prevents repeated freezing when Kodi is unreachable (e.g., during display disconnection)
            self._cooldown_until = time.time() + 2.0
            logger.debug("Kodi cooldown set: next retry after %.1fs", 2.0)
            return None

    def get_colors(self):
        """
        create color list by parsing core color file
        """
        self.colors = []
        if not self.color_file_path or not os.path.exists(self.color_file_path):
            return False
        root = utils.get_root_from_file(self.color_file_path)
        if root is None:
            return False
        for node in root.findall("color"):
            color = {"name": node.attrib["name"],
                     "line": node.sourceline,
                     "content": node.text,
                     "file": self.color_file_path}
            self.colors.append(color)
        logger.info("found color file %s including %i colors", self.color_file_path, len(self.colors))
        self.color_labels = {i["name"] for i in self.colors}

    def get_userdata_folder(self):
        """
        return userdata folder based on platform and portable setting
        """
        if platform.system() == "Linux":
            return os.path.join(os.path.expanduser("~"), ".%s" % APP_NAME)
        elif platform.system() == "Windows":
            if self.settings.get("portable_mode"):
                if self.kodi_path:
                    return os.path.join(self.kodi_path, "portable_data")
                return None
            else:
                appdata = os.getenv('APPDATA')
                if appdata:
                    return os.path.join(appdata, APP_NAME)
                return None
        elif platform.system() == "Darwin":
            return os.path.join(os.path.expanduser("~"), "Application Support", APP_NAME, "userdata")
        return None

    @property
    def user_addons_path(self):
        """
        get path to userdata addon dir
        """
        if self.userdata_folder:
            return os.path.join(self.userdata_folder, "addons")
        return None

    @property
    def core_addons_path(self):
        """
        get path to core addon dir
        """
        if self.kodi_path:
            return os.path.join(self.kodi_path, "addons")
        return None

    @property
    def color_file_path(self):
        """
        get path to core color xml
        """
        if self.kodi_path:
            return os.path.join(self.kodi_path, "system", "colors.xml")
        return None

    @property
    def default_skin_path(self):
        """
        get path to userdata addon dir
        """
        if self.user_addons_path:
            return os.path.join(self.user_addons_path, "skin.estuary", "xml")
        return None

    def get_userdata_addons(self):
        """
        get list of folders from userdata addon dir
        """
        if not self.user_addons_path or not os.path.exists(self.user_addons_path):
            return []
        return [f for f in os.listdir(self.user_addons_path) if not os.path.isfile(f)]

    def load_settings(self, settings, force: bool = False):
        """Apply settings; rebuild url/paths and sync log level. Idempotent."""
        if getattr(self, "_settings_loaded", False) and not force:
            return
        self._settings_loaded = True

        self.settings = settings or {}

        addr = (self.settings.get("kodi_address") or "").strip()
        if addr:
            # normalize like 'http://host:port' without trailing slash
            addr = addr.rstrip("/")
            self.json_url = addr
        else:
            scheme = (self.settings.get("kodi_scheme") or "http").strip()
            host = (self.settings.get("kodi_host") or "localhost").strip()
            try:
                port = int(self.settings.get("kodi_port", 8080))
            except Exception:
                port = 8080
            self.json_url = f"{scheme}://{host}:{port}"

        self.kodi_path = self.settings.get("kodi_path") or None
        self.userdata_folder = self.settings.get("userdata_folder") or self.get_userdata_folder()

        debug_mode = bool(self.settings.get("debug_mode", False))
        try:
            logger.setLevel(logging.DEBUG if debug_mode else logging.INFO)
        except Exception:
            pass

    def update_labels(self):
        """
        get core po files
        """
        po_files = self.get_po_files(self.user_addons_path)
        languages = {i.language for i in po_files}
        core_po_files = self.get_po_files(self.core_addons_path)
        core_po_files = [i for i in core_po_files if i.language not in languages]
        self.po_files = po_files + core_po_files

    def get_po_files(self, folder):
        """
        get list with pofile objects
        """
        if not folder:
            return []
        po_files = []
        folders = self.settings.get("language_folders", ["resource.language.en_gb", "English"])

        # Ensure core language is considered for the core addons tree even if settings omit it
        if folder == self.core_addons_path:
            scan_folders = list(dict.fromkeys(folders + ["resource.language.en_gb"]))
        else:
            scan_folders = folders

        for item in scan_folders:
            path = utils.check_paths([
                os.path.join(folder, item, "strings.po"),
                os.path.join(folder, item, "resources", "strings.po")
            ])
            if path:
                po_file = utils.get_po_file(path)
                if po_file:
                    po_file.language = item  # type: ignore[attr-defined]
                    po_files.append(po_file)
        return po_files
