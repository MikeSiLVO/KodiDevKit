"""
Include maps data structure for Kodi skin include resolution.

This module provides the IncludeMaps class that matches Kodi's CGUIIncludes
5-map structure for managing includes, constants, variables, expressions, and defaults.
"""

from __future__ import annotations

# Version for cache invalidation (increment when structure changes)
INCLUDE_MAPS_VERSION = 1


class SkinMaps:
    """
    Lightweight structure matching Kodi's CGUIIncludes 5-map structure.

    This represents what Kodi loads at skin startup (eager loading):
    - Includes.xml -> build 5 maps (includes, defaults, constants, variables, expressions)
    - Font.xml -> fonts_defined
    - Builtin controls -> builtin_controls

    This is separate from the full ValidationIndex to enable lazy window validation.
    Windows are validated on-demand using these pre-built maps.
    """

    def __init__(self):
        self.includes = {}           # {folder: {name: {static, parameterized, ...}}}
        self.defaults = {}           # {folder: {type: default_attribs}}
        self.constants = {}          # {folder: {name: value}}
        self.variables = {}          # {folder: {name: definition}}
        self.expressions = {}        # {folder: {name: expression}}

        self.include_files = {}      # {folder: [filenames]} - from <include file="..."/>
        self.builtin_controls = {}   # {control_id: window_file}
        self.builtin_filename_map = {}

        self.fonts_defined = {}
        self.fonts_used = {}

        self.version = INCLUDE_MAPS_VERSION
