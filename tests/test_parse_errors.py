"""A window file that fails to parse is reported, not skipped."""

import os
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.infoprovider.provider import InfoProvider
from libs.utils import xml

ADDON_XML = ('<addon id="skin.test" version="1.0.0"><requires>'
             '<import addon="xbmc.gui" version="5.18.0"/></requires>'
             '<extension point="xbmc.gui.skin"><res folder="16x9" default="true"/></extension></addon>')


class TestParseErrors(unittest.TestCase):
    """XML Validation carries one error row per unparseable file."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = self.temp_dir.name
        os.makedirs(os.path.join(self.path, "16x9"))
        for rel, text in (("addon.xml", ADDON_XML), ("16x9/Includes.xml", "<includes/>"),
                          ("16x9/Home.xml", "<window><controls/></window>"),
                          ("16x9/MyVideoNav.xml", "<window>\n<controls>\n<label>a & b</label>\n</controls>\n</window>")):
            with open(os.path.join(self.path, rel), "w", encoding="utf-8") as f:
                f.write(text)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_broken_window_is_reported(self):
        provider = InfoProvider()
        provider.settings = {}
        provider.init_addon(self.path)
        rows = [r for r in provider.get_check_listitems("general") if r.get("message", "").startswith("XML parse")]
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["file"].endswith("MyVideoNav.xml"))
        self.assertEqual((rows[0]["line"], rows[0]["severity"]), (3, "error"))

    def test_nested_grouplist_keeps_the_real_error(self):
        path = os.path.join(self.path, "16x9", "Nested.xml")
        with open(path, "w", encoding="utf-8") as f:
            f.write('<window>\n<control type="grouplist">\n<control type="grouplist">\n'
                    '<onclick>a & b</onclick>\n</control>\n</control>\n</window>')
        self.assertIsNone(xml.get_root_from_file(path))
        self.assertEqual(xml.last_xml_errors[0]["line"], 4)

    def test_escape_message_names_the_character(self):
        path = os.path.join(self.path, "16x9", "Escape.xml")
        for text, expected in (("<v>a=1&b=2</v>", "Unescaped '&'"), ("<v>a & b</v>", "Unescaped '&'"),
                               ("<v>a&nbsp;b</v>", "Unknown entity '&nbsp;'"),
                               ("<v>a < b</v>", "Unescaped '<'"),
                               ('<c a="x<y"/>', "Unescaped '<' in an attribute"),
                               ('<c a="x"y"/>', "Broken attribute"),
                               ("<v>a]]>b</v>", "Unescaped ']]>'")):
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"<window>{text}</window>")
            self.assertIsNone(xml.get_root_from_file(path))
            self.assertTrue(xml.last_xml_errors[0]["message"].startswith(expected), text)


if __name__ == "__main__":
    unittest.main()
