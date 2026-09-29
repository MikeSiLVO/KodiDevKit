"""Label ids and text in viewtype, fallback and idloc, and $LOCALIZE anywhere, are checked."""

import os
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.infoprovider.provider import InfoProvider

PO = 'msgid ""\nmsgstr ""\n\nmsgctxt "#31000"\nmsgid "defined"\nmsgstr ""\n'


class TestLabelAttrs(unittest.TestCase):
    """The attributes Kodi reads as labels get the same checks as label tags."""

    def test_attributes_and_localize_anywhere(self):
        with tempfile.TemporaryDirectory() as path:
            os.makedirs(os.path.join(path, "16x9"))
            os.makedirs(os.path.join(path, "language", "resource.language.en_gb"))
            files = {
                "addon.xml": '<addon id="skin.t" version="1.0.0"><requires><import addon="xbmc.gui" '
                             'version="5.18.0"/></requires><extension point="xbmc.gui.skin">'
                             '<res folder="16x9" default="true"/></extension></addon>',
                "language/resource.language.en_gb/strings.po": PO,
                "16x9/Font.xml": '<fonts><fontset id="Default" idloc="31555"/></fonts>',
                "16x9/Home.xml": '<window><controls><control type="list"><viewtype label="Big List">list</viewtype>'
                                 '</control><control type="label"><label fallback="31999">$INFO[ListItem.Label]</label>'
                                 '</control><control type="button"><onclick>Notification($LOCALIZE[31777],x)</onclick>'
                                 '<label>$LOCALIZE[31000]</label></control></controls></window>',
            }
            for rel, text in files.items():
                with open(os.path.join(path, rel), "w", encoding="utf-8") as f:
                    f.write(text)
            provider = InfoProvider()
            provider.settings = {}
            provider.init_addon(path)
            messages = sorted(r["message"] for r in provider.get_check_listitems("label") if r.get("file"))
        self.assertEqual(messages, [
            "Label in attribute label not translated: Big List",
            "Label not defined: 31555",
            "Label not defined: 31777",
            "Label not defined: 31999",
        ])


if __name__ == "__main__":
    unittest.main()
