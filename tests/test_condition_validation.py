"""Tests for the boolean-condition check in ``ValidationExpression``.

Conditions Kodi cannot parse are silently always-false at runtime
(InfoExpression.cpp:34-42), so they have to be caught here.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from libs.validation.expression import ValidationExpression


class DummyAddon:
    """Skin stand-in exposing just what the expression validator reads."""

    def __init__(self, path, folder, files, expressions=None):
        self.path = path
        self.xml_folders = [folder]
        self.window_files = {folder: files}
        self.expression_map = {folder: expressions or {}}


class TestConditionValidation(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.folder = "16x9"
        os.makedirs(os.path.join(self.root, self.folder))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _run(self, xml, expressions=None):
        name = "Test.xml"
        with open(os.path.join(self.root, self.folder, name), "w", encoding="utf-8") as handle:
            handle.write(xml)
        addon = DummyAddon(self.root, self.folder, [name], expressions)
        return ValidationExpression(addon).check()

    def _messages(self, xml, expressions=None):
        return " | ".join(i["message"] for i in self._run(xml, expressions))

    def test_valid_conditions_are_silent(self):
        xml = """<window>
          <control type="button">
            <visible>[Window.IsActive(home) | Window.IsActive(settings)] + !Player.HasVideo</visible>
            <enable>Skin.HasSetting(Foo)</enable>
            <label condition="String.IsEqual(ListItem.Label,$LOCALIZE[31000])">x</label>
          </control>
        </window>"""
        self.assertEqual(self._run(xml), [])

    def test_var_in_condition_is_flagged(self):
        xml = '<window><control><visible>String.IsEqual($VAR[Foo],x)</visible></control></window>'
        self.assertIn("$VAR[]", self._messages(xml))

    def test_info_in_condition_attribute_is_flagged(self):
        xml = '<window><control><label condition="String.IsEqual($INFO[Foo],x)">y</label></control></window>'
        self.assertIn("$INFO[]", self._messages(xml))

    def test_misplaced_operator_is_flagged(self):
        xml = '<window><control><visible>Skin.HasSetting(a) + Foo!Bar</visible></control></window>'
        self.assertIn("misplaced '!'", self._messages(xml))

    def test_unmatched_bracket_is_flagged(self):
        xml = '<window><control><visible>[Skin.HasSetting(a) + Player.HasVideo</visible></control></window>'
        self.assertIn("unmatched '['", self._messages(xml))

    def test_miscased_localize_is_flagged(self):
        xml = '<window><control><visible>String.IsEqual(x,$Localize[31000])</visible></control></window>'
        self.assertIn("uppercase", self._messages(xml))

    def test_param_is_skipped(self):
        xml = '<window><control><visible>$PARAM[visible]</visible></control></window>'
        self.assertEqual(self._run(xml), [])

    def test_known_expression_is_resolved_then_checked(self):
        xml = '<window><control><visible>$EXP[Good] + Player.HasVideo</visible></control></window>'
        self.assertEqual(self._run(xml, {"Good": "[Skin.HasSetting(a)]"}), [])

    def test_expression_hiding_a_broken_body_is_flagged(self):
        xml = '<window><control><visible>$EXP[Bad] + Player.HasVideo</visible></control></window>'
        self.assertIn("$VAR[]", self._messages(xml, {"Bad": "[String.IsEqual($VAR[x],y)]"}))

    def test_undefined_expression_is_flagged(self):
        xml = '<window><control><visible>$EXP[Missing] + Player.HasVideo</visible></control></window>'
        self.assertIn("undefined expression Missing", self._messages(xml, {"Other": "[A]"}))

    def test_expression_definition_body_is_checked(self):
        xml = '<window><expression name="Broken">Skin.HasSetting(a) + Foo!Bar</expression></window>'
        self.assertIn("misplaced '!'", self._messages(xml))


if __name__ == "__main__":
    unittest.main()
