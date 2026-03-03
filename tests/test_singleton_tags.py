"""
Tests for singleton tag validation (tags that should appear once per control).
"""

import unittest

import os

import sys

import tempfile

import shutil

# Add parent directory to path for imports
package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)


from libs.infoprovider import InfoProvider


class TestSingletonTags(unittest.TestCase):
    """Test singleton tag enforcement."""

    def setUp(self):
        """Create temporary skin directory for each test."""
        self.test_dir = tempfile.mkdtemp()
        self.provider = InfoProvider()
        self.provider.settings = {}

        # Create basic addon structure
        os.makedirs(os.path.join(self.test_dir, "1080i"))

        # Write addon.xml
        addon_xml = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test Skin" provider-name="test">
    <requires>
        <import addon="xbmc.gui" version="5.16.0"/>
    </requires>
    <extension point="xbmc.gui.skin" defaultthemename="Textures.xbt" debugging="false">
        <res width="1920" height="1080" aspect="16x9" default="true" folder="1080i" />
    </extension>
</addon>"""
        with open(os.path.join(self.test_dir, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(addon_xml)

        # Initialize provider
        self.provider.init_addon(self.test_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_single_colordiffuse_per_control_valid(self):
        """Test that single colordiffuse per control is valid."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="progress" id="100">
            <colordiffuse>FFFF0000</colordiffuse>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(xml_content)

        issues = self.provider.check_file(xml_path)

        # Should NOT flag single colordiffuse
        multiple_tag_issues = [i for i in issues if "Invalid multiple tags" in i.get("message", "")]
        self.assertEqual(len(multiple_tag_issues), 0, "Single colordiffuse should be valid")

    def test_multiple_colordiffuse_in_same_control_invalid(self):
        """Test that multiple colordiffuse tags in same control are flagged."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="progress" id="100">
            <colordiffuse>FFFF0000</colordiffuse>
            <colordiffuse>FF00FF00</colordiffuse>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(xml_content)

        issues = self.provider.check_file(xml_path)

        # SHOULD flag multiple colordiffuse in same control
        multiple_tag_issues = [i for i in issues if "Invalid multiple tags" in i.get("message", "") and "colordiffuse" in i.get("message", "")]
        self.assertEqual(len(multiple_tag_issues), 1, "Multiple colordiffuse in same control should be flagged")

    def test_separate_controls_each_with_colordiffuse(self):
        """Test that separate controls can each have their own colordiffuse."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="progress" id="100">
            <colordiffuse>FFFF0000</colordiffuse>
        </control>
        <control type="progress" id="101">
            <colordiffuse>FF00FF00</colordiffuse>
        </control>
        <control type="progress" id="102">
            <colordiffuse>FF0000FF</colordiffuse>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(xml_content)

        issues = self.provider.check_file(xml_path)

        # Should NOT flag colordiffuse in separate controls
        multiple_tag_issues = [i for i in issues if "Invalid multiple tags" in i.get("message", "")]
        self.assertEqual(len(multiple_tag_issues), 0, "Separate controls should each be allowed their own colordiffuse")

    def test_nested_controls_each_with_colordiffuse(self):
        """Test that nested controls can each have their own colordiffuse."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="group" id="100">
            <colordiffuse>FFFF0000</colordiffuse>
            <control type="progress" id="101">
                <colordiffuse>FF00FF00</colordiffuse>
            </control>
            <control type="progress" id="102">
                <colordiffuse>FF0000FF</colordiffuse>
            </control>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(xml_content)

        issues = self.provider.check_file(xml_path)

        # Should NOT flag colordiffuse in nested controls
        multiple_tag_issues = [i for i in issues if "Invalid multiple tags" in i.get("message", "")]
        self.assertEqual(len(multiple_tag_issues), 0, "Nested controls should each be allowed their own colordiffuse")

    def test_include_with_colordiffuse_in_control_with_colordiffuse(self):
        """Test control with colordiffuse that includes content also containing colordiffuse."""
        # Create an include file
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="ProgressDefaults">
        <width>100</width>
        <height>20</height>
        <colordiffuse>FFFF0000</colordiffuse>
    </include>
</includes>"""
        includes_path = os.path.join(self.test_dir, "1080i", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Create window that uses the include
        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="progress" id="100">
            <include>ProgressDefaults</include>
        </control>
        <control type="progress" id="101">
            <include>ProgressDefaults</include>
        </control>
    </controls>
</window>"""
        window_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(window_path, "w", encoding="utf-8") as f:
            f.write(window_xml)

        self.provider.init_addon(self.test_dir)
        issues = self.provider.check_file(window_path)

        # Should NOT flag - each control uses the include separately
        multiple_tag_issues = [i for i in issues if "Invalid multiple tags" in i.get("message", "")]
        self.assertEqual(len(multiple_tag_issues), 0, "Separate controls using same include should each be valid")

    def test_progress_control_with_var_colordiffuse(self):
        """Test progress control with $VAR colordiffuse with multiple conditional values."""
        # Create variable with MULTIPLE values (conditional) - this is valid Kodi pattern
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <variable name="HighlightColor">
        <value condition="Skin.HasSetting(RedTheme)">FFFF0000</value>
        <value condition="Skin.HasSetting(GreenTheme)">FF00FF00</value>
        <value>FF0000FF</value>
    </variable>
</includes>"""
        includes_path = os.path.join(self.test_dir, "1080i", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Create window with progress control - exact structure from user's example
        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="progress">
            <description>CPU BAR</description>
            <width>680</width>
            <height>16</height>
            <texturebg border="0,0,0,0">img/AmberDotBG.png</texturebg>
            <midtexture border="0,0,0,0">img/AmberDot.png</midtexture>
            <colordiffuse>$VAR[HighlightColor]</colordiffuse>
            <info>System.CPUUsage</info>
        </control>
    </controls>
</window>"""
        window_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(window_path, "w", encoding="utf-8") as f:
            f.write(window_xml)

        self.provider.init_addon(self.test_dir)
        issues = self.provider.check_file(window_path)

        # Should NOT flag - $VAR expansion with multiple conditional values is valid
        multiple_tag_issues = [i for i in issues if "Invalid multiple tags" in i.get("message", "")]
        self.assertEqual(len(multiple_tag_issues), 0, "VAR with multiple conditional values should not trigger multiple tag errors")


if __name__ == "__main__":
    unittest.main()
