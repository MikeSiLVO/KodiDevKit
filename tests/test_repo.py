"""Kodi repo rules from kodi-addon-checker, reported as labeled warnings."""

import os
import struct
import sys
import tempfile
import unittest
import zlib

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.infoprovider.provider import InfoProvider


def _png(width, height):
    """Smallest valid PNG header of the given size."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr
            + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr)))


GOOD_PO = 'msgid ""\nmsgstr ""\n\nmsgctxt "#31000"\nmsgid "a"\nmsgstr ""\n'


class TestRepo(unittest.TestCase):
    """Each rule in isolation against an otherwise clean skin."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp_dir.name, "skin.test")
        os.makedirs(os.path.join(self.path, "16x9"))
        os.makedirs(os.path.join(self.path, "resources"))
        self._write("resources/icon.png", _png(256, 256))
        self._write("language/resource.language.en_gb/strings.po", GOOD_PO)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write(self, rel, data):
        path = os.path.join(self.path, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb" if isinstance(data, bytes) else "w", encoding=None if isinstance(data, bytes) else "utf-8") as f:
            f.write(data)

    def _addon(self, version="1.0.0", news="Fixes", assets="<icon>resources/icon.png</icon>", addon_id="skin.test",
               gui="5.18.0"):
        """Write a skin addon.xml that passes every rule unless a field is overridden."""
        self._write("addon.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n<addon id="{addon_id}" version="{version}" '
                                 f'name="Test" provider-name="me"><requires><import addon="xbmc.gui" version="{gui}"/>'
                                 '</requires><extension point="xbmc.gui.skin" debugging="false">'
                                 '<res width="1920" height="1080" aspect="16:9" default="true" folder="16x9"/>'
                                 '</extension><extension point="xbmc.addon.metadata">'
                                 '<summary lang="en_GB">s</summary><description lang="en_GB">d</description>'
                                 '<platform>all</platform><license>GPL-2.0-or-later</license>'
                                 f'<news>{news}</news><assets>{assets}</assets></extension></addon>')

    def _messages(self, settings=None):
        """Sorted repo check messages for the test skin."""
        provider = InfoProvider()
        provider.settings = settings or {}
        provider.init_addon(self.path)
        return sorted(r["message"] for r in provider.get_check_listitems("repo") if r.get("file"))

    def test_clean_skin(self):
        self._addon()
        self.assertEqual(self._messages(), [])

    def test_forced_release_that_cannot_load_the_skin(self):
        """The repo check reports an xbmc.gui import the release named in the settings refuses."""
        self._addon(gui="5.18.0")
        self.assertEqual(self._messages({"kodi_release": "omega"}),
                         ["Kodi repo: xbmc.gui 5.18.0 is newer than Omega's 5.17.0, so Omega will not load it"])
        self._addon(gui="5.16.0")
        self.assertEqual(self._messages({"kodi_release": "piers"}),
                         ["Kodi repo: xbmc.gui 5.16.0 is older than the 5.17.0 Piers still accepts, "
                          "so Piers will not load it"])
        self._addon(gui="5.17.0")
        self.assertEqual(self._messages({"kodi_release": "piers"}), [])

    def test_addon_xml_rules(self):
        self._addon(version="1.0", news="x" * 1501, addon_id="skin.other")
        messages = self._messages()
        self.assertIn("Kodi repo: addon id skin.other does not match folder skin.test", messages)
        self.assertIn("Kodi repo: <news> is 1501 characters, over the 1500 limit", messages)
        self._addon(version="v1")
        self.assertIn("Kodi repo: version 'v1' is not major.minor.revision (e.g. 1.0.0)", self._messages())

    def test_artwork(self):
        self._write("fanart.jpg", b"\xff\xd8")
        self._write("resources/big.png", _png(300, 300))
        self._addon(assets="<icon>resources/big.png</icon><screenshot>missing.jpg</screenshot><banner/>")
        self.assertEqual(self._messages(), [
            "Kodi repo: empty <banner> tag in <assets>",
            "Kodi repo: fanart.jpg should be declared in addon.xml <assets>",
            "Kodi repo: icon is 300x300, the repo accepts 256x256 or 512x512",
            "Kodi repo: screenshot missing.jpg does not exist",
        ])

    def test_language_rules(self):
        self._addon()
        self._write("language/English/strings.po", GOOD_PO)
        self._write("language/resource.language.de_de/strings.po",
                    'msgctxt "#31000"\nmsgid "a"\nmsgstr ""\n\nmsgctxt "#31000"\nmsgid "b"\nmsgstr ""\n')
        self.assertEqual(self._messages(), [
            "Kodi repo: language/English uses the old language folder layout; use resource.language.<code>",
            'Kodi repo: language/resource.language.de_de/strings.po is missing the msgid "" / msgstr "" header',
            "Kodi repo: string id 31000 is defined twice (first on line 1)",
        ])

    def test_po_bom_and_a_msgid_without_value_are_reported(self):
        """A BOM reads as the checker reports it, and a msgid with no value is named."""
        self._addon()
        self._write("language/resource.language.de_de/strings.po", b"\xef\xbb\xbf" + GOOD_PO.encode())
        self._write("language/resource.language.fr_fr/strings.po", GOOD_PO + 'msgctxt "#31001"\nmsgid\n')
        self.assertEqual(self._messages(), [
            "Kodi repo: language/resource.language.de_de/strings.po starts with a BOM (byte order mark)",
            "Kodi repo: language/resource.language.fr_fr/strings.po: msgid has no quoted value",
        ])

    def test_po_syntax_error_names_the_line_and_what_it_follows(self):
        """A bare syntax error names what is wrong: an entry out of order, or an unreadable line."""
        self._addon()
        self._write("language/resource.language.cs_cz/strings.po",
                    GOOD_PO + 'msgctxt "#31087"\nmsgstr "Prapor"\nmsgstr "Banner"\n')
        self._write("language/resource.language.de_de/strings.po", GOOD_PO + "Banner Wall\n")
        self.assertEqual(self._messages(), [
            'Kodi repo: language/resource.language.cs_cz/strings.po: msgstr cannot follow msgctxt "#31087"',
            "Kodi repo: language/resource.language.de_de/strings.po: a line that is not a msgctxt, msgid, msgstr, "
            "comment or quoted text: Banner Wall",
        ])

    def test_nested_addon_reported_once_and_its_files_skipped(self):
        """A folder with its own addon.xml is one warning; nothing inside it is checked."""
        self._addon()
        self._write("addons/script.x/addon.xml", "<addon/>")
        self._write("addons/script.x/default.py", "pass")
        self._write("addons/script.x/tests/helper/addon.xml", "<addon/>")
        self._write("addons/script.x/art.psd", b"8BPS")
        self.assertEqual(self._messages(), [
            "Kodi repo: addons/script.x is a separate add-on inside this one. The Kodi repo takes one "
            "add-on per submission; outside the repo this works",
        ])

    def test_file_types(self):
        """A file ending outside the whitelist is reported; dotfiles and .xbt files are not."""
        self._addon()
        self._write("media/logo.psd", b"8BPS")
        self._write(".gitignore", "*.pyc")
        self._write("media/Textures.xbt", b"XBTF")
        self.assertEqual(self._messages(), ["Kodi repo: media/logo.psd has a file ending the add-on checker does not whitelist, "
                                            "so a repo PR gets a warning for it"])


if __name__ == "__main__":
    unittest.main()
