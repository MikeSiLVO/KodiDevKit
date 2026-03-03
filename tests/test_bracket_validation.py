"""
Tests for bracket validation in onclick and onback tags.
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


class TestBracketValidation(unittest.TestCase):
    """Test bracket validation for onclick and onback tags."""

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

        # Initialize provider
        self.provider.init_addon(self.test_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_onclick_with_unmatched_parenthesis(self):
        """Test detection of unmatched parenthesis in <onclick> tag."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <onclick>Control.IsVisible(100</onclick>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        issues = self.provider.check_file(xml_path)

        # Should detect unmatched bracket
        bracket_issues = [i for i in issues if "bracket" in i.get("message", "").lower()]
        self.assertTrue(len(bracket_issues) > 0, "Should detect unmatched bracket in onclick")
        self.assertIn("Control.IsVisible(100", bracket_issues[0]["message"])

    def test_onback_with_unmatched_bracket(self):
        """Test detection of unmatched bracket in <onback> tag."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <onback>SetProperty(foo,bar</onback>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        issues = self.provider.check_file(xml_path)

        # Should detect unmatched bracket
        bracket_issues = [i for i in issues if "bracket" in i.get("message", "").lower()]
        self.assertTrue(len(bracket_issues) > 0, "Should detect unmatched bracket in onback")
        self.assertIn("SetProperty(foo,bar", bracket_issues[0]["message"])

    def test_onclick_with_matched_brackets(self):
        """Test that properly matched brackets in onclick don't trigger issues."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <onclick>Control.IsVisible(100)</onclick>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        issues = self.provider.check_file(xml_path)

        # Should NOT detect bracket issues
        bracket_issues = [i for i in issues if "bracket" in i.get("message", "").lower()]
        self.assertEqual(len(bracket_issues), 0, "Should not report matched brackets")

    def test_onback_with_complex_nested_brackets(self):
        """Test validation of complex nested brackets in onback."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <onback>SetProperty(foo,String.IsEqual(bar,{test}))</onback>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        issues = self.provider.check_file(xml_path)

        # Should NOT detect bracket issues with properly nested brackets
        bracket_issues = [i for i in issues if "bracket" in i.get("message", "").lower()]
        self.assertEqual(len(bracket_issues), 0, "Should handle complex nested brackets correctly")

    def test_info_with_parentheses_and_prefix_postfix_ignored(self):
        """Test that $INFO expressions with parentheses and prefix/postfix are ignored."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label" id="100">
            <visible>$INFO[Window(Home).Property(SkinInfo.Movie.Year),(,)]</visible>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        issues = self.provider.check_file(xml_path)

        # Should NOT detect bracket issues - $INFO expressions are dynamic
        bracket_issues = [i for i in issues if "bracket" in i.get("message", "").lower()]
        self.assertEqual(len(bracket_issues), 0, "Should ignore parentheses in $INFO expressions")

    def test_var_with_complex_parameters_ignored(self):
        """Test that $VAR expressions with complex parameters are ignored."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <onclick>$VAR[CustomAction(param1,param2)]</onclick>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        issues = self.provider.check_file(xml_path)

        # Should NOT detect bracket issues - $VAR expressions are dynamic
        bracket_issues = [i for i in issues if "bracket" in i.get("message", "").lower()]
        self.assertEqual(len(bracket_issues), 0, "Should ignore parentheses in $VAR expressions")

    def test_addon_with_square_brackets_ignored(self):
        """Test that $ADDON expressions with square brackets are ignored."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label" id="100">
            <visible>$ADDON[script.some.addon 32001]</visible>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        issues = self.provider.check_file(xml_path)

        # Should NOT detect bracket issues - $ADDON expressions are dynamic
        bracket_issues = [i for i in issues if "bracket" in i.get("message", "").lower()]
        self.assertEqual(len(bracket_issues), 0, "Should ignore brackets in $ADDON expressions")

    def test_escinfo_with_unmatched_internal_parens_ignored(self):
        """Test that $ESCINFO expressions are properly ignored even with internal unmatched parens."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label" id="100">
            <visible>$ESCINFO[Window(10000).Property(test,(prefix,suffix)]</visible>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        issues = self.provider.check_file(xml_path)

        # Should NOT detect bracket issues - $ESCINFO expressions are dynamic
        bracket_issues = [i for i in issues if "bracket" in i.get("message", "").lower()]
        self.assertEqual(len(bracket_issues), 0, "Should ignore all content in $ESCINFO expressions")

    def test_onclick_setproperty_with_escinfo_label_formatting(self):
        """Test onclick with SetProperty containing $ESCINFO using label formatting [prefix],[suffix]."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <onclick>SetProperty(TextViewerSubHeader,$ESCINFO[Window(Home).Property(TMDbHelper.ListItem.Status,[LIGHT],[/LIGHT])],Home)</onclick>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        issues = self.provider.check_file(xml_path)

        # Should NOT detect bracket issues - all brackets are properly balanced
        bracket_issues = [i for i in issues if "bracket" in i.get("message", "").lower()]
        self.assertEqual(len(bracket_issues), 0, "Should accept properly balanced brackets in SetProperty with $ESCINFO and label formatting")

    def test_onclick_setproperty_with_escinfo_extra_closing_paren(self):
        """Test onclick with extra closing parenthesis is correctly flagged."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <onclick>SetProperty(TextViewerSubHeader,$ESCINFO[Window(Home).Property(TMDbHelper.ListItem.Status,[LIGHT],[/LIGHT])],Home))</onclick>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        issues = self.provider.check_file(xml_path)

        # SHOULD detect bracket mismatch - extra closing paren
        bracket_issues = [i for i in issues if "bracket" in i.get("message", "").lower()]
        self.assertEqual(len(bracket_issues), 1, "Should detect extra closing parenthesis")
        self.assertIn("do not match", bracket_issues[0]["message"])

    def test_onclick_setproperty_with_info_label_formatting(self):
        """Test onclick with SetProperty containing $INFO using label formatting [prefix],[suffix]."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <onclick>SetProperty(Status,$INFO[Window(Home).Property(Status,[BOLD],[/BOLD])],Home)</onclick>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        issues = self.provider.check_file(xml_path)

        # Should NOT detect bracket issues - all brackets are properly balanced
        bracket_issues = [i for i in issues if "bracket" in i.get("message", "").lower()]
        self.assertEqual(len(bracket_issues), 0, "Should accept properly balanced brackets in SetProperty with $INFO and label formatting")

    def test_onclick_setproperty_with_var_label_formatting(self):
        """Test onclick with SetProperty containing $VAR using label formatting [prefix],[suffix]."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <onclick>SetProperty(Title,$VAR[CustomTitle,[COLOR red],[/COLOR]],Home)</onclick>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        issues = self.provider.check_file(xml_path)

        # Should NOT detect bracket issues - all brackets are properly balanced
        bracket_issues = [i for i in issues if "bracket" in i.get("message", "").lower()]
        self.assertEqual(len(bracket_issues), 0, "Should accept properly balanced brackets in SetProperty with $VAR and label formatting")

    def test_label_with_escvar_label_formatting(self):
        """Test label with $ESCVAR using label formatting [prefix],[suffix]."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label" id="100">
            <label>$ESCVAR[CustomVariable,[B],[/B]]</label>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        issues = self.provider.check_file(xml_path)

        # Should NOT detect bracket issues - all brackets are properly balanced
        bracket_issues = [i for i in issues if "bracket" in i.get("message", "").lower()]
        self.assertEqual(len(bracket_issues), 0, "Should accept properly balanced brackets with $ESCVAR and label formatting")


if __name__ == "__main__":
    unittest.main()
