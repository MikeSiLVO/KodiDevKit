"""Faults written inside an include or an expression are reported once, where they are written."""

import os
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.infoprovider.provider import InfoProvider

ADDON_XML = ('<addon id="skin.test" version="1.0.0"><requires>'
             '<import addon="xbmc.gui" version="5.18.0"/></requires>'
             '<extension point="xbmc.gui.skin"><res folder="16x9" default="true"/></extension></addon>')

INCLUDES = """<includes>
<include name="Caption">
<param name="speed">200</param>
<definition>
<control type="label">
<fadetime>200</fadetime>
<scrollspeed>$PARAM[speed]</scrollspeed>
</control>
</definition>
</include>
<expression name="Broken">Player.HasVideo |</expression>
<include name="SpinTextures">
<textureup>up.png</textureup>
</include>
</includes>"""

WINDOW = """<window>
<controls>
<include content="Caption"><param name="speed" value="fast"/></include>
<control type="image"><visible>$EXP[Broken]</visible></control>
<control type="radiobutton"><include>SpinTextures</include></control>
</controls>
</window>"""


class TestIncludeFaults(unittest.TestCase):
    """XML Validation rows for faults that live in shared definitions."""

    def setUp(self):
        """Set up a two-window skin on shared includes and collect its XML Validation rows."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = self.temp_dir.name
        os.makedirs(os.path.join(self.path, "16x9"))
        files = {"addon.xml": ADDON_XML, "16x9/Includes.xml": INCLUDES,
                 "16x9/Home.xml": WINDOW, "16x9/MyVideoNav.xml": WINDOW}
        for rel, text in files.items():
            with open(os.path.join(self.path, rel), "w", encoding="utf-8") as f:
                f.write(text)
        provider = InfoProvider()
        provider.settings = {}
        provider.load_data("piers")
        provider.init_addon(self.path)
        self.rows = [(os.path.basename(r["file"]), r["line"], r["message"]) for r in provider.check_values()]

    def tearDown(self):
        """Tear down the temporary skin."""
        self.temp_dir.cleanup()

    def test_include_fault_reported_once_at_its_line(self):
        """An include fault outside any $PARAM gets one row at its own line."""
        rows = [r for r in self.rows if "<fadetime>" in r[2]]
        self.assertEqual(rows, [("Includes.xml", 6, "invalid tag for <control type=label>: <fadetime>")])

    def test_fault_that_depends_on_the_caller_names_the_calls(self):
        """A caller-dependent fault gets one row naming the include and its call count."""
        rows = [r for r in self.rows if "<textureup>" in r[2]]
        self.assertEqual(rows, [("Includes.xml", 13, "invalid tag for <control type=radiobutton>: <textureup> "
                                                     "(include 'SpinTextures', 2 calls)")])

    def test_param_fault_stays_at_each_call(self):
        """A fault in a $PARAM value keeps one row per call site."""
        rows = sorted((f, line) for f, line, m in self.rows if "scrollspeed" in m)
        self.assertEqual(rows, [("Home.xml", 3), ("MyVideoNav.xml", 3)])

    def test_expression_fault_reported_once_at_its_definition(self):
        """A broken expression gets one row at its own definition, none at its usages."""
        rows = [r for r in self.rows if "cannot parse" in r[2]]
        self.assertEqual([(f, line) for f, line, _ in rows], [("Includes.xml", 11)])


if __name__ == "__main__":
    unittest.main()
