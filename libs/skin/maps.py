"""SkinMaps: the five CGUIIncludes maps the resolver reads."""

from __future__ import annotations


class SkinMaps:
    """The five CGUIIncludes maps, each keyed by xml folder."""

    def __init__(self):
        self.includes = {}
        self.defaults = {}
        self.constants = {}
        self.variables = {}
        self.expressions = {}
