"""
Tests for LabelCheck class (label translation validation).
"""

import os
import sys
import tempfile
import shutil
import unittest

# Ensure parent directory is in path (base.py does this too, but be explicit)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Now we can import from base and libs
from tests.base import ValidationTestCase, LabelCheck
from libs.infoprovider import InfoProvider


class TestLabelValidation(ValidationTestCase):
    """Test label translation validation."""

    def setUp(self):
        """Create temporary skin directory for each test."""
        self.test_dir = tempfile.mkdtemp()
        self.provider = InfoProvider()

        # Configure settings with portable Kodi path if it exists
        portable_kodi = r"C:\Kodi - Piers"
        if os.path.exists(portable_kodi):
            self.provider.settings = {"kodi_path": portable_kodi}
        else:
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

    def test_untranslated_label_detected(self):
        """Test detection of untranslated (hardcoded) label text."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <label>Untranslated Button Text</label>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = LabelCheck(self.provider.addon, self.provider.get_po_files)
        issues = checker.check()

        # Should detect untranslated label
        untranslated_issues = [i for i in issues if "not translated" in i.get("message", "").lower()]
        self.assertTrue(len(untranslated_issues) > 0, "Should detect untranslated label text")
        self.assertIn("Untranslated Button Text", untranslated_issues[0]["message"])

    def test_numeric_label_no_untranslated_warning(self):
        """Test that numeric labels don't trigger untranslated warnings."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <label>31001</label>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = LabelCheck(self.provider.addon, self.provider.get_po_files)
        issues = checker.check()

        # Should not report numeric label as untranslated
        untranslated_issues = [i for i in issues if "not translated" in i.get("message", "").lower()]
        self.assertEqual(len(untranslated_issues), 0, "Should not report numeric labels as untranslated")

    def test_localize_expression_no_untranslated_warning(self):
        """Test that $LOCALIZE expressions don't trigger untranslated warnings."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <label>$LOCALIZE[31001]</label>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = LabelCheck(self.provider.addon, self.provider.get_po_files)
        issues = checker.check()

        # Should not report $LOCALIZE as untranslated
        untranslated_issues = [i for i in issues if "not translated" in i.get("message", "").lower()]
        self.assertEqual(len(untranslated_issues), 0, "Should not report $LOCALIZE expressions as untranslated")

    def test_empty_label_ignored(self):
        """Test that empty labels are ignored."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <label></label>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = LabelCheck(self.provider.addon, self.provider.get_po_files)
        issues = checker.check()

        # Should not crash or report empty labels
        self.assertIsInstance(issues, list)

    def test_xml_filename_in_label_ignored(self):
        """Test that XML filenames in labels are not flagged as untranslated."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <label>SomeInclude.xml</label>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = LabelCheck(self.provider.addon, self.provider.get_po_files)
        issues = checker.check()

        # Should not report .xml files as untranslated
        untranslated_issues = [i for i in issues if "not translated" in i.get("message", "").lower()]
        self.assertEqual(len(untranslated_issues), 0, "Should not report .xml filenames as untranslated")

    def test_single_character_label_ignored(self):
        """Test that single-character labels are ignored."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <label>X</label>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = LabelCheck(self.provider.addon, self.provider.get_po_files)
        issues = checker.check()

        # Should not report single-character labels (per the > 1 length check in code)
        untranslated_issues = [i for i in issues if "not translated" in i.get("message", "").lower() and "'X'" in i.get("message", "")]
        self.assertEqual(len(untranslated_issues), 0, "Should not report single-character labels as untranslated")

    def test_skinshortcuts_includes_ignored(self):
        """Test that script-skinshortcuts-includes.xml is ignored (user-entered labels)."""
        # Create a normal window file with untranslated label (should be flagged)
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <label>Normal Untranslated</label>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        # Create script-skinshortcuts-includes.xml with untranslated labels (should be ignored)
        shortcuts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="skinshortcuts-template-music">
        <control type="button" id="200">
            <label>User Entered Music Label</label>
        </control>
    </include>
</includes>"""
        shortcuts_path = os.path.join(self.test_dir, "16x9", "script-skinshortcuts-includes.xml")
        with open(shortcuts_path, "w", encoding="utf-8") as f:
            f.write(shortcuts_xml)

        self.provider.init_addon(self.test_dir)
        checker = LabelCheck(self.provider.addon, self.provider.get_po_files)
        issues = checker.check()

        # Should flag the normal window's untranslated label
        normal_issues = [i for i in issues if "Normal Untranslated" in i.get("message", "")]
        self.assertTrue(len(normal_issues) > 0, "Should flag untranslated labels in normal windows")

        # Should NOT flag the script-skinshortcuts-includes.xml labels
        skinshortcuts_issues = [i for i in issues if "User Entered Music Label" in i.get("message", "")]
        self.assertEqual(len(skinshortcuts_issues), 0, "Should ignore labels in script-skinshortcuts-includes.xml")

    def test_kodi_core_labels_recognized(self):
        """Test that Kodi core labels are recognized."""
        # Skip if kodi_path is not configured (no core labels available)
        if not self.provider.settings.get("kodi_path"):
            self.skipTest("Kodi installation path not configured - cannot test core labels")

        core_labels_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label" id="1"><label>24998</label></control>
        <control type="label" id="2"><label>24004</label></control>
        <control type="label" id="3"><label>24043</label></control>
        <control type="label" id="4"><label>24996</label></control>
        <control type="label" id="5"><label>23054</label></control>
        <control type="label" id="6"><label>24001</label></control>
        <control type="label" id="7"><label>137</label></control>
        <control type="label" id="8"><label>849</label></control>
        <control type="label" id="9"><label>1000</label></control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Test.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(core_labels_xml)

        self.provider.init_addon(self.test_dir)
        issues = self.provider.check_labels()

        # Should NOT flag these as undefined - they are Kodi core labels
        undefined_issues = [
            i for i in issues
            if "not defined" in i.get("message", "").lower()
        ]

        undefined_label_ids = [i.get("name") for i in undefined_issues]
        core_label_ids = ["24998", "24004", "24043", "24996", "23054", "24001", "137", "849", "1000"]

        for label_id in core_label_ids:
            self.assertNotIn(
                label_id,
                undefined_label_ids,
                f"Core Kodi label {label_id} should not be flagged as undefined"
            )

    def test_localize_format_with_core_labels(self):
        """Test $LOCALIZE[] format with Kodi core labels"""
        # Skip if kodi_path is not configured (no core labels available)
        if not self.provider.settings.get("kodi_path"):
            self.skipTest("Kodi installation path not configured - cannot test core labels")

        localize_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label" id="1"><label>$LOCALIZE[137]</label></control>
        <control type="label" id="2"><label>$LOCALIZE[24998]</label></control>
        <control type="label" id="3"><label>$LOCALIZE[849]</label></control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Localize.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(localize_xml)

        self.provider.init_addon(self.test_dir)
        issues = self.provider.check_labels()

        # Should NOT flag these as undefined
        undefined_issues = [
            i for i in issues
            if "not defined" in i.get("message", "").lower()
        ]

        undefined_label_ids = [i.get("name") for i in undefined_issues]
        localize_label_ids = ["137", "24998", "849"]

        for label_id in localize_label_ids:
            self.assertNotIn(
                label_id,
                undefined_label_ids,
                f"$LOCALIZE[{label_id}] should not be flagged as undefined"
            )


if __name__ == "__main__":
    unittest.main()
