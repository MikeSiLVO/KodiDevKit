"""
Tests for ``utils.extract_expression_at_offset`` — the hover-time extractor
that supplies the boolean evaluator in ``kodidevkit.py``.

The bug this guards against: Sublime's ``expand_by_class`` is called with
``[`` and ``]`` in the separator set, so hovering anywhere inside
``String.IsEqual(ListItem.Label,$LOCALIZE[40211])`` produced
``String.IsEqual(ListItem.Label,$LOCALIZE`` and that truncated string was
sent to ``XBMC.GetInfoBooleans``. Real-world expressions are mined from
``skin.estuary``.
"""

from tests.base import KodiDevKitTestCase
from libs.utils import extract_expression_at_offset


class ExtractExpressionAtOffsetTests(KodiDevKitTestCase):

    def _at_substr(self, line, needle):
        """Return cursor offset pointing into the middle of *needle* in *line*."""
        idx = line.index(needle)
        return idx + len(needle) // 2


    def test_hover_inside_localize_returns_full_expression(self):
        line = '<value condition="String.IsEqual(ListItem.Label,$LOCALIZE[40211])">x</value>'
        # cursor on the digits inside $LOCALIZE[...]
        cursor = self._at_substr(line, "40211")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "String.IsEqual(ListItem.Label,$LOCALIZE[40211])",
        )

    def test_hover_on_label_returns_full_expression(self):
        line = '<visible>String.IsEqual(ListItem.Label,$LOCALIZE[40211])</visible>'
        cursor = self._at_substr(line, "Label")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "String.IsEqual(ListItem.Label,$LOCALIZE[40211])",
        )

    def test_hover_on_localize_keyword_returns_full_expression(self):
        line = '<visible>String.IsEqual(ListItem.Label,$LOCALIZE[40211])</visible>'
        cursor = self._at_substr(line, "LOCALIZE")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "String.IsEqual(ListItem.Label,$LOCALIZE[40211])",
        )


    def test_quote_bounds_attribute_value(self):
        line = '<control visible="Window.IsActive(home)" id="1"/>'
        cursor = self._at_substr(line, "IsActive")
        self.assertEqual(extract_expression_at_offset(line, cursor), "Window.IsActive(home)")

    def test_angle_brackets_bound_element_text(self):
        line = '<visible>Skin.HasSetting(MyToggle)</visible>'
        cursor = self._at_substr(line, "HasSetting")
        self.assertEqual(extract_expression_at_offset(line, cursor), "Skin.HasSetting(MyToggle)")

    def test_returns_empty_on_empty_line(self):
        self.assertEqual(extract_expression_at_offset("", 0), "")

    def test_handles_cursor_past_end(self):
        line = "Window.IsActive(home)"
        self.assertEqual(extract_expression_at_offset(line, 999), line)

    def test_handles_negative_cursor(self):
        line = "Window.IsActive(home)"
        self.assertEqual(extract_expression_at_offset(line, -5), line)


    def test_estuary_param_in_string_isequal(self):
        line = '<visible>String.IsEqual(Container(9000).ListItem.Property(id),$PARAM[id])</visible>'
        cursor = self._at_substr(line, "Property")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "String.IsEqual(Container(9000).ListItem.Property(id),$PARAM[id])",
        )

    def test_estuary_localize_with_literal(self):
        line = '<visible>String.IsEqual(Container(5000).ListItem.Label,$LOCALIZE[184])</visible>'
        cursor = self._at_substr(line, "184")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "String.IsEqual(Container(5000).ListItem.Label,$LOCALIZE[184])",
        )

    def test_grouping_and_or_scopes_to_clause(self):
        # `[A | B]` — the `|` at top level inside the group is a sub-expression
        # boundary, so hovering on `music` returns just that clause.
        line = '<visible>[Window.IsActive(home) | Window.IsActive(music)]</visible>'
        cursor = self._at_substr(line, "music")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "Window.IsActive(music)",
        )

    def test_clause_without_negation_does_not_borrow_one(self):
        # Cursor on the second clause `Skin.HasSetting(x)` must not pick up the
        # `!` that belongs to the first clause's operand.
        line = '<enable>!Window.IsActive(home) + Skin.HasSetting(x)</enable>'
        cursor = self._at_substr(line, "Skin")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "Skin.HasSetting(x)",
        )


    def test_cursor_right_after_opening_quote(self):
        line = '<control visible="Window.IsActive(home)"/>'
        cursor = line.index('"') + 1
        self.assertEqual(extract_expression_at_offset(line, cursor), "Window.IsActive(home)")

    def test_cursor_right_before_closing_angle(self):
        line = '<visible>Skin.HasSetting(x)</visible>'
        cursor = line.index("</")
        self.assertEqual(extract_expression_at_offset(line, cursor), "Skin.HasSetting(x)")


    def test_compound_and_returns_only_the_clause_under_cursor(self):
        line = '<visible>ListItem.IsFolder + String.IsEqual(ListItem.Label,$LOCALIZE[40211]) + String.IsEmpty(ListItem.Art(fanart)) + !Skin.HasSetting(Disable.Fanart)</visible>'
        cursor = self._at_substr(line, "IsEqual")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "String.IsEqual(ListItem.Label,$LOCALIZE[40211])",
        )

    def test_compound_and_first_clause(self):
        line = '<visible>ListItem.IsFolder + String.IsEqual(ListItem.Label,$LOCALIZE[40211])</visible>'
        cursor = self._at_substr(line, "IsFolder")
        self.assertEqual(extract_expression_at_offset(line, cursor), "ListItem.IsFolder")

    def test_compound_and_last_clause_keeps_leading_negation(self):
        # `!` is a unary prefix that binds to the following operand — hovering
        # inside `!Skin.HasSetting(x)` must include the `!`, otherwise the
        # boolean we send to Kodi has the OPPOSITE truth value.
        line = '<visible>A + !Skin.HasSetting(Disable.Fanart)</visible>'
        cursor = self._at_substr(line, "HasSetting")
        self.assertEqual(extract_expression_at_offset(line, cursor), "!Skin.HasSetting(Disable.Fanart)")

    def test_standalone_negation_keeps_the_bang(self):
        # User-reported regression: !Skin.HasSetting(Disable.Fanart) was being
        # sent as Skin.HasSetting(Disable.Fanart), inverting the result.
        line = '<visible>!Skin.HasSetting(Disable.Fanart)</visible>'
        cursor = self._at_substr(line, "HasSetting")
        self.assertEqual(extract_expression_at_offset(line, cursor), "!Skin.HasSetting(Disable.Fanart)")

    def test_negation_in_first_clause_kept(self):
        line = '<visible>!Window.IsActive(home) + Skin.HasSetting(x)</visible>'
        cursor = self._at_substr(line, "IsActive")
        self.assertEqual(extract_expression_at_offset(line, cursor), "!Window.IsActive(home)")

    def test_compound_or_scopes_per_clause(self):
        line = '<visible>Window.IsActive(home) | Window.IsActive(music)</visible>'
        cursor = self._at_substr(line, "music")
        self.assertEqual(extract_expression_at_offset(line, cursor), "Window.IsActive(music)")

    def test_grouping_brackets_define_sub_expression(self):
        # `[A | B]` is a top-level group — hovering inside scopes to it.
        line = '<visible>[Window.IsActive(home) | Window.IsActive(music)] + Skin.HasSetting(x)</visible>'
        cursor = self._at_substr(line, "music")
        self.assertEqual(extract_expression_at_offset(line, cursor), "Window.IsActive(music)")

    def test_nested_function_call_does_not_split_at_inner_plus(self):
        # `+` inside parens is part of an operand (Kodi quirk: not common but
        # should not be treated as a top-level boundary).
        line = '<visible>String.IsEqual(Foo,Bar) + Skin.HasSetting(x)</visible>'
        cursor = self._at_substr(line, "Foo")
        self.assertEqual(extract_expression_at_offset(line, cursor), "String.IsEqual(Foo,Bar)")

    def test_nested_localize_does_not_split_at_inner_brackets(self):
        # `[`/`]` inside parens are part of `$LOCALIZE[N]`, not boundaries.
        line = '<visible>String.IsEqual(Label,$LOCALIZE[40211]) + Skin.HasSetting(x)</visible>'
        cursor = self._at_substr(line, "40211")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "String.IsEqual(Label,$LOCALIZE[40211])",
        )

    def test_doubly_nested_parens_track_depth_correctly(self):
        line = '<visible>String.IsEmpty(ListItem.Art(fanart)) + Foo</visible>'
        cursor = self._at_substr(line, "fanart")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "String.IsEmpty(ListItem.Art(fanart))",
        )

    def test_condition_attribute_scopes_to_clause(self):
        line = '<value condition="ListItem.IsFolder + String.IsEqual(ListItem.Label,$LOCALIZE[40211])">x</value>'
        cursor = self._at_substr(line, "IsEqual")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "String.IsEqual(ListItem.Label,$LOCALIZE[40211])",
        )


class KodiGrammarSourceAnchoredTests(KodiDevKitTestCase):
    """Tests that pin the helper's behavior to specific lines of Kodi's
    InfoExpression / GUIInfoLabel / GUIInfoManager source. If Kodi changes the
    grammar, these are what to update.
    """

    def _at(self, line, needle):
        idx = line.index(needle)
        return idx + len(needle) // 2

    # InfoExpression.cpp:125-139 — operator set is exactly [ ] ! + |
    # Anything else (including ( ) , . $ etc.) is part of an operand.

    def test_paren_is_operand_char_not_a_boundary(self):
        # InfoExpression.cpp:276 — non-operator chars accumulate into operand
        line = '<v>String.IsEqual(A,B) + Window.IsActive(home)</v>'
        cursor = self._at(line, "IsEqual")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "String.IsEqual(A,B)",
        )

    def test_comma_is_operand_char_not_a_boundary(self):
        line = '<v>String.IsEqual(Foo,Bar)</v>'
        cursor = self._at(line, "Foo")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "String.IsEqual(Foo,Bar)",
        )

    def test_dot_dollar_are_operand_chars(self):
        line = '<v>$INFO[ListItem.Label]</v>'
        cursor = self._at(line, "Label")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "$INFO[ListItem.Label]",
        )

    # GUIInfoManager.cpp:11441 — Register() calls ReplaceLocalize on the
    # expression before the boolean parser sees it.
    # GUIInfoLabel.cpp:276-282 — ReplaceLocalize handles $LOCALIZE and $NUMBER.

    def test_localize_brackets_are_masked(self):
        line = '<v>String.IsEqual(Label,$LOCALIZE[40211]) + Skin.HasSetting(x)</v>'
        cursor = self._at(line, "40211")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "String.IsEqual(Label,$LOCALIZE[40211])",
        )

    def test_number_brackets_are_masked(self):
        line = '<v>Integer.IsGreater(Container.NumItems,$NUMBER[5])</v>'
        cursor = self._at(line, "NumItems")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "Integer.IsGreater(Container.NumItems,$NUMBER[5])",
        )

    def test_nested_localize_inside_localize_stays_intact(self):
        # GUIInfoLabel.cpp:204 — FindEndBracket counts nesting
        line = '<v>String.IsEqual(L,$LOCALIZE[$LOCALIZE[40211]])</v>'
        cursor = self._at(line, "40211")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "String.IsEqual(L,$LOCALIZE[$LOCALIZE[40211]])",
        )

    def test_two_separate_localize_macros_in_one_clause(self):
        line = '<v>String.IsEqual($LOCALIZE[1],$LOCALIZE[2])</v>'
        cursor = self._at(line, "IsEqual")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "String.IsEqual($LOCALIZE[1],$LOCALIZE[2])",
        )

    # InfoExpression.cpp:131-132, 266-267 — `!` is a unary prefix that toggles
    # the invert flag for the operand it precedes.

    def test_single_bang_round_trips(self):
        # Without the `!`, the boolean Kodi returns is INVERTED — silent bug.
        line = '<v>!Skin.HasSetting(Disable.Fanart)</v>'
        cursor = self._at(line, "HasSetting")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "!Skin.HasSetting(Disable.Fanart)",
        )

    def test_double_bang_round_trips(self):
        # Per Kodi: !!A == A, but we must echo the user's literal text.
        line = '<v>!!Skin.HasSetting(x)</v>'
        cursor = self._at(line, "HasSetting")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "!!Skin.HasSetting(x)",
        )

    def test_bang_with_whitespace_before_operand(self):
        # InfoExpression.cpp:271-272 — whitespace skipped between operators.
        line = '<v>!  Skin.HasSetting(x)</v>'
        cursor = self._at(line, "HasSetting")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "!  Skin.HasSetting(x)",
        )

    def test_bang_clause_after_and(self):
        line = '<v>A + !Skin.HasSetting(x) + B</v>'
        cursor = self._at(line, "HasSetting")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "!Skin.HasSetting(x)",
        )

    def test_neighbour_clause_does_not_steal_bang(self):
        line = '<v>!A + B</v>'
        cursor = self._at(line, "B")
        self.assertEqual(extract_expression_at_offset(line, cursor), "B")

    # InfoExpression.cpp:127-130 — [ and ] are grouping operators at top level.

    def test_grouping_brackets_are_top_level_boundaries(self):
        line = '<v>[A | B] + C</v>'
        cursor = self._at(line, "A")
        self.assertEqual(extract_expression_at_offset(line, cursor), "A")

    def test_clause_after_close_bracket(self):
        line = '<v>[A | B] + Skin.HasSetting(x)</v>'
        cursor = self._at(line, "HasSetting")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "Skin.HasSetting(x)",
        )

    def test_bang_before_grouping(self):
        # Real Kodi syntax: ![A + B] negates the group.
        # Cursor on `A` — we return just `A` (the leaf), not the whole group.
        line = '<v>![A + B]</v>'
        cursor = self._at(line, "A")
        self.assertEqual(extract_expression_at_offset(line, cursor), "A")

    # GUIInfoManager.cpp:11450 — InfoExpression vs InfoSingle dispatch on
    # presence of any of |+[]! — single-condition strings have no operators.

    def test_single_condition_with_no_operators(self):
        # Goes through InfoSingle path in Kodi; for us, just one operand.
        line = '<v>Window.IsActive(home)</v>'
        cursor = self._at(line, "home")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "Window.IsActive(home)",
        )

    # Real Estuary patterns (.claude/kodi-source/addons/skin.estuary/xml/)

    def test_estuary_compound_with_negation_at_end(self):
        line = '<visible>ListItem.IsFolder + String.IsEqual(ListItem.Label,$LOCALIZE[40211]) + String.IsEmpty(ListItem.Art(fanart)) + !Skin.HasSetting(Disable.Fanart)</visible>'
        cursor = self._at(line, "Disable")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "!Skin.HasSetting(Disable.Fanart)",
        )

    def test_estuary_chained_negations(self):
        line = '<visible>!String.IsEmpty(Control.GetLabel(4410)) + !Skin.HasSetting(Disable.Extrafanart) + !Skin.HasSetting(Disable.Fanart)</visible>'
        cursor = self._at(line, "Extrafanart")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "!Skin.HasSetting(Disable.Extrafanart)",
        )

    def test_estuary_container_property_with_param(self):
        line = '<visible>String.IsEqual(Container(9000).ListItem.Property(id),$PARAM[id])</visible>'
        cursor = self._at(line, "Property")
        self.assertEqual(
            extract_expression_at_offset(line, cursor),
            "String.IsEqual(Container(9000).ListItem.Property(id),$PARAM[id])",
        )
