"""
Tests that the validation index lists findings in file order, whatever order the threads finish.
"""

import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.infoprovider.provider import InfoProvider
from libs.skin.index import SkinIndex


ADDON_XML = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test Skin" provider-name="test">
    <requires>
        <import addon="xbmc.gui" version="5.16.0"/>
    </requires>
    <extension point="xbmc.gui.skin" defaultthemename="Textures.xbt" debugging="false">
        <res width="1920" height="1080" aspect="16x9" default="true" folder="16x9" />
    </extension>
</addon>"""


class TestIndexOrder(unittest.TestCase):
    """The index merges per-file results in file order."""

    def setUp(self):
        """Create a skin whose windows each refer to a different control id."""
        self.test_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.test_dir, "16x9"))
        with open(os.path.join(self.test_dir, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(ADDON_XML)
        with open(os.path.join(self.test_dir, "16x9", "Includes.xml"), "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n<includes>\n</includes>')
        for name, ref in (("A.xml", 101), ("B.xml", 102), ("C.xml", 103)):
            with open(os.path.join(self.test_dir, "16x9", name), "w", encoding="utf-8") as f:
                f.write(f"""<?xml version="1.0" encoding="UTF-8"?>
<window><controls><control type="button"><onclick>SetFocus({ref})</onclick></control></controls></window>""")

    def tearDown(self):
        """Remove the temporary skin."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_first_file_finishing_last_keeps_file_order(self):
        """Slowing the first file's worker must not move its ids behind the others."""
        original = SkinIndex._process_window_file

        def slow_first(self, path, folder):
            if os.path.basename(path) == "A.xml":
                time.sleep(0.2)
            return original(self, path, folder)

        provider = InfoProvider()
        provider.settings = {}
        provider.init_addon(self.test_dir)
        with mock.patch.object(SkinIndex, "_process_window_file", slow_first):
            index = provider.addon.index_builder.build_validation_index()  # type: ignore[union-attr]

        refs = [r for r in index["ids_referenced"]["16x9"] if r in ("101", "102", "103")]
        self.assertEqual(refs, ["101", "102", "103"])


if __name__ == "__main__":
    unittest.main()
