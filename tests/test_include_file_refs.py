"""Resolving `<include file="..."/>` references: the jump target and the issue raised when it breaks."""

import os
import sys
import shutil
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from libs.infoprovider import InfoProvider
from libs.skin.skin import Skin
from libs.validation.include import check_include_file_ref, resolve_include_file

ADDON_XML = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test Skin" provider-name="test">
    <extension point="xbmc.gui.skin" defaultthemename="Textures.xbt">
        <res width="1920" height="1080" aspect="16x9" default="true" folder="16x9" />
    </extension>
</addon>"""


class _Addon:
    def __init__(self, path, xml_folders):
        self.path = path
        self.xml_folders = xml_folders


class _Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "16x9"))
        for name in ("Includes_Maps.xml", "Home.xml"):
            with open(os.path.join(self.root, "16x9", name), "w", encoding="utf8") as f:
                f.write("<includes/>")
        self.addon = _Addon(self.root, ["16x9"])

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)


class TestResolve(_Base):
    """`resolve_include_file` reports the path only when the name matches the disk exactly."""

    def test_exact_name_resolves(self):
        path, actual = resolve_include_file(self.addon, "16x9", "Includes_Maps.xml")
        self.assertEqual(path, os.path.join(self.root, "16x9", "Includes_Maps.xml"))
        self.assertIsNone(actual)

    def test_wrong_case_reports_the_real_name(self):
        path, actual = resolve_include_file(self.addon, "16x9", "includes_maps.xml")
        self.assertIsNone(path)
        self.assertEqual(actual, "Includes_Maps.xml")

    def test_absent_file_resolves_to_nothing(self):
        self.assertEqual(resolve_include_file(self.addon, "16x9", "Nope.xml"), (None, None))

    def test_unreadable_folder_is_skipped_not_raised(self):
        self.assertEqual(resolve_include_file(self.addon, "nosuchfolder", "Nope.xml"), (None, None))

    def test_other_resolution_folder_is_searched(self):
        # Kodi falls back to the default resolution when the closest one lacks the file.
        os.makedirs(os.path.join(self.root, "1080i"))
        other = os.path.join(self.root, "1080i", "Shared.xml")
        with open(other, "w", encoding="utf8") as f:
            f.write("<includes/>")
        self.addon.xml_folders = ["16x9", "1080i"]
        path, _ = resolve_include_file(self.addon, "16x9", "Shared.xml")
        self.assertEqual(path, other)


class TestIssue(_Base):
    """`check_include_file_ref` raises an issue only for a reference Kodi cannot open."""

    def test_good_reference_is_silent(self):
        self.assertIsNone(check_include_file_ref(self.addon, "16x9", "Includes_Maps.xml"))

    def test_case_mismatch_names_the_real_file(self):
        issue = check_include_file_ref(self.addon, "16x9", "includes_maps.xml")
        assert issue is not None
        self.assertIn("Case mismatch for 'includes_maps.xml'", issue["message"])
        self.assertIn("Includes_Maps.xml", issue["message"])
        self.assertEqual(issue["severity"], "error")

    def test_missing_file_is_reported(self):
        issue = check_include_file_ref(self.addon, "16x9", "Nope.xml")
        assert issue is not None
        self.assertIn("Missing include file 'Nope.xml'", issue["message"])

    def test_surrounding_whitespace_is_trimmed(self):
        self.assertIsNone(check_include_file_ref(self.addon, "16x9", "  Includes_Maps.xml  "))

    def test_runtime_generated_file_is_not_flagged(self):
        # script.skinshortcuts writes this at runtime, so it is absent from a shipped skin.
        self.assertIsNone(
            check_include_file_ref(self.addon, "16x9", "script-skinshortcuts-includes.xml"))

    def test_reference_built_from_a_parameter_is_skipped(self):
        self.assertIsNone(check_include_file_ref(self.addon, "16x9", "$PARAM[layout].xml"))

    def test_empty_reference_is_skipped(self):
        self.assertIsNone(check_include_file_ref(self.addon, "16x9", ""))


class TestCheckFileReportsIt(unittest.TestCase):
    """The per-file check reports a broken reference, so one call site covers save and the full report."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.test_dir, "16x9"))
        with open(os.path.join(self.test_dir, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(ADDON_XML)
        self._write("Includes_Maps.xml", "<includes/>")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _write(self, name, body):
        path = os.path.join(self.test_dir, "16x9", name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        return path

    def _issues(self, path):
        provider = InfoProvider()
        provider.addon = Skin(path=self.test_dir, settings={})
        provider.settings = {}
        return [i for i in (provider.check_file(path) or [])
                if "Case mismatch" in i["message"] or "Missing include file" in i["message"]]

    def test_mis_cased_reference_is_located(self):
        path = self._write("Includes.xml",
                           '<includes>\n<include file="includes_maps.xml" />\n</includes>')
        issues = self._issues(path)
        self.assertEqual(len(issues), 1)
        self.assertIn("Case mismatch for 'includes_maps.xml'", issues[0]["message"])
        self.assertIn("Includes_Maps.xml", issues[0]["message"])
        self.assertEqual(issues[0]["line"], 2)
        self.assertEqual(issues[0]["severity"], "error")

    def test_matching_reference_is_silent(self):
        path = self._write("Includes.xml",
                           '<includes><include file="Includes_Maps.xml" /></includes>')
        self.assertEqual(self._issues(path), [])

    def test_commented_out_reference_is_ignored(self):
        path = self._write("Includes.xml",
                           '<includes><!-- <include file="Gone.xml" /> --></includes>')
        self.assertEqual(self._issues(path), [])

    def test_reference_from_a_window_file_is_checked(self):
        # ResolveIncludes (GUIIncludes.cpp:377-379) loads file= from any resolved node,
        # so a window can pull in a definitions file too.
        path = self._write("Home.xml", '<window>\n<include file="Nope.xml" />\n</window>')
        issues = self._issues(path)
        self.assertEqual(len(issues), 1)
        self.assertIn("Missing include file 'Nope.xml'", issues[0]["message"])

    def test_reported_once(self):
        # check_values runs check_file over every file, so a second call site would double it.
        self._write("Includes.xml",
                    '<includes><include file="includes_maps.xml" /></includes>')
        provider = InfoProvider()
        provider.addon = Skin(path=self.test_dir, settings={})
        provider.settings = {}
        found = [i for i in provider.check_values() if "Case mismatch for" in i["message"]]
        self.assertEqual(len(found), 1)


if __name__ == "__main__":
    unittest.main()
