"""
Tests for ``utils.split_top_level_commas`` — the splitter that backs the
``XBMC.GetInfoBooleans`` / ``XBMC.GetInfoLabels`` JSON-RPC prompts.

These prompts let the user paste comma-separated InfoLabels or boolean
conditions. A naive ``str.split(',')`` corrupts every expression that
contains a comma inside parentheses or square brackets, e.g.::

    String.IsEqual(ListItem.Label,$LOCALIZE[40211])
    Container(50).ListItem.Property(foo)
    $INFO[ListItem.Label, , - ]

The splitter must only break on commas at depth 0. Cases below are mined
from real ``skin.estuary`` XML and the Kodi C++ docs; the bug that triggered
this test (``$LOCALIZE[40211]`` getting truncated to ``$LOCALIZE``) is the
first regression case.
"""

from tests.base import KodiDevKitTestCase
from libs.utils import split_top_level_commas


class SplitTopLevelCommasTests(KodiDevKitTestCase):

    # The original bug: $LOCALIZE[N] inside an operand was severed at the
    # comma, sending two corrupted halves to Kodi.
    def test_localize_inside_string_isequal_stays_intact(self):
        expr = "String.IsEqual(ListItem.Label,$LOCALIZE[40211])"
        self.assertEqual(split_top_level_commas(expr), [expr])

    def test_simple_no_commas(self):
        self.assertEqual(
            split_top_level_commas("Window.IsActive(home)"),
            ["Window.IsActive(home)"],
        )

    def test_plain_comma_separated_labels(self):
        self.assertEqual(
            split_top_level_commas("ListItem.Title,ListItem.Year,ListItem.Genre"),
            ["ListItem.Title", "ListItem.Year", "ListItem.Genre"],
        )

    def test_whitespace_around_separators_is_stripped(self):
        self.assertEqual(
            split_top_level_commas("  Foo ,  Bar  ,Baz"),
            ["Foo", "Bar", "Baz"],
        )

    def test_empty_input(self):
        self.assertEqual(split_top_level_commas(""), [])

    def test_only_whitespace(self):
        self.assertEqual(split_top_level_commas("   "), [])

    def test_only_commas(self):
        self.assertEqual(split_top_level_commas(",,,"), [])

    def test_trailing_comma_is_ignored(self):
        self.assertEqual(
            split_top_level_commas("Foo,Bar,"),
            ["Foo", "Bar"],
        )

    def test_leading_comma_is_ignored(self):
        self.assertEqual(
            split_top_level_commas(",Foo,Bar"),
            ["Foo", "Bar"],
        )


    def test_string_isequal_with_two_nested_calls(self):
        expr = "String.IsEqual(Container(11).CurrentItem,Container(11).NumItems)"
        self.assertEqual(split_top_level_commas(expr), [expr])

    def test_string_isequal_with_property_and_param(self):
        expr = "String.IsEqual(Container(9000).ListItem.Property(id),$PARAM[id])"
        self.assertEqual(split_top_level_commas(expr), [expr])

    def test_string_isequal_with_localize_and_literal(self):
        expr = "String.IsEqual(Container(5000).ListItem.Label,$LOCALIZE[184])"
        self.assertEqual(split_top_level_commas(expr), [expr])

    def test_two_full_boolean_expressions(self):
        a = "String.IsEqual(ListItem.Label,$LOCALIZE[40211])"
        b = "Window.IsActive(home)"
        self.assertEqual(split_top_level_commas(f"{a},{b}"), [a, b])

    def test_three_full_boolean_expressions(self):
        a = "String.Contains(Container(50).ListItem.Title,foo)"
        b = "!Window.IsActive(home)"
        c = "Skin.HasSetting(MyToggle)"
        self.assertEqual(split_top_level_commas(f"{a},{b},{c}"), [a, b, c])


    def test_info_macro_with_prefix_suffix(self):
        # commas inside $INFO[] must not split the label
        expr = "$INFO[ListItem.Label, , - ]"
        self.assertEqual(split_top_level_commas(expr), [expr])

    def test_two_info_macros_with_internal_commas(self):
        a = "$INFO[ListItem.Year, (, )]"
        b = "$INFO[ListItem.Genre,  - ]"
        self.assertEqual(split_top_level_commas(f"{a},{b}"), [a, b])


    def test_grouping_brackets_at_top_level(self):
        # [A | B] is a single expression; outer brackets are operator-level
        # but our splitter treats them as depth-tracking, which is correct:
        # commas inside [ ] groups should still not split.
        expr = "[Window.IsActive(home) | Window.IsActive(music)]"
        self.assertEqual(split_top_level_commas(expr), [expr])

    def test_and_or_not_operators_are_not_separators(self):
        expr = "!Window.IsActive(home) + Window.IsVisible(MyDialog) | Skin.HasSetting(x)"
        self.assertEqual(split_top_level_commas(expr), [expr])


    def test_unmatched_open_paren_keeps_input_as_one_piece(self):
        # Better to send the whole broken thing to Kodi (which will error)
        # than to silently fragment it.
        expr = "String.IsEqual(ListItem.Label,foo"
        self.assertEqual(split_top_level_commas(expr), [expr])

    def test_unmatched_close_paren_does_not_underflow_depth(self):
        # Stray ) shouldn't make subsequent commas fail to split.
        self.assertEqual(
            split_top_level_commas("foo),bar"),
            ["foo)", "bar"],
        )

    def test_deeply_nested_parens_track_depth_correctly(self):
        expr = "String.IsEqual(Container(50).ListItem.Property(Foo(Bar(Baz))),x)"
        self.assertEqual(split_top_level_commas(expr), [expr])

    def test_mixed_paren_and_bracket_nesting(self):
        a = "String.IsEqual(Container(9000).ListItem.Property(id),$LOCALIZE[40211])"
        b = "$INFO[Container(50).ListItem.Title, [, ]]"
        self.assertEqual(split_top_level_commas(f"{a},{b}"), [a, b])
