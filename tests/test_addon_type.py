"""The project loads as a skin or a plain add-on by its first non-metadata extension."""

import os
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.addon.addon import Addon
from libs.skin.skin import Skin

SKIN_EXT = '<extension point="xbmc.gui.skin"><res folder="1080i" default="true"/></extension>'
SCRIPT_EXT = '<extension point="xbmc.python.script" library="default.py"/>'
META_EXT = '<extension point="xbmc.addon.metadata"><platform>all</platform></extension>'


class TestAddonType(unittest.TestCase):
    """Tests for which class Addon.by_project picks from the first non-metadata extension."""

    def _load(self, extensions):
        """Load an addon.xml importing xbmc.python and return the class by_project builds."""
        with tempfile.TemporaryDirectory() as path:
            os.makedirs(os.path.join(path, "1080i"))
            with open(os.path.join(path, "addon.xml"), "w", encoding="utf-8") as f:
                f.write('<addon id="x" version="1.0.0"><requires>'
                        '<import addon="xbmc.python" version="3.0.1"/></requires>'
                        f"{extensions}</addon>")
            return type(Addon.by_project(path, {}))

    def test_skin_that_ships_a_script_is_a_skin(self):
        """A skin importing xbmc.python for a bundled script still loads as a skin."""
        self.assertIs(self._load(META_EXT + SKIN_EXT + SCRIPT_EXT), Skin)

    def test_script_listed_first_is_an_addon(self):
        """An add-on whose first extension is a script loads as a plain add-on."""
        self.assertIs(self._load(SCRIPT_EXT + SKIN_EXT), Addon)


if __name__ == "__main__":
    unittest.main()
