"""Tests for the TexturePacker runner."""

import os
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.skin.textures import texturepacker

FAKE_PACKER = """#!{python}
import sys
args = sys.argv[1:]
if "fail" in args[args.index("-input") + 1]:
    sys.exit(3)
with open(args[args.index("-output") + 1], "w") as f:
    f.write("xbt")
"""


@unittest.skipIf(os.name == "nt", "the stand-in packer is a script run through its shebang")
class TestTexturePacker(unittest.TestCase):
    """Where the bundle is written, and what the run reports back."""

    def setUp(self):
        """Set up a media folder and an executable stand-in for TexturePacker."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.media = os.path.join(self.temp_dir.name, "media")
        os.makedirs(self.media)
        self.packer = os.path.join(self.temp_dir.name, "packer")
        with open(self.packer, "w", encoding="utf-8") as f:
            f.write(FAKE_PACKER.format(python=sys.executable))
        os.chmod(self.packer, 0o755)

    def tearDown(self):
        """Tear down the temp folder."""
        self.temp_dir.cleanup()

    def test_writes_textures_xbt_into_the_folder_by_default(self):
        """With no path given, the bundle is written as the folder's own Textures.xbt."""
        self.assertTrue(texturepacker(self.media, {"texturepacker_path": self.packer}))
        self.assertTrue(os.path.isfile(os.path.join(self.media, "Textures.xbt")))

    def test_writes_to_the_path_given(self):
        """A theme bundle goes where the caller says, such as media/<theme>.xbt."""
        theme = os.path.join(self.temp_dir.name, "themes", "Blue")
        os.makedirs(theme)
        output = os.path.join(self.media, "Blue.xbt")

        self.assertTrue(texturepacker(theme, {"texturepacker_path": self.packer}, output_path=output))
        self.assertTrue(os.path.isfile(output))
        self.assertFalse(os.path.exists(os.path.join(theme, "Blue.xbt")))

    def test_no_packer_set_is_reported(self):
        """With no texturepacker_path set the run is reported as a failure."""
        self.assertFalse(texturepacker(self.media, {}))

    def test_failed_run_is_reported(self):
        """A packer that exits non-zero is reported as a failure."""
        failing = os.path.join(self.temp_dir.name, "fail")
        os.makedirs(failing)

        self.assertFalse(texturepacker(failing, {"texturepacker_path": self.packer}))

    def test_missing_packer_is_reported(self):
        """A texturepacker_path that does not exist is reported as a failure."""
        self.assertFalse(texturepacker(self.media, {"texturepacker_path": self.packer + "-gone"}))


if __name__ == "__main__":
    unittest.main()
