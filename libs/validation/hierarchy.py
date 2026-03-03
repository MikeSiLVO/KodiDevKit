"""
Static hierarchy data for context-aware XML validation.

Defines valid children at each nesting level, derived from Kodi C++ source.
All sets are verified against GUIWindow.cpp, GUIControlFactory.cpp,
GUIBaseContainer.cpp, GUIEPGGridContainer.cpp, GUIIncludes.cpp,
GUIFontManager.cpp, and StaticProvider.cpp.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Window level — GUIWindow.cpp:186-268
# Tags processed in CGUIWindow::Load() before and inside the child loop.
# <include> is valid at author time but resolved before Load() runs.
# ---------------------------------------------------------------------------
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
    "description",  # Silently ignored by Kodi, universal documentation tag
    # Less common but valid (see GUIWindow.cpp:186-190)
    "allowoverlay",
    "views",
})

# ---------------------------------------------------------------------------
# <controls> — GUIWindow.cpp:258-268
# Only <control> elements are loaded; everything else is silently skipped.
# ---------------------------------------------------------------------------
CONTROLS_CHILDREN = frozenset({"control", "include", "description"})

# ---------------------------------------------------------------------------
# <coordinates> — GUIWindow.cpp:234-250
# Sub-elements inside <coordinates system="1">
# ---------------------------------------------------------------------------
COORDINATES_CHILDREN = frozenset({
    "posx", "posy", "left", "top",
    "origin",
    "system",
})

# ---------------------------------------------------------------------------
# Control types that are groups — GUIControlGroup.h:74, GUIControlGroupList.h
# IsGroup() returns true → child <control> elements are recursively loaded
# by GUIWindow::LoadControl() (GUIWindow.cpp:302)
# ---------------------------------------------------------------------------
GROUP_TYPES = frozenset({"group", "grouplist"})

# ---------------------------------------------------------------------------
# Container types — GUIControlFactory.cpp:70-107
# These inherit IGUIContainer and use LoadLayout() for itemlayout/focusedlayout.
# ---------------------------------------------------------------------------
CONTAINER_TYPES = frozenset({
    "list", "panel", "wraplist", "fixedlist",
    "epggrid", "gamecontrollerlist",
})

# ---------------------------------------------------------------------------
# Layout tags — GUIBaseContainer.cpp:1317-1334, GUIEPGGridContainer.cpp:1641-1694
# Standard containers use itemlayout + focusedlayout.
# EPG grid has 6 layout tags.
# ---------------------------------------------------------------------------
STANDARD_LAYOUT_TAGS = frozenset({"itemlayout", "focusedlayout"})

EPG_LAYOUT_TAGS = frozenset({
    "itemlayout", "focusedlayout",
    "channellayout", "focusedchannellayout",
    "rulerlayout", "rulerdatelayout",
})

# Union of all layout tags (for general checks)
ALL_LAYOUT_TAGS = STANDARD_LAYOUT_TAGS | EPG_LAYOUT_TAGS

# ---------------------------------------------------------------------------
# Layout children — layouts only contain <control> elements
# (each layout is a CGUIListItemLayout which extends CGUIControlGroup)
# ---------------------------------------------------------------------------
LAYOUT_CHILDREN = frozenset({"control", "include"})

# ---------------------------------------------------------------------------
# <content> children — StaticProvider.cpp:20-34
# Static content contains <item> elements. <include> valid at author time.
# ---------------------------------------------------------------------------
CONTENT_CHILDREN = frozenset({"item", "include"})

# ---------------------------------------------------------------------------
# <includes> root element — GUIIncludes.cpp:88-99
# Five child types loaded by Load_Internal().
# ---------------------------------------------------------------------------
INCLUDES_CHILDREN = frozenset({
    "include", "default", "constant", "variable", "expression",
})

# ---------------------------------------------------------------------------
# Font.xml hierarchy — GUIFontManager.cpp:67, 426-510
# ---------------------------------------------------------------------------
FONTS_CHILDREN = frozenset({"fontset"})

FONTSET_CHILDREN = frozenset({"font"})

FONT_CHILDREN = frozenset({
    "name", "filename", "size", "style",
    "color", "shadow", "aspect", "linespacing",
    "borderpercent",
})

# ---------------------------------------------------------------------------
# <variable> children — GUIIncludes.cpp:160-168, 244-257
# Only <value> children with optional condition attribute.
# ---------------------------------------------------------------------------
VARIABLE_CHILDREN = frozenset({"value"})


__all__ = [
    "WINDOW_CHILDREN",
    "CONTROLS_CHILDREN",
    "COORDINATES_CHILDREN",
    "GROUP_TYPES",
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
]
