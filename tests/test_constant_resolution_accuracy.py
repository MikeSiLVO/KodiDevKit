"""
Tests for constant resolution matching Kodi behavior.

Kodi resolves bare constant names (no $-prefix syntax) in whitelisted
attribs/nodes via comma-split lookup. See GUIIncludes.cpp:139-153 (load),
:320-342 (traversal), :641-651 (resolve algorithm).
"""

import os
import sys
import tempfile
import unittest
from lxml import etree as ET

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.skin import Skin
from tests.test_utils import kodi_resolve


class TestConstantResolutionAccuracy(unittest.TestCase):
    """Constant resolution matches CGUIIncludes::ResolveConstant (GUIIncludes.cpp:641-651)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.skin_path = self.temp_dir.name
        os.makedirs(os.path.join(self.skin_path, "16x9"))

        addon_xml = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test" provider-name="Test">
    <requires><import addon="xbmc.gui" version="5.15.0"/></requires>
    <extension point="xbmc.gui.skin" debugging="false">
        <res width="1920" height="1080" aspect="16:9" default="true" folder="16x9" />
    </extension>
</addon>"""
        with open(os.path.join(self.skin_path, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(addon_xml)

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
        self.temp_dir.cleanup()

    def test_bare_name_resolves_in_whitelisted_attribute(self):
        """Bare constant name resolves in a CONSTANT_ATTRIBUTES attrib."""
        test_xml = """<control type="button" width="ButtonWidth" />"""
        root = ET.fromstring(test_xml)
        kodi_resolve(self.skin, root, "16x9")
        self.assertEqual(root.attrib.get("width"), "200")

    def test_bare_name_resolves_in_whitelisted_node_text(self):
        """Bare constant name resolves in a CONSTANT_NODES text."""
        test_xml = """<control type="button">
    <width>ButtonWidth</width>
</control>"""
        root = ET.fromstring(test_xml)
        kodi_resolve(self.skin, root, "16x9")
        self.assertEqual(root.find("width").text, "200")

    def test_bare_name_does_not_resolve_in_non_whitelisted_attribute(self):
        """`id` is not in CONSTANT_ATTRIBUTES so the bare name stays."""
        test_xml = """<control type="button" id="ButtonWidth" />"""
        root = ET.fromstring(test_xml)
        kodi_resolve(self.skin, root, "16x9")
        self.assertEqual(root.attrib.get("id"), "ButtonWidth")

    def test_bare_name_does_not_resolve_in_non_whitelisted_node(self):
        """`label` is not in CONSTANT_NODES so the bare name stays."""
        test_xml = """<control type="button">
    <label>ButtonWidth</label>
</control>"""
        root = ET.fromstring(test_xml)
        kodi_resolve(self.skin, root, "16x9")
        self.assertEqual(root.find("label").text, "ButtonWidth")

    def test_comma_separated_pieces_each_lookup(self):
        """Each comma-separated piece is resolved independently."""
        # `border` is whitelisted; four-value border with constant pieces.
        test_xml = """<control type="button" border="CommonPadding,CommonPadding,CommonPadding,CommonPadding" />"""
        root = ET.fromstring(test_xml)
        kodi_resolve(self.skin, root, "16x9")
        self.assertEqual(root.attrib.get("border"), "10,10,10,10")

    def test_mixed_known_and_unknown_pieces(self):
        """Unknown pieces pass through unchanged; known pieces resolve."""
        test_xml = """<control type="button" border="ButtonWidth,Unknown,ButtonHeight,Unknown" />"""
        root = ET.fromstring(test_xml)
        kodi_resolve(self.skin, root, "16x9")
        self.assertEqual(root.attrib.get("border"), "200,Unknown,50,Unknown")

    def test_undefined_name_stays(self):
        """Names not in the constant map pass through unchanged."""
        test_xml = """<control type="button" width="UndefinedConstant" />"""
        root = ET.fromstring(test_xml)
        kodi_resolve(self.skin, root, "16x9")
        self.assertEqual(root.attrib.get("width"), "UndefinedConstant")

    def test_lookup_is_case_sensitive(self):
        """`buttonwidth` does NOT match `ButtonWidth` (case-sensitive lookup)."""
        test_xml = """<control type="button" width="buttonwidth" />"""
        root = ET.fromstring(test_xml)
        kodi_resolve(self.skin, root, "16x9")
        self.assertEqual(root.attrib.get("width"), "buttonwidth")

    def test_no_recursion_in_constant_values(self):
        """Constant values are NOT re-scanned (no recursive expansion)."""
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <constant name="BaseWidth">100</constant>
    <constant name="NestedWidth">BaseWidth</constant>
</includes>"""
        with open(os.path.join(self.skin_path, "16x9", "Includes.xml"), "w", encoding="utf-8") as f:
            f.write(includes_xml)
        skin = Skin(path=self.skin_path)
        skin.update_include_list()

        test_xml = """<control type="button" width="NestedWidth" />"""
        root = ET.fromstring(test_xml)
        kodi_resolve(skin, root, "16x9")
        # NestedWidth -> "BaseWidth" verbatim; not re-scanned to "100".
        self.assertEqual(root.attrib.get("width"), "BaseWidth")


if __name__ == "__main__":
    unittest.main()
