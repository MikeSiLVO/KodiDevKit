"""Redundant tags against control defaults, including defaults only some skin settings load."""

import os
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.infoprovider.provider import InfoProvider

ADDON_XML = ('<addon id="skin.test" version="1.0.0"><requires>'
             '<import addon="xbmc.gui" version="5.18.0"/></requires>'
             '<extension point="xbmc.gui.skin"><res folder="16x9" default="true"/></extension></addon>')
WINDOW = ('<window><controls><include>Spacer</include>'
          '<control type="label"><height>40</height><font>small</font></control></controls></window>')
SPACER = '<include name="Spacer"><control type="image"/></include>'
SIZES = {"Small": "small", "Regular": "regular", "Large": "large"}


class TestConditionalDefaults(unittest.TestCase):
    """Redundant tags when each font size setting loads its own defaults file."""

    def setUp(self):
        """Create a skin with a defaults file per font size, each giving its own <font>."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = self.temp_dir.name
        os.makedirs(os.path.join(self.path, "16x9"))
        self._write("addon.xml", ADDON_XML)
        self._write("16x9/Home.xml", WINDOW)
        for size, font in SIZES.items():
            self._write(f"16x9/Defaults_{size}.xml", '<includes><default type="label"><height>40</height>'
                                                     f'<font>{font}</font></default></includes>')

    def tearDown(self):
        """Remove the temporary skin."""
        self.temp_dir.cleanup()

    def _write(self, rel, text):
        """Write a file into the skin folder."""
        with open(os.path.join(self.path, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def _redundant(self, include_lines):
        """Sorted redundant-tag messages for the window, Includes.xml made of include tags."""
        self._write("16x9/Includes.xml", "<includes>" + "".join(include_lines) + SPACER + "</includes>")
        provider = InfoProvider()
        provider.load_settings({})
        provider.init_addon(self.path)
        rows = provider.check_file(os.path.join(self.path, "16x9", "Home.xml")) or []
        return sorted(r["message"] for r in rows if r["message"].startswith("Redundant"))

    def test_tag_differing_between_the_files_is_kept(self):
        """A tag differing between the defaults files is kept; one they all share is redundant."""
        lines = [f'<include condition="Skin.HasSetting({size})" file="Defaults_{size}.xml"/>' for size in SIZES]
        lines.append('<include condition="![Skin.HasSetting(Small) | Skin.HasSetting(Regular) | '
                     'Skin.HasSetting(Large)]" file="Defaults_Regular.xml"/>')
        self.assertEqual(self._redundant(lines), ['Redundant <height>: same value as <default type="label">'])

    def test_state_with_no_defaults_file_keeps_every_tag(self):
        """A state that loads no defaults file keeps every tag the lone conditional file repeats."""
        self.assertEqual(self._redundant(['<include condition="Skin.HasSetting(Small)" '
                                          'file="Defaults_Small.xml"/>']), [])

    def test_window_without_includes_is_checked(self):
        """A window calling no include still gets its controls compared with their defaults."""
        self._write("16x9/Home.xml", WINDOW.replace("<include>Spacer</include>", ""))
        self.assertEqual(self._redundant(['<include file="Defaults_Small.xml"/>']), [
            'Redundant <font>: same value as <default type="label">',
            'Redundant <height>: same value as <default type="label">',
        ])

    def test_unconditional_defaults_file_still_reports(self):
        """An unconditional defaults file still reports every repeated tag."""
        self.assertEqual(self._redundant(['<include file="Defaults_Small.xml"/>']), [
            'Redundant <font>: same value as <default type="label">',
            'Redundant <height>: same value as <default type="label">',
        ])


if __name__ == "__main__":
    unittest.main()
