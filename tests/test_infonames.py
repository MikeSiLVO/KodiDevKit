"""Info names read from a Kodi source tree at kodi_path, in place of the bundled list."""

import os
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.infonames import from_tree, names_of
from libs.infoprovider.provider import InfoProvider

SOURCE = """constexpr std::array<InfoMap, 1> listitem_labels = {{
    {"newinfo", LISTITEM_NEWINFO},
}};
int CGUIInfoManager::TranslateSingleString(const std::string &strCondition, bool &listItemDependent)
{
  if (cat.name == "listitem")
    for (const auto& i : listitem_labels) {}
}
int CGUIInfoManager::TranslateListItem(const Property& cat, const Property& prop)
"""
ADDON_XML = ('<addon id="skin.test" version="1.0.0"><requires><import addon="xbmc.gui" version="5.17.0"/>'
             '</requires><extension point="xbmc.gui.skin"><res folder="16x9" default="true"/></extension>'
             '</addon>')
HOME_XML = '<window><controls><control type="image"><visible>ListItem.NewInfo</visible></control></controls></window>'


class TestInfoNames(unittest.TestCase):
    """Reading the table from a source tree, and the checks using it when kodi_path has one."""

    def setUp(self):
        """Set up a temp folder for a source tree and a skin."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = self.temp_dir.name

    def tearDown(self):
        """Tear down the temp folder."""
        self.temp_dir.cleanup()

    def write(self, rel, text):
        """Write the text to the path under the temp folder, making its folders."""
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def unknown_infos(self, kodi_path):
        """Unknown infos reported for a skin using ListItem.NewInfo, and its provider."""
        self.write("skin.test/addon.xml", ADDON_XML)
        self.write("skin.test/16x9/Home.xml", HOME_XML)
        provider = InfoProvider()
        provider.settings = {"kodi_path": kodi_path}
        provider.init_addon(os.path.join(self.root, "skin.test"))
        return [r["subject"] for r in provider.check_values() if r["rule"] == "xml.unknown-info"], provider

    def test_names_come_from_the_dispatch_arrays(self):
        """An array the dispatch searches gives its names to the category that searches it."""
        self.assertEqual(names_of(SOURCE)["categories"]["listitem"], ["newinfo"])

    def test_an_array_the_categories_do_not_map_is_refused(self):
        """Source dispatching an array kdk does not know raises instead of guessing."""
        with self.assertRaisesRegex(ValueError, "unmapped array strange"):
            names_of(SOURCE.replace("listitem_labels) {}", "listitem_labels) {}\n    for (const auto& i : strange) {}"))

    def test_a_folder_without_source_gives_nothing(self):
        """A folder that is no source tree, such as an installed Kodi, gives no table."""
        self.assertIsNone(from_tree(self.root))

    def test_a_source_tree_at_kodi_path_knows_its_own_infos(self):
        """With a source tree at kodi_path an info only it defines is known, and the run says so."""
        self.write("xbmc/xbmc/GUIInfoManager.cpp", SOURCE)
        found, provider = self.unknown_infos(os.path.join(self.root, "xbmc"))
        self.assertEqual((found, provider.info_source), ([], "checkout"))

    def test_without_one_the_bundled_list_reports_it(self):
        """With no source tree the same info is unknown to the bundled list."""
        found, provider = self.unknown_infos("")
        self.assertEqual((found, provider.info_source), (["ListItem.NewInfo"], "snapshot"))

    def test_source_that_cannot_be_read_falls_back_with_a_notice(self):
        """A source tree kdk cannot map leaves the bundled list in use and says why."""
        self.write("xbmc/xbmc/GUIInfoManager.cpp", "int main() {}")
        found, provider = self.unknown_infos(os.path.join(self.root, "xbmc"))
        self.assertEqual((found, provider.info_source), (["ListItem.NewInfo"], "snapshot"))
        self.assertTrue(any("could not be read" in n for n in provider.addon.notices))


if __name__ == "__main__":
    unittest.main()
