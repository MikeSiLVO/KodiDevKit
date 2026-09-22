"""SkinMaps: Kodi's 5-map include/constant/variable/expression/default structure."""

from __future__ import annotations

# bump when the pickled layout changes so stale caches are discarded
INCLUDE_MAPS_VERSION = 1


class SkinMaps:
    """What Kodi loads at skin start, per folder: the five CGUIIncludes maps, fonts, builtins."""

    def __init__(self):
        self.includes = {}
        self.defaults = {}
        self.constants = {}
        self.variables = {}
        self.expressions = {}

        self.include_files = {}
        self.builtin_controls = {}
        self.builtin_filename_map = {}

        self.fonts_defined = {}
        self.fonts_used = {}

        self.version = INCLUDE_MAPS_VERSION
