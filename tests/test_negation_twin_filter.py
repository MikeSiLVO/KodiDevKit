"""The debug print drops the `![cond]` probe twin the hover adds."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from libs.kodi.jsonrpc import _without_negation_twins


class TestNegationTwinFilter(unittest.TestCase):

    def test_twin_is_dropped(self):
        result = {"result": {"Player.HasVideo": False, "![Player.HasVideo]": True}}
        self.assertEqual(_without_negation_twins(result), {"result": {"Player.HasVideo": False}})

    def test_user_query_without_twins_is_untouched(self):
        result = {"result": {"Skin.HasSetting(a)": True, "Player.HasVideo": False}}
        self.assertEqual(_without_negation_twins(result), result)

    def test_standalone_negation_is_kept(self):
        # A real query for `![X]` with no bare `X` present is a genuine result.
        result = {"result": {"![Player.HasVideo]": True}}
        self.assertEqual(_without_negation_twins(result), result)

    def test_non_dict_passes_through(self):
        self.assertEqual(_without_negation_twins(None), None)
        self.assertEqual(_without_negation_twins({"error": {}}), {"error": {}})


if __name__ == "__main__":
    unittest.main()
