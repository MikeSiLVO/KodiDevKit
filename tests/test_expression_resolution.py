"""$EXP resolution matches CGUIIncludes::ResolveExpressions: listed tag text, else the condition."""

import os
import sys
import tempfile
import unittest
from lxml import etree as ET

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.skin.skin import Skin
from tests.test_utils import kodi_resolve


class TestExpressionResolution(unittest.TestCase):
    """A listed tag with text keeps its condition attribute unresolved, as in Kodi."""

    def setUp(self):
        """Create a temporary skin with three expressions, one named with parentheses."""
        self.temp_dir = tempfile.TemporaryDirectory()
        path = self.temp_dir.name
        os.makedirs(os.path.join(path, "16x9"))
        with open(os.path.join(path, "addon.xml"), "w", encoding="utf-8") as f:
            f.write('<addon id="skin.test" version="1.0.0"><requires>'
                    '<import addon="xbmc.gui" version="5.17.0"/></requires>'
                    '<extension point="xbmc.gui.skin"><res folder="16x9" default="true"/>'
                    '</extension></addon>')
        with open(os.path.join(path, "16x9", "Includes.xml"), "w", encoding="utf-8") as f:
            f.write('<includes><expression name="A">Player.HasMedia</expression>'
                    '<expression name="B">Player.Paused</expression>'
                    '<expression name="Window.Next(all)">Window.Next(home)</expression></includes>')
        self.skin = Skin(path=path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _resolve(self, xml):
        root = ET.fromstring(xml)
        kodi_resolve(self.skin, root, "16x9")
        return root

    def test_listed_tag_text_resolves_and_condition_stays(self):
        root = self._resolve('<control><visible condition="$EXP[B]">$EXP[A]</visible></control>')
        node = root.find("visible")
        self.assertEqual(node.text, "[Player.HasMedia]")
        self.assertEqual(node.get("condition"), "$EXP[B]")

    def test_condition_resolves_without_listed_text(self):
        root = self._resolve('<control><include condition="$EXP[B]">X</include></control>')
        self.assertEqual(root.find("include").get("condition"), "[Player.Paused]")

    def test_name_runs_to_the_matching_bracket(self):
        """A name holding parentheses or dots resolves, read up to the bracket that closes it."""
        root = self._resolve('<control><visible>$EXP[Window.Next(all)] + $EXP[A]</visible></control>')
        self.assertEqual(root.find("visible").text, "[Window.Next(home)] + [Player.HasMedia]")

    def test_keyword_is_case_sensitive(self):
        """Only the upper-case keyword is replaced; `$exp[A]` stays as written."""
        root = self._resolve('<control><visible>$exp[A]</visible></control>')
        self.assertEqual(root.find("visible").text, "$exp[A]")


if __name__ == "__main__":
    unittest.main()
