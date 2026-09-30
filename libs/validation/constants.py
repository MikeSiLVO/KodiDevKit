"""Constants and data tables for Kodi skin validation: control tags, allowed values, validation rules."""

from __future__ import annotations
from lxml import etree as ET

# Control type tags recognized by Kodi
CONTROL_TAGS = {
    "button", "togglebutton", "radiobutton", "edit", "image", "label", "textbox",
    "progress", "slider", "spincontrol", "list", "panel", "group", "multiimage",
    "wraplist", "scrollbar", "visualisation", "grouplist", "sliderex", "panelcontainer"
}

# text Kodi registers as a boolean condition, besides any `condition` attribute
CONDITION_TAGS = frozenset({"visible", "enable", "usealttexture", "selected", "expression"})

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

# Control tags Kodi reads every copy of, any other only once (GUIControlFactory.cpp:582)
REPEATABLE_TAGS = {
    "visible", "animation", "include", "description",
    "onup", "ondown", "onleft", "onright", "onnext", "onprev", "onback", "oninfo",
    "onclick", "ontextchange", "onfocus", "onunfocus", "altclick",
}

# Repeatable per control type; other controls use only the first <label> or <info>
ALLOWED_MULTI = {
    ("control", "fadelabel"): {"label", "info"},
}

# Read through GetInfoLabels, which skips an empty copy (GUIControlFactory.cpp:683)
LABEL_READ_TAGS = {
    "label", "info", "hinttext", "texture", "imagepath", "videofilter", "stretchmode", "rotation",
    "pixels", "imagefilter", "diffusefilter", "controllerid", "controlleraddress", "portaddress",
    "peripherallocation",
}


def is_read_copy(element, tag_low):
    """Whether Kodi could read this copy of a read-once tag, rather than skip it."""
    if (element.get("_kdk_inc_name") or "").startswith("default type="):
        # defaults are appended after everything else, so they only fill gaps
        return False
    if tag_low in LABEL_READ_TAGS and not (element.text or "").strip():
        return any(not a.startswith("_kdk_") for a in element.attrib)
    return True

# Attribute values with enumerations (normalized to lowercase for efficient case-insensitive lookups)
ALLOWED_VALUES = {
    "align": {"left", "center", "right", "justify"},
    "grouplistalign": {"left", "center", "right", "justify", "top", "bottom"},
    "aligny": {"top", "center", "bottom"},
    "bool": {"true", "false", "yes", "no", "on", "off", "enabled", "disabled", "0"},
    "orientation": {"horizontal", "vertical"},
    "aspect": {"scale", "stretch", "center", "keep"},
    "filter": {"linear", "nearest"},
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

# Enum types that Kodi parses case-insensitively (see XMLUtils.cpp:213, VisibleEffect.cpp:102)
CASE_INSENSITIVE_ENUMS = {"bool", "orientation", "tween", "easing", "aspect"}

# XML parser configuration
PARSER = ET.XMLParser(remove_blank_text=True, remove_comments=True)

# Severity levels for validation issues
SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"

__all__ = [
    'CONTROL_TAGS',
    'BRACKET_TAGS',
    'CONDITION_TAGS',
    'INCLUDE_DEFINITION_TAGS',
    'NOOP_TAGS',
    'POS_TAGS',
    'REPEATABLE_TAGS',
    'LABEL_READ_TAGS',
    'is_read_copy',
    'attribute_bool_problem',
    'ALLOWED_MULTI',
    'ALLOWED_VALUES',
    'CASE_INSENSITIVE_ENUMS',
    'PARSER',
    'SEVERITY_ERROR',
    'SEVERITY_WARNING',
]


def attribute_bool_problem(attr, value):
    """How Kodi misreads a bool attribute, or None; each one compares its own spellings by hand."""
    v = value.strip().lower()
    if attr in ("flipx", "flipy", "pulse", "loop", "always", "background"):
        if v not in ("true", "false"):
            return f'{attr}="{value}" is off: Kodi turns it on only for "true"'
    elif attr == "scalediffuse":
        if v not in ("true", "yes", "false", "no"):
            return f'{attr}="{value}" is off: Kodi turns it on only for "true" or "yes"'
    elif attr in ("infill", "reversible"):
        if v not in ("true", "false"):
            return f'{attr}="{value}" is on: Kodi turns it off only for "false"'
    elif attr == "reverse" and v in ("false", "no", "off", "0"):
        return f'reverse="{value}" still reverses: Kodi turns it on whenever the attribute is present'
    return None
