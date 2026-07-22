"""Tests for the hover verdict path in ``kodidevkit.evaluate_condition``.

Sublime, mdpopups and the Kodi connection are stubbed so the popup logic can be
exercised outside the editor.
"""

import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _install_stubs():
    """Put fake sublime / sublime_plugin / mdpopups in place before import."""
    import mock_sublime

    for attr in ("COOPERATE_WITH_AUTO_COMPLETE", "CLASS_WORD_START",
                 "CLASS_WORD_END", "HIDE_ON_MOUSE_MOVE_AWAY"):
        setattr(mock_sublime, attr, 1)
    setattr(mock_sublime, "Region", type("Region", (object,), {}))
    setattr(mock_sublime, "set_timeout", lambda *args, **kwargs: None)
    setattr(mock_sublime, "platform", lambda: "linux")
    sys.modules["sublime"] = mock_sublime

    plugin = types.ModuleType("sublime_plugin")
    for name in ("EventListener", "TextCommand", "WindowCommand",
                 "ViewEventListener", "TextInputHandler"):
        setattr(plugin, name, type(name, (object,), {}))
    sys.modules["sublime_plugin"] = plugin

    popups = types.ModuleType("mdpopups")
    setattr(popups, "syntax_highlight", lambda **kwargs: f"<CODE>{kwargs.get('src', '')}</CODE>")
    setattr(popups, "show_popup", lambda **kwargs: None)
    sys.modules["mdpopups"] = popups

    package = types.ModuleType("KodiDevKit")
    package.__path__ = [os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]
    sys.modules["KodiDevKit"] = package

    import importlib
    return importlib.import_module("KodiDevKit.kodidevkit")


kodidevkit = _install_stubs()


class FakeView:
    """View stub exposing only what the verdict path reads."""

    def file_name(self):
        return "/skin/16x9/Home.xml"


class FakeAddon:
    def __init__(self, expressions):
        self.expression_map = {"16x9": expressions}


class TestEvaluateCondition(unittest.TestCase):

    def setUp(self):
        self.sent = []
        self.response = None
        kodidevkit.kodi._cooldown_until = 0.0
        kodidevkit.kodi.request = self._request
        kodidevkit.INFOS.addon = FakeAddon({"Good": "[Skin.HasSetting(a)]"})

    def _request(self, method=None, params=None):
        self.sent.append((params or {}).get("booleans", []))
        return self.response

    def _answer(self, condition, direct, negated):
        self.response = {"result": {condition: direct, f"![{condition}]": negated}}

    def _run(self, condition):
        return kodidevkit.evaluate_condition(FakeView(), condition) or ""

    def test_true(self):
        self._answer("Player.HasVideo", True, False)
        self.assertIn("TRUE", self._run("Player.HasVideo"))

    def test_false(self):
        self._answer("Player.HasVideo", False, True)
        self.assertIn("FALSE", self._run("Player.HasVideo"))

    def test_parse_failure_is_not_reported_as_false(self):
        self._answer("Foo.Bar", False, False)
        self.assertIn("NOT PARSEABLE", self._run("Foo.Bar"))

    def test_unreachable_kodi(self):
        self.response = None
        self.assertIn("UNREACHABLE", self._run("Player.HasVideo"))

    def test_label_macro_is_rejected_without_asking_kodi(self):
        body = self._run("String.IsEqual($VAR[Foo],x)")
        self.assertIn("NOT PARSEABLE", body)
        self.assertIn("$VAR[]", body)
        self.assertEqual(self.sent, [])

    def test_unresolved_param_is_its_own_state(self):
        body = self._run("$PARAM[visible]")
        self.assertIn("NEEDS INCLUDE CONTEXT", body)
        self.assertEqual(self.sent, [])

    def test_syntax_error_is_named(self):
        # The reason is HTML-escaped for the popup, so the quotes arrive encoded.
        self.assertIn("misplaced", self._run("Skin.HasSetting(a) + Foo!Bar"))
        self.assertEqual(self.sent, [])

    def test_entities_are_decoded_before_sending(self):
        self._answer("String.IsEqual(ListItem.Label,A & B)", True, False)
        self._run("String.IsEqual(ListItem.Label,A &amp; B)")
        self.assertEqual(self.sent[0][0], "String.IsEqual(ListItem.Label,A & B)")

    def test_expression_is_flattened_before_sending(self):
        self._answer("[Skin.HasSetting(a)]", True, False)
        body = self._run("$EXP[Good]")
        self.assertEqual(self.sent[0][0], "[Skin.HasSetting(a)]")
        self.assertIn("TRUE", body)
        self.assertIn("expands to", body)
        self.assertIn("[Skin.HasSetting(a)]", body)

    def test_undefined_expression_is_named(self):
        body = self._run("$EXP[Missing] + Player.HasVideo")
        self.assertIn("undefined expression Missing", body)
        self.assertEqual(self.sent, [])

    def test_no_expansion_block_when_nothing_expanded(self):
        self._answer("Player.HasVideo", True, False)
        self.assertNotIn("expands to", self._run("Player.HasVideo"))

    def test_verdict_has_no_extra_note(self):
        self._answer("String.IsEmpty(ListItem.Label)", True, False)
        body = self._run("String.IsEmpty(ListItem.Label)")
        self.assertIn("TRUE", body)
        self.assertNotIn("current window", body)

    def test_empty_and_wordless_conditions_are_ignored(self):
        self.assertEqual(kodidevkit.evaluate_condition(FakeView(), ""), None)
        self.assertEqual(kodidevkit.evaluate_condition(FakeView(), "  +  "), None)
        self.assertEqual(self.sent, [])


class TestOnTagName(unittest.TestCase):
    """The tag-name gate that selects whole-statement evaluation."""

    def _at(self, line, needle):
        return kodidevkit._on_tag_name(line, line.index(needle))

    def test_tag_name(self):
        self.assertTrue(self._at("    <visible>A + B</visible>", "visible>"))

    def test_closing_tag_name(self):
        line = "    <visible>A + B</visible>"
        self.assertTrue(kodidevkit._on_tag_name(line, line.index("visible>", 10)))

    def test_attribute_is_not_the_tag_name(self):
        self.assertFalse(self._at('    <visible allowhiddenfocus="true">A</visible>', "allowhiddenfocus"))
        self.assertFalse(self._at('    <expression name="Foo">A</expression>', "Foo"))

    def test_content_is_not_the_tag_name(self):
        self.assertFalse(self._at("    <visible>Skin.HasSetting(a)</visible>", "Skin"))


class TestOperandClause(unittest.TestCase):
    """The single-item gate for condition content."""

    def _at(self, line, needle):
        return kodidevkit._operand_clause(line, line.index(needle))

    def test_single_item_at_caret(self):
        line = "A + B + C"
        self.assertEqual(self._at(line, "A"), "A")
        self.assertEqual(self._at(line, "B"), "B")
        self.assertEqual(self._at(line, "C"), "C")

    def test_operator_does_not_fire(self):
        line = "A + B | C"
        self.assertIsNone(kodidevkit._operand_clause(line, line.index("+")))
        self.assertIsNone(kodidevkit._operand_clause(line, line.index("|")))

    def test_whitespace_does_not_fire(self):
        line = "A + B"
        self.assertIsNone(kodidevkit._operand_clause(line, 1))

    def test_grouped_item(self):
        self.assertEqual(self._at("[A + B] | C", "C"), "C")
        self.assertEqual(self._at("[A + B] | C", "B"), "B")

    def test_bracket_does_not_fire(self):
        self.assertIsNone(kodidevkit._operand_clause("[A + B]", 0))

    def test_function_call_is_one_item(self):
        line = "String.IsEqual(x,y) + Player.HasVideo"
        self.assertEqual(self._at(line, "IsEqual"), "String.IsEqual(x,y)")

    def test_exp_reference_is_one_item(self):
        self.assertEqual(self._at("$EXP[Foo] + A", "Foo"), "$EXP[Foo]")
        self.assertEqual(self._at("$EXP[Foo] + A", "EXP"), "$EXP[Foo]")

    def test_negated_item_keeps_the_bang(self):
        self.assertEqual(self._at("!Skin.HasSetting(a) + B", "Skin"), "!Skin.HasSetting(a)")


if __name__ == "__main__":
    unittest.main()
