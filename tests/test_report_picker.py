"""Tests for the entries the open-report picker lists."""

import importlib
import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_hover  # noqa: F401  installs the sublime stubs and the KodiDevKit package

commands = importlib.import_module("KodiDevKit.commands")


class TestReportEntry(unittest.TestCase):
    """Skin name and date read from a report's file name."""

    def setUp(self):
        """Set up a temp folder for report files."""
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        """Tear down the temp folder."""
        self.temp_dir.cleanup()

    def report(self, name):
        """Write an empty report file in the temp folder and return its path."""
        path = os.path.join(self.temp_dir.name, name)
        open(path, "w").close()
        return path

    def test_date_and_skin_come_from_the_name(self):
        """The timestamp the report was saved under is the date shown, the rest the skin."""
        entry = commands._report_entry(self.report("Aeon_Nox_SiLVO_20261016_144353.html"))

        self.assertEqual(entry["skin_name"], "Aeon Nox SiLVO")
        self.assertEqual(entry["date"], "2026-10-16 14:43:53")
        self.assertEqual(entry["timestamp"], datetime(2026, 10, 16, 14, 43, 53))

    def test_name_without_a_timestamp_falls_back_to_modified_time(self):
        """A file not named by the report writer shows its whole name and when it last changed."""
        path = self.report("notes.html")
        os.utime(path, (0, datetime(2025, 1, 2, 3, 4, 5).timestamp()))

        entry = commands._report_entry(path)

        self.assertEqual(entry["skin_name"], "notes")
        self.assertEqual(entry["date"], "2025-01-02 03:04:05")


if __name__ == "__main__":
    unittest.main()
