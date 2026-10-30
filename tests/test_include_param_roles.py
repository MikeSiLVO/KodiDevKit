"""Tests for Skin.resolve_param_role and Skin.include_params, which the hovers read."""

import os
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.skin.skin import Skin


def _make_skin(includes_body):
    """Create a temp skin whose Includes.xml has the given body."""
    tmp = tempfile.mkdtemp(prefix="kdk_paramrole_")
    os.makedirs(os.path.join(tmp, "16x9"))
    with open(os.path.join(tmp, "addon.xml"), "w", encoding="utf-8") as f:
        f.write("""<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test" provider-name="Test">
    <requires><import addon="xbmc.gui" version="5.15.0"/></requires>
    <extension point="xbmc.gui.skin">
        <res width="1920" height="1080" aspect="16:9" default="true" folder="16x9" />
    </extension>
</addon>""")
    with open(os.path.join(tmp, "16x9", "Includes.xml"), "w", encoding="utf-8") as f:
        f.write(f"""<?xml version="1.0" encoding="UTF-8"?>
<includes>
{includes_body}
</includes>""")
    return Skin(path=tmp), tmp


class TestIncludeParamRoles(unittest.TestCase):

    def test_param_used_in_visible_tag(self):
        skin, _ = _make_skin("""
    <include name="CloseButton">
        <control type="button">
            <visible>$PARAM[visible]</visible>
        </control>
    </include>
""")
        role = skin.resolve_param_role("16x9", "CloseButton", "visible")
        self.assertEqual(role, ("tag", "visible"))

    def test_param_used_in_condition_attribute(self):
        skin, _ = _make_skin("""
    <include name="FadeAnim">
        <animation effect="fade" condition="$PARAM[when]">Conditional</animation>
    </include>
""")
        role = skin.resolve_param_role("16x9", "FadeAnim", "when")
        self.assertEqual(role, ("attr", "condition"))

    def test_param_in_non_condition_role(self):
        skin, _ = _make_skin("""
    <include name="Label">
        <control type="label">
            <label>$PARAM[text]</label>
        </control>
    </include>
""")
        role = skin.resolve_param_role("16x9", "Label", "text")
        self.assertEqual(role, ("tag", "label"))

    def test_forwarded_param_chain(self):
        skin, _ = _make_skin("""
    <include name="Inner">
        <control type="button">
            <visible>$PARAM[show]</visible>
        </control>
    </include>
    <include name="Outer">
        <include content="Inner">
            <param name="show">$PARAM[show]</param>
        </include>
    </include>
""")
        # Outer.show forwards to Inner.show, which is a visible role.
        role = skin.resolve_param_role("16x9", "Outer", "show")
        self.assertEqual(role, ("tag", "visible"))

    def test_deep_chain_three_levels(self):
        skin, _ = _make_skin("""
    <include name="A">
        <control type="button">
            <visible>$PARAM[v]</visible>
        </control>
    </include>
    <include name="B">
        <include content="A">
            <param name="v">$PARAM[v]</param>
        </include>
    </include>
    <include name="C">
        <include content="B">
            <param name="v">$PARAM[v]</param>
        </include>
    </include>
""")
        role = skin.resolve_param_role("16x9", "C", "v")
        self.assertEqual(role, ("tag", "visible"))

    def test_multi_context_returns_multi(self):
        skin, _ = _make_skin("""
    <include name="DualUse">
        <control type="button">
            <visible>$PARAM[x]</visible>
            <enable>$PARAM[x]</enable>
        </control>
    </include>
""")
        role = skin.resolve_param_role("16x9", "DualUse", "x")
        self.assertEqual(role, "multi")

    def test_cycle_detection_returns_none(self):
        skin, _ = _make_skin("""
    <include name="A">
        <include content="B">
            <param name="x">$PARAM[x]</param>
        </include>
    </include>
    <include name="B">
        <include content="A">
            <param name="x">$PARAM[x]</param>
        </include>
    </include>
""")
        role = skin.resolve_param_role("16x9", "A", "x")
        self.assertIsNone(role)

    def test_unknown_param_returns_none(self):
        skin, _ = _make_skin("""
    <include name="X">
        <control type="button">
            <visible>$PARAM[visible]</visible>
        </control>
    </include>
""")
        role = skin.resolve_param_role("16x9", "X", "nonexistent")
        self.assertIsNone(role)

    def test_top_level_default_param_is_not_a_usage(self):
        """A top-level <param> declares a default, not a use of $PARAM."""
        skin, _ = _make_skin("""
    <include name="WithDefault">
        <param name="visible">true</param>
        <definition>
            <control type="button">
                <visible>$PARAM[visible]</visible>
            </control>
        </definition>
    </include>
""")
        role = skin.resolve_param_role("16x9", "WithDefault", "visible")
        self.assertEqual(role, ("tag", "visible"))

    def test_value_attribute_forward_is_followed(self):
        """A value= forward takes the role the nested include gives the param."""
        skin, _ = _make_skin("""
    <include name="Inner">
        <control type="button">
            <visible>$PARAM[show]</visible>
        </control>
    </include>
    <include name="Outer">
        <include content="Inner">
            <param name="show" value="$PARAM[show]"/>
        </include>
    </include>
""")
        role = skin.resolve_param_role("16x9", "Outer", "show")
        self.assertEqual(role, ("tag", "visible"))


class TestIncludeParams(unittest.TestCase):
    """Param rows the include hover lists: default, direct use and forwards."""

    def _rows(self, body, name):
        """Rows of the named include in a skin whose Includes.xml has the body."""
        skin, _ = _make_skin(body)
        return skin.include_params("16x9", name)

    def test_body_order_then_unused_declared(self):
        """Params in body order, unused declared ones last; comments and stray tags add none."""
        rows = self._rows("""
    <include name="Card">
        <param name="width" default="300"/>
        <param name="spare">x</param>
        <definition>
            <control type="label" id="$PARAM[id]">
                <width>$PARAM[width]</width>
                <label>$PARAM[text]</label>
                <!-- $PARAM[commented] -->
            </control>
        </definition>
        <description>$PARAM[outside]</description>
    </include>
""", "Card")
        self.assertEqual(rows, [
            ("id", None, True, []),
            ("width", "300", True, []),
            ("text", None, True, []),
            ("spare", "x", False, []),
        ])

    def test_forward_value_is_the_nested_default_only_for_a_lone_undeclared_param(self):
        """A bare undeclared $PARAM gets the nested default; declared or mixed text does not."""
        rows = self._rows("""
    <include name="Bar">
        <param name="top" default="10"/>
        <definition>
            <top>$PARAM[top]</top>
        </definition>
    </include>
    <include name="List">
        <param name="size" default=""/>
        <definition>
            <include content="Bar">
                <param name="top">$PARAM[top]</param>
            </include>
            <include content="Bar">
                <param name="top" value="$PARAM[size]"/>
            </include>
            <include content="Bar">
                <param name="top">$PARAM[offset]px</param>
            </include>
        </definition>
    </include>
""", "List")
        self.assertEqual(rows, [
            ("top", None, False, [("Bar", "top", "10")]),
            ("size", "", False, [("Bar", "top", None)]),
            ("offset", None, False, [("Bar", "top", None)]),
        ])

    def test_forward_chain_reaches_the_first_default(self):
        """A chain of undeclared forwards takes the default at its end."""
        rows = self._rows("""
    <include name="A">
        <param name="x" default="5"/>
        <definition>
            <left>$PARAM[x]</left>
        </definition>
    </include>
    <include name="B">
        <include content="A">
            <param name="x">$PARAM[x]</param>
        </include>
    </include>
    <include name="C">
        <include content="B">
            <param name="x">$PARAM[x]</param>
        </include>
    </include>
""", "C")
        self.assertEqual(rows, [("x", None, False, [("B", "x", "5")])])

    def test_forward_cycle_has_no_value(self):
        """Forwards that loop back have no value to pass."""
        rows = self._rows("""
    <include name="A">
        <include content="B">
            <param name="x">$PARAM[x]</param>
        </include>
    </include>
    <include name="B">
        <include content="A">
            <param name="x">$PARAM[x]</param>
        </include>
    </include>
""", "A")
        self.assertEqual(rows, [("x", None, False, [("B", "x", None)])])


if __name__ == "__main__":
    unittest.main()
