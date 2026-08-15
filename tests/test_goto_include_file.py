"""Jumping from an `<include file="..."/>` reference to the file it names."""

import os
import sys
import shutil
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from libs.infoprovider.navigation import NavigationMixin


class _Addon:
    def __init__(self, path):
        self.path = path


class _Nav(NavigationMixin):
    """NavigationMixin with only the pieces `_xml_file_in_folder` touches."""

    def __init__(self, addon):
        self.addon = addon


class TestXmlFileLookup(unittest.TestCase):
    """`_xml_file_in_folder` resolves a reference to a real file, case-sensitively."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "16x9"))
        for name in ("Includes_Maps.xml", "Home.xml"):
            with open(os.path.join(self.root, "16x9", name), "w", encoding="utf8") as f:
                f.write("<includes/>")
        self.nav = _Nav(_Addon(self.root))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_resolves_an_existing_file(self):
        got = self.nav._xml_file_in_folder("Includes_Maps.xml", "16x9")
        self.assertEqual(got, os.path.join(self.root, "16x9", "Includes_Maps.xml"))

    def test_wrong_case_does_not_resolve(self):
        # Kodi reads loose files through the OS, so this reference breaks on Linux even
        # though Windows would open it. Refusing the jump is the signal.
        self.assertIsNone(self.nav._xml_file_in_folder("includes_maps.xml", "16x9"))

    def test_missing_file_does_not_resolve(self):
        self.assertIsNone(self.nav._xml_file_in_folder("Includes_Nope.xml", "16x9"))

    def test_missing_folder_does_not_raise(self):
        self.assertIsNone(self.nav._xml_file_in_folder("Home.xml", "nosuchfolder"))

    def test_no_folder_does_not_raise(self):
        self.assertIsNone(self.nav._xml_file_in_folder("Home.xml", ""))


if __name__ == "__main__":
    unittest.main()
