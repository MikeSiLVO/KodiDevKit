"""
InfoProvider facade class — combines all mixins into a single public API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .loader import LoaderMixin
from .tooltips import TooltipMixin
from .navigation import NavigationMixin
from .checker import CheckerMixin

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
