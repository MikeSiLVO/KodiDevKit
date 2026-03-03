"""
Comprehensive expression parsing tests.

Consolidated from:
- test_number_expressions.py: $NUMBER[] expression parsing and validation
- test_contains_dynamic_expression.py: Dynamic expression detection

Test organization:
- $NUMBER[] Parsing: Extraction, validation, case-insensitive
- Dynamic Expression Detection: $VAR, $INFO, $PARAM detection
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
from libs import utils


# ============================================================================
# SECTION 1: $NUMBER[] PARSING
# Tests for $NUMBER[] expression extraction and validation
# ============================================================================

class TestNumberExpressions(unittest.TestCase):
    """Test $NUMBER[] expression handling."""

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

    def test_extract_number_value_valid(self):
        """Test extracting numeric value from valid $NUMBER[] expressions."""
        self.assertEqual(utils.extract_number_value("$NUMBER[25]"), "25")
        self.assertEqual(utils.extract_number_value("$NUMBER[100]"), "100")
        self.assertEqual(utils.extract_number_value("$NUMBER[0]"), "0")
        self.assertEqual(utils.extract_number_value("$number[50]"), "50")  # case insensitive

    def test_extract_number_value_invalid(self):
        """Test that invalid $NUMBER[] expressions return None."""
        self.assertIsNone(utils.extract_number_value("25"))  # not a $NUMBER expression
        self.assertIsNone(utils.extract_number_value("$NUMBER[abc]"))  # non-numeric
        self.assertIsNone(utils.extract_number_value("$NUMBER[]"))  # empty
        self.assertIsNone(utils.extract_number_value("$INFO[25]"))  # different expression
        self.assertIsNone(utils.extract_number_value(None))  # type: ignore[arg-type]

    def test_number_in_limit_attribute(self):
        """Test that $NUMBER[] in limit attribute validates correctly."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="list" id="100">
            <content limit="$NUMBER[25]">special://skin/playlists/movies.xsp</content>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(xml_content)

        issues = self.provider.check_file(xml_path)

        # Should NOT flag $NUMBER[25] as invalid integer
        integer_issues = [i for i in issues if "invalid integer value for limit" in i.get("message", "")]
        self.assertEqual(len(integer_issues), 0, "$NUMBER[25] should be valid integer expression")

    def test_number_in_id_attribute(self):
        """Test that $NUMBER[] in id attribute validates correctly."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="$NUMBER[500]">
            <label>Test</label>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(xml_content)

        issues = self.provider.check_file(xml_path)

        # Should NOT flag $NUMBER[500] as invalid integer
        integer_issues = [i for i in issues if "invalid integer" in i.get("message", "").lower() and "500" in i.get("message", "")]
        self.assertEqual(len(integer_issues), 0, "$NUMBER[500] should be valid for id attribute")

    def test_invalid_number_expression_flagged(self):
        """Test that $NUMBER[] with non-numeric content is flagged as error."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="list" id="100">
            <content limit="$NUMBER[invalid]">special://skin/playlists/movies.xsp</content>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(xml_content)

        issues = self.provider.check_file(xml_path)

        # SHOULD flag $NUMBER[invalid] as invalid integer
        integer_issues = [i for i in issues if "invalid integer value for limit" in i.get("message", "")]
        self.assertTrue(len(integer_issues) > 0, "$NUMBER[invalid] should be flagged as invalid")

    def test_regular_integers_still_work(self):
        """Test that regular integer values still validate normally."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="list" id="100">
            <content limit="25">special://skin/playlists/movies.xsp</content>
        </control>
        <control type="button" id="200">
            <label>Test</label>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(xml_content)

        issues = self.provider.check_file(xml_path)

        # Should NOT flag regular integers
        integer_issues = [i for i in issues if "invalid integer" in i.get("message", "").lower()]
        self.assertEqual(len(integer_issues), 0, "Regular integers should still validate correctly")

    def test_number_case_insensitive(self):
        """Test that $NUMBER[] is case-insensitive."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="list" id="100">
            <content limit="$number[25]">special://skin/playlists/movies.xsp</content>
        </control>
        <control type="list" id="101">
            <content limit="$Number[30]">special://skin/playlists/tvshows.xsp</content>
        </control>
        <control type="list" id="102">
            <content limit="$NUMBER[50]">special://skin/playlists/music.xsp</content>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(xml_content)

        issues = self.provider.check_file(xml_path)

        # Should NOT flag any case variations
        integer_issues = [i for i in issues if "invalid integer value for limit" in i.get("message", "")]
        self.assertEqual(len(integer_issues), 0, "$NUMBER[] should be case-insensitive")


# ============================================================================
# SECTION 2: DYNAMIC EXPRESSION DETECTION
# Tests for detecting $VAR, $INFO, $PARAM expressions
# ============================================================================

class TestContainsDynamicExpression(unittest.TestCase):
    """Test contains_dynamic_expression() function for embedded expressions."""

    def test_embedded_param_expression(self):
        """Test detection of embedded $PARAM[] in value."""
        self.assertTrue(utils.contains_dynamic_expression("800$PARAM[id]"))

    def test_embedded_var_expression(self):
        """Test detection of embedded $VAR[] in value."""
        self.assertTrue(utils.contains_dynamic_expression("prefix$VAR[MyVar]"))

    def test_embedded_info_expression(self):
        """Test detection of embedded $INFO[] in value."""
        self.assertTrue(utils.contains_dynamic_expression("text$INFO[Label]suffix"))

    def test_plain_value_no_expression(self):
        """Test that plain values without expressions return False."""
        self.assertFalse(utils.contains_dynamic_expression("normalvalue"))
        self.assertFalse(utils.contains_dynamic_expression("800"))
        self.assertFalse(utils.contains_dynamic_expression("plain123"))

    def test_full_expression_detected(self):
        """Test that full expressions starting with $ are detected."""
        self.assertTrue(utils.contains_dynamic_expression("$VAR[test]"))
        self.assertTrue(utils.contains_dynamic_expression("$PARAM[foo]"))
        self.assertTrue(utils.contains_dynamic_expression("$INFO[label]"))

    def test_case_insensitive_detection(self):
        """Test that expression detection is case-insensitive."""
        self.assertTrue(utils.contains_dynamic_expression("$var[test]"))
        self.assertTrue(utils.contains_dynamic_expression("$PARAM[test]"))
        self.assertTrue(utils.contains_dynamic_expression("800$param[id]"))

    def test_addon_expression_detected(self):
        """Test detection of $ADDON[] expressions."""
        self.assertTrue(utils.contains_dynamic_expression("test$ADDON[foo]"))

    def test_escvar_expression_detected(self):
        """Test detection of $ESCVAR[] expressions."""
        self.assertTrue(utils.contains_dynamic_expression("prefix$ESCVAR[test]"))

    def test_escinfo_expression_detected(self):
        """Test detection of $ESCINFO[] expressions."""
        self.assertTrue(utils.contains_dynamic_expression("text$ESCINFO[label]"))

    def test_empty_string(self):
        """Test that empty strings return False."""
        self.assertFalse(utils.contains_dynamic_expression(""))

    def test_none_value(self):
        """Test that None values return False."""
        self.assertFalse(utils.contains_dynamic_expression(None))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
