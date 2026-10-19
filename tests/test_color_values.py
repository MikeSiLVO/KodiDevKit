"""Color attributes and tags: hex, a color name, or an info label Kodi reads the color from."""

import os
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.infoprovider.provider import InfoProvider

ADDON_XML = ('<addon id="skin.test" version="1.0.0"><requires><import addon="xbmc.gui" version="5.17.0"/>'
             '</requires><extension point="xbmc.gui.skin"><res folder="16x9" default="true"/></extension>'
             '</addon>')


class TestColorValues(unittest.TestCase):
    """Which color values the color check accepts, as written and once resolved."""

    def setUp(self):
        """Set up a skin with an empty Includes.xml."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = self.temp_dir.name
        os.makedirs(os.path.join(self.root, "16x9"))
        self.write("addon.xml", ADDON_XML)
        self.write("16x9/Includes.xml", "<includes/>")

    def tearDown(self):
        """Tear down the skin."""
        self.temp_dir.cleanup()

    def write(self, rel, text):
        """Write the text to the path under the skin."""
        with open(os.path.join(self.root, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def flagged(self, value):
        """Invalid-color rows for a progress midtexture with the value as its colordiffuse."""
        self.write("16x9/Home.xml", '<window><controls><control type="progress">'
                                    f'<midtexture colordiffuse="{value}">bar.png</midtexture>'
                                    '</control></controls></window>')
        provider = InfoProvider()
        provider.settings = {}
        provider.init_addon(self.root)
        rows = provider.check_file(os.path.join(self.root, "16x9", "Home.xml")) or []
        return [r for r in rows if r["rule"] == "xml.invalid-color"]

    def flagged_tag(self, text):
        """Invalid-color messages for the <textcolor> of a label."""
        self.write("16x9/Home.xml", '<window><controls><control type="label">'
                                    f'<textcolor>{text}</textcolor></control></controls></window>')
        provider = InfoProvider()
        provider.settings = {}
        provider.init_addon(self.root)
        rows = provider.check_file(os.path.join(self.root, "16x9", "Home.xml")) or []
        return [r["message"] for r in rows if r["rule"] == "xml.invalid-color"]

    def test_a_known_info_label_is_a_color(self):
        """A bare info label such as Skin.String(name) passes, as Kodi reads the color from it."""
        self.assertEqual(self.flagged("Skin.String(flat_back)"), [])

    def test_an_unknown_info_or_word_is_not(self):
        """A misspelled info and a plain word are both reported."""
        self.assertEqual(len(self.flagged("Skin.Strin(flat_back)")), 1)
        self.assertEqual(len(self.flagged("notacolor")), 1)

    def test_hex_still_passes(self):
        """An AARRGGBB hex value passes."""
        self.assertEqual(self.flagged("FF00FF00"), [])

    def test_tag_text(self):
        """Color tag text is checked too, leaving dynamic values and surrounding space alone."""
        self.assertEqual(self.flagged_tag("notacolor"), ["Invalid color for <textcolor>: notacolor"])
        for text in (" FF00FF00 ", "Skin.String(flat_back)", "$VAR[TextColor]", "$INFO[Skin.String(x)]"):
            self.assertEqual(self.flagged_tag(text), [], text)


if __name__ == "__main__":
    unittest.main()
