"""Unit tests for `kdk-ignore` suppression comments."""

import os
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.infoprovider import InfoProvider
from libs.validation.suppress import scan

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

    def test_unrelated_comment_ignored(self):
        path = self.write('<window>\n<!-- just a note -->\n<label>x</label>\n</window>\n')

        found = scan([path])

        self.assertFalse(found)
        self.assertFalse(found.muted("Labels", path, 3))


class TestSuppressionApplied(unittest.TestCase):
    """End to end: a directive removes the finding from the check result."""

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

    def labels(self):
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

    def test_file_directive_silences_the_category(self):
        self.write_window("Home.xml", (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!-- kdk-ignore-file: labels -->\n'
            '<window>\n    <controls>\n        <control type="label">\n'
            '            <label>Player.Playing</label>\n'
            '        </control>\n    </controls>\n</window>\n'
        ))

        issues = self.labels()

        self.assertFalse(
            any("Player.Playing" in i["message"] for i in issues),
            f"Directive should have silenced the label, got: {issues}",
        )

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


if __name__ == "__main__":
    unittest.main()
