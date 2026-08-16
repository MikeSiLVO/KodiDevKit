"""InfoProvider facade class: combines all mixins into a single public API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .loader import LoaderMixin
from .tooltips import TooltipMixin
from .navigation import NavigationMixin
from .checker import CheckerMixin
from ..validation.constants import SEVERITY_ERROR

if TYPE_CHECKING:
    from ..kodi.jsonrpc import KodiJsonrpc


class InfoProvider(LoaderMixin, TooltipMixin, NavigationMixin, CheckerMixin):
    def __init__(self):
        self.addon = None
        self.template_root = None
        self.WINDOW_FILENAMES: list = []
        self.WINDOW_NAMES: list = []
        self.WINDOW_IDS: list = []
        self.builtins: list = []
        self.conditions: list = []
        self.template_attribs: dict = {}
        self.template_values: dict = {}
        self.settings: dict = {}
        self.kodi_path: str | None = None
        self.kodi: KodiJsonrpc | None = None

    def get_check_listitems(self, check_type, progress_callback=None):
        """Engine's rows, minus the include-originated warnings the quick panel hides."""
        # The panel renders rows as-is, so this can't wait for a report layer.
        rows = super().get_check_listitems(check_type, progress_callback=progress_callback)
        if not self.settings.get("hide_include_warnings", True):
            return rows
        return [r for r in rows
                if not (r.get("include_name") and r.get("severity") != SEVERITY_ERROR)]
