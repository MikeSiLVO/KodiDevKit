"""
Tests for constant resolution accuracy matching Kodi behavior.

Tests the fix for incorrect constant resolution that was resolving bare
constant names (skin.py:1241-1252). Kodi ONLY resolves constants using
explicit $CONSTANT[] syntax, NOT bare names.

Kodi behavior (GUIIncludes.cpp:391-410):
- $CONSTANT[name] syntax: Resolves to constant value
- Bare constant names: NOT resolved (left as-is)
- Only resolves in whitelisted attributes and nodes
"""

import os
import sys
import tempfile
import unittest
from lxml import etree as ET

# Add parent directory to path for imports
package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.skin import Skin
from tests.test_utils import kodi_resolve


class TestConstantResolutionAccuracy(unittest.TestCase):
    """Test that constant resolution matches Kodi's exact behavior."""

    def setUp(self):
        """Create temporary skin with constants."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.skin_path = self.temp_dir.name
        os.makedirs(os.path.join(self.skin_path, "16x9"))

        # Create minimal addon.xml
        addon_xml = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test" provider-name="Test">
    <requires><import addon="xbmc.gui" version="5.15.0"/></requires>
    <extension point="xbmc.gui.skin" debugging="false">
        <res width="1920" height="1080" aspect="16:9" default="true" folder="16x9" />
    </extension>
</addon>"""
        with open(os.path.join(self.skin_path, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(addon_xml)

        # Create Includes.xml with constants
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <constant name="ButtonWidth">200</constant>
    <constant name="ButtonHeight">50</constant>
    <constant name="DialogWidth">800</constant>
    <constant name="CommonPadding">10</constant>
</includes>"""
        with open(os.path.join(self.skin_path, "16x9", "Includes.xml"), "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.skin = Skin(path=self.skin_path)
        self.skin.update_include_list()

    def tearDown(self):
        """Clean up temporary directory."""
        self.temp_dir.cleanup()

    def test_explicit_constant_syntax_resolves(self):
        """Test that $CONSTANT[name] syntax resolves correctly in whitelisted attribute."""
        # 'width' is in constant_attribs whitelist
        test_xml = """<control type="button" width="$CONSTANT[ButtonWidth]" />"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin,root, "16x9")

        self.assertEqual(root.attrib.get("width"), "200",
                        "$CONSTANT[ButtonWidth] should resolve to '200'")

    def test_bare_constant_name_does_not_resolve(self):
        """Test that bare constant names do NOT resolve (Kodi spec)."""
        # Even though ButtonWidth is defined as constant, bare name should NOT resolve
        test_xml = """<control type="button" width="ButtonWidth" />"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin,root, "16x9")

        # Should remain as-is (Kodi doesn't resolve bare names)
        self.assertEqual(root.attrib.get("width"), "ButtonWidth",
                        "Bare constant name should NOT resolve")

    def test_comma_separated_bare_names_do_not_resolve(self):
        """Test that comma-separated bare constant names do NOT resolve."""
        # This was the buggy behavior we removed (lines 1241-1252)
        test_xml = """<control type="button" width="ButtonWidth,ButtonHeight" />"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin,root, "16x9")

        # Should remain unchanged
        self.assertEqual(root.attrib.get("width"), "ButtonWidth,ButtonHeight",
                        "Comma-separated bare names should NOT resolve")

    def test_explicit_constant_in_node_text(self):
        """Test $CONSTANT[] in whitelisted node text."""
        # 'width' is in constant_nodes whitelist
        test_xml = """<control type="button">
    <width>$CONSTANT[ButtonWidth]</width>
</control>"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin,root, "16x9")

        width_elem = root.find("width")
        self.assertEqual(width_elem.text, "200",
                        "$CONSTANT[] in node text should resolve")

    def test_bare_constant_in_node_text_does_not_resolve(self):
        """Test bare constant name in whitelisted node does NOT resolve."""
        test_xml = """<control type="button">
    <width>ButtonWidth</width>
</control>"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin,root, "16x9")

        width_elem = root.find("width")
        self.assertEqual(width_elem.text, "ButtonWidth",
                        "Bare constant in node should NOT resolve")

    def test_constant_not_resolved_in_non_whitelisted_attribute(self):
        """Test that constants don't resolve in non-whitelisted attributes."""
        # 'id' is NOT in constant_attribs whitelist
        test_xml = """<control type="button" id="$CONSTANT[ButtonWidth]" />"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin,root, "16x9")

        # Should remain unexpanded (id not whitelisted)
        self.assertEqual(root.attrib.get("id"), "$CONSTANT[ButtonWidth]",
                        "Constants should NOT expand in non-whitelisted attributes")

    def test_constant_not_resolved_in_non_whitelisted_node(self):
        """Test that constants don't resolve in non-whitelisted nodes."""
        # 'label' is NOT in constant_nodes whitelist
        test_xml = """<control type="button">
    <label>$CONSTANT[ButtonWidth]</label>
</control>"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin,root, "16x9")

        label_elem = root.find("label")
        self.assertEqual(label_elem.text, "$CONSTANT[ButtonWidth]",
                        "Constants should NOT expand in non-whitelisted nodes")

    def test_multiple_constants_in_same_value(self):
        """Test multiple $CONSTANT[] references in same value."""
        # This is valid Kodi syntax
        test_xml = """<control type="button" width="$CONSTANT[ButtonWidth]" height="$CONSTANT[ButtonHeight]" />"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin,root, "16x9")

        self.assertEqual(root.attrib.get("width"), "200")
        self.assertEqual(root.attrib.get("height"), "50")

    def test_undefined_constant_not_resolved(self):
        """Test that undefined constants remain as-is."""
        test_xml = """<control type="button" width="$CONSTANT[UndefinedConstant]" />"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin,root, "16x9")

        # Undefined constant should remain unchanged
        self.assertEqual(root.attrib.get("width"), "$CONSTANT[UndefinedConstant]",
                        "Undefined constant should remain unchanged")

    def test_constant_with_whitespace(self):
        """Test $CONSTANT[] with whitespace in name (should still work)."""
        test_xml = """<control type="button" width="$CONSTANT[  ButtonWidth  ]" />"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin,root, "16x9")

        # Whitespace should be trimmed, constant should resolve
        self.assertEqual(root.attrib.get("width"), "200",
                        "Constant with whitespace should resolve")

    def test_constant_case_insensitive(self):
        """Test that $CONSTANT[] is case-insensitive."""
        test_xml = """<control type="button" width="$constant[ButtonWidth]" />"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin,root, "16x9")

        self.assertEqual(root.attrib.get("width"), "200",
                        "$constant (lowercase) should resolve")

    def test_mixed_constant_and_text(self):
        """Test constant mixed with other text."""
        # Some attributes might have constants mixed with text
        test_xml = """<control type="button" x="$CONSTANT[CommonPadding]" />"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin,root, "16x9")

        # x is whitelisted, should resolve
        self.assertEqual(root.attrib.get("x"), "10",
                        "Constant in whitelisted attribute should resolve")

    def test_nested_constants_not_supported(self):
        """Test that nested constants are not resolved recursively."""
        # Recreate skin with nested constant
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <constant name="BaseWidth">100</constant>
    <constant name="NestedWidth">$CONSTANT[BaseWidth]</constant>
</includes>"""
        includes_path = os.path.join(self.skin_path, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Reload skin to pick up new constants
        skin = Skin(path=self.skin_path)
        skin.update_include_list()

        test_xml = """<control type="button" width="$CONSTANT[NestedWidth]" />"""
        root = ET.fromstring(test_xml)

        kodi_resolve(skin, root, "16x9")

        # NestedWidth should expand to its literal value "$CONSTANT[BaseWidth]"
        # Kodi doesn't recursively resolve constants in constant definitions
        self.assertEqual(root.attrib.get("width"), "$CONSTANT[BaseWidth]",
                        "Nested constants should not resolve recursively")


if __name__ == "__main__":
    unittest.main()
