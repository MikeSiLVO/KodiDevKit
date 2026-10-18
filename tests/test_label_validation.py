"""Tests for the label check's translation validation."""

import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.base import ValidationTestCase, LabelCheck
from libs.infoprovider.provider import InfoProvider


class TestLabelValidation(ValidationTestCase):
    """Test label translation validation."""

    def setUp(self):
        """Create a temporary skin for each test, with kodi_path set when a portable Kodi exists."""
        self.test_dir = tempfile.mkdtemp()
        self.provider = InfoProvider()

        portable_kodi = r"C:\Kodi - Piers"
        if os.path.exists(portable_kodi):
            self.provider.settings = {"kodi_path": portable_kodi}
        else:
            self.provider.settings = {}

        os.makedirs(os.path.join(self.test_dir, "16x9"))

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
        checker = LabelCheck(self.provider.addon, self.provider.get_po_files, validation_index=self.provider.get_validation_index())
        issues = checker.check()

        untranslated_issues = [i for i in issues if "not translated" in i.get("message", "").lower()]
        self.assertTrue(len(untranslated_issues) > 0, "Should detect untranslated label text")
        self.assertIn("Untranslated Button Text", untranslated_issues[0]["message"])

    def test_every_addon_type_id_read_as_an_addon_id(self):
        """An id of any add-on type, repository included, gets the add-on id message."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label" id="100">
            <label>screensaver.arctic.mirage</label>
        </control>
        <control type="label" id="101">
            <label>repository.xbmc.org</label>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = LabelCheck(self.provider.addon, self.provider.get_po_files, validation_index=self.provider.get_validation_index())
        messages = [i.get("message", "") for i in checker.check()]

        for addon_id in ("screensaver.arctic.mirage", "repository.xbmc.org"):
            self.assertIn(f"Possible addon ID: {addon_id}.", " ".join(messages))
        self.assertFalse([m for m in messages if "not translated" in m.lower()])

    def test_hex_color_passes_and_a_bare_info_asks_for_its_wrapper(self):
        """A hex color is not untranslated text; a bare info Kodi knows asks for its $INFO[]."""
        with open(os.path.join(self.test_dir, "16x9", "Home.xml"), "w", encoding="utf-8") as f:
            f.write('<window><controls><control type="label"><label>FF00ff00</label></control>'
                    '<control type="label"><label>Player.Title</label></control>'
                    '<control type="label"><label>Hello.World</label></control></controls></window>')
        self.provider.init_addon(self.test_dir)
        messages = sorted(i["message"] for i in self.provider.check_labels() if i.get("file"))
        self.assertEqual(len(messages), 2)
        self.assertIn("not translated: Hello.World", messages[0])
        self.assertTrue(messages[1].startswith("Possible missing $INFO[] wrapper: Player.Title."))

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
        checker = LabelCheck(self.provider.addon, self.provider.get_po_files, validation_index=self.provider.get_validation_index())
        issues = checker.check()

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
        checker = LabelCheck(self.provider.addon, self.provider.get_po_files, validation_index=self.provider.get_validation_index())
        issues = checker.check()

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
        checker = LabelCheck(self.provider.addon, self.provider.get_po_files, validation_index=self.provider.get_validation_index())
        issues = checker.check()

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
        checker = LabelCheck(self.provider.addon, self.provider.get_po_files, validation_index=self.provider.get_validation_index())
        issues = checker.check()

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
        checker = LabelCheck(self.provider.addon, self.provider.get_po_files, validation_index=self.provider.get_validation_index())
        issues = checker.check()

        untranslated_issues = [i for i in issues if "not translated" in i.get("message", "").lower() and "'X'" in i.get("message", "")]
        self.assertEqual(len(untranslated_issues), 0, "Should not report single-character labels as untranslated")

    def test_skinshortcuts_includes_ignored(self):
        """Test that script-skinshortcuts-includes.xml is ignored (user-entered labels)."""
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
        checker = LabelCheck(self.provider.addon, self.provider.get_po_files, validation_index=self.provider.get_validation_index())
        issues = checker.check()

        normal_issues = [i for i in issues if "Normal Untranslated" in i.get("message", "")]
        self.assertTrue(len(normal_issues) > 0, "Should flag untranslated labels in normal windows")

        skinshortcuts_issues = [i for i in issues if "User Entered Music Label" in i.get("message", "")]
        self.assertEqual(len(skinshortcuts_issues), 0, "Should ignore labels in script-skinshortcuts-includes.xml")

    def test_kodi_core_labels_recognized(self):
        """Test that Kodi core labels are recognized."""
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
        """A $LOCALIZE[] of a Kodi core label id is not reported as undefined."""
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
