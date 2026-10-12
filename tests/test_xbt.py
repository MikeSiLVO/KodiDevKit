"""Images in a Textures.xbt are checked against its index; one beside source images is flagged."""

import os
import struct
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.infoprovider.provider import InfoProvider
from libs.utils.files import read_xbt_names

ADDON_XML = ('<addon id="skin.test" version="1.0.0"><requires>'
             '<import addon="xbmc.gui" version="5.18.0"/></requires>'
             '<extension point="xbmc.gui.skin"><res folder="16x9" default="true"/></extension></addon>')


def _xbt(names):
    """Bytes of a version 2 bundle holding one frame per name."""
    out = b"XBTF2" + struct.pack("<I", len(names))
    for name in names:
        out += name.encode().ljust(256, b"\0") + struct.pack("<II", 0, 1)
        out += struct.pack("<IIIQQIQ", 1, 1, 0, 0, 0, 0, 0)
    return out


class TestXbt(unittest.TestCase):
    """Built skins resolve media/ against the bundle; sources beside it are a warning."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = self.temp_dir.name
        os.makedirs(os.path.join(self.path, "16x9"))
        os.makedirs(os.path.join(self.path, "media"))
        self._write("addon.xml", ADDON_XML)
        self._write("16x9/Home.xml", '<window><controls><control type="image"><texture>Icons/A.png</texture>'
                                     '</control><control type="image"><texture>icons/b.png</texture></control>'
                                     '</controls></window>')

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write(self, rel, data):
        with open(os.path.join(self.path, rel), "wb" if isinstance(data, bytes) else "w") as f:
            f.write(data)

    def _messages(self):
        provider = InfoProvider()
        provider.settings = {}
        provider.init_addon(self.path)
        return sorted(r["message"] for r in provider.get_check_listitems("image") if r.get("file"))

    def test_reader(self):
        self._write("media/Textures.xbt", _xbt(["icons/a.png", "Icons\\C.png"]))
        self.assertEqual(read_xbt_names(os.path.join(self.path, "media", "Textures.xbt")),
                         {"icons/a.png", "icons/c.png"})

    def test_built_skin_resolves_against_bundle(self):
        self._write("media/Textures.xbt", _xbt(["icons/a.png"]))
        self.assertEqual(self._messages(), ["Missing image 'icons/b.png'"])

    def test_bundle_beside_sources(self):
        """An image only in a bundle beside loose images warns that a repo build drops it."""
        self._write("media/Textures.xbt", _xbt(["icons/a.png", "icons/b.png"]))
        os.makedirs(os.path.join(self.path, "media", "icons"))
        self._write("media/icons/b.png", b"png")
        self.assertEqual(self._messages(), [
            "'Icons/A.png' is only in Textures.xbt, not among the loose images. Kodi finds it, but the "
            "Kodi repo expects loose images and packs Textures.xbt itself, so a repo build drops it",
            "Kodi repo: Textures.xbt ships beside the source images in media/",
        ])

    def test_theme_bundle_beside_sources(self):
        self._write("media/Dark.xbt", _xbt(["icons/a.png"]))
        os.makedirs(os.path.join(self.path, "media", "icons"))
        self._write("media/icons/a.png", b"png")
        self._write("media/icons/b.png", b"png")
        self._write("media/Broken.xbt", b"not a bundle")
        self.assertEqual(sorted(m for m in self._messages() if ".xbt" in m), [
            "Broken.xbt is not a texture bundle Kodi can read",
            "Kodi repo: Dark.xbt ships beside the source images in media/",
        ])

    def test_unreadable_bundle(self):
        self._write("media/Textures.xbt", b"not a bundle")
        self.assertIn("Textures.xbt is not a texture bundle Kodi can read", self._messages())

    def test_addon_window_and_full_path_are_not_checked(self):
        self._write("media/Textures.xbt", _xbt(["icons/a.png", "icons/b.png"]))
        self._write("16x9/script-example-main.xml", '<window><controls><control type="image">'
                                                    '<texture>addonart.png</texture></control></controls></window>')
        self._write("16x9/MyVideoNav.xml", '<window><controls><control type="image">'
                                           '<texture>/usr/share/kodi/media/x.png</texture></control>'
                                           '</controls></window>')
        provider = InfoProvider()
        provider.settings = {}
        provider.load_data("piers")
        provider.init_addon(self.path)
        self.assertEqual([r["message"] for r in provider.get_check_listitems("image") if r.get("file")], [])


if __name__ == "__main__":
    unittest.main()
