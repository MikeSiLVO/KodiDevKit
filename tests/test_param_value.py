"""An include call param takes its value attribute before its text."""

import os
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.infoprovider.provider import InfoProvider
from libs.utils.xml import get_params
from lxml import etree as ET

ADDON_XML = ('<addon id="skin.test" version="1.0.0"><requires>'
             '<import addon="xbmc.gui" version="5.18.0"/></requires>'
             '<extension point="xbmc.gui.skin"><res folder="16x9" default="true"/></extension></addon>')


class TestGetParams(unittest.TestCase):
    """Attribute first, text second, first of a name kept."""

    def test_attribute_text_and_duplicates(self):
        node = ET.fromstring('<include content="X"><param name="a" value="attr">text</param>'
                             '<param name="b">text</param><param name="a" value="later"/>'
                             '<param value="nameless"/></include>')
        self.assertEqual(get_params(node, "value"), {"a": "attr", "b": "text"})


class TestValueAttributeInChecks(unittest.TestCase):
    """A param passed as value="..." reaches the include and id checks."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = self.temp_dir.name
        os.makedirs(os.path.join(self.path, "16x9"))
        self._write("addon.xml", ADDON_XML)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write(self, rel, text):
        with open(os.path.join(self.path, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def _rows(self, check_type):
        provider = InfoProvider()
        provider.settings = {}
        provider.init_addon(self.path)
        return [r["message"] for r in provider.get_check_listitems(check_type)]

    def test_include_named_by_value_attribute_is_used(self):
        self._write("16x9/Includes.xml",
                    '<includes><include name="Outer"><param name="inner"/><definition>'
                    '<include>$PARAM[inner]</include></definition></include>'
                    '<include name="Inner"><control type="label"/></include></includes>')
        self._write("16x9/Home.xml", '<window><controls><include content="Outer">'
                                     '<param name="inner" value="Inner"/></include></controls></window>')
        self.assertFalse([m for m in self._rows("include") if "Inner" in m])

    def test_default_named_include_is_used_by_plain_call(self):
        self._write("16x9/Includes.xml",
                    '<includes><include name="Outer"><param name="inner" default="Inner"/><definition>'
                    '<include>$PARAM[inner]</include></definition></include>'
                    '<include name="Inner"><control type="label"/></include>'
                    '<include name="Other"><control type="label"/></include></includes>')
        self._write("16x9/Home.xml", '<window><controls><include>Outer</include>'
                                     '<include content="Outer"><param name="inner" value="Other"/>'
                                     '</include></controls></window>')
        self.assertFalse([m for m in self._rows("include") if "Inner" in m or "Other" in m])

    def test_control_id_from_value_attribute_is_defined(self):
        self._write("16x9/Includes.xml",
                    '<includes><include name="Btn"><param name="id"/><definition>'
                    '<control type="button" id="$PARAM[id]"/></definition></include></includes>')
        self._write("16x9/Home.xml", '<window><controls><include content="Btn">'
                                     '<param name="id" value="500"/></include>'
                                     '<control type="button"><onclick>SetFocus(500)</onclick>'
                                     '</control></controls></window>')
        self.assertFalse([m for m in self._rows("id") if "500" in m])


if __name__ == "__main__":
    unittest.main()
