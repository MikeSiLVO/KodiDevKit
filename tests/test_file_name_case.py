"""Font.xml, and Includes.xml outside the default folder, must match the name Kodi opens."""

import os
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.infoprovider.provider import InfoProvider

ADDON_XML = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test" provider-name="Test">
    <requires><import addon="xbmc.gui" version="5.17.0"/></requires>
    <extension point="xbmc.gui.skin">{res}</extension>
</addon>
"""
DEFAULT_RES = '<res width="1920" height="1080" folder="16x9" default="true"/>'
FONTS_XML = """<fonts><fontset id="Default" unicode="true"><font><name>font13</name>
<filename>arial.ttf</filename><size>13</size></font></fontset></fonts>"""
INCLUDES_XML = """<includes><include name="Used"><control type="label"/></include></includes>"""
HOME_XML = """<window><controls><include>Used</include>
<control type="label"><font>font13</font></control></controls></window>"""


class TestFileNameCase(unittest.TestCase):
    """Errors for a miscased Font.xml, or Includes.xml outside the default folder; both load."""

    def setUp(self):
        """Set up a skin whose default 16x9 folder holds Home.xml, with its font file on disk."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.skin = self.temp_dir.name
        self.xml_dir = os.path.join(self.skin, "16x9")
        os.makedirs(os.path.join(self.skin, "fonts"))
        os.makedirs(self.xml_dir)
        open(os.path.join(self.skin, "fonts", "arial.ttf"), "wb").close()
        self._addon(DEFAULT_RES)
        with open(os.path.join(self.xml_dir, "Home.xml"), "w") as f:
            f.write(HOME_XML)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _addon(self, res):
        """Write the skin's addon.xml with those <res> elements in its skin extension."""
        with open(os.path.join(self.skin, "addon.xml"), "w") as f:
            f.write(ADDON_XML.format(res=res))

    def _write(self, name, content, folder="16x9"):
        """Write a file into an xml folder, 16x9 unless another is named."""
        with open(os.path.join(self.skin, folder, name), "w") as f:
            f.write(content)

    def _check(self, check_type):
        provider = InfoProvider()
        provider.settings = {}
        provider.init_addon(self.skin)
        return provider.get_check_listitems(check_type)

    def test_lowercase_font_xml_is_an_error(self):
        self._write("font.xml", FONTS_XML)
        self._write("Includes.xml", INCLUDES_XML)
        rows = self._check("font")
        named = [r for r in rows if "must be named Font.xml" in r["message"]]
        self.assertEqual(len(named), 1)
        self.assertEqual(named[0]["severity"], "error")
        self.assertFalse([r for r in rows if "not defined" in r["message"]])

    def test_lowercase_includes_xml_in_default_folder_passes(self):
        """A lowercase includes.xml in the default folder loads on Linux and is not reported."""
        self._write("Font.xml", FONTS_XML)
        self._write("includes.xml", INCLUDES_XML)
        rows = self._check("include")
        self.assertFalse([r for r in rows if "must be named" in r["message"]])
        self.assertFalse([r for r in rows if "not defined" in r["message"]])

    def test_lowercase_includes_xml_in_other_folder_is_an_error(self):
        """Outside the default folder, the error names the folder whose copy loads instead."""
        self._addon(DEFAULT_RES + '<res width="2560" height="1080" folder="21x9"/>')
        os.makedirs(os.path.join(self.skin, "21x9"))
        self._write("Font.xml", FONTS_XML)
        self._write("Includes.xml", INCLUDES_XML)
        self._write("Home.xml", HOME_XML, "21x9")
        self._write("includes.xml", INCLUDES_XML, "21x9")
        named = [r for r in self._check("include") if "must be named Includes.xml" in r["message"]]
        self.assertEqual(len(named), 1)
        self.assertEqual(named[0]["severity"], "error")
        self.assertIn("21x9", named[0]["file"])
        self.assertIn("the 16x9 folder's Includes.xml in its place", named[0]["message"])

    def test_lowercase_includes_xml_without_default_is_an_error(self):
        """With no default folder declared, a lowercase includes.xml does not load on Linux."""
        self._addon('<res width="1920" height="1080" folder="16x9"/>')
        self._write("Font.xml", FONTS_XML)
        self._write("includes.xml", INCLUDES_XML)
        named = [r for r in self._check("include") if "must be named Includes.xml" in r["message"]]
        self.assertEqual(len(named), 1)
        self.assertIn("Kodi does not load it on Linux", named[0]["message"])

    def test_renamed_file_is_seen_by_the_next_check(self):
        """Renaming includes.xml to Includes.xml clears the error on the next check."""
        self._addon('<res width="1920" height="1080" folder="16x9"/>')
        self._write("Font.xml", FONTS_XML)
        self._write("includes.xml", INCLUDES_XML)
        self.assertTrue([r for r in self._check("include") if "must be named" in r["message"]])
        os.rename(os.path.join(self.xml_dir, "includes.xml"), os.path.join(self.xml_dir, "Includes.xml"))
        # a rename inside one clock tick can leave the folder's mtime where it was
        os.utime(self.xml_dir, (1, 1))
        self.assertFalse([r for r in self._check("include") if "must be named" in r["message"]])

    def test_correct_names_pass(self):
        self._write("Font.xml", FONTS_XML)
        self._write("Includes.xml", INCLUDES_XML)
        for check_type in ("font", "include"):
            rows = self._check(check_type)
            self.assertFalse([r for r in rows if "must be named" in r["message"]])


if __name__ == "__main__":
    unittest.main()
