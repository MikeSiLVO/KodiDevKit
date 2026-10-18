"""Tests for XmlInterpreter's structural walk and provenance tracking."""

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
        """A well-formed window gets no structural warnings."""
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
        # template_attribs given so child validation runs
        attribs = {
            "group": {"posx": {}, "posy": {}, "control": {}, "label": {}},
            "label": {"label": {}, "posx": {}, "posy": {}},
        }
        values = {"group": {}, "label": {}}
        interp = XmlInterpreter(template_attribs=attribs, template_values=values)
        issues = interp.interpret(root)
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
                        <default always="true">1</default>
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


class TestDefaultControl(unittest.TestCase):
    """<defaultcontrol> must point at a control that can take focus."""

    def _messages(self, window):
        attribs = {t: {"defaultcontrol": {}} for t in ("button", "label", "image", "group", "list")}
        values = {t: {} for t in attribs}
        interp = XmlInterpreter(template_attribs=attribs, template_values=values)
        return [i["message"] for i in interp.interpret(_parse(window)) if "defaultcontrol" in i["message"]]

    def test_unfocusable_targets(self):
        self.assertEqual(self._messages("""
        <window>
            <defaultcontrol>10</defaultcontrol>
            <controls>
                <control type="label" id="10"/>
                <control type="group" id="20">
                    <defaultcontrol>21</defaultcontrol>
                    <control type="group" id="21"><control type="image"/></control>
                </control>
            </controls>
        </window>"""), ["defaultcontrol 10 is a label, which can never take focus",
                        "defaultcontrol 21 is a group with no control that can take focus"])

    def test_focusable_targets(self):
        self.assertEqual(self._messages("""
        <window>
            <defaultcontrol>10</defaultcontrol>
            <controls>
                <control type="group"><defaultcontrol>5</defaultcontrol><control type="grouplist" id="5"/></control>
                <control type="label" id="10"/>
                <control type="button" id="10"/>
                <control type="group" id="20">
                    <defaultcontrol>50</defaultcontrol>
                    <control type="list" id="50">
                        <itemlayout><control type="label" id="60"/></itemlayout>
                    </control>
                </control>
            </controls>
        </window>"""), [])

class TestLabelBrackets(unittest.TestCase):
    """A label block without its ']' is reported with what Kodi does about it."""

    def test_label_blocks(self):
        attribs = {"label": {"label": {}, "label2": {}, "hinttext": {}}}
        values = {"label": {}}
        interp = XmlInterpreter(template_attribs=attribs, template_values=values)
        issues = interp.interpret(_parse("""
        <window>
            <controls>
                <control type="label">
                    <label>$INFO[ListItem.Label,[B],[/B]] $VAR[Name]</label>
                    <label2>$INFO[ListItem.Label2</label2>
                    <hinttext>$LOCALIZE[31000 more</hinttext>
                </control>
            </controls>
        </window>"""))
        self.assertEqual([i["message"] for i in issues], [
            "Missing ']' after $INFO[ in <label2>: Kodi drops the rest of the label",
            "Missing ']' after $LOCALIZE[ in <hinttext>: Kodi shows it as plain text",
        ])

    def test_variable_value(self):
        interp = XmlInterpreter(template_attribs={}, template_values={})
        issues = interp.interpret(_parse(
            '<includes><variable name="V"><value>$ESCINFO[Player.Title</value></variable></includes>'))
        self.assertEqual([i["message"] for i in issues],
                         ["Missing ']' after $ESCINFO[ in <value>: Kodi drops the rest of the label"])

class TestBoolAttributes(unittest.TestCase):
    """Bool attributes follow the spelling each Kodi reader accepts."""

    def test_attribute_spellings(self):
        attribs = {"image": {"texture": {"flipx": "bool", "infill": "bool", "background": "bool"},
                             "autoscroll": {"reverse": "bool"}}}
        interp = XmlInterpreter(template_attribs=attribs, template_values={"image": {}})
        issues = interp.interpret(_parse("""
        <window>
            <controls>
                <control type="image">
                    <texture flipx="yes" infill="no" background="true">a.png</texture>
                    <autoscroll reverse="false">true</autoscroll>
                </control>
            </controls>
        </window>"""))
        self.assertEqual(sorted(i["message"] for i in issues), [
            'flipx="yes" is off: Kodi turns it on only for "true"',
            'infill="no" is on: Kodi turns it off only for "false"',
            'reverse="false" still reverses: Kodi turns it on whenever the attribute is present',
        ])

class TestNumberFields(unittest.TestCase):
    """A name left in a number field is an undefined constant or a field Kodi never substitutes."""

    def _messages(self, runtime=False):
        attribs = {"label": {t: {} for t in ("width", "itemgap", "bordersize", "centerleft", "scroll")}}
        values = {"label": {t: "int" for t in ("width", "itemgap", "bordersize", "centerleft", "scroll")}}
        interp = XmlInterpreter(template_attribs=attribs, template_values=values, runtime_generator=runtime)
        return sorted((i["severity"], i["message"]) for i in interp.interpret(_parse("""
        <window><controls><control type="label">
            <width>MainWidth</width><itemgap>100%</itemgap><bordersize>12,0,12,0</bordersize>
            <centerleft>50%</centerleft><scroll>Gap</scroll>
        </control></controls></window>""")))

    def test_names(self):
        self.assertEqual(self._messages(), [
            ("error", "<scroll> value Gap: Kodi does not substitute constants in <scroll>"),
            ("error", "<width> value MainWidth is not a number or a defined constant"),
        ])

    def test_runtime_generator_softens_undefined(self):
        self.assertIn(("warning", "<width> value MainWidth is not a defined constant, unless a runtime "
                                  "generator adds it"), self._messages(runtime=True))

class TestDefaultType(unittest.TestCase):
    """A default is matched by its exact type string."""

    def test_mixed_case_type(self):
        interp = XmlInterpreter(template_attribs={"label": {}}, template_values={"label": {}})
        issues = interp.interpret(_parse('<includes><default type="Label"/><default type="label"/></includes>'))
        self.assertEqual([i["message"] for i in issues],
                         ['<default type="Label"> applies only to controls written type="Label"; Kodi matches it exactly'])

class TestControlNesting(unittest.TestCase):
    """Only groups hold child controls, and control types are written lowercase."""

    def test_nested_and_case(self):
        interp = XmlInterpreter(template_attribs={t: {} for t in ("button", "group", "label")},
                                template_values={t: {} for t in ("button", "group", "label")})
        issues = interp.interpret(_parse("""
        <window><controls>
            <control type="button"><control type="label"/></control>
            <control type="group"><control type="Label"/></control>
            <control type="group"><control type="$PARAM[ListType]"/></control>
        </controls></window>"""))
        self.assertEqual(sorted(i["message"] for i in issues), [
            "<control> inside <control type=button> is ignored; only groups hold controls",
            'type="Label" should be lowercase; Kodi accepts it, but a <default> only matches the exact string',
        ])

class TestConditions(unittest.TestCase):
    """Conditions Kodi cannot parse, or whose operand has no info, always read false."""

    NAMES = {"categories": {"window": {"isvisible"}, "player": {"hasvideo"}}, "listitem_aliases": set(),
             "platforms": set(), "players": {}}

    def messages(self, xml, runtime_generator=False):
        interp = XmlInterpreter(template_attribs={"button": {"visible": {}}, "label": {}},
                                template_values={"button": {}, "label": {}}, info_names=self.NAMES,
                                runtime_generator=runtime_generator)
        return sorted(i["message"] for i in interp.interpret(_parse(xml)) if "reads false" in i["message"]
                      or "runtime generator" in i["message"])

    def test_tag_the_control_ignores(self):
        self.assertEqual(self.messages(
            '<window><controls><control type="label"><selected>Player.HasVidoe</selected></control>'
            '</controls></window>'), [])

    def test_expression_from_runtime_generator(self):
        xml = '<window><controls><control type="button"><visible>$EXP[gen]</visible></control></controls></window>'
        self.assertEqual(self.messages(xml, runtime_generator=True),
                         ["Condition uses an unknown expression gen, unless a runtime generator defines it: $EXP[gen]"])
        self.assertEqual(self.messages(xml), [
            "Kodi cannot parse this condition (unknown expression gen), it always reads false: $EXP[gen]"])

    def test_window_conditions(self):
        self.assertEqual(self.messages("""
        <window><controls>
            <control type="button"><visible>!Window.IsVisble(1114) + Player.HasVideo</visible></control>
            <control type="button"><visible>Player.HasVideo +</visible></control>
            <control type="button"><visible>$PARAM[x]</visible></control>
        </controls></window>"""), [
            "Kodi cannot parse this condition (missing operand), it always reads false: Player.HasVideo +",
            "Kodi has no info 'Window.IsVisble(1114)', it always reads false",
        ])

    def test_unbalanced_condition_is_left_to_the_bracket_check(self):
        """An unbalanced condition is left to the bracket check, its unknown info unreported."""
        visible = "<visible>[Player.HasVideo | Player.HasVidoe</visible>"
        self.assertEqual(self.messages(f'<window><controls><control type="button">{visible}</control>'
                                       f'<control type="button">{visible}</control></controls></window>'), [])

    def test_parse_faults(self):
        cases = {
            "[Window.IsVisible(home) | Player.HasVideo] + !Player.HasVideo": None,
            "String.IsEqual($VAR[Foo],x)": "$VAR[]",
            "Window.IsVisible(home) + Foo!Bar": "misplaced '!'",
            "String.IsEqual(x,$Localize[31000])": "uppercase",
        }
        for condition, expected in cases.items():
            messages = self.messages(f'<window><controls><control type="button"><visible>{condition}'
                                     f'</visible></control></controls></window>')
            if expected is None:
                self.assertEqual([m for m in messages if "cannot parse" in m], [], condition)
            else:
                self.assertTrue(any(expected in m for m in messages), (condition, messages))

    def test_condition_attribute(self):
        messages = self.messages('<window><controls><control type="button"><visible condition='
                                 '"String.IsEqual($INFO[Foo],x)">Player.HasVideo</visible></control>'
                                 '</controls></window>')
        self.assertTrue(any("$INFO[]" in m for m in messages), messages)

    def test_variable_value_condition(self):
        self.assertEqual(self.messages("""
        <includes><variable name="v">
            <value condition="Player.HasVidoe">a</value>
            <value condition="$EXP[e]">b</value>
        </variable></includes>"""), ["Kodi has no info 'Player.HasVidoe', it always reads false"])

class TestLiteralTags(unittest.TestCase):
    """Kodi reads sizes, fonts and button textures literally, so no dynamic expression expands."""

    def test_dynamic_expression_in_literal_tag(self):
        """A dynamic expression in a literal tag is reported, while one in a label is not."""
        interp = XmlInterpreter(template_attribs={"button": {"width": {}, "texturefocus": {}, "label": {}}},
                                template_values={"button": {"width": "int"}})
        issues = interp.interpret(_parse("""
        <window><controls><control type="button">
            <width>$INFO[System.ScreenWidth]</width>
            <texturefocus>$VAR[Focus]</texturefocus>
            <label>$INFO[ListItem.Label]</label>
        </control></controls></window>"""))
        self.assertEqual(sorted(i["message"] for i in issues), [
            "<texturefocus> takes its text as written: Kodi does not expand $VAR[] in it, and this copy "
            "still overrides any <default> value",
            "<width> takes its text as written: Kodi does not expand $INFO[] in it, and this copy "
            "still overrides any <default> value",
        ])

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
        self.assertEqual([i["message"] for i in issues], ["Use 'noop' for an empty <onclick>"])

    def test_enum_case_follows_kodi(self):
        attribs = {"image": {"aspectratio": {}, "animation": {"tween": "tween", "easing": "easing"},
                             "visible": {}, "wrapmultiline": {}}}
        values = {"image": {"aspectratio": "aspect", "wrapmultiline": "bool"}}
        root = _parse("""
        <window>
            <controls>
                <control type="image">
                    <aspectratio>Keep</aspectratio>
                    <animation tween="Sine" easing="Out">focus</animation>
                    <wrapmultiline>0</wrapmultiline>
                </control>
            </controls>
        </window>
        """)
        interp = XmlInterpreter(template_attribs=attribs, template_values=values)
        self.assertEqual(interp.interpret(root), [])

    def test_values_kodi_compares_in_any_case(self):
        """Slider action, spin subtype and aspectratio alignment take any case; <align> does not."""
        attribs = {"slider": {"action": {}}, "spincontrol": {"subtype": {}},
                   "image": {"aspectratio": {"align": "aspectalign", "aligny": "aspectaligny"}},
                   "label": {"align": {}}}
        values = {"slider": {"action": "action"}, "spincontrol": {"subtype": "subtype"},
                  "image": {"aspectratio": "aspect"}, "label": {"align": "align"}}
        root = _parse("""
        <window>
            <controls>
                <control type="slider"><action>Volume</action></control>
                <control type="spincontrol"><subtype>Int</subtype></control>
                <control type="image">
                    <aspectratio align="Center" aligny="Top">keep</aspectratio>
                </control>
                <control type="label"><align>Center</align></control>
            </controls>
        </window>
        """)
        interp = XmlInterpreter(template_attribs=attribs, template_values=values)
        self.assertEqual([i["message"] for i in interp.interpret(root)],
                         ["invalid value for align: Center (must be lowercase)"])

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

    def test_brackets_ignore_angle_and_curly(self):
        attribs = {"button": {"onclick": {}}}
        values = {"button": {}}
        root = _parse("""
        <window>
            <controls>
                <control type="button">
                    <onclick>RunScript(script.x,{"a":1)</onclick>
                    <onclick>Skin.SetString(arrow,-&gt;)</onclick>
                </control>
            </controls>
        </window>
        """)
        interp = XmlInterpreter(template_attribs=attribs, template_values=values)
        self.assertEqual(interp.interpret(root), [])

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
        self.assertEqual([(i["message"], i["severity"]) for i in issues],
                         [("Invalid multiple tags for control: <enable>", SEVERITY_ERROR)])

    def test_copies_kodi_skips_are_not_duplicates(self):
        attribs = {"button": {"label": {}, "height": {}}}
        values = {"button": {}}
        root = _parse("""
        <window>
            <controls>
                <control type="button">
                    <label _kdk_inc_name="Hidden" _kdk_call_line="4"></label>
                    <label>$LOCALIZE[186]</label>
                    <height>50</height>
                    <height _kdk_inc_name="default type=button" _kdk_call_line="4">60</height>
                </control>
            </controls>
        </window>
        """)
        interp = XmlInterpreter(template_attribs=attribs, template_values=values)
        self.assertEqual(interp.interpret(root), [])

    def test_conditional_include_copies(self):
        attribs = {"image": {"fadetime": {}}}
        values = {"image": {}}
        root = _parse("""
        <window>
            <controls>
                <control type="image">
                    <fadetime _kdk_inc_name="Slow" _kdk_call_line="4" _kdk_inc_cond="1">1800</fadetime>
                    <fadetime _kdk_inc_name="Fast" _kdk_call_line="5" _kdk_inc_cond="1">400</fadetime>
                    <fadetime>600</fadetime>
                </control>
                <control type="image">
                    <fadetime>600</fadetime>
                    <fadetime _kdk_inc_name="Slow" _kdk_call_line="9" _kdk_inc_cond="1">1800</fadetime>
                </control>
            </controls>
        </window>
        """)
        interp = XmlInterpreter(template_attribs=attribs, template_values=values)
        self.assertEqual([(i["line"], i["severity"]) for i in interp.interpret(root)], [(9, SEVERITY_WARNING)])

    def test_duplicate_severity_follows_which_copy_is_dropped(self):
        """Severity and rule follow which copy Kodi drops; an own override of an include passes."""
        attribs = {"button": {"enable": {}, "selected": {}, "usealttexture": {}}}
        values = {"button": {}}
        root = _parse("""
        <window>
            <controls>
                <control type="button">
                    <enable _kdk_inc_name="A" _kdk_call_line="4">true</enable>
                    <enable>true</enable>
                    <selected>true</selected>
                    <selected _kdk_inc_name="A" _kdk_call_line="4">false</selected>
                    <usealttexture _kdk_inc_name="A" _kdk_call_line="4">true</usealttexture>
                    <usealttexture _kdk_inc_name="B" _kdk_call_line="5">false</usealttexture>
                </control>
            </controls>
        </window>
        """)
        interp = XmlInterpreter(template_attribs=attribs, template_values=values)
        issues = interp.interpret(root)
        self.assertEqual([(i["message"], i["severity"], i["rule"], i.get("include_name")) for i in issues], [
            ("Invalid multiple tags for control: <enable>, include 'A' already sets it", SEVERITY_WARNING,
             "xml.include-duplicate-tag", None),
            ("Invalid multiple tags for control: <usealttexture>, this copy is never read (from include 'B')",
             SEVERITY_WARNING, "xml.include-duplicate-tag", "B"),
        ])

    def test_own_tag_repeating_default_is_redundant(self):
        attribs = {"label": {"aligny": {}, "height": {}, "font": {}, "width": {}}}
        values = {"label": {}}
        dflt = '_kdk_inc_name="default type=label" _kdk_call_line="3"'
        root = _parse(f"""
        <window>
            <controls>
                <control type="label">
                    <aligny>center</aligny>
                    <height>40</height>
                    <font _kdk_inc_name="Fonts" _kdk_call_line="3">font12</font>
                    <font>font12</font>
                    <aligny {dflt}>center</aligny>
                    <height {dflt}>66</height>
                    <font {dflt}>font12</font>
                </control>
            </controls>
        </window>
        """)
        interp = XmlInterpreter(template_attribs=attribs, template_values=values)
        messages = [i["message"] for i in interp.interpret(root)]
        self.assertIn('Redundant <aligny>: same value as <default type="label">', messages)
        self.assertFalse([m for m in messages if "Redundant <height>" in m or "Redundant <font>" in m])

    def test_tag_whose_default_changes_with_a_setting_is_kept(self):
        """A tag whose default changes with a setting is kept; a settled one is still redundant."""
        attribs = {"label": {"aligny": {}, "font": {}}}
        dflt = '_kdk_inc_name="default type=label" _kdk_call_line="3"'
        root = _parse(f"""
        <window><controls><control type="label">
            <aligny>center</aligny>
            <font>font12</font>
            <aligny {dflt}>center</aligny>
            <font {dflt}>font12</font>
        </control></controls></window>
        """)
        interp = XmlInterpreter(template_attribs=attribs, template_values={"label": {}},
                                settled_defaults={"label": {"aligny"}})
        self.assertEqual([i["message"] for i in interp.interpret(root)],
                         ['Redundant <aligny>: same value as <default type="label">'])

    def test_own_value_after_include_is_ignored(self):
        attribs = {"button": {"enable": {}, "selected": {}}}
        values = {"button": {}}
        root = _parse("""
        <window>
            <controls>
                <control type="button">
                    <enable _kdk_inc_name="Size" _kdk_call_line="4">true</enable>
                    <enable>false</enable>
                    <selected>true</selected>
                    <selected _kdk_inc_name="Size" _kdk_call_line="4">false</selected>
                </control>
            </controls>
        </window>
        """)
        interp = XmlInterpreter(template_attribs=attribs, template_values=values)
        issues = interp.interpret(root)
        self.assertEqual([(i["message"], i["severity"]) for i in issues],
                         [("Invalid multiple tags for control: <enable>, ignored because include 'Size' "
                           "sets it first", SEVERITY_ERROR)])


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
