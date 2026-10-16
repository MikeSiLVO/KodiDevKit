"""Tests for resolution order, constants, $EXP, defaults and params."""

import os
import sys
import tempfile
import unittest
from lxml import etree as ET

# Add parent directory to path for imports
package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.skin.skin import Skin
from tests.test_utils import kodi_resolve


class TestKodiResolutionOrder(unittest.TestCase):
    """Resolution order: defaults, constants, $EXP, then includes."""

    def setUp(self):
        """Create temporary skin structure."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.skin_path = self.temp_dir.name

        os.makedirs(os.path.join(self.skin_path, "16x9"))
        addon_xml = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test" provider-name="Test">
    <requires><import addon="xbmc.gui" version="5.15.0"/></requires>
    <extension point="xbmc.gui.skin" debugging="false">
        <res width="1920" height="1080" aspect="16:9" default="true" folder="16x9" />
    </extension>
</addon>"""
        with open(os.path.join(self.skin_path, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(addon_xml)

        self.skin = Skin(path=self.skin_path)

    def tearDown(self):
        """Clean up temporary directory."""
        self.temp_dir.cleanup()

    def test_resolution_order_constants_before_includes(self):
        """Constants resolve before includes."""
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <constant name="ButtonWidth">200</constant>
    <include name="TestButton">
        <control type="button">
            <width>ButtonWidth</width>
        </control>
    </include>
</includes>"""
        includes_path = os.path.join(self.skin_path, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.skin.update_include_list()

        test_xml = """<window>
    <include>TestButton</include>
</window>"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin, root, "16x9")

        width_elem = root.find(".//width")
        self.assertIsNotNone(width_elem, "Width element should exist after resolution")
        self.assertEqual(width_elem.text, "200", "Constant should be resolved to '200'")


class TestConstantWhitelist(unittest.TestCase):
    """Constant expansion, limited to the listed tags and attributes."""

    def setUp(self):
        """Create temporary skin with constants."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.skin_path = self.temp_dir.name
        os.makedirs(os.path.join(self.skin_path, "16x9"))

        addon_xml = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test" provider-name="Test">
    <requires><import addon="xbmc.gui" version="5.15.0"/></requires>
    <extension point="xbmc.gui.skin" debugging="false">
        <res width="1920" height="1080" aspect="16:9" default="true" folder="16x9" />
    </extension>
</addon>"""
        with open(os.path.join(self.skin_path, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(addon_xml)

        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <constant name="TestValue">100</constant>
</includes>"""
        with open(os.path.join(self.skin_path, "16x9", "Includes.xml"), "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.skin = Skin(path=self.skin_path)
        self.skin.update_include_list()

    def tearDown(self):
        """Clean up."""
        self.temp_dir.cleanup()

    def test_constant_expands_in_whitelisted_attribute(self):
        """A bare constant name resolves in a listed attribute."""
        test_xml = """<control type="button" width="TestValue" />"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin, root, "16x9")

        self.assertEqual(root.attrib.get("width"), "100")

    def test_constant_expands_in_whitelisted_node(self):
        """A bare constant name resolves in a listed tag's text."""
        test_xml = """<control type="button">
    <width>TestValue</width>
</control>"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin, root, "16x9")

        width_elem = root.find("width")
        self.assertEqual(width_elem.text, "100")

    def test_constant_does_not_expand_in_non_whitelisted_attribute(self):
        """`id` is not in CONSTANT_ATTRIBUTES, so the bare name stays."""
        test_xml = """<control type="button" id="TestValue" />"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin, root, "16x9")

        self.assertEqual(root.attrib.get("id"), "TestValue")

    def test_constant_does_not_expand_in_non_whitelisted_node(self):
        """`label` is not in CONSTANT_NODES, so the bare name stays."""
        test_xml = """<control type="button">
    <label>TestValue</label>
</control>"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin, root, "16x9")

        label_elem = root.find("label")
        self.assertEqual(label_elem.text, "TestValue")


class TestExpressionWrapping(unittest.TestCase):
    """Expression resolution, each body wrapped in brackets."""

    def setUp(self):
        """Create temporary skin with expressions."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.skin_path = self.temp_dir.name
        os.makedirs(os.path.join(self.skin_path, "16x9"))

        addon_xml = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test" provider-name="Test">
    <requires><import addon="xbmc.gui" version="5.15.0"/></requires>
    <extension point="xbmc.gui.skin" debugging="false">
        <res width="1920" height="1080" aspect="16:9" default="true" folder="16x9" />
    </extension>
</addon>"""
        with open(os.path.join(self.skin_path, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(addon_xml)

        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <expression name="IsPlaying">Player.HasMedia</expression>
</includes>"""
        with open(os.path.join(self.skin_path, "16x9", "Includes.xml"), "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.skin = Skin(path=self.skin_path)
        self.skin.update_include_list()

    def tearDown(self):
        """Clean up."""
        self.temp_dir.cleanup()

    def test_expression_wrapped_in_brackets(self):
        """$EXP[name] is replaced with the expression wrapped in brackets."""
        test_xml = """<control type="button">
    <visible>$EXP[IsPlaying]</visible>
</control>"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin, root, "16x9")

        visible_elem = root.find("visible")
        self.assertEqual(visible_elem.text, "[Player.HasMedia]",
                        "Expression should be wrapped in brackets")


class TestControlDefaults(unittest.TestCase):
    """Control defaults by control type."""

    def setUp(self):
        """Create temporary skin with control defaults."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.skin_path = self.temp_dir.name
        os.makedirs(os.path.join(self.skin_path, "16x9"))

        addon_xml = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test" provider-name="Test">
    <requires><import addon="xbmc.gui" version="5.15.0"/></requires>
    <extension point="xbmc.gui.skin" debugging="false">
        <res width="1920" height="1080" aspect="16:9" default="true" folder="16x9" />
    </extension>
</addon>"""
        with open(os.path.join(self.skin_path, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(addon_xml)

        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <default type="button">
        <width>200</width>
        <height>50</height>
        <left>100</left>
        <top>100</top>
    </default>
    <constant name="BarHeight">40</constant>
    <default type="label">
        <height>BarHeight</height>
        <include>LabelFont</include>
    </default>
    <include name="LabelFont"><font>font12</font></include>
</includes>"""
        self.includes_path = os.path.join(self.skin_path, "16x9", "Includes.xml")
        with open(self.includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.skin = Skin(path=self.skin_path)
        self.skin.update_include_list()

    def tearDown(self):
        """Clean up."""
        self.temp_dir.cleanup()

    def test_defaults_applied_to_matching_control_type(self):
        """Defaults apply to controls of the matching type."""
        test_xml = """<control type="button">
    <label>Test</label>
</control>"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin, root, "16x9")

        self.assertIsNotNone(root.find("width"), "Width from default should be applied")
        self.assertEqual(root.find("width").text, "200")
        self.assertIsNotNone(root.find("height"), "Height from default should be applied")
        self.assertEqual(root.find("height").text, "50")

    def test_defaults_skip_position_when_posx_exists(self):
        """Horizontal position defaults are skipped when the control has posx."""
        test_xml = """<control type="button">
    <posx>500</posx>
    <label>Test</label>
</control>"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin, root, "16x9")

        self.assertIsNone(root.find("left"), "Left default should be skipped when posx exists")
        self.assertIsNotNone(root.find("top"), "Top default should still be applied")

    def test_defaults_skip_position_when_posy_exists(self):
        """Vertical position defaults are skipped when the control has posy."""
        test_xml = """<control type="button">
    <posy>300</posy>
    <label>Test</label>
</control>"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin, root, "16x9")

        self.assertIsNone(root.find("top"), "Top default should be skipped when posy exists")
        self.assertIsNotNone(root.find("left"), "Left default should still be applied")

    def test_each_control_gets_its_own_resolved_default(self):
        """Every label gets the default resolved, its include spliced, and its own call line."""
        root = ET.fromstring('<control type="group">\n<control type="label"/>\n<control type="label"/>\n</control>')

        kodi_resolve(self.skin, root, "16x9")

        for label in root.findall("control"):
            self.assertEqual(label.find("height").text, "40")
            self.assertEqual(label.find("font").text, "font12")
            self.assertEqual(label.find("height").get("_kdk_call_line"), str(label.sourceline))

    def test_default_follows_a_reloaded_constant(self):
        """The default follows a constant changed in Includes.xml once the skin reloads."""
        with open(self.includes_path, encoding="utf-8") as f:
            text = f.read()
        kodi_resolve(self.skin, ET.fromstring('<control type="label"/>'), "16x9")
        with open(self.includes_path, "w", encoding="utf-8") as f:
            f.write(text.replace(">40<", ">60<"))
        self.skin.update_include_list()

        root = ET.fromstring('<control type="label"/>')
        kodi_resolve(self.skin, root, "16x9")

        self.assertEqual(root.find("height").text, "60")


class TestParameterMerging(unittest.TestCase):
    """Call params merged over an include's defaults, and conditions they settle."""

    def setUp(self):
        """Create temporary skin with parameterized includes."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.skin_path = self.temp_dir.name
        os.makedirs(os.path.join(self.skin_path, "16x9"))

        addon_xml = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test" provider-name="Test">
    <requires><import addon="xbmc.gui" version="5.15.0"/></requires>
    <extension point="xbmc.gui.skin" debugging="false">
        <res width="1920" height="1080" aspect="16:9" default="true" folder="16x9" />
    </extension>
</addon>"""
        with open(os.path.join(self.skin_path, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(addon_xml)

        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="TestButton">
        <param name="width" default="200"/>
        <param name="label" default="DefaultLabel"/>
        <definition>
            <control type="button">
                <width>$PARAM[width]</width>
                <label>$PARAM[label]</label>
            </control>
        </definition>
    </include>
    <include name="Textured">
        <param name="texture" default="false"/>
        <definition>
            <include content="TextureTag" condition="Skin.HasSetting(x) + $PARAM[texture]"/>
        </definition>
    </include>
    <include name="TextureTag">
        <texture>box.png</texture>
    </include>
</includes>"""
        with open(os.path.join(self.skin_path, "16x9", "Includes.xml"), "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.skin = Skin(path=self.skin_path)
        self.skin.update_include_list()

    def tearDown(self):
        """Clean up."""
        self.temp_dir.cleanup()

    def test_call_site_params_override_defaults(self):
        """Call-site parameters should override default parameters."""
        test_xml = """<window>
    <include content="TestButton">
        <param name="width" value="300"/>
        <param name="label" value="CustomLabel"/>
    </include>
</window>"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin, root, "16x9")

        control = root.find(".//control")
        self.assertIsNotNone(control, "Control should exist after include resolution")

        width_elem = control.find("width")
        self.assertEqual(width_elem.text, "300", "Call-site width should override default")

        label_elem = control.find("label")
        self.assertEqual(label_elem.text, "CustomLabel", "Call-site label should override default")

    def test_default_params_used_when_not_overridden(self):
        """Default parameters should be used when not overridden at call-site."""
        test_xml = """<window>
    <include content="TestButton">
        <param name="width" value="300"/>
    </include>
</window>"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin, root, "16x9")

        control = root.find(".//control")

        width_elem = control.find("width")
        self.assertEqual(width_elem.text, "300", "Call-site width should be used")

        label_elem = control.find("label")
        self.assertEqual(label_elem.text, "DefaultLabel", "Default label should be used")

    def test_include_whose_condition_is_always_false_stays_out(self):
        """A condition a default param makes always false keeps its include out."""
        root = ET.fromstring('<control type="button"><include content="Textured"/>'
                             '<include content="Textured"><param name="texture" value="true"/>'
                             '</include></control>')

        kodi_resolve(self.skin, root, "16x9")

        self.assertEqual(len(root.findall("texture")), 1)


class TestNestedParameterizedFanout(unittest.TestCase):
    """Wrapper include calling one parameterized sub-include several times."""

    def setUp(self):
        """Create a skin whose wrapper include calls the panel include once per id."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.skin_path = self.temp_dir.name
        os.makedirs(os.path.join(self.skin_path, "16x9"))

        addon_xml = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test" provider-name="Test">
    <requires><import addon="xbmc.gui" version="5.15.0"/></requires>
    <extension point="xbmc.gui.skin" debugging="false">
        <res width="1920" height="1080" aspect="16:9" default="true" folder="16x9" />
    </extension>
</addon>"""
        with open(os.path.join(self.skin_path, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(addon_xml)

        instances = "\n".join(
            f'        <include content="Layout"><param name="id">{900_10 + n}</param></include>'
            for n in range(1, 12)
        )
        includes_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="Layout">
        <control type="panel" id="$PARAM[id]">
            <visible>Integer.IsGreater(Container($PARAM[id]).NumItems,0)</visible>
        </control>
    </include>
    <include name="Lists">
{instances}
    </include>
</includes>"""
        with open(os.path.join(self.skin_path, "16x9", "Includes.xml"), "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.skin = Skin(path=self.skin_path)
        self.skin.update_include_list()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_all_fanout_ids_resolved(self):
        """Every panel id the wrapper fans out to resolves, with no $PARAM left."""
        test_xml = """<window>
    <controls>
        <control type="group">
            <include condition="true">Lists</include>
        </control>
    </controls>
</window>"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin, root, "16x9")

        resolved_ids = {c.get("id") for c in root.iter("control") if c.get("id")}
        expected = {str(90010 + n) for n in range(1, 12)}
        self.assertEqual(
            expected, resolved_ids & expected,
            f"Every fan-out panel id must resolve. Missing: {sorted(expected - resolved_ids)}",
        )
        self.assertNotIn("$PARAM[id]", resolved_ids)


if __name__ == "__main__":
    unittest.main()
