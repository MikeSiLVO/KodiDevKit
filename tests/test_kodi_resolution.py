"""
Tests for Kodi-exact resolution behavior matching GUIIncludes.cpp.

These tests verify that kodi_resolve() matches Kodi's CGUIIncludes::Resolve exactly:
- Resolution order: SetDefaults → ResolveConstants → ResolveExpressions → ResolveIncludes → Recurse
- Constant whitelist enforcement (only expand in whitelisted attributes/nodes)
- Expression wrapping in [...]
- Control defaults with position skipping
- Parameter merging (call-site overrides defaults)

References:
- GUIIncludes.cpp lines 341-359: Resolve() method
- GUIIncludes.cpp lines 362-389: SetDefaults() method
- GUIIncludes.cpp lines 391-410: ResolveConstants() method
- GUIIncludes.cpp lines 412-430: ResolveExpressions() method
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


class TestKodiResolutionOrder(unittest.TestCase):
    """Test that resolution happens in correct order per GUIIncludes.cpp:341-359."""

    def setUp(self):
        """Create temporary skin structure."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.skin_path = self.temp_dir.name

        # Create minimal addon.xml
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

        # Initialize skin
        self.skin = Skin(path=self.skin_path)

    def tearDown(self):
        """Clean up temporary directory."""
        self.temp_dir.cleanup()

    def test_resolution_order_constants_before_includes(self):
        """Test that constants are resolved before includes (GUIIncludes.cpp:341-359)."""
        # Create Includes.xml with constant and include
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <constant name="ButtonWidth">200</constant>
    <include name="TestButton">
        <control type="button">
            <width>$CONSTANT[ButtonWidth]</width>
        </control>
    </include>
</includes>"""
        includes_path = os.path.join(self.skin_path, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Load includes
        self.skin.update_include_list()

        # Create test XML that uses the include
        test_xml = """<window>
    <include>TestButton</include>
</window>"""
        root = ET.fromstring(test_xml)

        # Apply Kodi resolution
        kodi_resolve(self.skin, root, "16x9")

        # After resolution:
        # 1. Constants should be expanded first
        # 2. Then include should be spliced in
        # Result: <width>200</width>
        width_elem = root.find(".//width")
        self.assertIsNotNone(width_elem, "Width element should exist after resolution")
        self.assertEqual(width_elem.text, "200", "Constant should be resolved to '200'")


class TestConstantWhitelist(unittest.TestCase):
    """Test constant expansion whitelist per GUIIncludes.cpp:18-50, 391-410."""

    def setUp(self):
        """Create temporary skin with constants."""
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

        # Create Includes.xml with constants
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <constant name="TestValue">100</constant>
</includes>"""
        with open(os.path.join(self.skin_path, "16x9", "Includes.xml"), "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.skin = Skin(path=self.skin_path)
        self.skin.update_include_list()

    def tearDown(self):
        """Clean up."""
        self.temp_dir.cleanup()

    def test_constant_expands_in_whitelisted_attribute(self):
        """Constants should expand in whitelisted attributes (GUIIncludes.cpp:391-410)."""
        # 'width' is in CONSTANT_ATTRIBUTES whitelist
        test_xml = """<control type="button" width="$CONSTANT[TestValue]" />"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin, root, "16x9")

        self.assertEqual(root.attrib.get("width"), "100", "Constant should expand in whitelisted attribute")

    def test_constant_expands_in_whitelisted_node(self):
        """Constants should expand in whitelisted node text (GUIIncludes.cpp:391-410)."""
        # 'width' is in CONSTANT_NODES whitelist
        test_xml = """<control type="button">
    <width>$CONSTANT[TestValue]</width>
</control>"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin, root, "16x9")

        width_elem = root.find("width")
        self.assertEqual(width_elem.text, "100", "Constant should expand in whitelisted node")

    def test_constant_does_not_expand_in_non_whitelisted_attribute(self):
        """Constants should NOT expand in non-whitelisted attributes (GUIIncludes.cpp:391-410)."""
        # 'id' is NOT in CONSTANT_ATTRIBUTES whitelist
        test_xml = """<control type="button" id="$CONSTANT[TestValue]" />"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin, root, "16x9")

        # Constant should remain unexpanded
        self.assertEqual(root.attrib.get("id"), "$CONSTANT[TestValue]",
                        "Constant should NOT expand in non-whitelisted attribute")

    def test_constant_does_not_expand_in_non_whitelisted_node(self):
        """Constants should NOT expand in non-whitelisted node text (GUIIncludes.cpp:391-410)."""
        # 'label' is NOT in CONSTANT_NODES whitelist
        test_xml = """<control type="button">
    <label>$CONSTANT[TestValue]</label>
</control>"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin, root, "16x9")

        label_elem = root.find("label")
        # Constant should remain unexpanded
        self.assertEqual(label_elem.text, "$CONSTANT[TestValue]",
                        "Constant should NOT expand in non-whitelisted node")


class TestExpressionWrapping(unittest.TestCase):
    """Test expression wrapping in brackets per GUIIncludes.cpp:412-430."""

    def setUp(self):
        """Create temporary skin with expressions."""
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

        # Create Includes.xml with expression
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <expression name="IsPlaying">Player.HasMedia</expression>
</includes>"""
        with open(os.path.join(self.skin_path, "16x9", "Includes.xml"), "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.skin = Skin(path=self.skin_path)
        self.skin.update_include_list()

    def tearDown(self):
        """Clean up."""
        self.temp_dir.cleanup()

    def test_expression_wrapped_in_brackets(self):
        """$EXP[name] should be replaced with [expression_value] (GUIIncludes.cpp:412-430)."""
        test_xml = """<control type="button">
    <visible>$EXP[IsPlaying]</visible>
</control>"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin, root, "16x9")

        visible_elem = root.find("visible")
        # Expression should be wrapped in brackets
        self.assertEqual(visible_elem.text, "[Player.HasMedia]",
                        "Expression should be wrapped in brackets")


class TestControlDefaults(unittest.TestCase):
    """Test control defaults application per GUIIncludes.cpp:362-389."""

    def setUp(self):
        """Create temporary skin with control defaults."""
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

        # Create Includes.xml with default
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <default type="button">
        <width>200</width>
        <height>50</height>
        <left>100</left>
        <top>100</top>
    </default>
</includes>"""
        with open(os.path.join(self.skin_path, "16x9", "Includes.xml"), "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.skin = Skin(path=self.skin_path)
        self.skin.update_include_list()

    def tearDown(self):
        """Clean up."""
        self.temp_dir.cleanup()

    def test_defaults_applied_to_matching_control_type(self):
        """Defaults should be applied to controls of matching type (GUIIncludes.cpp:362-389)."""
        test_xml = """<control type="button">
    <label>Test</label>
</control>"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin, root, "16x9")

        # Defaults should be applied
        self.assertIsNotNone(root.find("width"), "Width from default should be applied")
        self.assertEqual(root.find("width").text, "200")
        self.assertIsNotNone(root.find("height"), "Height from default should be applied")
        self.assertEqual(root.find("height").text, "50")

    def test_defaults_skip_position_when_posx_exists(self):
        """Position defaults should be skipped if control has posx (GUIIncludes.cpp:375-380)."""
        test_xml = """<control type="button">
    <posx>500</posx>
    <label>Test</label>
</control>"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin, root, "16x9")

        # left/right/centerleft/centerright should be skipped (has_posx = true)
        self.assertIsNone(root.find("left"), "Left default should be skipped when posx exists")
        # But top should still be applied (only posx exists, not posy)
        self.assertIsNotNone(root.find("top"), "Top default should still be applied")

    def test_defaults_skip_position_when_posy_exists(self):
        """Position defaults should be skipped if control has posy (GUIIncludes.cpp:375-380)."""
        test_xml = """<control type="button">
    <posy>300</posy>
    <label>Test</label>
</control>"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin, root, "16x9")

        # top/bottom/centertop/centerbottom should be skipped (has_posy = true)
        self.assertIsNone(root.find("top"), "Top default should be skipped when posy exists")
        # But left should still be applied (only posy exists, not posx)
        self.assertIsNotNone(root.find("left"), "Left default should still be applied")


class TestParameterMerging(unittest.TestCase):
    """Test parameter merging behavior per GUIIncludes.cpp."""

    def setUp(self):
        """Create temporary skin with parameterized includes."""
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

        # Create Includes.xml with parameterized include
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="TestButton">
        <param name="width" default="200"/>
        <param name="label" default="DefaultLabel"/>
        <definition>
            <control type="button">
                <width>$PARAM[width]</width>
                <label>$PARAM[label]</label>
            </control>
        </definition>
    </include>
</includes>"""
        with open(os.path.join(self.skin_path, "16x9", "Includes.xml"), "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.skin = Skin(path=self.skin_path)
        self.skin.update_include_list()

    def tearDown(self):
        """Clean up."""
        self.temp_dir.cleanup()

    def test_call_site_params_override_defaults(self):
        """Call-site parameters should override default parameters."""
        test_xml = """<window>
    <include content="TestButton">
        <param name="width" value="300"/>
        <param name="label" value="CustomLabel"/>
    </include>
</window>"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin, root, "16x9")

        # Call-site params should override defaults
        control = root.find(".//control")
        self.assertIsNotNone(control, "Control should exist after include resolution")

        width_elem = control.find("width")
        self.assertEqual(width_elem.text, "300", "Call-site width should override default")

        label_elem = control.find("label")
        self.assertEqual(label_elem.text, "CustomLabel", "Call-site label should override default")

    def test_default_params_used_when_not_overridden(self):
        """Default parameters should be used when not overridden at call-site."""
        test_xml = """<window>
    <include content="TestButton">
        <param name="width" value="300"/>
    </include>
</window>"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin, root, "16x9")

        control = root.find(".//control")

        # Width overridden at call-site
        width_elem = control.find("width")
        self.assertEqual(width_elem.text, "300", "Call-site width should be used")

        # Label not overridden, should use default
        label_elem = control.find("label")
        self.assertEqual(label_elem.text, "DefaultLabel", "Default label should be used")


if __name__ == "__main__":
    unittest.main()
