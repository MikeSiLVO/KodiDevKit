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
<include name="Press">
<param name="onclick"/>
<definition>
<control type="button">
<onclick>$PARAM[onclick]</onclick>
</control>
</definition>
</include>
<include name="Scroll">
<param name="jumpbar" default="true"/>
<param name="onright"/>
<definition>
<control type="scrollbar">
<onright condition="!$PARAM[jumpbar]">$PARAM[onright]</onright>
</control>
</definition>
</include>
<include name="Radio">
<param name="icon" default="off.png"/>
<definition>
<control type="radiobutton">
<textureradiooffdisabled colordiffuse="nocolor">$PARAM[icon]</textureradiooffdisabled>
</control>
</definition>
</include>
</includes>"""

WINDOW = """<window>
<controls>
<include content="Caption"><param name="speed" value="fast"/></include>
<control type="image"><visible>$EXP[Broken]</visible></control>
<control type="radiobutton"><include>SpinTextures</include></control>
<include content="Press"/>
<include content="Scroll"/>
<include content="Scroll"><param name="jumpbar" value="false"/></include>
<include content="Radio"/>
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

    def test_fault_that_depends_on_the_caller_names_the_windows(self):
        """A caller-dependent fault is one row naming its include and how many windows reach it."""
        rows = [r for r in self.rows if "<textureup>" in r[2]]
        self.assertEqual(rows, [("Includes.xml", 13, "invalid tag for <control type=radiobutton>: <textureup> "
                                                     "(include 'SpinTextures', in 2 windows)")])

    def test_empty_action_from_a_missing_param_is_reported_at_the_definition(self):
        """An action left empty because no call passes its param is one row at the definition."""
        rows = [r for r in self.rows if "<onclick>" in r[2]]
        self.assertEqual(rows, [("Includes.xml", 19, "<onclick> is empty where a call passes no onclick; "
                                                     "give the onclick param a default of noop "
                                                     "(include 'Press', in 2 windows)")])

    def test_empty_action_names_the_param_in_its_text(self):
        """An empty action names the $PARAM in its text and counts windows its condition allows."""
        rows = [r for r in self.rows if "<onright>" in r[2]]
        self.assertEqual(rows, [("Includes.xml", 28, "<onright> is empty where a call passes no onright; "
                                                     "give the onright param a default of noop "
                                                     "(include 'Scroll', in 2 windows)")])

    def test_literal_fault_beside_a_param_is_reported_once_at_its_line(self):
        """A literal fault on an element whose text a $PARAM fills is one row at the definition."""
        rows = [r for r in self.rows if "colordiffuse" in r[2]]
        self.assertEqual(rows, [("Includes.xml", 36, "Invalid color for colordiffuse: nocolor")])

    def test_param_fault_stays_at_each_call(self):
        """A fault in a $PARAM value keeps one row per call site."""
        rows = sorted((f, line) for f, line, m in self.rows if "scrollspeed" in m)
        self.assertEqual(rows, [("Home.xml", 3), ("MyVideoNav.xml", 3)])

    def test_expression_fault_reported_once_at_its_definition(self):
        """A broken expression gets one row at its own definition, none at its usages."""
        rows = [r for r in self.rows if "cannot parse" in r[2]]
        self.assertEqual([(f, line) for f, line, _ in rows], [("Includes.xml", 11)])


class TestEmptyIncludeCondition(unittest.TestCase):
    """An include call whose condition is empty once its params are filled."""

    def test_empty_condition_is_never_spliced(self):
        """A condition written empty is reported, one a param empties not; neither body splices."""
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = temp_dir.name
        os.makedirs(os.path.join(path, "16x9"))
        files = {"addon.xml": ADDON_XML,
                 "16x9/Includes.xml": '<includes><include name="Cond"><fadetime>5</fadetime></include>'
                                      '<include name="Wrap"><definition>'
                                      '<include content="Cond" condition="$PARAM[c]"/></definition></include>'
                                      '</includes>',
                 "16x9/Home.xml": '<window><controls><control type="label"><label>x</label>'
                                  '<include content="Wrap"/><include condition="">Cond</include></control>'
                                  '</controls></window>'}
        for rel, text in files.items():
            with open(os.path.join(path, rel), "w", encoding="utf-8") as f:
                f.write(text)
        provider = InfoProvider()
        provider.settings = {}
        provider.load_data("piers")
        provider.init_addon(path)
        rows = sorted((os.path.basename(r["file"]), r["rule"], r["message"]) for r in provider.check_values()
                      if r["rule"] in ("xml.empty-condition", "xml.invalid-tag"))
        self.assertEqual(rows, [("Home.xml", "xml.empty-condition",
                                 "Include call 'Cond' has an empty condition, so Kodi never splices it")])


class TestIncludeCycles(unittest.TestCase):
    """An include that reaches itself, which Kodi expands without end."""

    def test_cycles(self):
        """Each loop is reported once; a loop a param condition or a false one ends is not."""
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = temp_dir.name
        os.makedirs(os.path.join(path, "16x9"))
        includes = ('<includes><include name="Self"><include>Self</include></include>'
                    '<include name="Ping"><include>Pong</include></include>'
                    '<include name="Pong"><include>Ping</include></include>'
                    '<include name="Tree"><include content="Tree" condition="$PARAM[deeper]"/></include>'
                    '<include name="Off"><include condition="false">Off</include></include></includes>')
        files = {"addon.xml": ADDON_XML, "16x9/Includes.xml": includes,
                 "16x9/Home.xml": '<window><controls><control type="group"><include>Self</include>'
                                  '<include>Ping</include><include>Tree</include><include>Off</include>'
                                  '</control></controls></window>'}
        for rel, text in files.items():
            with open(os.path.join(path, rel), "w", encoding="utf-8") as f:
                f.write(text)
        provider = InfoProvider()
        provider.settings = {}
        provider.init_addon(path)
        self.assertEqual(sorted(r["subject"] for r in provider.check_includes() if r["rule"] == "includes.cycle"),
                         ["Ping > Pong > Ping", "Self > Self"])


class TestPaddedNames(unittest.TestCase):
    """An include or constant name with spaces around it, which Kodi looks up as written."""

    def test_padded_include_and_constant(self):
        """A padded include call finds nothing, its include unused; a padded constant reads 0."""
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = temp_dir.name
        os.makedirs(os.path.join(path, "16x9"))
        files = {"addon.xml": ADDON_XML,
                 "16x9/Includes.xml": '<includes><constant name="W">40</constant>'
                                      '<include name="Btn"><width>W</width></include></includes>',
                 "16x9/Home.xml": '<window><controls><control type="label"><include> Btn </include>'
                                  '<height>\n\tW\n</height><label>x</label></control></controls></window>'}
        for rel, text in files.items():
            with open(os.path.join(path, rel), "w", encoding="utf-8") as f:
                f.write(text)
        provider = InfoProvider()
        provider.settings = {}
        provider.load_data("piers")
        provider.init_addon(path)
        rows = sorted((r["rule"], r["subject"]) for r in provider.check_includes() + provider.check_values()
                      if r["rule"].startswith(("includes.", "xml.undefined-constant")))
        self.assertEqual(rows, [("includes.undefined", "Btn"), ("includes.unused", "Btn"),
                                ("xml.undefined-constant", "W")])


if __name__ == "__main__":
    unittest.main()
