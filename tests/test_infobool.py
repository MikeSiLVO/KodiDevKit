# pyright: reportAttributeAccessIssue=false
"""Tests for ``utils.infobool`` -- the Kodi boolean-condition syntax check and
the negation probe that tells a parse failure apart from a genuine false.

Expected verdicts were confirmed against a running Kodi via XBMC.GetInfoBooleans.
"""

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
        # Kodi accepts any name and evaluates it false (GUIInfoManager.cpp:11444).
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
        # Kodi matches the literal "$LOCALIZE[" (GUIInfoLabel.cpp:196), so a
        # lowercase spelling keeps its bracket and breaks the parse.
        self.assertInvalid("String.IsEqual(ListItem.Label,$Localize[31000])", "misplaced '['")

    def test_unclosed_localize_reaches_the_parser(self):
        # Kodi leaves an incomplete reference in place (GUIInfoLabel.cpp:214-218),
        # so its '[' still breaks the parse.
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
        # A failed parse becomes a constant false, so the negation is false too
        # (InfoExpression.cpp:34-42).
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
        # The permission layer answers the direct key and the evaluator answers
        # the negation (XBMCOperations.cpp:60-69), so the pair can disagree.
        cond = "System.CanShutdown"
        self.assertEqual(infobool.read_probe(self._response(cond, True, True), cond),
                         infobool.STATE_TRUE)
        self.assertEqual(infobool.read_probe(self._response(cond, False, False), cond),
                         infobool.STATE_FALSE)


if __name__ == "__main__":
    unittest.main()
