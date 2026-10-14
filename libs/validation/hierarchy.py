"""Which child tags Kodi reads at each nesting level, taken from the loaders in its source."""

from __future__ import annotations

# a window's own tags; <include> is resolved before load but valid as written
WINDOW_CHILDREN = frozenset({
    "previouswindow",
    "defaultcontrol",
    "menucontrol",
    "visible",
    "animation",
    "zorder",
    "coordinates",
    "camera",
    "depth",
    "controls",
    "backgroundcolor",
    "onload",
    "onunload",
    "include",
    "description",  # ignored by Kodi, allowed anywhere as documentation
    # read by media windows
    "views",
})

# a window loads only <control> here and skips the rest
CONTROLS_CHILDREN = frozenset({"control", "include", "description"})

COORDINATES_CHILDREN = frozenset({
    "posx", "posy", "left", "top",
    "origin",
})

# group types, whose child controls the window loads too
GROUP_TYPES = frozenset({"group", "grouplist"})

NEVER_FOCUSABLE = frozenset({
    "fadelabel", "image", "label", "multiimage", "progress", "ranges", "textbox",
    "videowindow", "visualisation", "renderaddon",
})

# container types, which load layouts
CONTAINER_TYPES = frozenset({
    "list", "panel", "wraplist", "fixedlist",
    "epggrid", "gamecontrollerlist",
})

# the layouts a container loads; the EPG grid has its own
STANDARD_LAYOUT_TAGS = frozenset({"itemlayout", "focusedlayout"})

EPG_LAYOUT_TAGS = frozenset({
    "itemlayout", "focusedlayout",
    "channellayout", "focusedchannellayout",
    "rulerlayout", "rulerdatelayout",
})

ALL_LAYOUT_TAGS = STANDARD_LAYOUT_TAGS | EPG_LAYOUT_TAGS

# a layout is a control group
LAYOUT_CHILDREN = frozenset({"control", "include"})

CONTENT_CHILDREN = frozenset({"item", "default", "include"})

# <map> only from Kodi 22
INCLUDES_CHILDREN = frozenset({
    "include", "default", "constant", "variable", "expression", "map",
})

FONTS_CHILDREN = frozenset({"fontset"})

FONTSET_CHILDREN = frozenset({"font"})

FONT_CHILDREN = frozenset({
    "name", "filename", "size", "style",
    "color", "shadow", "aspect", "linespacing",
})

# <value> with an optional condition
VARIABLE_CHILDREN = frozenset({"value"})

# <entry key> only, the rest skipped
MAP_CHILDREN = frozenset({"entry"})


__all__ = [
    "WINDOW_CHILDREN",
    "CONTROLS_CHILDREN",
    "COORDINATES_CHILDREN",
    "GROUP_TYPES",
    "NEVER_FOCUSABLE",
    "CONTAINER_TYPES",
    "STANDARD_LAYOUT_TAGS",
    "EPG_LAYOUT_TAGS",
    "ALL_LAYOUT_TAGS",
    "LAYOUT_CHILDREN",
    "CONTENT_CHILDREN",
    "INCLUDES_CHILDREN",
    "FONTS_CHILDREN",
    "FONTSET_CHILDREN",
    "FONT_CHILDREN",
    "VARIABLE_CHILDREN",
    "MAP_CHILDREN",
]
