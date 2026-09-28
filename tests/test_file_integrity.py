"""Unit tests for BOM and line-ending validation."""

import os
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.infoprovider.provider import InfoProvider

ADDON_XML = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test Skin" provider-name="Test">
    <requires>
        <import addon="xbmc.gui" version="5.15.0"/>
    </requires>
    <extension point="xbmc.gui.skin" debugging="false">
        <res width="1920" height="1080" aspect="16:9" default="true" folder="16x9" />
    </extension>
</addon>
"""

WINDOW_XML = '<?xml version="1.0" encoding="UTF-8"?>\n<window>\n    <controls/>\n</window>\n'


class TestFileIntegrity(unittest.TestCase):
    """Line endings and BOM, including files a runtime addon owns."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.skin_path = self.temp_dir.name
        self.xml_dir = os.path.join(self.skin_path, "16x9")
        os.makedirs(self.xml_dir, exist_ok=True)

        with open(os.path.join(self.skin_path, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(ADDON_XML)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write(self, name, text, *, crlf=False, bom=False):
        """Write `name` into the xml folder with the requested line endings and BOM."""
        data = text.replace("\n", "\r\n").encode() if crlf else text.encode()
        if bom:
            data = b"\xef\xbb\xbf" + data
        path = os.path.join(self.xml_dir, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def issues(self):
        provider = InfoProvider()
        provider.settings = {}
        provider.init_addon(self.skin_path)
        return provider.check_file_integrity()

    def test_sixteen_bit_png_in_packed_folders(self):
        """A 16-bit PNG that TexturePacker would pack is an error; elsewhere it is fine."""
        def png(depth):
            return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + b"\x00\x00\x00\x01" * 2 + bytes([depth, 6])
        for rel, depth in (("media/deep.png", 16), ("media/flat.png", 8), ("themes/dark/deep.png", 16),
                           ("extras/deep.png", 16)):
            path = os.path.join(self.skin_path, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(png(depth))
        rows = sorted(os.path.relpath(i["file"], self.skin_path) for i in self.issues() if "16-bit" in i["message"])
        self.assertEqual(rows, [os.path.join("media", "deep.png"), os.path.join("themes", "dark", "deep.png")])

    def test_bom_in_any_text_file(self):
        """A BOM is reported in strings.po and addon.xml, not only in window files."""
        lang = os.path.join(self.skin_path, "language", "resource.language.en_gb")
        os.makedirs(lang)
        with open(os.path.join(lang, "strings.po"), "wb") as f:
            f.write(b"\xef\xbb\xbfmsgid \"\"\n")
        with open(os.path.join(self.skin_path, "addon.xml"), "wb") as f:
            f.write(b"\xef\xbb\xbf" + ADDON_XML.encode())
        rows = sorted(os.path.basename(i["file"]) for i in self.issues() if "BOM" in i["message"])
        self.assertEqual(rows, ["addon.xml", "strings.po"])

    def test_crlf_reported(self):
        """A skin-authored file with Windows line endings is an error."""
        self.write("Home.xml", WINDOW_XML, crlf=True)

        issues = self.issues()

        self.assertTrue(
            any("Home.xml" in i["message"] and "Windows Line Endings" in i["message"] for i in issues),
            f"Should flag CRLF in a skin file, got: {issues}",
        )

    def test_bom_reported(self):
        """A skin-authored file with a BOM is an error."""
        self.write("Home.xml", WINDOW_XML, bom=True)

        issues = self.issues()

        self.assertTrue(
            any("Home.xml" in i["message"] and "BOM" in i["message"] for i in issues),
            f"Should flag a BOM in a skin file, got: {issues}",
        )

    def test_generated_shortcuts_file_is_checked_like_any_other(self):
        """Skins may ship it, and the Kodi repo reviews its line endings when they do."""
        self.write("script-skinshortcuts-includes.xml", WINDOW_XML, crlf=True)

        issues = self.issues()

        self.assertTrue(
            any("skinshortcuts" in i["message"] and "Windows Line Endings" in i["message"] for i in issues),
            f"Should flag CRLF in a shipped generated file, got: {issues}",
        )

    def test_unix_endings_raise_nothing(self):
        self.write("Home.xml", WINDOW_XML)

        self.assertEqual(self.issues(), [])


if __name__ == "__main__":
    unittest.main()
