"""Tests for hierarchy.py — validates data table correctness."""

import unittest

from libs.validation.hierarchy import (
    WINDOW_CHILDREN,
    CONTROLS_CHILDREN,
    COORDINATES_CHILDREN,
    GROUP_TYPES,
    CONTAINER_TYPES,
    STANDARD_LAYOUT_TAGS,
    EPG_LAYOUT_TAGS,
    ALL_LAYOUT_TAGS,
    LAYOUT_CHILDREN,
    CONTENT_CHILDREN,
    INCLUDES_CHILDREN,
    FONTS_CHILDREN,
    FONTSET_CHILDREN,
    FONT_CHILDREN,
    VARIABLE_CHILDREN,
)


class TestWindowChildren(unittest.TestCase):
    """Verify WINDOW_CHILDREN matches GUIWindow.cpp:186-268."""

    def test_core_tags_present(self):
        core = {"controls", "defaultcontrol", "backgroundcolor", "visible",
                "animation", "zorder", "coordinates", "camera", "depth",
                "onload", "onunload", "include"}
        self.assertTrue(core.issubset(WINDOW_CHILDREN))

    def test_no_control_tag(self):
        self.assertNotIn("control", WINDOW_CHILDREN)


class TestControlsChildren(unittest.TestCase):
    """Verify CONTROLS_CHILDREN — only <control> plus <include>."""

    def test_only_control_and_include(self):
        self.assertEqual(CONTROLS_CHILDREN, frozenset({"control", "include", "description"}))


class TestCoordinatesChildren(unittest.TestCase):
    def test_position_tags(self):
        self.assertIn("posx", COORDINATES_CHILDREN)
        self.assertIn("posy", COORDINATES_CHILDREN)
        self.assertIn("origin", COORDINATES_CHILDREN)


class TestGroupTypes(unittest.TestCase):
    def test_group_and_grouplist(self):
        self.assertEqual(GROUP_TYPES, frozenset({"group", "grouplist"}))

    def test_no_container_overlap(self):
        self.assertFalse(GROUP_TYPES & CONTAINER_TYPES)


class TestContainerTypes(unittest.TestCase):
    def test_all_containers(self):
        expected = {"list", "panel", "wraplist", "fixedlist", "epggrid", "gamecontrollerlist"}
        self.assertEqual(CONTAINER_TYPES, frozenset(expected))


class TestLayoutTags(unittest.TestCase):
    def test_standard_layouts(self):
        self.assertEqual(STANDARD_LAYOUT_TAGS, frozenset({"itemlayout", "focusedlayout"}))

    def test_epg_extra_layouts(self):
        epg_extras = {"channellayout", "focusedchannellayout", "rulerlayout", "rulerdatelayout"}
        self.assertTrue(epg_extras.issubset(EPG_LAYOUT_TAGS))

    def test_all_is_union(self):
        self.assertEqual(ALL_LAYOUT_TAGS, STANDARD_LAYOUT_TAGS | EPG_LAYOUT_TAGS)

    def test_layout_children(self):
        self.assertEqual(LAYOUT_CHILDREN, frozenset({"control", "include"}))


class TestContentChildren(unittest.TestCase):
    def test_item_and_include(self):
        self.assertEqual(CONTENT_CHILDREN, frozenset({"item", "include"}))


class TestIncludesChildren(unittest.TestCase):
    def test_five_types(self):
        expected = {"include", "default", "constant", "variable", "expression"}
        self.assertEqual(INCLUDES_CHILDREN, frozenset(expected))


class TestFontsHierarchy(unittest.TestCase):
    def test_fonts_only_fontset(self):
        self.assertEqual(FONTS_CHILDREN, frozenset({"fontset"}))

    def test_fontset_only_font(self):
        self.assertEqual(FONTSET_CHILDREN, frozenset({"font"}))

    def test_font_children(self):
        required = {"name", "filename", "size"}
        self.assertTrue(required.issubset(FONT_CHILDREN))
        self.assertIn("style", FONT_CHILDREN)
        self.assertIn("color", FONT_CHILDREN)


class TestVariableChildren(unittest.TestCase):
    def test_only_value(self):
        self.assertEqual(VARIABLE_CHILDREN, frozenset({"value"}))


if __name__ == "__main__":
    unittest.main()
