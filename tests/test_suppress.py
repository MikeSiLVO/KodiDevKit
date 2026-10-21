"""Unit tests for `kdk-ignore` suppression comments."""

import inspect
import os
import re
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.infoprovider.checker import CheckerMixin
from libs.infoprovider.provider import InfoProvider
from libs.validation.suppress import CHECKS, FILE_FAULT, muted_note, scan

ADDON_XML = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test Skin" provider-name="Test">
    <requires>
        <import addon="xbmc.gui" version="5.15.0"/>
    </requires>
    <extension point="xbmc.gui.skin" debugging="false">
        <res width="1920" height="1080" aspect="16:9" default="true" folder="16x9" />
    </extension>
</addon>
"""


class TestDirectiveParsing(unittest.TestCase):
    """The comment syntax itself."""

    def setUp(self):
        """Set up a temp folder for the window."""
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        """Tear down the temp folder."""
        self.temp_dir.cleanup()

    def write(self, text):
        """Write the text as Home.xml and return its path."""
        path = os.path.join(self.temp_dir.name, "Home.xml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_bare_line_directive_mutes_every_category(self):
        """A directive with no check list mutes every check on its line."""
        path = self.write('<window>\n<label>x</label> <!-- kdk-ignore -->\n</window>\n')

        found = scan([path])

        self.assertTrue(found.muted("Labels", path, 2))
        self.assertTrue(found.muted("Images", path, 2))

    def test_line_directive_limited_to_named_categories(self):
        """A check list limits the directive to those checks."""
        path = self.write('<window>\n<label>x</label> <!-- kdk-ignore: labels -->\n</window>\n')

        found = scan([path])

        self.assertTrue(found.muted("Labels", path, 2))
        self.assertFalse(found.muted("Images", path, 2))

    def test_directive_alone_on_a_line_targets_the_line_below(self):
        """So the comment can sit above a long element rather than trailing it."""
        path = self.write('<window>\n<!-- kdk-ignore: labels -->\n<label>x</label>\n</window>\n')

        found = scan([path])

        self.assertTrue(found.muted("Labels", path, 3))
        self.assertFalse(found.muted("Labels", path, 2))
        self.assertFalse(found.muted("Labels", path, 4))

    def test_inline_directive_does_not_reach_the_next_line(self):
        """An inline comment targets its own markup; the line below is untouched."""
        path = self.write('<window>\n<label>x</label> <!-- kdk-ignore: labels -->\n<label>y</label>\n</window>\n')

        found = scan([path])

        self.assertTrue(found.muted("Labels", path, 2))
        self.assertFalse(found.muted("Labels", path, 3))

    def test_indented_directive_still_counts_as_alone(self):
        """Leading whitespace is formatting, not markup."""
        path = self.write('<window>\n\t\t<!-- kdk-ignore: labels -->\n\t\t<label>x</label>\n</window>\n')

        found = scan([path])

        self.assertTrue(found.muted("Labels", path, 3))

    def test_file_directive_covers_every_line(self):
        """A file directive covers every line of its file, for the checks it names."""
        path = self.write('<!-- kdk-ignore-file: labels; debug overlay -->\n<window>\n<label>x</label>\n</window>\n')

        found = scan([path])

        self.assertTrue(found.muted("Labels", path, 3))
        self.assertTrue(found.muted("Labels", path, 999))
        self.assertFalse(found.muted("Images", path, 3))

    def test_multiple_categories(self):
        """A file directive can name several checks."""
        path = self.write('<!-- kdk-ignore-file: labels, images; debug overlay -->\n<window/>\n')

        found = scan([path])

        self.assertTrue(found.muted("Labels", path, 1))
        self.assertTrue(found.muted("Images", path, 1))
        self.assertFalse(found.muted("Fonts", path, 1))

    def test_category_name_spelling_is_forgiving(self):
        """A check name matches without regard to case, spaces or hyphens: `xml-validation`."""
        path = self.write('<!-- kdk-ignore-file: xml-validation; generated -->\n<window/>\n')

        found = scan([path])

        self.assertTrue(found.muted("XML Validation", path, 1))

    def test_case_insensitive_directive(self):
        """The directive itself is matched in any case."""
        path = self.write('<!-- KDK-IGNORE-FILE: Labels; debug overlay -->\n<window/>\n')

        found = scan([path])

        self.assertTrue(found.muted("labels", path, 1))

    def test_reason_follows_a_semicolon(self):
        """The text after `;` is the reason, kept with the line the directive sits on."""
        path = self.write('<window>\n<label>x</label> <!-- kdk-ignore: labels; debug overlay -->\n</window>\n')

        found = scan([path])

        self.assertEqual(found.muted("Labels", path, 2), {"line": 2, "reason": "debug overlay"})

    def test_directive_alone_keeps_its_own_line(self):
        """A directive covering the line below still points the reviewer at the comment itself."""
        path = self.write('<window>\n<!-- kdk-ignore: labels -->\n<label>x</label>\n</window>\n')

        found = scan([path])

        self.assertEqual(found.muted("Labels", path, 3), {"line": 2, "reason": ""})

    def test_bare_directive_takes_a_reason(self):
        """A reason needs no category list in front of it."""
        path = self.write('<window>\n<label>x</label> <!-- kdk-ignore; add-on name -->\n</window>\n')

        found = scan([path])

        self.assertEqual(found.muted("Images", path, 2), {"line": 2, "reason": "add-on name"})

    def test_file_directive_keeps_its_line_and_reason(self):
        """Every line a file directive covers points back at the one comment."""
        path = self.write('<window>\n<!-- kdk-ignore-file: labels; debug overlay -->\n<label>x</label>\n</window>\n')

        found = scan([path])

        self.assertEqual(found.muted("Labels", path, 999), {"line": 2, "reason": "debug overlay"})

    def test_line_directive_wins_over_the_file_directive(self):
        """The narrower directive gives the reason shown for its line."""
        path = self.write('<!-- kdk-ignore-file: labels; whole file -->\n<window>\n'
                          '<label>x</label> <!-- kdk-ignore: labels; this label -->\n</window>\n')

        found = scan([path])

        self.assertEqual(found.muted("Labels", path, 3), {"line": 3, "reason": "this label"})
        self.assertEqual(found.muted("Labels", path, 2), {"line": 1, "reason": "whole file"})

    def test_unrelated_comment_ignored(self):
        """An ordinary comment mutes nothing."""
        path = self.write('<window>\n<!-- just a note -->\n<label>x</label>\n</window>\n')

        found = scan([path])

        self.assertFalse(found)
        self.assertFalse(found.muted("Labels", path, 3))


class TestFaults(unittest.TestCase):
    """Directives that mute less than they say, and the warnings each one gets."""

    def setUp(self):
        """Set up a temp folder for the window."""
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        """Tear down the temp folder."""
        self.temp_dir.cleanup()

    def scan_text(self, text):
        """Scan a Home.xml holding the text; returns the path and what the scan found."""
        path = os.path.join(self.temp_dir.name, "Home.xml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path, scan([path])

    def test_file_directive_without_a_reason_mutes_nothing(self):
        """A file-wide mute has to say why, or it is reported instead of applied."""
        path, found = self.scan_text('<!-- kdk-ignore-file: labels -->\n<window/>\n')

        self.assertIsNone(found.muted("Labels", path, 2))
        self.assertEqual([(f["line"], f["message"], f["severity"]) for f in found.faults_in(path)],
                         [(1, FILE_FAULT, "warning")])

    def test_file_directive_without_checks_mutes_nothing(self):
        """A file-wide mute has to name its checks, a reason alone is not enough."""
        path, found = self.scan_text('<!-- kdk-ignore-file; debug overlay -->\n<window/>\n')

        self.assertIsNone(found.muted("Labels", path, 2))
        self.assertEqual([f["message"] for f in found.faults_in(path)], [FILE_FAULT])

    def test_complete_file_directive_has_no_fault(self):
        """Checks and a reason together make a file directive apply, with nothing reported."""
        path, found = self.scan_text('<!-- kdk-ignore-file: labels; debug overlay -->\n<window/>\n')

        self.assertTrue(found.muted("Labels", path, 2))
        self.assertEqual(found.faults_in(), [])

    def test_unknown_check_is_reported_and_known_ones_apply(self):
        """A misspelled check is named in a warning; the checks it got right still mute."""
        path, found = self.scan_text('<window>\n<label>x</label> <!-- kdk-ignore: lables, images -->\n</window>\n')

        self.assertTrue(found.muted("Images", path, 2))
        self.assertIsNone(found.muted("Labels", path, 2))
        faults = found.faults_in(path)
        self.assertEqual(len(faults), 1)
        self.assertIn("does not exist: lables.", faults[0]["message"])

    def test_only_unknown_checks_mute_nothing(self):
        """A directive whose every check is unknown never falls back to muting all of them."""
        path, found = self.scan_text('<window>\n<label>x</label> <!-- kdk-ignore: nope -->\n</window>\n')

        self.assertIsNone(found.muted("Labels", path, 2))
        self.assertFalse(found)
        self.assertEqual(len(found.faults_in(path)), 1)

    def test_faults_in_keeps_to_the_file(self):
        """Faults asked for by file come only from that file."""
        _, found = self.scan_text('<!-- kdk-ignore-file: labels -->\n<window/>\n')

        self.assertEqual(found.faults_in(os.path.join(self.temp_dir.name, "Other.xml")), [])
        self.assertEqual(len(found.faults_in()), 1)

    def test_checks_name_every_category_the_checker_marks(self):
        """Each category the checker passes for marking is one a directive can name."""
        names = set(re.findall(r'_reported\("([^"]+)"', inspect.getsource(CheckerMixin)))

        self.assertTrue(names)
        self.assertLessEqual(names, set(CHECKS))


class TestMarking(unittest.TestCase):
    """Marked copies of muted issues, and the note saying where and why they were muted."""

    def setUp(self):
        """Set up a window muting Labels on its second line."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp_dir.name, "Home.xml")
        with open(self.path, "w", encoding="utf-8") as f:
            f.write('<window>\n<label>x</label> <!-- kdk-ignore: labels; brand -->\n</window>\n')

    def tearDown(self):
        """Tear down the temp folder."""
        self.temp_dir.cleanup()

    def test_mark_copies_a_muted_issue(self):
        """The muted issue comes back as a marked copy; the input row is left alone."""
        issue = {"file": self.path, "line": 2, "message": "m"}

        marked = scan([self.path]).mark("Labels", [issue])

        self.assertEqual(marked, [{**issue, "muted": {"line": 2, "reason": "brand"}}])
        self.assertNotIn("muted", issue)

    def test_mark_leaves_other_categories_and_lines(self):
        """Only the named category on the covered line is marked."""
        issues = [{"file": self.path, "line": 2, "message": "m"}, {"file": self.path, "line": 3, "message": "n"}]

        self.assertEqual(scan([self.path]).mark("Images", issues), issues)
        self.assertNotIn("muted", scan([self.path]).mark("Labels", issues)[1])

    def test_mark_never_mutes_an_error_or_a_blocking_warning(self):
        """Errors and warnings that block a Kodi repo submission stay unmuted on a covered line."""
        issues = [{"file": self.path, "line": 2, "message": "e", "severity": "error"},
                  {"file": self.path, "line": 2, "message": "b", "severity": "warning", "rule": "files.executable"},
                  {"file": self.path, "line": 2, "message": "w", "severity": "warning", "rule": "labels.not-translated"}]

        marked = scan([self.path]).mark("Labels", issues)

        self.assertEqual([bool(i.get("muted")) for i in marked], [False, False, True])

    def test_note_gives_the_reason(self):
        """The note names the directive's line and the skin's reason."""
        note = muted_note({"muted": {"line": 7, "reason": "debug overlay"}})

        self.assertEqual(note, "Muted by kdk-ignore at line 7: debug overlay")

    def test_note_without_a_reason_says_so(self):
        """A directive with no reason is shown as having none, never given one."""
        note = muted_note({"muted": {"line": 7, "reason": ""}})

        self.assertEqual(note, "Muted by kdk-ignore at line 7, no reason given")


def _muted(issues, text):
    """Whether an issue mentioning the text is there, and marked muted."""
    return any(text in i["message"] and i.get("muted") for i in issues)


class TestSuppressionApplied(unittest.TestCase):
    """Directives marking findings in real check results, end to end."""

    def setUp(self):
        """Set up a skin folder with an addon.xml and an empty xml folder."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.skin_path = self.temp_dir.name
        self.xml_dir = os.path.join(self.skin_path, "16x9")
        os.makedirs(self.xml_dir, exist_ok=True)
        with open(os.path.join(self.skin_path, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(ADDON_XML)

    def tearDown(self):
        """Tear down the skin folder."""
        self.temp_dir.cleanup()

    def write_window(self, name, text):
        """Write a window file into the xml folder and return its path."""
        path = os.path.join(self.xml_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def labels(self, provider=None):
        """Label check rows, over a skin already loaded or else one loaded fresh."""
        if provider is None:
            provider = InfoProvider()
            provider.settings = {}
            provider.init_addon(self.skin_path)
        return provider.check_labels()

    def test_untranslated_label_reported_without_directive(self):
        """Without a directive the untranslated label is reported."""
        self.write_window("Home.xml", (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<window>\n    <controls>\n        <control type="label">\n'
            '            <label>Player.Playing</label>\n'
            '        </control>\n    </controls>\n</window>\n'
        ))

        issues = self.labels()

        self.assertTrue(
            any("Player.Playing" in i["message"] for i in issues),
            f"Expected the untranslated label to be reported, got: {issues}",
        )

    def test_file_directive_marks_the_category(self):
        """The label stays in the result, marked muted."""
        self.write_window("Home.xml", (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!-- kdk-ignore-file: labels; debug overlay -->\n'
            '<window>\n    <controls>\n        <control type="label">\n'
            '            <label>Player.Playing</label>\n'
            '        </control>\n    </controls>\n</window>\n'
        ))

        issues = self.labels()

        self.assertTrue(_muted(issues, "Player.Playing"), f"Directive should have marked the label, got: {issues}")

    def test_directive_does_not_leak_to_other_files(self):
        """A file directive marks nothing in another file."""
        self.write_window("Home.xml", (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!-- kdk-ignore-file: labels; debug overlay -->\n'
            '<window>\n    <controls>\n        <control type="label">\n'
            '            <label>Player.Playing</label>\n'
            '        </control>\n    </controls>\n</window>\n'
        ))
        self.write_window("MyVideoNav.xml", (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<window>\n    <controls>\n        <control type="label">\n'
            '            <label>Still Untranslated</label>\n'
            '        </control>\n    </controls>\n</window>\n'
        ))

        issues = self.labels()

        self.assertTrue(
            any("Still Untranslated" in i["message"] for i in issues),
            f"Other files must still be checked, got: {issues}",
        )

    def test_directive_added_after_a_check_applies(self):
        """A directive saved into a file marks its findings on the next check, without a re-init."""
        window = ('<window>\n<controls>\n<control type="label">\n<label>Player.Playing</label>\n'
                  '</control>\n</controls>\n</window>\n')
        path = self.write_window("Home.xml", window)
        provider = InfoProvider()
        provider.settings = {}
        provider.init_addon(self.skin_path)
        self.assertFalse(_muted(self.labels(provider), "Player.Playing"))

        self.write_window("Home.xml", "<!-- kdk-ignore-file: labels; debug overlay -->\n" + window)
        provider.addon.update_xml_files()
        provider.addon.reload(path)

        self.assertTrue(_muted(self.labels(provider), "Player.Playing"))

    def test_directive_in_a_subfolder_window_applies(self):
        """A window file below a subfolder of the xml folder is scanned for directives too."""
        os.makedirs(os.path.join(self.xml_dir, "Custom"))
        self.write_window(os.path.join("Custom", "Extra.xml"), (
            '<!-- kdk-ignore-file: labels; debug overlay -->\n'
            '<window>\n<controls>\n<control type="label">\n<label>Player.Playing</label>\n'
            '</control>\n</controls>\n</window>\n'
        ))

        self.assertTrue(_muted(self.labels(), "Player.Playing"))

    def test_check_file_marks_muted_rows(self):
        """The file check behind the on-save phantoms marks rows like the full check does."""
        path = self.write_window("Home.xml", (
            '<window>\n<controls>\n<control type="label">\n'
            '<!-- kdk-ignore: xml-validation; testing -->\n<bogus>1</bogus>\n'
            '</control>\n</controls>\n</window>\n'
        ))
        provider = InfoProvider()
        provider.settings = {}
        provider.init_addon(self.skin_path)

        rows = provider.check_file(path) or []

        self.assertTrue(_muted(rows, "<bogus>"), f"Expected a muted <bogus> row, got: {rows}")
        self.assertEqual([r["muted"] for r in rows if r.get("muted")], [{"line": 4, "reason": "testing"}])

    def test_faulty_directive_is_reported_by_both_file_checks(self):
        """The full check and the file check behind the phantoms both carry the fault row."""
        path = self.write_window("Home.xml", '<!-- kdk-ignore-file: labels -->\n<window/>\n')
        provider = InfoProvider()
        provider.settings = {}
        provider.init_addon(self.skin_path)

        for rows in (provider.check_values(), provider.check_file(path) or []):
            faults = [r for r in rows if r["message"] == FILE_FAULT]
            self.assertEqual([(r["file"], r["line"]) for r in faults], [(path, 1)])


if __name__ == "__main__":
    unittest.main()
