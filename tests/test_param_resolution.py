"""
Tests for $PARAM resolution in include names following Kodi's behavior.
"""

import os
import sys
import tempfile
import shutil
import unittest

# Ensure parent directory is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.base import ValidationTestCase, IncludeCheck
from libs.skin import Skin


class TestParamResolution(ValidationTestCase):
    """Test that undefined $PARAM in include names resolve to empty strings (Kodi behavior)."""

    def setUp(self):
        """Create a temporary test skin."""
        self.test_dir = tempfile.mkdtemp()
        self.skin_dir = os.path.join(self.test_dir, "skin.test")
        os.makedirs(self.skin_dir)

        # Create addon.xml
        addon_xml = os.path.join(self.skin_dir, "addon.xml")
        with open(addon_xml, "w", encoding="utf-8") as f:
            f.write("""<?xml version="1.0"?>
<addon id="skin.test" version="1.0.0">
    <requires><import addon="xbmc.gui" version="5.15.0"/></requires>
    <extension point="xbmc.gui.skin" debugging="false">
        <res width="1920" height="1080" aspect="16:9" default="true" folder="1080i"/>
    </extension>
</addon>""")

        # Create 1080i directory
        self.xml_dir = os.path.join(self.skin_dir, "1080i")
        os.makedirs(self.xml_dir)

    def tearDown(self):
        """Clean up test directory."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_undefined_param_resolves_to_base_name(self):
        """
        Test that include names with undefined $PARAM resolve to base name.

        Example: "Dialog_Blur$PARAM[size]" → "Dialog_Blur" when size is undefined.
        This matches Kodi's behavior (GUIIncludes.cpp:628).
        """
        # Create includes file with base include and parameterized wrapper
        includes_xml = os.path.join(self.xml_dir, "Includes.xml")
        with open(includes_xml, "w", encoding="utf-8") as f:
            f.write("""<?xml version="1.0"?>
<includes>
    <!-- Base include that exists -->
    <include name="Dialog_Blur">
        <control type="image">
            <texture>blur.png</texture>
        </control>
    </include>

    <!-- Wrapper that references base + param (param not defined here) -->
    <include name="Dialog_Wrapper">
        <definition>
            <control type="group">
                <!-- This should resolve to "Dialog_Blur" when size is undefined -->
                <include content="Dialog_Blur$PARAM[size]">
                    <param name="fallback">default</param>
                </include>
            </control>
        </definition>
    </include>
</includes>""")

        # Create window that uses the wrapper without passing size param
        window_xml = os.path.join(self.xml_dir, "Home.xml")
        with open(window_xml, "w", encoding="utf-8") as f:
            f.write("""<?xml version="1.0"?>
<window>
    <controls>
        <!-- Call wrapper without size param - should resolve nested include to "Dialog_Blur" -->
        <include content="Dialog_Wrapper"/>
    </controls>
</window>""")

        # Validate
        skin = Skin(path=self.skin_dir)
        checker = IncludeCheck(skin)
        issues = checker.check()

        # Should not report "Dialog_Blur$PARAM[size]" as undefined
        # because it resolves to "Dialog_Blur" which exists
        undefined = [i for i in issues if "not defined" in i.get("message", "")]
        undefined_names = [i["message"].replace("Include not defined: ", "") for i in undefined]

        self.assertNotIn("Dialog_Blur$PARAM[size]", undefined_names,
                         "Include with undefined $PARAM should resolve to base name")

    def test_param_suffix_variants_resolve_correctly(self):
        """
        Test that different param positions in include names resolve correctly.
        """
        includes_xml = os.path.join(self.xml_dir, "Includes.xml")
        with open(includes_xml, "w", encoding="utf-8") as f:
            f.write("""<?xml version="1.0"?>
<includes>
    <!-- Base includes -->
    <include name="Button">
        <control type="button"/>
    </include>

    <include name="Button_Special">
        <control type="button"/>
    </include>

    <!-- Wrapper with various param patterns -->
    <include name="Control_Wrapper">
        <definition>
            <control type="group">
                <!-- Suffix param: Button$PARAM[type] → Button (if undefined) -->
                <include>Button$PARAM[type]</include>

                <!-- Middle param: Button_$PARAM[style]_Special → Button__Special (if undefined) -->
                <!-- Wait, this won't work - two underscores. Let me use suffix only. -->
                <include content="Button$PARAM[modifier]"/>
            </control>
        </definition>
    </include>
</includes>""")

        window_xml = os.path.join(self.xml_dir, "Home.xml")
        with open(window_xml, "w", encoding="utf-8") as f:
            f.write("""<?xml version="1.0"?>
<window>
    <controls>
        <include content="Control_Wrapper"/>
    </controls>
</window>""")

        skin = Skin(path=self.skin_dir)
        checker = IncludeCheck(skin)
        issues = checker.check()

        undefined = [i for i in issues if "not defined" in i.get("message", "")]
        undefined_names = [i["message"].replace("Include not defined: ", "").strip() for i in undefined]

        # Both should resolve to "Button"
        self.assertNotIn("Button$PARAM[type]", undefined_names)
        self.assertNotIn("Button$PARAM[modifier]", undefined_names)


if __name__ == "__main__":
    unittest.main()
