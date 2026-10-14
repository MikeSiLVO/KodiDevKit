"""SkinMaps: the five include maps the resolver reads."""

from __future__ import annotations


class SkinMaps:
    """Includes, defaults, constants, variables and expressions, each keyed by xml folder."""

    def __init__(self):
        self.includes = {}
        self.defaults = {}
        self.constants = {}
        self.variables = {}
        self.expressions = {}
