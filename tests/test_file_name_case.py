"""Font.xml and Includes.xml must match the name Kodi opens, case included."""

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
    <extension point="xbmc.gui.skin"><res width="1920" height="1080" folder="16x9" default="true"/></extension>
</addon>
"""
FONTS_XML = """<fonts><fontset id="Default" unicode="true"><font><name>font13</name>
<filename>arial.ttf</filename><size>13</size></font></fontset></fonts>"""
INCLUDES_XML = """<includes><include name="Used"><control type="label"/></include></includes>"""
HOME_XML = """<window><controls><include>Used</include>
<control type="label"><font>font13</font></control></controls></window>"""


class TestFileNameCase(unittest.TestCase):
    """A wrongly cased Font.xml or Includes.xml is an error, and the file is still read."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.skin = self.temp_dir.name
        self.xml_dir = os.path.join(self.skin, "16x9")
        os.makedirs(os.path.join(self.skin, "fonts"))
        os.makedirs(self.xml_dir)
        open(os.path.join(self.skin, "fonts", "arial.ttf"), "wb").close()
        with open(os.path.join(self.skin, "addon.xml"), "w") as f:
            f.write(ADDON_XML)
        with open(os.path.join(self.xml_dir, "Home.xml"), "w") as f:
            f.write(HOME_XML)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write(self, name, content):
        with open(os.path.join(self.xml_dir, name), "w") as f:
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

    def test_lowercase_includes_xml_is_an_error(self):
        self._write("Font.xml", FONTS_XML)
        self._write("includes.xml", INCLUDES_XML)
        rows = self._check("include")
        named = [r for r in rows if "must be named Includes.xml" in r["message"]]
        self.assertEqual(len(named), 1)
        self.assertEqual(named[0]["severity"], "error")
        self.assertFalse([r for r in rows if "not defined" in r["message"]])

    def test_renamed_file_is_seen_by_the_next_check(self):
        """Renaming includes.xml to Includes.xml clears the error on the next check."""
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
