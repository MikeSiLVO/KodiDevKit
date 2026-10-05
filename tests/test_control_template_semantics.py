"""Tests for control tags and attributes Kodi consumes, checked against GUIControlFactory.cpp."""

import os
import shutil
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.infoprovider.provider import InfoProvider
from libs.validation.include import ValidationInclude as IncludeCheck


ADDON_XML = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test Skin" provider-name="test">
    <requires>
        <import addon="xbmc.gui" version="5.16.0"/>
    </requires>
    <extension point="xbmc.gui.skin" defaultthemename="Textures.xbt" debugging="false">
        <res width="1920" height="1080" aspect="16x9" default="true" folder="16x9" />
    </extension>
</addon>"""


class TestControlTemplateSemantics(unittest.TestCase):
    """Tags a control really uses must pass; tags it ignores must still warn."""

    def setUp(self):
        """Create a temporary skin with an empty Includes.xml."""
        self.test_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.test_dir, "16x9"))
        self._write("addon.xml", ADDON_XML)
        self._write("16x9/Includes.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<includes>\n</includes>')

    def tearDown(self):
        """Remove the temporary skin."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _write(self, rel, text):
        """Write a file under the temporary skin."""
        with open(os.path.join(self.test_dir, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def _issues(self, controls, release):
        """Check a Home.xml holding the controls against one Kodi release's data."""
        self._write(
            "16x9/Home.xml",
            '<?xml version="1.0" encoding="UTF-8"?>\n<window>\n<controls>\n' + controls + "\n</controls>\n</window>",
        )
        provider = InfoProvider()
        provider.settings = {}
        provider.load_data(release)
        provider.init_addon(self.test_dir)
        return provider.check_values()

    def _assert_clean(self, controls):
        """No issue for the controls under either release."""
        for release in ("omega", "piers"):
            with self.subTest(release=release):
                self.assertEqual(self._issues(controls, release), [])

    def test_grouplist_auto_width_enable_and_bottom_align(self):
        """Grouplist uses min/max width, the enable condition and bottom alignment."""
        self._assert_clean("""
<control type="grouplist">
    <width min="20" max="100">auto</width>
    <orientation>vertical</orientation>
    <align>bottom</align>
    <enable>false</enable>
</control>""")

    def test_auto_max_on_any_control(self):
        """Every control takes an auto size from max, so max is valid everywhere."""
        self._assert_clean("""
<control type="image">
    <width max="300">auto</width>
</control>
<control type="list">
    <height max="570">auto</height>
</control>""")

    def test_min_only_where_kodi_reads_it(self):
        """Only grouplist, label, buttons and textbox use min; elsewhere it still warns."""
        issues = self._issues("""
<control type="list">
    <height min="100" max="570">auto</height>
</control>
<control type="image">
    <width min="10">auto</width>
</control>
<control type="colorbutton">
    <colorwidth min="10">40</colorwidth>
</control>""", "piers")
        found = sorted(i["message"] for i in issues if "invalid attribute" in i["message"])
        self.assertEqual(found, ["invalid attribute for <colorwidth>: min",
                                 "invalid attribute for <height>: min",
                                 "invalid attribute for <width>: min"])

    def test_group_enable(self):
        """A disabled group cannot take focus, so enable is meaningful."""
        self._assert_clean("""
<control type="group">
    <enable>false</enable>
</control>""")

    def test_gamecontrollerlist_align(self):
        """Gamecontrollerlist takes the label alignment in its constructor."""
        self._assert_clean("""
<control type="gamecontrollerlist">
    <align>right</align>
</control>""")

    def test_allowhiddenfocus_condition(self):
        """allowhiddenfocus is parsed as an info bool, not a literal."""
        self._assert_clean("""
<control type="button">
    <visible allowhiddenfocus="!String.IsEmpty(VideoPlayer.DBID)">false</visible>
</control>""")

    def test_itemlayout_auto_width(self):
        """A non-numeric layout size falls back to the container size."""
        self._assert_clean("""
<control type="list">
    <itemlayout width="auto" height="64"></itemlayout>
    <focusedlayout width="auto" height="64"></focusedlayout>
</control>""")

    def test_texture_attributes_and_label_textwidth(self):
        """Every texture GetTexture reads takes its attributes; a label reads textwidth."""
        self._assert_clean("""
<control type="button">
    <texturefocus background="true" infill="false">a.png</texturefocus>
</control>
<control type="togglebutton">
    <alttexturenofocus background="true">a.png</alttexturenofocus>
</control>
<control type="radiobutton">
    <textureradioonfocus flipy="true">a.png</textureradioonfocus>
</control>
<control type="label">
    <textwidth>300</textwidth>
</control>""")

    def test_button_label_fallback_warns(self):
        """Buttons read their label through GetString, which ignores fallback."""
        issues = self._issues("""
<control type="button">
    <label fallback="424">$INFO[ListItem.Label]</label>
</control>""", "piers")
        self.assertTrue(any("invalid attribute for <label>: fallback" in i["message"] for i in issues), issues)

    def test_invalid_viewtype_lists_allowed_values(self):
        """An unknown viewtype is reported with the allowed values, not a case hint."""
        issues = self._issues("""
<control type="fixedlist">
    <viewtype>fixedlist</viewtype>
</control>""", "piers")
        viewtype = [i["message"] for i in issues if "viewtype" in i["message"]]
        self.assertTrue(viewtype, issues)
        self.assertIn("allowed:", viewtype[0])
        self.assertNotIn("lowercase", viewtype[0])


class TestIncludeDefinitionText(unittest.TestCase):
    """Stray text inside an include definition is not an include call."""

    def setUp(self):
        """Create a temporary skin whose include definition holds stray text."""
        self.test_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.test_dir, "16x9"))
        with open(os.path.join(self.test_dir, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(ADDON_XML)
        with open(os.path.join(self.test_dir, "16x9", "Includes.xml"), "w", encoding="utf-8") as f:
            f.write("""<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="Stray">
s        <definition>
            <control type="label"><label>x</label></control>
        </definition>
    </include>
</includes>""")
        with open(os.path.join(self.test_dir, "16x9", "Home.xml"), "w", encoding="utf-8") as f:
            f.write("""<?xml version="1.0" encoding="UTF-8"?>
<window><controls><include>Stray</include></controls></window>""")

    def tearDown(self):
        """Remove the temporary skin."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_stray_text_reported_where_it_sits(self):
        """Text beside the definition is reported once, on the line it sits on."""
        provider = InfoProvider()
        provider.settings = {}
        provider.load_data("piers")
        provider.init_addon(self.test_dir)
        issues = [i for i in provider.check_values() if "outside <definition>" in i["message"]]
        self.assertEqual(len(issues), 1, issues)
        self.assertEqual(issues[0]["line"], 4)
        self.assertIn("ignored: s", issues[0]["message"])

    def test_text_only_include_not_reported(self):
        """Without a definition the text is the include's body, spliced in as a value."""
        with open(os.path.join(self.test_dir, "16x9", "Includes.xml"), "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n<includes>\n'
                    '    <include name="Pad">20</include>\n</includes>')
        provider = InfoProvider()
        provider.settings = {}
        provider.load_data("piers")
        provider.init_addon(self.test_dir)
        self.assertEqual([i for i in provider.check_values() if "outside <definition>" in i["message"]], [])

    def test_stray_text_not_reported_as_undefined(self):
        """The definition's text must not show up as an undefined include."""
        provider = InfoProvider()
        provider.settings = {}
        provider.init_addon(self.test_dir)
        issues = IncludeCheck(provider.addon).check()
        self.assertEqual([i for i in issues if "not defined" in i.get("message", "")], [])


if __name__ == "__main__":
    unittest.main()
