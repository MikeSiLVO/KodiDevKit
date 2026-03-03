"""
Test for tag validation regression where KeyError occurred on tags without template values.
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


class TestTagValidationRegression(unittest.TestCase):
    """Test that tag validation handles tags with only attributes (no text values)."""

    def setUp(self):
        """Create temporary skin directory for each test."""
        self.test_dir = tempfile.mkdtemp()
        self.provider = InfoProvider()
        self.provider.settings = {}

        # Create basic addon structure
        os.makedirs(os.path.join(self.test_dir, "16x9"))

        # Write addon.xml
        addon_xml = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test Skin" provider-name="test">
    <requires>
        <import addon="xbmc.gui" version="5.16.0"/>
    </requires>
    <extension point="xbmc.gui.skin" defaultthemename="Textures.xbt" debugging="false">
        <res width="1920" height="1080" aspect="16x9" default="true" folder="16x9" />
    </extension>
</addon>"""
        with open(os.path.join(self.test_dir, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(addon_xml)

    def tearDown(self):
        """Clean up temporary directory."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_control_with_animation_tag(self):
        """Test that controls with <animation> tags don't cause KeyError.

        Animation tags typically have attributes but no text value in controls.xml,
        which previously caused a KeyError when accessing self.template_values[c_type][tag].
        """
        # Create window with animation
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <posx>100</posx>
            <posy>100</posy>
            <width>200</width>
            <height>50</height>
            <label>Test Button</label>
            <animation effect="fade" start="0" end="100" time="300">WindowOpen</animation>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        # Create empty includes file
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
</includes>"""
        includes_path = os.path.join(self.test_dir, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.provider.init_addon(self.test_dir)

        # This should not raise KeyError
        try:
            issues = self.provider.check_values()
            # Should complete without error
            self.assertIsInstance(issues, list)
        except KeyError as e:
            self.fail(f"KeyError raised during validation: {e}")

    def test_control_with_camera_tag(self):
        """Test that controls with <camera> tags don't cause KeyError.

        Camera tags have attributes (x, y) but typically no text value.
        """
        # Create window with camera
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="image" id="100">
            <posx>100</posx>
            <posy>100</posy>
            <width>200</width>
            <height>150</height>
            <texture>test.png</texture>
            <camera x="0" y="0">10</camera>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        # Create empty includes file
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
</includes>"""
        includes_path = os.path.join(self.test_dir, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.provider.init_addon(self.test_dir)

        # This should not raise KeyError
        try:
            issues = self.provider.check_values()
            # Should complete without error
            self.assertIsInstance(issues, list)
        except KeyError as e:
            self.fail(f"KeyError raised during validation: {e}")

    def test_control_with_include_tag(self):
        """Test that controls with nested <include> tags are handled correctly.

        Include tags within controls have content but no template value.
        """
        # Create window with include
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="group" id="100">
            <posx>0</posx>
            <posy>0</posy>
            <include>SomeInclude</include>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        # Create includes file with the referenced include
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="SomeInclude">
        <control type="label">
            <label>From Include</label>
        </control>
    </include>
</includes>"""
        includes_path = os.path.join(self.test_dir, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.provider.init_addon(self.test_dir)

        # This should not raise KeyError
        try:
            issues = self.provider.check_values()
            # Should complete without error
            self.assertIsInstance(issues, list)
        except KeyError as e:
            self.fail(f"KeyError raised during validation: {e}")


if __name__ == "__main__":
    unittest.main()
