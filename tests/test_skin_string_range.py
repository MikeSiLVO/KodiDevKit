"""Kodi 22 reads a skin's own strings only in 31000-31999; Omega reads any id."""

import os
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.infoprovider.provider import InfoProvider

PO = ('msgid ""\nmsgstr ""\n\nmsgctxt "#31000"\nmsgid "in range"\nmsgstr ""\n\n'
      'msgctxt "#32000"\nmsgid "out of range"\nmsgstr ""\n\nmsgctxt "#186"\nmsgid "mine"\nmsgstr ""\n')


class TestSkinStringRange(unittest.TestCase):
    """Out-of-range skin ids are errors on Piers and fine on Omega."""

    def _messages(self, gui):
        with tempfile.TemporaryDirectory() as path:
            os.makedirs(os.path.join(path, "16x9"))
            os.makedirs(os.path.join(path, "language", "resource.language.en_gb"))
            files = {
                "addon.xml": f'<addon id="skin.t" version="1.0.0"><requires><import addon="xbmc.gui" '
                             f'version="{gui}"/></requires><extension point="xbmc.gui.skin">'
                             '<res folder="16x9" default="true"/></extension></addon>',
                "language/resource.language.en_gb/strings.po": PO,
                "16x9/Home.xml": '<window><controls><control type="label"><label>$LOCALIZE[31000]</label></control>'
                                 '<control type="label"><label>$LOCALIZE[32000]</label></control>'
                                 '<control type="label"><label>$LOCALIZE[186]</label></control></controls></window>',
            }
            for rel, text in files.items():
                with open(os.path.join(path, rel), "w", encoding="utf-8") as f:
                    f.write(text)
            provider = InfoProvider()
            provider.settings = {}
            provider.init_addon(path)
            return sorted(r["message"] for r in provider.get_check_listitems("label") if r.get("file"))

    def test_piers(self):
        self.assertEqual(self._messages("5.18.0"), [
            "Skin string 186 is outside 31000-31999, so Kodi 22 shows Kodi's own string for it",
            "Skin string 32000 is outside 31000-31999, so Kodi 22 shows nothing for it",
        ])

    def test_omega(self):
        self.assertEqual(self._messages("5.17.0"), [])


if __name__ == "__main__":
    unittest.main()
