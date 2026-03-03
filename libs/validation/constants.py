"""
Constants and data tables for Kodi skin validation.

Extracted from infoprovider.py as part of Phase 2 refactoring.
Contains control tag definitions, allowed values, and validation rules.
"""

from __future__ import annotations
from lxml import etree as ET

# Control type tags recognized by Kodi
CONTROL_TAGS = {
    "button", "togglebutton", "radiobutton", "edit", "image", "label", "textbox",
    "progress", "slider", "spincontrol", "list", "panel", "group", "multiimage",
    "wraplist", "scrollbar", "visualisation", "grouplist", "sliderex", "panelcontainer"
}

# Tags whose text is a bracketed condition that must balance
BRACKET_TAGS = {"visible", "enable", "usealttexture", "selected", "expression", "onclick", "onback"}

# Tags that are valid only in include definitions, not in expanded controls
INCLUDE_DEFINITION_TAGS = {"param", "definition", "nested"}

# Action-ish tags that should be "noop" when intentionally empty
NOOP_TAGS = {
    "onclick",
    "onfocus",
    "onunfocus",
    "onup",
    "onleft",
    "onright",
    "ondown",
    "onback",
}

# Position/dimension tags
POS_TAGS = {
    "posx",
    "posy",
    "left",
    "centerleft",
    "right",
    "centerright",
    "top",
    "centertop",
    "bottom",
    "centerbottom",
    "width",
    "height",
    "offsetx",
    "offsety",
    "textoffsetx",
    "textoffsety",
    "textwidth",
    "spinposx",
    "spinposy",
    "spinwidth",
    "spinheight",
    "radioposx",
    "radioposy",
    "radiowidth",
    "radioheight",
    "sliderwidth",
    "sliderheight",
    "itemgap",
    "bordersize",
    "timeperimage",
    "fadetime",
    "pauseatend",
    "depth",
}

# Tags that should appear at most once per control (per parent control scope)
SINGLETON_TAGS = {
    "enable",
    "usealttexture",
    "selected",
    "colordiffuse",
}

# Allow multiple child tags for specific control types
ALLOWED_MULTI = {
    # fadelabel control can contain multiple <label> children
    ("control", "fadelabel"): {"label"},
}

# Attribute values with enumerations (normalized to lowercase for efficient case-insensitive lookups)
ALLOWED_VALUES = {
    "align": {"left", "center", "right", "justify"},
    "grouplistalign": {"left", "center", "right", "justify", "top", "bottom"},
    "aligny": {"top", "center", "bottom"},
    "bool": {"true", "false", "yes", "no", "on", "off", "enabled", "disabled"},
    "orientation": {"horizontal", "vertical"},
    "aspect": {"scale", "stretch", "center", "keep"},
    "subtype": {"page", "int", "float", "text"},
    "action": {"volume", "seek", "pvr.seek"},
    "viewtype": {
        "list",
        "icon",
        "biglist",
        "bigicon",
        "wide",
        "bigwide",
        "wrap",
        "bigwrap",
        "info",
        "biginfo",
    },
    "tween": {
        "quadratic",
        "linear",
        "sine",
        "cubic",
        "back",
        "bounce",
        "circle",
        "elastic",
    },
    "easing": {"inout", "in", "out"},
}

# Enum types that Kodi parses case-insensitively
# (see Kodi source: GUIControlFactory.cpp lines 1124, XMLUtils::GetBoolean)
CASE_INSENSITIVE_ENUMS = {"bool", "orientation"}

# XML parser configuration
PARSER = ET.XMLParser(remove_blank_text=True, remove_comments=True)

# Severity levels for validation issues
SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"

__all__ = [
    'CONTROL_TAGS',
    'BRACKET_TAGS',
    'INCLUDE_DEFINITION_TAGS',
    'NOOP_TAGS',
    'POS_TAGS',
    'SINGLETON_TAGS',
    'ALLOWED_MULTI',
    'ALLOWED_VALUES',
    'CASE_INSENSITIVE_ENUMS',
    'PARSER',
    'SEVERITY_ERROR',
    'SEVERITY_WARNING',
]
