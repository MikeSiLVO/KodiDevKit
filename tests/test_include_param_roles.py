"""
Tests for include-param role inference (Skin.resolve_param_role).

Used so a hover on `<param name="visible">SomeCondition</param>` inside an
include call can know that "visible" is a boolean-condition role and route
the value through JSON-RPC accordingly.
"""

import os
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.skin import Skin


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
        # The top-level <param> in an include def declares a default; it is
        # not itself a usage of $PARAM elsewhere.
        skin, _ = _make_skin("""
    <include name="WithDefault">
        <param name="visible">true</param>
        <control type="button">
            <visible>$PARAM[visible]</visible>
        </control>
    </include>
""")
        role = skin.resolve_param_role("16x9", "WithDefault", "visible")
        # Only the <visible> usage counts as a role, not the default.
        self.assertEqual(role, ("tag", "visible"))


if __name__ == "__main__":
    unittest.main()
