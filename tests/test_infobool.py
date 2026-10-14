# pyright: reportAttributeAccessIssue=false
"""Tests for ``utils.infobool`` -- the Kodi boolean-condition syntax check and
the negation probe that tells a parse failure apart from a genuine false.

Expected verdicts were confirmed against a running Kodi via XBMC.GetInfoBooleans.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from libs.utils import infobool


class TestCheckSyntax(unittest.TestCase):

    def assertValid(self, condition):
        self.assertIsNone(infobool.check_syntax(condition), condition)

    def assertInvalid(self, condition, fragment):
        reason = infobool.check_syntax(condition)
        self.assertIsNotNone(reason, f"{condition!r} should not parse")
        self.assertIn(fragment, reason or "")

    def test_plain_operands(self):
        self.assertValid("Player.HasVideo")
        self.assertValid("Skin.HasSetting(Home.Widgets)")
        self.assertValid("Integer.IsGreater(Container(50).NumItems,0)")

    def test_unknown_operand_name_still_parses(self):
        # Kodi accepts any name and evaluates it false
        self.assertValid("Totally.BogusInfo")

    def test_operators(self):
        self.assertValid("A + B")
        self.assertValid("A | B")
        self.assertValid("!A")
        self.assertValid("!!A")
        self.assertValid("[A + B] | [C + !D]")
        self.assertValid("[A + [B | C]]")

    def test_bang_after_operand_is_misplaced(self):
        self.assertInvalid("Foo!Bar", "misplaced '!'")

    def test_bracket_after_operand_is_misplaced(self):
        self.assertInvalid("Foo[Bar]", "misplaced '['")

    def test_leading_binary_operator(self):
        self.assertInvalid("+ A", "misplaced '+'")
        self.assertInvalid("| A", "misplaced '|'")
        self.assertInvalid("] A", "misplaced ']'")

    def test_trailing_binary_operator(self):
        self.assertInvalid("A + ", "missing operand")
        self.assertInvalid("A |", "missing operand")

    def test_unbalanced_brackets(self):
        self.assertInvalid("[A + B", "unmatched '['")
        self.assertInvalid("A + B]", "unmatched ']'")

    def test_empty(self):
        self.assertInvalid("", "empty condition")
        self.assertInvalid("   ", "empty condition")

    def test_localize_brackets_are_presubstituted(self):
        self.assertValid("String.IsEqual(ListItem.Label,$LOCALIZE[31000])")
        self.assertValid("String.IsEqual(ListItem.Label,$LOCALIZE[$LOCALIZE[40211]])")
        self.assertValid("Integer.IsGreater(ListItem.Year,$NUMBER[2000])")

    def test_localize_keyword_is_case_sensitive(self):
        # Kodi matches only the literal "$LOCALIZE["; a lowercase one keeps its bracket
        self.assertInvalid("String.IsEqual(ListItem.Label,$Localize[31000])", "misplaced '['")

    def test_unclosed_localize_reaches_the_parser(self):
        # Kodi leaves an incomplete reference in place; its '[' still breaks the parse
        self.assertInvalid("String.IsEqual(ListItem.Label,$LOCALIZE[31000)", "missing ']'")

    def test_case_hint_only_when_the_keyword_is_miscased(self):
        self.assertInvalid("String.IsEqual(x,$localize[31000])", "must be uppercase")
        self.assertInvalid("String.IsEqual(x,$Localize[31000])", "must be uppercase")
        self.assertNotIn("uppercase", infobool.check_syntax("Foo[Bar]") or "")


class TestCheckCondition(unittest.TestCase):

    def test_sendable(self):
        self.assertIsNone(infobool.check_condition("Player.HasVideo"))
        self.assertIsNone(infobool.check_condition("[A + B] | !C"))

    def test_label_macros_are_invalid_in_conditions(self):
        for cond, macro in (("String.IsEqual($VAR[Foo],x)", "$VAR[]"),
                            ("String.IsEqual($INFO[Foo],x)", "$INFO[]"),
                            ("String.IsEqual($ESCINFO[Foo],x)", "$ESCINFO[]")):
            state, reason = infobool.check_condition(cond) or ("", "")
            self.assertEqual(state, infobool.STATE_INVALID)
            self.assertIn(macro, reason)

    def test_unresolved_param_needs_context(self):
        for cond in ("$PARAM[visible]", "Skin.HasSetting($PARAM[name])"):
            state, reason = infobool.check_condition(cond) or ("", "")
            self.assertEqual(state, infobool.STATE_NEEDS_CONTEXT)
            self.assertIn("$PARAM", reason)

    def test_leftover_exp_is_named(self):
        state, reason = infobool.check_condition("$EXP[Gone] + Player.HasVideo") or ("", "")
        self.assertEqual(state, infobool.STATE_INVALID)
        self.assertIn("unknown expression Gone", reason)

    def test_syntax_error_passes_through(self):
        state, reason = infobool.check_condition("Foo!Bar") or ("", "")
        self.assertEqual(state, infobool.STATE_INVALID)
        self.assertIn("misplaced '!'", reason)


@unittest.skipUnless(
    hasattr(infobool, "read_probe"),
    "live-probe helpers ship only with the editor plugin",
)
class TestStaticValue(unittest.TestCase):
    """Conditions whose value is the same in any state."""

    def test_literals_in_any_case(self):
        """The literals false, no, true and yes read the same in any case."""
        self.assertIs(infobool.static_value("False"), False)
        self.assertIs(infobool.static_value("no"), False)
        self.assertIs(infobool.static_value("YES"), True)

    def test_operators_follow_three_valued_logic(self):
        """An unknown operand stays unknown unless the other side settles the result."""
        self.assertIs(infobool.static_value("Skin.HasSetting(a) + false"), False)
        self.assertIs(infobool.static_value("Skin.HasSetting(a) | true"), True)
        self.assertIs(infobool.static_value("[Player.HasVideo + no] | !true"), False)
        self.assertIsNone(infobool.static_value("Skin.HasSetting(a) | false"))

    def test_unparsed_text_is_unknown(self):
        """Text that fails to parse, such as an unexpanded $PARAM, reads as unknown."""
        self.assertIsNone(infobool.static_value("[false"))
        self.assertIsNone(infobool.static_value("$PARAM[texture] + false"))


class TestNegationProbe(unittest.TestCase):

    def _response(self, condition, direct, negated):
        return {"result": {condition: direct, infobool.negation_of(condition): negated}}

    def test_probe_booleans_pairs_the_condition_with_its_negation(self):
        self.assertEqual(
            infobool.probe_booleans("Player.HasVideo"),
            ["Player.HasVideo", "![Player.HasVideo]"],
        )

    def test_true(self):
        cond = "Window.IsActive(home)"
        self.assertEqual(infobool.read_probe(self._response(cond, True, False), cond),
                         infobool.STATE_TRUE)

    def test_false(self):
        cond = "Player.HasVideo"
        self.assertEqual(infobool.read_probe(self._response(cond, False, True), cond),
                         infobool.STATE_FALSE)

    def test_both_false_means_parse_failure(self):
        # a failed parse becomes a constant false; its negation is false too
        cond = "String.IsEqual($VAR[Foo],x)"
        self.assertEqual(infobool.read_probe(self._response(cond, False, False), cond),
                         infobool.STATE_INVALID)

    def test_missing_response_is_offline(self):
        self.assertEqual(infobool.read_probe(None, "A"), infobool.STATE_OFFLINE)
        self.assertEqual(infobool.read_probe({}, "A"), infobool.STATE_OFFLINE)
        self.assertEqual(infobool.read_probe({"error": {}}, "A"), infobool.STATE_OFFLINE)

    def test_partial_response_is_offline(self):
        self.assertEqual(infobool.read_probe({"result": {"A": True}}, "A"),
                         infobool.STATE_OFFLINE)

    def test_permission_gated_booleans_use_the_direct_value(self):
        # the permission layer answers the direct key, the evaluator the negation; they can disagree
        cond = "System.CanShutdown"
        self.assertEqual(infobool.read_probe(self._response(cond, True, True), cond),
                         infobool.STATE_TRUE)
        self.assertEqual(infobool.read_probe(self._response(cond, False, False), cond),
                         infobool.STATE_FALSE)


class TestInfoNames(unittest.TestCase):
    """Operand names checked against the generated Piers table."""

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(infobool.__file__)))
        with open(os.path.join(root, "..", "data", "piers", "infonames.json"), encoding="utf-8") as f:
            cls.names = infobool.info_name_sets(json.load(f))

    def unknown(self, condition):
        return infobool.unknown_infos(condition, self.names)

    def test_known_forms(self):
        self.assertEqual(self.unknown(
            "Window.IsVisible(1114) + !Skin.HasSetting(a.b) | Container(50).ListItem(1).Property(x.y)"
            " + ListItemNoWrap(2).Title + System.Platform.Linux + Player.Offset(1).Title + true"
            " + Control.HasFocus(3) + String.IsEqual(ListItem.Label,a.b)"), [])

    def test_typo_and_bare_word(self):
        self.assertEqual(self.unknown("!Window.IsVisble(1114) + Player.HasVideo + foo"),
                         ["Window.IsVisble(1114)", "foo"])

    def test_macros_are_left_alone(self):
        self.assertEqual(self.unknown("$EXP[name] + String.IsEmpty($INFO[ListItem.Label]) + $PARAM[x]"), [])

    def test_split_info_keeps_dots_inside_params(self):
        self.assertEqual(infobool.split_info("Window(Home).Property(a.b)"),
                         [("window", "Home"), ("property", "a.b")])


if __name__ == "__main__":
    unittest.main()
