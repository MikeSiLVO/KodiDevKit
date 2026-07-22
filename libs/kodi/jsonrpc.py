import os
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

_USER_VISIBLE_METHODS = frozenset({"XBMC.GetInfoBooleans", "XBMC.GetInfoLabels"})


def _without_negation_twins(result):
    """Drop the `![cond]` probe twin the hover adds, so only real queries print."""
    if not isinstance(result, dict) or not isinstance(result.get("result"), dict):
        return result
    values = result["result"]
    trimmed = {
        key: val
        for key, val in values.items()
        if not (key.startswith("![") and key.endswith("]") and key[2:-1] in values)
    }
    return {**result, "result": trimmed}

if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.propagate = True


class KodiJsonrpc:
    """JSON-RPC client for a Kodi install: core paths, languages, addons, queries."""
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
        self._settings_loaded = False

        try:
            self.load_settings(self.settings)
        except Exception:
            pass

    @utils.run_async
    def request_async(self, method, params):
        """Fire-and-forget version of `request()` (runs on a worker thread)."""
        return self.request(method, params)

    def request(self, method, params=None):
        """Send a JSON-RPC call to Kodi; return the parsed dict or None on failure."""
        # Re-read connection settings each call so changes apply immediately.
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

        # Stay quiet for a few seconds after a transport failure so we don't
        # repeatedly freeze the UI when Kodi is unreachable.
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

        request_start = time.time()
        logger.debug("Kodi request START: method=%s url=%s", method, self.json_url)

        try:
            # Tight timeout: tooltips can fire from the main thread, so a long
            # block here freezes the editor (e.g. when the display sleeps).
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
            elif method in _USER_VISIBLE_METHODS:
                print(json.dumps(_without_negation_twins(result), indent=2, ensure_ascii=False, sort_keys=True))
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

            # 2-second cooldown so repeated tooltips don't all hit the timeout in turn.
            self._cooldown_until = time.time() + 2.0
            logger.debug("Kodi cooldown set: next retry after %.1fs", 2.0)
            return None

    def get_colors(self):
        """Parse Kodi's core colors.xml into `self.colors` and `self.color_labels`."""
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
        """Detect Kodi's userdata folder for the current OS / portable mode."""
        from ..utils import get_platform
        _plat = get_platform()
        if _plat == "linux":
            return os.path.join(os.path.expanduser("~"), ".%s" % APP_NAME)
        elif _plat == "windows":
            if self.settings.get("portable_mode"):
                if self.kodi_path:
                    return os.path.join(self.kodi_path, "portable_data")
                return None
            else:
                appdata = os.getenv('APPDATA')
                if appdata:
                    return os.path.join(appdata, APP_NAME)
                return None
        elif _plat == "osx":
            return os.path.join(os.path.expanduser("~"), "Application Support", APP_NAME, "userdata")
        return None

    @property
    def user_addons_path(self):
        """`<userdata>/addons` if known, else None."""
        if self.userdata_folder:
            return os.path.join(self.userdata_folder, "addons")
        return None

    @property
    def core_addons_path(self):
        """`<kodi_path>/addons` if known, else None."""
        if self.kodi_path:
            return os.path.join(self.kodi_path, "addons")
        return None

    @property
    def color_file_path(self):
        """Path to Kodi's core `system/colors.xml`."""
        if self.kodi_path:
            return os.path.join(self.kodi_path, "system", "colors.xml")
        return None

    @property
    def default_skin_path(self):
        """Path to Estuary's xml folder under user addons (used as a sample skin)."""
        if self.user_addons_path:
            return os.path.join(self.user_addons_path, "skin.estuary", "xml")
        return None

    def get_userdata_addons(self):
        """List addon folder names under `<userdata>/addons`."""
        if not self.user_addons_path or not os.path.exists(self.user_addons_path):
            return []
        return [f for f in os.listdir(self.user_addons_path) if not os.path.isfile(f)]

    def load_settings(self, settings, force: bool = False):
        """Apply `settings`; rebuild url/paths and re-sync the log level.

        Idempotent: returns immediately if already loaded unless `force=True`.
        """
        if getattr(self, "_settings_loaded", False) and not force:
            return
        self._settings_loaded = True

        self.settings = settings or {}

        addr = (self.settings.get("kodi_address") or "").strip()
        if addr:
            self.json_url = addr.rstrip("/")
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
        """Reload PO files: prefer user-installed languages, fall back to core."""
        po_files = self.get_po_files(self.user_addons_path)
        languages = {i.language for i in po_files}
        core_po_files = self.get_po_files(self.core_addons_path)
        core_po_files = [i for i in core_po_files if i.language not in languages]
        self.po_files = po_files + core_po_files

    def get_po_files(self, folder):
        """Return PO files for the configured languages under `folder`."""
        if not folder:
            return []
        po_files = []
        folders = self.settings.get("language_folders", ["resource.language.en_gb", "English"])

        # Always include en_gb when scanning core addons, even if the user's
        # language settings don't list it; core has English regardless.
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
