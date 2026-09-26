"""Definitions load in Load_Internal's order, with its first-wins and last-wins rules."""

import os
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.skin.skin import Skin

ADDON_XML = ('<addon id="skin.test" version="1.0.0"><requires>'
             '<import addon="xbmc.gui" version="5.18.0"/></requires>'
             '<extension point="xbmc.gui.skin"><res folder="16x9" default="true"/></extension></addon>')


class _SkinCase(unittest.TestCase):
    """A throwaway skin with an Includes.xml and an optional nested include file."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = self.temp_dir.name
        os.makedirs(os.path.join(self.path, "16x9"))
        with open(os.path.join(self.path, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(ADDON_XML)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _skin(self, includes, nested=""):
        with open(os.path.join(self.path, "16x9", "Includes.xml"), "w", encoding="utf-8") as f:
            f.write(f"<includes>{includes}</includes>")
        if nested:
            with open(os.path.join(self.path, "16x9", "Nested.xml"), "w", encoding="utf-8") as f:
                f.write(f"<includes>{nested}</includes>")
        return Skin(path=self.path)

    def _shadowed(self, skin, kind):
        return [d for d in skin.shadowed_defs["16x9"] if d["kind"] == kind]


class TestLoadOrder(_SkinCase):
    """Which of two same-named definitions Kodi keeps, and that the other is recorded."""

    def test_first_variable_wins_in_one_file(self):
        skin = self._skin('<variable name="V"><value>first</value></variable>'
                          '<variable name="V"><value>second</value></variable>')
        node, _ = skin.variable_map["16x9"]["V"]
        self.assertEqual(node.find("value").text, "first")
        self.assertEqual(len(self._shadowed(skin, "variable")), 1)

    def test_parent_variable_beats_nested_file(self):
        skin = self._skin('<include file="Nested.xml"/><variable name="V"><value>parent</value></variable>',
                          '<variable name="V"><value>nested</value></variable>')
        node, _ = skin.variable_map["16x9"]["V"]
        self.assertEqual(node.find("value").text, "parent")
        self.assertTrue(self._shadowed(skin, "variable")[0]["file"].endswith("Nested.xml"))

    def test_includes_follow_document_order(self):
        skin = self._skin('<include file="Nested.xml"/><include name="I"><control type="label"/></include>',
                          '<include name="I"><control type="image"/></include>')
        _, _, source = skin.include_map["16x9"]["I"]
        self.assertTrue(source.endswith("Nested.xml"))
        self.assertTrue(self._shadowed(skin, "include")[0]["file"].endswith("Includes.xml"))

    def test_parent_map_beats_nested_map(self):
        skin = self._skin('<include file="Nested.xml"/><map name="M"><entry key="a">parent</entry></map>',
                          '<map name="M"><entry key="a">nested</entry></map>')
        node, _ = skin.map_map["16x9"]["M"]
        self.assertEqual(node.find("entry").text, "parent")

    def test_include_with_params_and_no_definition_is_dropped(self):
        skin = self._skin('<include name="Bad"><param name="p">1</param><control type="label"/></include>')
        self.assertNotIn("Bad", skin.include_map["16x9"])
        self.assertEqual(len(self._shadowed(skin, "include without definition")), 1)


class TestShadowedReports(_SkinCase):
    """Definitions Kodi drops are reported, pointing at the one it keeps."""

    def _rows(self, check_type):
        from libs.infoprovider.provider import InfoProvider
        provider = InfoProvider()
        provider.settings = {}
        provider.init_addon(self.path)
        return [r["message"] for r in provider.get_check_listitems(check_type)]

    def _window(self, body):
        with open(os.path.join(self.path, "16x9", "Home.xml"), "w", encoding="utf-8") as f:
            f.write(f"<window><controls>{body}</controls></window>")

    def test_duplicate_include_names_the_kept_one(self):
        self._skin('<include name="I"><control type="label"/></include>'
                   '<include name="I"><control type="image"/></include>')
        self._window("<include>I</include>")
        rows = [m for m in self._rows("include") if "Duplicate include" in m]
        self.assertEqual(rows, ["Duplicate include 'I': Kodi uses the first definition (Includes.xml:1)"])

    def test_include_without_definition_is_reported(self):
        self._skin('<include name="Bad"><param name="p">1</param><control type="label"/></include>')
        self._window("")
        self.assertIn("Include 'Bad' has <param> but no <definition>, so Kodi ignores it",
                      self._rows("include"))

    def test_conditional_override_is_not_a_duplicate(self):
        self._skin('<include file="Nested.xml" condition="Skin.HasSetting(Big)"/>'
                   '<constant name="W">100</constant>',
                   '<constant name="W">200</constant>')
        self._window('<control type="label"><width>W</width></control>')
        self.assertFalse([m for m in self._rows("include") if "Duplicate" in m])

    def test_duplicate_variable_is_reported(self):
        self._skin('<variable name="V"><value>a</value></variable>'
                   '<variable name="V"><value>b</value></variable>')
        self._window('<control type="label"><label>$VAR[V]</label></control>')
        self.assertTrue(any(m.startswith("Duplicate variable 'V'") for m in self._rows("variable")))


if __name__ == "__main__":
    unittest.main()
