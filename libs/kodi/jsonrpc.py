import os
from ..utils.files import check_paths
from ..addon.translations import get_po_file
from ..utils.decorators import run_async
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import socket
import json
import base64
import time
import logging


logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.propagate = True

APP_NAME = "kodi"

_USER_VISIBLE_METHODS = frozenset({"XBMC.GetInfoBooleans", "XBMC.GetInfoLabels"})


def prettyprint(obj) -> None:
    """Log any value as sorted, readable JSON, falling back to repr."""
    try:
        if isinstance(obj, (bytes, bytearray)):
            obj = obj.decode("utf-8", "replace")
        text = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)
    except Exception:
        try:
            text = repr(obj)
        except Exception:
            text = "<unprintable>"
    logger.debug(text)


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


class KodiJsonrpc:
    """JSON-RPC client for a Kodi install: core paths, languages, addons, queries."""
    def __init__(self, settings=None):
        try:
            import sublime
        except Exception:
            sublime = None

        self.settings = settings or (sublime.load_settings('kodidevkit.sublime-settings') if sublime else {})
        self.po_files = []
        self.json_url = None
        self.kodi_path = None
        self.userdata_folder = None
        self._settings_loaded = False
        self._cooldown_until = 0.0

        try:
            self.load_settings(self.settings)
        except Exception:
            pass

    @run_async
    def request_async(self, method, params):
        """Fire-and-forget version of `request()` (runs on a worker thread)."""
        return self.request(method, params)

    def request(self, method, params=None):
        """Request the JSON-RPC method from Kodi; the parsed reply, or None on failure."""
        s = self.settings or {}
        # re-read each call so settings edits apply at once
        self.json_url = self._url()

        # an unreachable Kodi would freeze the UI on every hover
        if time.time() < self._cooldown_until:
            logger.debug("Kodi request skipped (cooldown active): %s", method)
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
                prettyprint(result)

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

    def get_userdata_folder(self):
        """Get Kodi's home folder for the OS and portable mode, the parent of userdata."""
        from ..utils.files import get_platform
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
            return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "Kodi")
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

    def get_userdata_addons(self):
        """List addon folder names under `<userdata>/addons`."""
        if not self.user_addons_path or not os.path.exists(self.user_addons_path):
            return []
        path = self.user_addons_path
        return [f for f in os.listdir(path) if os.path.isdir(os.path.join(path, f))]

    def load_settings(self, settings, force: bool = False):
        """Load the settings into the url, paths and log level; only once unless forced."""
        if self._settings_loaded and not force:
            return
        self._settings_loaded = True

        self.settings = settings or {}
        self.json_url = self._url()

        self.kodi_path = self.settings.get("kodi_path") or None
        folder = (self.settings.get("userdata_folder") or "").rstrip("/\\")
        if os.path.basename(folder).lower() == "userdata":
            folder = os.path.dirname(folder)
        self.userdata_folder = folder or self.get_userdata_folder()

        debug_mode = bool(self.settings.get("debug_mode", False))
        logger.setLevel(logging.DEBUG if debug_mode else logging.INFO)

    def _url(self):
        """Base url of Kodi's web server, from the address or the scheme, host and port."""
        s = self.settings or {}
        addr = (s.get("kodi_address") or "").strip()
        if addr:
            return addr.rstrip("/")
        scheme = (s.get("kodi_scheme") or "http").strip()
        host = (s.get("kodi_host") or "localhost").strip()
        try:
            port = int(s.get("kodi_port", 8080))
        except (TypeError, ValueError):
            port = 8080
        return f"{scheme}://{host}:{port}"

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
        folders = self.settings.get("language_folders", ["resource.language.en_gb"])

        # core always has English, listed or not
        if folder == self.core_addons_path:
            scan_folders = list(dict.fromkeys(folders + ["resource.language.en_gb"]))
        else:
            scan_folders = folders

        for item in scan_folders:
            path = check_paths([
                os.path.join(folder, item, "strings.po"),
                os.path.join(folder, item, "resources", "strings.po")
            ])
            if path:
                po_file = get_po_file(path)
                if po_file:
                    po_file.language = item  # type: ignore[attr-defined]
                    po_files.append(po_file)
        return po_files
