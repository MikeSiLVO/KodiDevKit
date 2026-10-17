"""Tests for the installable add-on zip."""

import os
import sys
import tempfile
import unittest
import zipfile

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.utils.files import make_archive

FILES = ("addon.xml", "1080i/Home.xml", "media/Textures.xbt", "media/loose.png", "themes/Blue/a.png",
         ".git/config", "fonts/.hidden", "old.zip", "lib/cache.pyc", "colors/defaults.xml",
         "validation_report.html")


class TestMakeArchive(unittest.TestCase):
    """What the zip holds and how it is laid out."""

    def setUp(self):
        """Set up an add-on folder holding one file of each kind."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addon = os.path.join(self.temp_dir.name, ".kodi", "addons", "skin.test")
        for name in FILES:
            path = os.path.join(self.addon, *name.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(name)

    def tearDown(self):
        """Tear down the temp folder."""
        self.temp_dir.cleanup()

    def names(self, archive):
        """Entry names of the zip at the path."""
        with zipfile.ZipFile(archive) as zf:
            return sorted(zf.namelist())

    def test_make_archive_keeps_shipped_files_under_one_top_folder(self):
        """Every entry sits in one folder named for the add-on, as install from zip needs."""
        archive = os.path.join(self.temp_dir.name, "skin.test-1.0.0.zip")

        make_archive(self.addon, archive, "skin.test", leave_out=("validation_report.html",))

        self.assertEqual(self.names(archive), ["skin.test/1080i/Home.xml", "skin.test/addon.xml",
                                               "skin.test/colors/defaults.xml", "skin.test/media/Textures.xbt"])

    def test_make_archive_inside_the_addon_leaves_itself_out(self):
        """A zip saved into the add-on folder, in any extension case, is not packed into itself."""
        archive = os.path.join(self.addon, "skin.test-1.0.0.ZIP")

        make_archive(self.addon, archive, "skin.test")

        self.assertNotIn("skin.test/skin.test-1.0.0.ZIP", self.names(archive))


if __name__ == "__main__":
    unittest.main()
