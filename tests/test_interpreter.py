"""Tests for XmlInterpreter — structural walk and provenance tracking."""

import unittest
from lxml import etree as ET

from libs.validation.interpreter import XmlInterpreter
from libs.validation.constants import SEVERITY_WARNING, SEVERITY_ERROR


def _parse(xml_str: str):
    """Parse XML string into lxml root element."""
    return ET.fromstring(xml_str.encode("utf-8"))


class TestWindowStructure(unittest.TestCase):
    """Test window-level structural validation."""

    def test_valid_window(self):
        root = _parse("""
        <window>
            <defaultcontrol>100</defaultcontrol>
            <backgroundcolor>FF000000</backgroundcolor>
            <controls>
                <control type="group">
                    <posx>0</posx>
                </control>
            </controls>
        </window>
        """)
        interp = XmlInterpreter()
        issues = interp.interpret(root)
        # No structural issues in a well-formed window
        structural = [i for i in issues if i["severity"] == SEVERITY_WARNING]
        self.assertEqual(structural, [])

    def test_invalid_window_child(self):
        root = _parse("""
        <window>
            <bogustag>value</bogustag>
            <controls></controls>
        </window>
        """)
        interp = XmlInterpreter()
        issues = interp.interpret(root)
        warnings = [i for i in issues if i["severity"] == SEVERITY_WARNING]
        self.assertEqual(len(warnings), 1)
        self.assertIn("bogustag", warnings[0]["message"])

    def test_controls_rejects_non_control(self):
        root = _parse("""
        <window>
            <controls>
                <label>text</label>
            </controls>
        </window>
        """)
        interp = XmlInterpreter()
        issues = interp.interpret(root)
        warnings = [i for i in issues if i["severity"] == SEVERITY_WARNING]
        self.assertEqual(len(warnings), 1)
        self.assertIn("label", warnings[0]["message"])


class TestGroupControl(unittest.TestCase):
    """Test group control recursion."""

    def test_group_recurses_into_children(self):
        """Group controls should recurse and validate child controls."""
        root = _parse("""
        <window>
            <controls>
                <control type="group">
                    <control type="label">
                        <label>Test</label>
                    </control>
                </control>
            </controls>
        </window>
        """)
        # Provide template_attribs so child validation runs
        attribs = {
            "group": {"posx": {}, "posy": {}, "control": {}, "label": {}},
            "label": {"label": {}, "posx": {}, "posy": {}},
        }
        values = {"group": {}, "label": {}}
        interp = XmlInterpreter(template_attribs=attribs, template_values=values)
        issues = interp.interpret(root)
        # No issues — label inside group is valid
        self.assertEqual(len(issues), 0)


class TestContainerStructure(unittest.TestCase):
    """Test container + layout validation."""

    def test_valid_list_with_layouts(self):
        root = _parse("""
        <window>
            <controls>
                <control type="list">
                    <itemlayout>
                        <control type="label">
                            <label>Item</label>
                        </control>
                    </itemlayout>
                    <focusedlayout>
                        <control type="label">
                            <label>Focused</label>
                        </control>
                    </focusedlayout>
                </control>
            </controls>
        </window>
        """)
        attribs = {
            "list": {"itemlayout": {}, "focusedlayout": {}, "content": {}},
            "label": {"label": {}},
        }
        values = {"list": {}, "label": {}}
        interp = XmlInterpreter(template_attribs=attribs, template_values=values)
        issues = interp.interpret(root)
        self.assertEqual(len(issues), 0)

    def test_epg_layout_on_non_epg_container(self):
        """EPG-only layout tags should warn on a regular list."""
        root = _parse("""
        <window>
            <controls>
                <control type="list">
                    <channellayout>
                        <control type="label"><label>Ch</label></control>
                    </channellayout>
                </control>
            </controls>
        </window>
        """)
        attribs = {"list": {}, "label": {"label": {}}}
        values = {"list": {}, "label": {}}
        interp = XmlInterpreter(template_attribs=attribs, template_values=values)
        issues = interp.interpret(root)
        warnings = [i for i in issues if i["severity"] == SEVERITY_WARNING]
        self.assertTrue(any("channellayout" in w["message"] for w in warnings))

    def test_layout_rejects_non_control(self):
        root = _parse("""
        <window>
            <controls>
                <control type="list">
                    <itemlayout>
                        <label>Wrong</label>
                    </itemlayout>
                </control>
            </controls>
        </window>
        """)
        attribs = {"list": {"itemlayout": {}}, "label": {}}
        values = {"list": {}, "label": {}}
        interp = XmlInterpreter(template_attribs=attribs, template_values=values)
        issues = interp.interpret(root)
        warnings = [i for i in issues if i["severity"] == SEVERITY_WARNING]
        self.assertTrue(any("label" in w["message"] and "itemlayout" in w["message"] for w in warnings))


class TestContentValidation(unittest.TestCase):
    """Test <content> child validation."""

    def test_valid_content(self):
        root = _parse("""
        <window>
            <controls>
                <control type="list">
                    <content>
                        <item><label>One</label></item>
                        <item><label>Two</label></item>
                    </content>
                </control>
            </controls>
        </window>
        """)
        attribs = {"list": {"content": {}}}
        values = {"list": {}}
        interp = XmlInterpreter(template_attribs=attribs, template_values=values)
        issues = interp.interpret(root)
        self.assertEqual(len(issues), 0)

    def test_invalid_content_child(self):
        root = _parse("""
        <window>
            <controls>
                <control type="list">
                    <content>
                        <label>Wrong</label>
                    </content>
                </control>
            </controls>
        </window>
        """)
        attribs = {"list": {"content": {}}}
        values = {"list": {}}
        interp = XmlInterpreter(template_attribs=attribs, template_values=values)
        issues = interp.interpret(root)
        warnings = [i for i in issues if i["severity"] == SEVERITY_WARNING]
        self.assertTrue(any("label" in w["message"] and "content" in w["message"] for w in warnings))


class TestIncludesFile(unittest.TestCase):
    """Test <includes> root validation."""

    def test_valid_includes(self):
        root = _parse("""
        <includes>
            <include name="Test"><label>hi</label></include>
            <constant name="Gap">10</constant>
            <variable name="Color"><value>FF000000</value></variable>
            <expression name="IsHome">Window.IsVisible(Home)</expression>
            <default type="button"><width>100</width></default>
        </includes>
        """)
        interp = XmlInterpreter()
        issues = interp.interpret(root)
        self.assertEqual(len(issues), 0)

    def test_invalid_includes_child(self):
        root = _parse("""
        <includes>
            <control type="button"><label>Wrong</label></control>
        </includes>
        """)
        interp = XmlInterpreter()
        issues = interp.interpret(root)
        warnings = [i for i in issues if i["severity"] == SEVERITY_WARNING]
        self.assertEqual(len(warnings), 1)
        self.assertIn("control", warnings[0]["message"])

    def test_variable_only_value_children(self):
        root = _parse("""
        <includes>
            <variable name="Test">
                <value>one</value>
                <label>wrong</label>
            </variable>
        </includes>
        """)
        interp = XmlInterpreter()
        issues = interp.interpret(root)
        warnings = [i for i in issues if i["severity"] == SEVERITY_WARNING]
        self.assertEqual(len(warnings), 1)
        self.assertIn("label", warnings[0]["message"])


class TestFontsFile(unittest.TestCase):
    """Test <fonts> file validation."""

    def test_valid_fonts(self):
        root = _parse("""
        <fonts>
            <fontset id="Default">
                <font>
                    <name>font13</name>
                    <filename>arial.ttf</filename>
                    <size>20</size>
                </font>
            </fontset>
        </fonts>
        """)
        interp = XmlInterpreter()
        issues = interp.interpret(root)
        self.assertEqual(len(issues), 0)

    def test_invalid_fonts_child(self):
        root = _parse("""
        <fonts>
            <font><name>wrong</name></font>
        </fonts>
        """)
        interp = XmlInterpreter()
        issues = interp.interpret(root)
        warnings = [i for i in issues if i["severity"] == SEVERITY_WARNING]
        self.assertTrue(any("font" in w["message"] for w in warnings))

    def test_invalid_font_child(self):
        root = _parse("""
        <fonts>
            <fontset id="Default">
                <font>
                    <name>font13</name>
                    <bogus>value</bogus>
                </font>
            </fontset>
        </fonts>
        """)
        interp = XmlInterpreter()
        issues = interp.interpret(root)
        warnings = [i for i in issues if i["severity"] == SEVERITY_WARNING]
        self.assertTrue(any("bogus" in w["message"] for w in warnings))


class TestProvenance(unittest.TestCase):
    """Test that provenance attributes are read correctly for issue reporting."""

    def test_stamped_node_reports_call_line(self):
        """Nodes with _kdk_call_line should report that line, not sourceline."""
        root = _parse("""
        <window>
            <controls>
                <bogus _kdk_call_line="42" _kdk_inc_name="MyInclude">text</bogus>
            </controls>
        </window>
        """)
        interp = XmlInterpreter()
        issues = interp.interpret(root)
        warnings = [i for i in issues if i["severity"] == SEVERITY_WARNING]
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["line"], 42)
        self.assertIn("MyInclude", warnings[0]["message"])

    def test_unstamped_node_reports_sourceline(self):
        """Nodes without provenance attributes use their own sourceline."""
        root = _parse("""
        <window>
            <bogus>text</bogus>
        </window>
        """)
        interp = XmlInterpreter()
        issues = interp.interpret(root)
        warnings = [i for i in issues if i["severity"] == SEVERITY_WARNING]
        self.assertEqual(len(warnings), 1)
        # sourceline is whatever lxml assigns (non-zero)
        self.assertGreater(warnings[0]["line"], 0)


class TestControlChildValidation(unittest.TestCase):
    """Test per-control tag/attribute/value checks on resolved tree."""

    def test_invalid_tag_for_control(self):
        attribs = {"button": {"label": {}, "posx": {}, "onclick": {}}}
        values = {"button": {}}
        root = _parse("""
        <window>
            <controls>
                <control type="button">
                    <label>OK</label>
                    <fakechild>bad</fakechild>
                </control>
            </controls>
        </window>
        """)
        interp = XmlInterpreter(template_attribs=attribs, template_values=values)
        issues = interp.interpret(root)
        warnings = [i for i in issues if i["severity"] == SEVERITY_WARNING]
        self.assertTrue(any("fakechild" in w["message"] for w in warnings))

    def test_noop_check(self):
        attribs = {"button": {"onclick": {}}}
        values = {"button": {}}
        root = _parse("""
        <window>
            <controls>
                <control type="button">
                    <onclick></onclick>
                </control>
            </controls>
        </window>
        """)
        interp = XmlInterpreter(template_attribs=attribs, template_values=values)
        issues = interp.interpret(root)
        errors = [i for i in issues if i["severity"] == SEVERITY_ERROR]
        self.assertTrue(any("noop" in i["message"] for i in errors))

    def test_bracket_mismatch(self):
        attribs = {"button": {"visible": {}}}
        values = {"button": {}}
        root = _parse("""
        <window>
            <controls>
                <control type="button">
                    <visible>Control.IsVisible(100</visible>
                </control>
            </controls>
        </window>
        """)
        interp = XmlInterpreter(template_attribs=attribs, template_values=values)
        issues = interp.interpret(root)
        errors = [i for i in issues if i["severity"] == SEVERITY_ERROR]
        self.assertTrue(any("Brackets" in e["message"] for e in errors))

    def test_empty_condition(self):
        attribs = {"button": {"visible": {}}}
        values = {"button": {}}
        root = _parse("""
        <window>
            <controls>
                <control type="button">
                    <visible></visible>
                </control>
            </controls>
        </window>
        """)
        interp = XmlInterpreter(template_attribs=attribs, template_values=values)
        issues = interp.interpret(root)
        errors = [i for i in issues if i["severity"] == SEVERITY_ERROR]
        self.assertTrue(any("Empty condition" in e["message"] for e in errors))

    def test_singleton_enforcement(self):
        attribs = {"button": {"enable": {}}}
        values = {"button": {}}
        root = _parse("""
        <window>
            <controls>
                <control type="button">
                    <enable>true</enable>
                    <enable>false</enable>
                </control>
            </controls>
        </window>
        """)
        interp = XmlInterpreter(template_attribs=attribs, template_values=values)
        issues = interp.interpret(root)
        warnings = [i for i in issues if i["severity"] == SEVERITY_WARNING]
        self.assertTrue(any("multiple" in w["message"].lower() for w in warnings))


class TestUnknownRoot(unittest.TestCase):
    """Unknown root tags should produce no issues."""

    def test_unknown_root_no_issues(self):
        root = _parse("<textures><texture>img.png</texture></textures>")
        interp = XmlInterpreter()
        issues = interp.interpret(root)
        self.assertEqual(len(issues), 0)


class TestNoneRoot(unittest.TestCase):
    def test_none_returns_empty(self):
        interp = XmlInterpreter()
        self.assertEqual(interp.interpret(None), [])


if __name__ == "__main__":
    unittest.main()
