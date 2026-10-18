"""Tests for split_top_level_commas, which splits the infolabel and condition prompts' input."""

from tests.base import KodiDevKitTestCase
from libs.utils.expressions import split_top_level_commas


class SplitTopLevelCommasTests(KodiDevKitTestCase):
    """Cases for splitting prompt input at commas outside any brackets."""

    def test_localize_inside_string_isequal_stays_intact(self):
        """A comma inside an info's parentheses does not split it, $LOCALIZE[] included."""
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
        """The prefix and suffix commas inside $INFO[] do not split the label."""
        expr = "$INFO[ListItem.Label, , - ]"
        self.assertEqual(split_top_level_commas(expr), [expr])

    def test_two_info_macros_with_internal_commas(self):
        a = "$INFO[ListItem.Year, (, )]"
        b = "$INFO[ListItem.Genre,  - ]"
        self.assertEqual(split_top_level_commas(f"{a},{b}"), [a, b])


    def test_grouping_brackets_at_top_level(self):
        """A top-level [A | B] group is one piece."""
        expr = "[Window.IsActive(home) | Window.IsActive(music)]"
        self.assertEqual(split_top_level_commas(expr), [expr])

    def test_and_or_not_operators_are_not_separators(self):
        expr = "!Window.IsActive(home) + Window.IsVisible(MyDialog) | Skin.HasSetting(x)"
        self.assertEqual(split_top_level_commas(expr), [expr])


    def test_unmatched_open_paren_keeps_input_as_one_piece(self):
        """An unclosed parenthesis keeps the input whole, for Kodi to reject, not in fragments."""
        expr = "String.IsEqual(ListItem.Label,foo"
        self.assertEqual(split_top_level_commas(expr), [expr])

    def test_unmatched_close_paren_does_not_underflow_depth(self):
        """A stray `)` does not stop the commas after it from splitting."""
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
