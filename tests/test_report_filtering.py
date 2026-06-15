"""Tests for the text-export filters that mirror the HTML report toggles."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from libs.reporting import text as T
from libs.reporting import html as H


def _report():
    return {
        "skin_name": "skin.test",
        "skin_path": "/skin",
        "timestamp": "now",
        "all_issues": {
            "XML Validation": [
                {"file": "/skin/16x9/Home.xml", "line": 10, "message": "plain error", "severity": "error"},
                {"file": "/skin/16x9/Home.xml", "line": 11, "message": "plain warning", "severity": "warning"},
                {"file": "/skin/16x9/Home.xml", "line": 12, "message": "tag (from include 'X')",
                 "severity": "warning", "include_name": "X"},
                {"file": "/skin/16x9/Home.xml", "line": 13, "message": "include error",
                 "severity": "error", "include_name": "X"},
            ],
        },
    }


def _count(txt):
    return sum(1 for line in txt.splitlines() if line.strip().startswith("Line "))


class TestExportFiltering(unittest.TestCase):
    def test_no_filters_exports_everything(self):
        self.assertEqual(_count(T.generate_text_report(_report())), 4)

    def test_hide_warnings_keeps_only_errors(self):
        txt = T.generate_text_report(_report(), hidden_severities={"warning"})
        self.assertEqual(_count(txt), 2)
        self.assertNotIn("plain warning", txt)

    def test_hide_include_warnings_drops_only_include_warning(self):
        txt = T.generate_text_report(_report(), hide_include_warnings=True)
        self.assertEqual(_count(txt), 3)
        self.assertNotIn("from include 'X'", txt)
        # Include-sourced *error* is kept.
        self.assertIn("include error", txt)

    def test_combined_filters(self):
        txt = T.generate_text_report(
            _report(), hidden_severities={"warning"}, hide_include_warnings=True
        )
        self.assertEqual(_count(txt), 2)

    def test_filter_note_present_when_filtering(self):
        txt = T.generate_text_report(_report(), hidden_severities={"warning"})
        self.assertIn("Filters:", txt)
        # No note when nothing is filtered.
        self.assertNotIn("Filters:", T.generate_text_report(_report()))

    def test_issue_visible_predicate(self):
        inc_warn = {"severity": "warning", "include_name": "X"}
        self.assertFalse(T.issue_visible(inc_warn, frozenset(), True))
        self.assertTrue(T.issue_visible(inc_warn, frozenset(), False))
        inc_err = {"severity": "error", "include_name": "X"}
        self.assertTrue(T.issue_visible(inc_err, frozenset(), True))


class TestHtmlIncludeTagging(unittest.TestCase):
    def test_include_warning_rows_tagged_and_toggle_present(self):
        import tempfile
        out = os.path.join(tempfile.mkdtemp(), "r.html")
        H.generate_html_report(_report()["all_issues"], "skin.test", "/skin", output_path=out, server_port=48273)
        doc = open(out, encoding="utf-8").read()
        # Include warning tagged on its category row and file list item (2 elements).
        self.assertEqual(doc.count('from-include"'), 2)
        self.assertIn("toggleIncludeWarnings(this)", doc)
        self.assertIn('id="export-link"', doc)

    def test_default_toggle_states(self):
        """Errors + Warnings shown by default; include warnings hidden."""
        import tempfile
        out = os.path.join(tempfile.mkdtemp(), "r.html")
        H.generate_html_report(_report()["all_issues"], "skin.test", "/skin", output_path=out, server_port=48273)
        doc = open(out, encoding="utf-8").read()
        self.assertIn("const hiddenSeverities = new Set();", doc)
        self.assertIn("let includeWarningsHidden = true;", doc)
        self.assertIn('class="sev-toggle active" data-severity="warning"', doc)
        self.assertIn('class="sev-toggle" data-filter="include"', doc)


if __name__ == "__main__":
    unittest.main()
