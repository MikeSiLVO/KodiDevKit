"""Tests for ImageCheck class (image reference validation)."""

import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.base import ValidationTestCase, ImageCheck
from libs.infoprovider.provider import InfoProvider


class TestImageValidation(ValidationTestCase):
    """Test image reference validation."""

    def setUp(self):
        """Create temporary skin directory for each test."""
        self.test_dir = tempfile.mkdtemp()
        self.provider = InfoProvider()
        self.provider.settings = {}

        os.makedirs(os.path.join(self.test_dir, "16x9"))
        os.makedirs(os.path.join(self.test_dir, "media"))

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

    def _build_checker(self):
        """Re-init addon, build index, return ImageCheck with index."""
        self.provider.init_addon(self.test_dir)
        index = self.provider.addon.index_builder.build_validation_index()
        return ImageCheck(self.provider.addon, validation_index=index)

    def test_missing_image_detected(self):
        """Test detection of missing image file."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="image">
            <texture>missing_image.png</texture>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        checker = self._build_checker()
        issues = checker.check()

        missing_issues = [i for i in issues if "missing" in i.get("message", "").lower()]
        self.assertTrue(len(missing_issues) > 0, "Should detect missing image file")

    def test_dash_and_noop_are_not_empty(self):
        """'-' and 'noop' as a texture get their own message, not a missing file."""
        with open(os.path.join(self.test_dir, "16x9", "Home.xml"), "w", encoding="utf-8") as f:
            f.write('<window><controls><control type="image"><texture>-</texture></control>'
                    '<control type="image"><texture>noop</texture></control></controls></window>')
        messages = sorted(i["message"] for i in self._build_checker().check() if i.get("file"))
        self.assertEqual(messages, ["'-' is not an empty texture in Kodi; leave the value empty",
                                    "'noop' is not an empty texture in Kodi; leave the value empty"])

    def test_file_outside_media_is_found_only_through_special_skin(self):
        """A file outside media/ is found through special://skin/; bare, it is a wrong path."""
        os.makedirs(os.path.join(self.test_dir, "backgrounds"))
        with open(os.path.join(self.test_dir, "backgrounds", "Default.jpg"), "wb") as f:
            f.write(b"jpg")
        with open(os.path.join(self.test_dir, "16x9", "Home.xml"), "w", encoding="utf-8") as f:
            f.write('<window><controls>'
                    '<control type="image"><texture>special://skin/backgrounds/Default.jpg</texture></control>'
                    '<control type="image"><texture>backgrounds/Default.jpg</texture></control>'
                    '</controls></window>')
        messages = [i["message"] for i in self._build_checker().check() if i.get("file")]
        self.assertEqual(messages, ["Wrong path 'backgrounds/Default.jpg': Kodi looks for "
                                    "media/backgrounds/Default.jpg, the file is at backgrounds/Default.jpg"])

    def test_existing_image_no_issue(self):
        """Test that existing images don't trigger issues."""
        img_path = os.path.join(self.test_dir, "media", "button.png")
        with open(img_path, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")  # Minimal PNG header

        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="image">
            <texture>button.png</texture>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        checker = self._build_checker()
        issues = checker.check()

        button_issues = [i for i in issues if "button.png" in i.get("message", "") and "missing" in i.get("message", "").lower()]
        self.assertEqual(len(button_issues), 0, "Should not report existing image as missing")

    def test_dynamic_image_reference_ignored(self):
        """Test that dynamic image references (with $INFO, $VAR, etc.) are ignored."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="image">
            <texture>$INFO[ListItem.Icon]</texture>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        checker = self._build_checker()
        issues = checker.check()

        dynamic_issues = [i for i in issues if "$INFO" in i.get("message", "")]
        self.assertEqual(len(dynamic_issues), 0, "Should ignore dynamic image references")

    def test_embedded_dynamic_expression_ignored(self):
        """Test that paths with embedded $INFO expressions are ignored."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="image">
            <texture>thumbs/case/portrait/$INFO[Container($PARAM[id]).ListItemAbsolute($PARAM[item]).VideoResolution]p.png</texture>
        </control>
        <control type="image">
            <texture>flags/$VAR[MediaFlagVar].png</texture>
        </control>
        <control type="image">
            <texture>posters/$ESCINFO[ListItem.Label]/poster.png</texture>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        checker = self._build_checker()
        issues = checker.check()

        missing_issues = [i for i in issues if "missing" in i.get("message", "").lower()]
        dynamic_paths = ["thumbs/case/portrait", "flags/", "posters/"]
        for issue in missing_issues:
            msg = issue.get("message", "")
            for path_part in dynamic_paths:
                self.assertNotIn(path_part, msg, f"Should ignore paths with embedded dynamic expressions: {msg}")

    def test_url_image_reference_ignored(self):
        """Test that URL-based image references are ignored."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="image">
            <texture>http://example.com/image.png</texture>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        checker = self._build_checker()
        issues = checker.check()

        url_issues = [i for i in issues if "http://example.com" in i.get("message", "")]
        self.assertEqual(len(url_issues), 0, "Should ignore URL-based image references")

    def test_empty_texture_ignored(self):
        """Test that empty texture tags are ignored."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="image">
            <texture></texture>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        checker = self._build_checker()
        issues = checker.check()

        self.assertIsInstance(issues, list)

    def test_case_mismatch_detected(self):
        """Test detection of case mismatch between reference and actual file."""
        img_path = os.path.join(self.test_dir, "media", "Button.png")
        with open(img_path, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")

        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="image">
            <texture>button.png</texture>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        checker = self._build_checker()
        issues = checker.check()

        case_issues = [i for i in issues if "case mismatch" in i.get("message", "").lower()]
        self.assertTrue(len(case_issues) > 0, "Should detect case mismatch in image filename")

    def test_case_mismatch_outside_the_bundle_is_an_error(self):
        """A case mismatch on a special://skin/ path is an error, on a bare path a warning."""
        os.makedirs(os.path.join(self.test_dir, "extras"), exist_ok=True)
        for rel in ("media/Button.png", "extras/Back.jpg"):
            with open(os.path.join(self.test_dir, rel), "wb") as f:
                f.write(b"\x89PNG\r\n\x1a\n")
        with open(os.path.join(self.test_dir, "16x9", "Home.xml"), "w", encoding="utf-8") as f:
            f.write('<window><controls><control type="image"><texture>button.png</texture></control>'
                    '<control type="image"><texture>special://skin/extras/back.jpg</texture></control>'
                    '</controls></window>')
        found = {(i["rule"], i["severity"]) for i in self._build_checker().check() if "ase mismatch" in i["message"]}
        self.assertEqual(found, {("images.case-mismatch", "warning"), ("images.unbundled-case-mismatch", "error")})

    def test_every_texture_tag_is_checked(self):
        """Images in button and progress textures are checked like a <texture>."""
        with open(os.path.join(self.test_dir, "16x9", "Home.xml"), "w", encoding="utf-8") as f:
            f.write('<window><controls><control type="button"><texturefocus>gone_focus.png</texturefocus>'
                    '</control><control type="progress"><midtexture>gone_mid.png</midtexture>'
                    '<texturebg>gone_bg.png</texturebg></control></controls></window>')
        found = sorted(i["subject"] for i in self._build_checker().check() if i["rule"] == "images.missing")
        self.assertEqual(found, ["gone_bg.png", "gone_focus.png", "gone_mid.png"])

    def test_special_skin_media_path_breaks_once_media_is_packed(self):
        """A special://skin/media/ path to a file on disk is an error that names the bare path."""
        with open(os.path.join(self.test_dir, "media", "Button.png"), "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")
        with open(os.path.join(self.test_dir, "16x9", "Home.xml"), "w", encoding="utf-8") as f:
            f.write('<window><controls><control type="image"><texture>special://skin/media/Button.png'
                    '</texture></control></controls></window>')
        found = [i for i in self._build_checker().check() if i["rule"] == "images.special-skin-media"]
        self.assertEqual([(i["severity"], i["message"].endswith("'Button.png'")) for i in found], [("error", True)])


if __name__ == "__main__":
    unittest.main()
