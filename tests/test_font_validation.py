"""
Unit tests for font validation functionality.
Tests cover all aspects of check_fonts() behavior before refactoring.
Python 3.8 compatible.
"""

import os
import sys
import tempfile
import unittest

# Add parent directory to path for imports
package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.infoprovider import InfoProvider


class TestFontValidation(unittest.TestCase):
    """Test suite for font validation before and after refactoring."""

    def setUp(self):
        """Create temporary skin structure for testing."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.skin_path = self.temp_dir.name

        # Create skin directory structure
        self.xml_dir = os.path.join(self.skin_path, "16x9")
        self.fonts_dir = os.path.join(self.skin_path, "fonts")
        os.makedirs(self.xml_dir, exist_ok=True)
        os.makedirs(self.fonts_dir, exist_ok=True)

        # Create minimal addon.xml
        addon_xml = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test Skin" provider-name="Test">
    <requires>
        <import addon="xbmc.gui" version="5.15.0"/>
    </requires>
    <extension point="xbmc.gui.skin" debugging="false">
        <res width="1920" height="1080" aspect="16:9" default="true" folder="16x9" />
    </extension>
</addon>
"""
        with open(os.path.join(self.skin_path, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(addon_xml)

    def tearDown(self):
        """Clean up temporary directory."""
        self.temp_dir.cleanup()

    def create_font_file(self, filename):
        """Create a dummy font file."""
        path = os.path.join(self.fonts_dir, filename)
        with open(path, "wb") as f:
            f.write(b"FAKE TTF FILE")
        return path

    def create_fonts_xml(self, content):
        """Create Font.xml in the xml directory."""
        path = os.path.join(self.xml_dir, "Font.xml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def create_window_xml(self, content):
        """Create a window XML file."""
        path = os.path.join(self.xml_dir, "Home.xml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def init_provider(self):
        """Initialize InfoProvider with test skin."""
        provider = InfoProvider()
        provider.settings = {}
        provider.init_addon(self.skin_path)
        return provider

    def test_valid_single_fontset(self):
        """Test valid single fontset with all required elements."""
        self.create_font_file("font.ttf")

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font13</name>
            <filename>font.ttf</filename>
            <size>13</size>
        </font>
        <font>
            <name>font16</name>
            <filename>font.ttf</filename>
            <size>16</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)

        # Create a window that uses the fonts
        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label">
            <font>font13</font>
            <label>Test</label>
        </control>
        <control type="label">
            <font>font16</font>
            <label>Test</label>
        </control>
    </controls>
</window>
"""
        self.create_window_xml(window_xml)

        provider = self.init_provider()
        issues = provider.check_fonts()

        # Should have no structural issues (only "no issues" or unused fonts if any)
        # Filter out any non-error messages
        errors = [i for i in issues if "no" not in i["message"].lower() and "unused" not in i["message"].lower()]
        self.assertEqual(len(errors), 0, f"Should have no errors, got: {errors}")

    def test_missing_font13(self):
        """Test detection of missing required font13."""
        self.create_font_file("font.ttf")

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font16</name>
            <filename>font.ttf</filename>
            <size>16</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)
        provider = self.init_provider()

        issues = provider.check_fonts()

        # Should detect missing font13
        has_font13_error = any("font13" in issue["message"].lower() for issue in issues)
        self.assertTrue(has_font13_error, "Should detect missing font13")

    def test_missing_unicode_fontset(self):
        """Test detection of missing unicode='true' fontset."""
        self.create_font_file("font.ttf")

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default">
        <font>
            <name>font13</name>
            <filename>font.ttf</filename>
            <size>13</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)
        provider = self.init_provider()

        issues = provider.check_fonts()

        # Should detect missing unicode='true'
        has_unicode_error = any("unicode" in issue["message"].lower() for issue in issues)
        self.assertTrue(has_unicode_error, "Should detect missing unicode fontset")

    def test_missing_font_file(self):
        """Test detection of missing font file."""
        # Don't create the font file

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font13</name>
            <filename>missing.ttf</filename>
            <size>13</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)
        provider = self.init_provider()

        issues = provider.check_fonts()

        # Should detect missing file
        has_missing_file = any("missing.ttf" in issue["message"].lower() for issue in issues)
        self.assertTrue(has_missing_file, "Should detect missing font file")

    def test_case_mismatch_font_file(self):
        """Test detection of case mismatch in font filename."""
        self.create_font_file("Font.ttf")  # Capital F

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font13</name>
            <filename>font.ttf</filename>
            <size>13</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)
        provider = self.init_provider()

        issues = provider.check_fonts()

        # Debug output
        print("\n=== test_case_mismatch_font_file issues ===")
        for issue in issues:
            print(f"  {issue}")

        # Should detect case mismatch
        has_case_error = any("case" in issue["message"].lower() for issue in issues)
        self.assertTrue(has_case_error, "Should detect case mismatch in filename")

    def test_invalid_font_size(self):
        """Test detection of invalid font size."""
        self.create_font_file("font.ttf")

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font13</name>
            <filename>font.ttf</filename>
            <size>-5</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)
        provider = self.init_provider()

        issues = provider.check_fonts()

        # Should detect invalid size
        has_size_error = any("size" in issue["message"].lower() and "positive" in issue["message"].lower() for issue in issues)
        self.assertTrue(has_size_error, "Should detect invalid font size")

    def test_duplicate_font_name_in_fontset(self):
        """Test detection of duplicate font name within a fontset."""
        self.create_font_file("font.ttf")

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font13</name>
            <filename>font.ttf</filename>
            <size>13</size>
        </font>
        <font>
            <name>font13</name>
            <filename>font.ttf</filename>
            <size>16</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)
        provider = self.init_provider()

        issues = provider.check_fonts()

        # Should detect duplicate
        has_duplicate_error = any("duplicate" in issue["message"].lower() for issue in issues)
        self.assertTrue(has_duplicate_error, "Should detect duplicate font name")

    def test_missing_font_name(self):
        """Test detection of missing <name> element."""
        self.create_font_file("font.ttf")

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <filename>font.ttf</filename>
            <size>13</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)
        provider = self.init_provider()

        issues = provider.check_fonts()

        # Should detect missing name
        has_name_error = any("missing" in issue["message"].lower() and "name" in issue["message"].lower() for issue in issues)
        self.assertTrue(has_name_error, "Should detect missing font name")

    def test_cross_fontset_consistency(self):
        """Test detection of inconsistent font names across fontsets."""
        self.create_font_file("font.ttf")

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font13</name>
            <filename>font.ttf</filename>
            <size>13</size>
        </font>
        <font>
            <name>font16</name>
            <filename>font.ttf</filename>
            <size>16</size>
        </font>
    </fontset>
    <fontset id="Alternative">
        <font>
            <name>font13</name>
            <filename>font.ttf</filename>
            <size>13</size>
        </font>
        <!-- Missing font16 -->
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)
        provider = self.init_provider()

        issues = provider.check_fonts()

        # Should detect inconsistency
        has_consistency_error = any("missing font" in issue["message"].lower() and "compared to" in issue["message"].lower() for issue in issues)
        self.assertTrue(has_consistency_error, "Should detect cross-fontset inconsistency")

    def test_used_but_undefined_font(self):
        """Test detection of font used in window but not defined in Fonts.xml."""
        self.create_font_file("font.ttf")

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font13</name>
            <filename>font.ttf</filename>
            <size>13</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)

        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label">
            <font>UndefinedFont</font>
            <label>Test</label>
        </control>
    </controls>
</window>
"""
        self.create_window_xml(window_xml)

        provider = self.init_provider()
        issues = provider.check_fonts()

        # Should detect undefined font usage
        has_undefined_error = any("undefinedfont" in issue["message"].lower() and "not defined" in issue["message"].lower() for issue in issues)
        self.assertTrue(has_undefined_error, "Should detect used but undefined font")

    def test_defined_but_unused_font(self):
        """Test detection of font defined but never used."""
        self.create_font_file("font.ttf")

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font13</name>
            <filename>font.ttf</filename>
            <size>13</size>
        </font>
        <font>
            <name>UnusedFont</name>
            <filename>font.ttf</filename>
            <size>20</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)

        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label">
            <font>font13</font>
            <label>Test</label>
        </control>
    </controls>
</window>
"""
        self.create_window_xml(window_xml)

        provider = self.init_provider()
        issues = provider.check_fonts()

        # Should detect unused font
        has_unused_error = any("unusedfont" in issue["message"].lower() and "unused" in issue["message"].lower() for issue in issues)
        self.assertTrue(has_unused_error, "Should detect defined but unused font")

    def test_dynamic_param_values_ignored(self):
        """Test that $PARAM[...] values are correctly ignored in validation."""
        self.create_font_file("font.ttf")

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font13</name>
            <filename>$PARAM[fontfile]</filename>
            <size>$PARAM[fontsize]</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)
        provider = self.init_provider()

        issues = provider.check_fonts()

        # Should NOT flag missing file or invalid size for $PARAM values
        has_false_positive = any(
            "param[fontfile]" in issue["message"].lower() or
            "param[fontsize]" in issue["message"].lower()
            for issue in issues
        )
        self.assertFalse(has_false_positive, "Should ignore $PARAM[] in validation")

    def test_font13_not_flagged_as_unused(self):
        """Test that font13 is never flagged as unused (it's a required Kodi font)."""
        self.create_font_file("font.ttf")

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font13</name>
            <filename>font.ttf</filename>
            <size>13</size>
        </font>
        <font>
            <name>font16</name>
            <filename>font.ttf</filename>
            <size>16</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)

        # Create window that only uses font16, not font13
        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label">
            <font>font16</font>
            <label>Test</label>
        </control>
    </controls>
</window>
"""
        self.create_window_xml(window_xml)

        provider = self.init_provider()
        issues = provider.check_fonts()

        # font13 should NOT be flagged as unused (it's required by Kodi)
        font13_unused = any("font13" in issue["message"].lower() and "unused" in issue["message"].lower() for issue in issues)
        self.assertFalse(font13_unused, "font13 should not be flagged as unused (it's a required Kodi font)")


if __name__ == "__main__":
    unittest.main()
