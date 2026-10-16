"""Unit tests for `kdk-ignore` suppression comments."""

import os
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.infoprovider.provider import InfoProvider
from libs.validation.suppress import muted_note, scan

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
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def write(self, text):
        path = os.path.join(self.temp_dir.name, "Home.xml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_bare_line_directive_mutes_every_category(self):
        path = self.write('<window>\n<label>x</label> <!-- kdk-ignore -->\n</window>\n')

        found = scan([path])

        self.assertTrue(found.muted("Labels", path, 2))
        self.assertTrue(found.muted("Images", path, 2))

    def test_line_directive_limited_to_named_categories(self):
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
        path = self.write('<!-- kdk-ignore-file: labels -->\n<window>\n<label>x</label>\n</window>\n')

        found = scan([path])

        self.assertTrue(found.muted("Labels", path, 3))
        self.assertTrue(found.muted("Labels", path, 999))
        self.assertFalse(found.muted("Images", path, 3))

    def test_multiple_categories(self):
        path = self.write('<!-- kdk-ignore-file: labels, images -->\n<window/>\n')

        found = scan([path])

        self.assertTrue(found.muted("Labels", path, 1))
        self.assertTrue(found.muted("Images", path, 1))
        self.assertFalse(found.muted("Fonts", path, 1))

    def test_category_name_spelling_is_forgiving(self):
        """`XML Validation` is the display name, so accept the spellings a skinner would type."""
        path = self.write('<!-- kdk-ignore-file: xml-validation -->\n<window/>\n')

        found = scan([path])

        self.assertTrue(found.muted("XML Validation", path, 1))

    def test_case_insensitive_directive(self):
        path = self.write('<!-- KDK-IGNORE-FILE: Labels -->\n<window/>\n')

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
        path = self.write('<window>\n<!-- just a note -->\n<label>x</label>\n</window>\n')

        found = scan([path])

        self.assertFalse(found)
        self.assertFalse(found.muted("Labels", path, 3))


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
        self.temp_dir = tempfile.TemporaryDirectory()
        self.skin_path = self.temp_dir.name
        self.xml_dir = os.path.join(self.skin_path, "16x9")
        os.makedirs(self.xml_dir, exist_ok=True)
        with open(os.path.join(self.skin_path, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(ADDON_XML)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_window(self, name, text):
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
            '<!-- kdk-ignore-file: labels -->\n'
            '<window>\n    <controls>\n        <control type="label">\n'
            '            <label>Player.Playing</label>\n'
            '        </control>\n    </controls>\n</window>\n'
        ))

        issues = self.labels()

        self.assertTrue(_muted(issues, "Player.Playing"), f"Directive should have marked the label, got: {issues}")

    def test_directive_does_not_leak_to_other_files(self):
        self.write_window("Home.xml", (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!-- kdk-ignore-file: labels -->\n'
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

        self.write_window("Home.xml", "<!-- kdk-ignore-file: labels -->\n" + window)
        provider.addon.update_xml_files()
        provider.addon.reload(path)

        self.assertTrue(_muted(self.labels(provider), "Player.Playing"))

    def test_directive_in_a_subfolder_window_applies(self):
        """A window file below a subfolder of the xml folder is scanned for directives too."""
        os.makedirs(os.path.join(self.xml_dir, "Custom"))
        self.write_window(os.path.join("Custom", "Extra.xml"), (
            '<!-- kdk-ignore-file: labels -->\n'
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


if __name__ == "__main__":
    unittest.main()
