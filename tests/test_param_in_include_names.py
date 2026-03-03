"""
Tests for $PARAM resolution in include names.

Tests the fix for the critical bug where includes with $PARAM in their names
were completely skipped instead of being resolved (skin.py:1348-1351).

Kodi behavior (GUIIncludes.cpp:628):
- Defined params: Substitute value
- Undefined params: Replace with empty string (NOT leave as-is)
- Example: "Dialog_$PARAM[size]" with size undefined → "Dialog_" (param → "")
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


class TestParamInIncludeNames(unittest.TestCase):
    """Test $PARAM resolution in include names."""

    def setUp(self):
        """Create temporary skin structure."""
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

        self.skin = Skin(path=self.skin_path)

    def tearDown(self):
        """Clean up temporary directory."""
        self.temp_dir.cleanup()

    def test_simple_param_in_include_name_defined(self):
        """Test simple $PARAM in include name with defined parameter."""
        # Create includes: Button_Primary and Button_Secondary
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="Button_Primary">
        <control type="button">
            <width>200</width>
            <label>Primary Button</label>
        </control>
    </include>
    <include name="Button_Secondary">
        <control type="button">
            <width>150</width>
            <label>Secondary Button</label>
        </control>
    </include>
    <include name="ButtonGroup">
        <param name="type" default="Primary"/>
        <definition>
            <include>Button_$PARAM[type]</include>
        </definition>
    </include>
</includes>"""
        includes_path = os.path.join(self.skin_path, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.skin.update_include_list()

        # Call ButtonGroup with type=Secondary
        test_xml = """<window>
    <include content="ButtonGroup">
        <param name="type" value="Secondary"/>
    </include>
</window>"""
        root = ET.fromstring(test_xml)
        kodi_resolve(self.skin,root, "16x9")

        # Should resolve Button_$PARAM[type] → Button_Secondary → insert button with width 150
        control = root.find(".//control[@type='button']")
        self.assertIsNotNone(control, "Button control should exist after resolution")

        width_elem = control.find("width")
        self.assertEqual(width_elem.text, "150", "Should resolve to Button_Secondary (width=150)")

        label_elem = control.find("label")
        self.assertEqual(label_elem.text, "Secondary Button", "Label should match Secondary button")

    def test_multiple_params_in_include_name(self):
        """Test multiple $PARAM references in single include name."""
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="Dialog_Small_Blur">
        <control type="image">
            <texture>dialog_small_blur.png</texture>
        </control>
    </include>
    <include name="Dialog_Large_Blur">
        <control type="image">
            <texture>dialog_large_blur.png</texture>
        </control>
    </include>
    <include name="Dialog_Large_NoBlur">
        <control type="image">
            <texture>dialog_large_noblur.png</texture>
        </control>
    </include>
    <include name="DialogBackground">
        <param name="size" default="Small"/>
        <param name="blur" default="Blur"/>
        <definition>
            <include>Dialog_$PARAM[size]_$PARAM[blur]</include>
        </definition>
    </include>
</includes>"""
        includes_path = os.path.join(self.skin_path, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.skin.update_include_list()

        # Call with size=Large, blur=NoBlur
        test_xml = """<window>
    <include content="DialogBackground">
        <param name="size" value="Large"/>
        <param name="blur" value="NoBlur"/>
    </include>
</window>"""
        root = ET.fromstring(test_xml)
        kodi_resolve(self.skin,root, "16x9")

        # Should resolve to Dialog_Large_NoBlur
        control = root.find(".//control[@type='image']")
        self.assertIsNotNone(control, "Image control should exist")

        texture_elem = control.find("texture")
        self.assertEqual(texture_elem.text, "dialog_large_noblur.png",
                        "Should resolve to Dialog_Large_NoBlur")

    def test_undefined_param_in_include_name_becomes_empty(self):
        """Test that undefined $PARAM in include name becomes empty string (Kodi spec)."""
        # Create include: Button_ (no suffix) and Button_Large
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="Button_">
        <control type="button">
            <width>100</width>
            <label>Default Button</label>
        </control>
    </include>
    <include name="Button_Large">
        <control type="button">
            <width>200</width>
            <label>Large Button</label>
        </control>
    </include>
    <include name="ButtonWrapper">
        <definition>
            <include>Button_$PARAM[size]</include>
        </definition>
    </include>
</includes>"""
        includes_path = os.path.join(self.skin_path, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.skin.update_include_list()

        # Call ButtonWrapper WITHOUT providing size param
        # Should resolve Button_$PARAM[size] → Button_ (param replaced with "")
        test_xml = """<window>
    <include>ButtonWrapper</include>
</window>"""
        root = ET.fromstring(test_xml)
        kodi_resolve(self.skin,root, "16x9")

        control = root.find(".//control[@type='button']")
        self.assertIsNotNone(control, "Button control should exist")

        width_elem = control.find("width")
        self.assertEqual(width_elem.text, "100",
                        "Should resolve to Button_ (undefined param → empty string)")

        label_elem = control.find("label")
        self.assertEqual(label_elem.text, "Default Button")

    def test_nested_param_forwarding_in_include_names(self):
        """Test parameter forwarding through nested includes with $PARAM in names."""
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="Icon_Home">
        <control type="image">
            <texture>icon_home.png</texture>
        </control>
    </include>
    <include name="Icon_Settings">
        <control type="image">
            <texture>icon_settings.png</texture>
        </control>
    </include>
    <include name="MenuItemInner">
        <param name="icon" default="Home"/>
        <definition>
            <include>Icon_$PARAM[icon]</include>
        </definition>
    </include>
    <include name="MenuItemOuter">
        <param name="icon" default="Home"/>
        <definition>
            <include content="MenuItemInner">
                <param name="icon" value="$PARAM[icon]"/>
            </include>
        </definition>
    </include>
</includes>"""
        includes_path = os.path.join(self.skin_path, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.skin.update_include_list()

        # Call MenuItemOuter with icon=Settings
        # Should forward param through: MenuItemOuter → MenuItemInner → Icon_Settings
        test_xml = """<window>
    <include content="MenuItemOuter">
        <param name="icon" value="Settings"/>
    </include>
</window>"""
        root = ET.fromstring(test_xml)
        kodi_resolve(self.skin,root, "16x9")

        control = root.find(".//control[@type='image']")
        self.assertIsNotNone(control, "Image control should exist after nested resolution")

        texture_elem = control.find("texture")
        self.assertEqual(texture_elem.text, "icon_settings.png",
                        "Param should forward through nested includes to resolve Icon_Settings")

    def test_param_with_default_in_include_name(self):
        """Test $PARAM in include name using default parameter value."""
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="Layout_Grid">
        <control type="panel" id="50">
            <viewtype label="Grid">icon</viewtype>
        </control>
    </include>
    <include name="Layout_List">
        <control type="panel" id="51">
            <viewtype label="List">list</viewtype>
        </control>
    </include>
    <include name="ContentView">
        <param name="layout" default="Grid"/>
        <definition>
            <include>Layout_$PARAM[layout]</include>
        </definition>
    </include>
</includes>"""
        includes_path = os.path.join(self.skin_path, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.skin.update_include_list()

        # Call ContentView WITHOUT providing layout param (should use default "Grid")
        test_xml = """<window>
    <include>ContentView</include>
</window>"""
        root = ET.fromstring(test_xml)
        kodi_resolve(self.skin,root, "16x9")

        # Should use default param value: Layout_$PARAM[layout] → Layout_Grid
        control = root.find(".//control[@type='panel']")
        self.assertIsNotNone(control, "Panel control should exist")
        self.assertEqual(control.attrib.get("id"), "50", "Should resolve to Layout_Grid (id=50)")

    def test_complex_param_pattern_real_world(self):
        """Test complex real-world pattern from Arctic Fuse 2 skin."""
        # This tests the actual pattern that was broken before the fix
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="View_Poster_Wrap">
        <control type="wraplist" id="500">
            <viewtype label="Poster Wrap">wrap</viewtype>
        </control>
    </include>
    <include name="View_Poster_Panel">
        <control type="panel" id="501">
            <viewtype label="Poster Panel">icon</viewtype>
        </control>
    </include>
    <include name="ViewTypeWrapper">
        <param name="view_prefix" default="Poster"/>
        <param name="view_suffix" default="Wrap"/>
        <definition>
            <include>View_$PARAM[view_prefix]_$PARAM[view_suffix]</include>
        </definition>
    </include>
</includes>"""
        includes_path = os.path.join(self.skin_path, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.skin.update_include_list()

        # Test with Panel suffix
        test_xml = """<window>
    <include content="ViewTypeWrapper">
        <param name="view_suffix" value="Panel"/>
    </include>
</window>"""
        root = ET.fromstring(test_xml)
        kodi_resolve(self.skin,root, "16x9")

        control = root.find(".//control")
        self.assertIsNotNone(control, "Control should exist")
        self.assertEqual(control.attrib.get("type"), "panel",
                        "Should resolve to View_Poster_Panel")
        self.assertEqual(control.attrib.get("id"), "501")


if __name__ == "__main__":
    unittest.main()
