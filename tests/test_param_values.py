"""Param values reach a resolved tree as written, and are escaped only where text is re-parsed."""

import os
import sys
import tempfile
import unittest
from lxml import etree as ET

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.skin.skin import Skin
from libs.utils.expressions import resolve_params_in_text


class TestParamValues(unittest.TestCase):
    """Special characters in a param value survive resolution unchanged."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        path = self.temp_dir.name
        os.makedirs(os.path.join(path, "16x9"))
        with open(os.path.join(path, "addon.xml"), "w", encoding="utf-8") as f:
            f.write('<addon id="skin.test" version="1.0.0"><requires>'
                    '<import addon="xbmc.gui" version="5.17.0"/></requires>'
                    '<extension point="xbmc.gui.skin"><res folder="16x9" default="true"/>'
                    '</extension></addon>')
        with open(os.path.join(path, "16x9", "Includes.xml"), "w", encoding="utf-8") as f:
            f.write('<includes><include name="Lbl"><param name="t"/><definition>'
                    '<control type="label" description="$PARAM[t]"><label>$PARAM[t]</label>'
                    '</control></definition></include></includes>')
        self.skin = Skin(path=path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_resolved_text_and_attribute_keep_the_value(self):
        root = ET.fromstring('<window><controls><include content="Lbl">'
                             '<param name="t">Tom &amp; Jerry &lt;3</param></include></controls></window>')
        self.skin.resolver.resolve(root, "16x9")
        control = root.find(".//control")
        self.assertEqual(control.find("label").text, "Tom & Jerry <3")
        self.assertEqual(control.get("description"), "Tom & Jerry <3")

    def test_reparsed_text_is_escaped(self):
        text, _ = resolve_params_in_text("<label>$PARAM[t]</label>", {"t": "A & B"}, escape=True)
        self.assertEqual(ET.fromstring(text).text, "A & B")


if __name__ == "__main__":
    unittest.main()
