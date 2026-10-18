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
        """Hiding include warnings drops the include warning but keeps the include error."""
        txt = T.generate_text_report(_report(), hide_include_warnings=True)
        self.assertEqual(_count(txt), 3)
        self.assertNotIn("from include 'X'", txt)
        self.assertIn("include error", txt)

    def test_combined_filters(self):
        txt = T.generate_text_report(
            _report(), hidden_severities={"warning"}, hide_include_warnings=True
        )
        self.assertEqual(_count(txt), 2)

    def test_filter_note_present_when_filtering(self):
        """The filter note shows only when something is filtered."""
        txt = T.generate_text_report(_report(), hidden_severities={"warning"})
        self.assertIn("Filters:", txt)
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


class TestQuickPanelFiltering(unittest.TestCase):
    """`InfoProvider` applies the include-warning filter the panel has no render step for."""

    def _provider(self, hide):
        from libs.infoprovider.provider import InfoProvider

        provider = InfoProvider()
        provider.settings = {"hide_include_warnings": hide}
        provider.check_variables = lambda *a, **k: _report()["all_issues"]["XML Validation"]
        return provider

    def test_include_warning_hidden_by_default(self):
        rows = self._provider(True).get_check_listitems("variable")
        self.assertEqual([r["message"] for r in rows],
                         ["plain error", "plain warning", "include error"])

    def test_setting_off_keeps_everything(self):
        rows = self._provider(False).get_check_listitems("variable")
        self.assertEqual(len(rows), 4)


def _muted_report():
    """Report whose second warning a `kdk-ignore` comment on the line above mutes."""
    report = _report()
    rows = report["all_issues"]["XML Validation"]
    rows[1] = {**rows[1], "muted": {"line": 10, "reason": "debug overlay"}}
    return report


def _html(all_issues):
    """HTML report text for the issues."""
    import tempfile
    out = os.path.join(tempfile.mkdtemp(), "r.html")
    H.generate_html_report(all_issues, "skin.test", "/skin", output_path=out, server_port=48273)
    with open(out, encoding="utf-8") as f:
        return f.read()


class TestMutedRows(unittest.TestCase):
    """Muted rows, counted apart in both reports and kept out of the quick panel."""

    def test_text_export_lists_muted_row_with_its_note(self):
        """The row stays, its note follows it, and the totals count it apart."""
        txt = T.generate_text_report(_muted_report())
        self.assertEqual(_count(txt), 4)
        self.assertIn("Muted by kdk-ignore at line 10: debug overlay", txt)
        self.assertIn("Total Issues: 3", txt)
        self.assertIn("Muted: 1", txt)

    def test_text_export_hides_muted_when_asked(self):
        """The muted filter drops the row and says so."""
        txt = T.generate_text_report(_muted_report(), hide_muted=True)
        self.assertEqual(_count(txt), 3)
        self.assertNotIn("plain warning", txt)
        self.assertIn("muted issues hidden", txt)

    def test_html_marks_muted_row_and_counts_it_apart(self):
        """Rows carry the class and note, with a separate total and a legend row."""
        doc = _html(_muted_report()["all_issues"])
        self.assertEqual(doc.count(' muted"'), 2)
        self.assertEqual(doc.count("Muted by kdk-ignore at line 10: debug overlay"), 2)
        self.assertIn('<div class="stat-number stat-number-muted">1</div>', doc)
        self.assertIn('<div class="stat-number stat-number-warning">1</div>', doc)
        self.assertIn("toggleMuted(this)", doc)
        self.assertIn("<strong>Muted</strong>", doc)

    def test_html_without_muted_rows_has_no_muted_controls(self):
        """A report with nothing muted shows no muted button, total, column or legend row."""
        doc = _html(_report()["all_issues"])
        self.assertNotIn("toggleMuted(this)", doc)
        self.assertNotIn('class="stat-number stat-number-muted"', doc)
        self.assertNotIn("<th>Muted</th>", doc)
        self.assertNotIn("<strong>Muted</strong>", doc)

    def test_quick_panel_drops_muted_rows(self):
        """Muted rows stay out of the quick panel, the skinner's own view."""
        from libs.infoprovider.provider import InfoProvider

        provider = InfoProvider()
        provider.settings = {"hide_include_warnings": False}
        provider.check_variables = lambda *a, **k: _muted_report()["all_issues"]["XML Validation"]
        rows = provider.get_check_listitems("variable")
        self.assertNotIn("plain warning", [r["message"] for r in rows])
        self.assertEqual(len(rows), 3)


if __name__ == "__main__":
    unittest.main()
