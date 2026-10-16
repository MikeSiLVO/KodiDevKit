"""Round and square brackets in a condition close in order, each by its own kind."""

import os
import sys
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.utils.xml import check_brackets


class TestCheckBrackets(unittest.TestCase):
    """Balanced texts, and texts with a missing, stray or crossed bracket."""

    def test_cases(self):
        """Test each text against the verdict it should get."""
        cases = {
            "": True,
            "Player.HasVideo": True,
            "[Window.IsVisible(home) | String.IsEqual($INFO[Foo],x)] + !Player.HasVideo": True,
            "Window.IsVisible(home": False,
            "Window.IsVisible(home))": False,
            "[Window.IsVisible(home])": False,
            "]Player.HasVideo[": False,
        }
        for text, expected in cases.items():
            self.assertEqual(check_brackets(text), expected, text)


if __name__ == "__main__":
    unittest.main()
