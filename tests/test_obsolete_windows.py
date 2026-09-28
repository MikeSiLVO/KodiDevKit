"""Window files an earlier Kodi loaded, and this release does not, are reported."""

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


class TestObsoleteWindows(unittest.TestCase):
    """An obsolete file is an error naming its successor; an included one is fine."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = self.temp_dir.name
        os.makedirs(os.path.join(self.path, "16x9"))
        for rel, text in (("addon.xml", ADDON_XML),
                          ("16x9/Includes.xml", '<includes><include file="DialogKaiToast.xml"/></includes>'),
                          ("16x9/DialogKaiToast.xml", "<includes/>"),
                          ("16x9/DialogOK.xml", "<window><controls/></window>"),
                          ("16x9/DialogConfirm.xml", "<window><controls/></window>")):
            with open(os.path.join(self.path, rel), "w", encoding="utf-8") as f:
                f.write(text)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_obsolete_file_is_reported(self):
        provider = InfoProvider()
        provider.settings = {}
        provider.load_data("piers")
        provider.init_addon(self.path)
        rows = [(os.path.basename(r["file"]), r["message"], r["severity"])
                for r in provider.get_check_listitems("general") if "not a window file" in r.get("message", "")]
        self.assertEqual(rows, [("DialogOK.xml", "DialogOK.xml is not a window file in this Kodi release; "
                                                 "DialogConfirm.xml serves that window", "error")])


if __name__ == "__main__":
    unittest.main()
