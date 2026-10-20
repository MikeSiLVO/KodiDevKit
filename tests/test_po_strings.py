"""Broken strings in strings.po: what Kodi reads of them and which check reports them."""

import os
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.addon.translations import broken_strings
from libs.infoprovider.provider import InfoProvider

HEADER = 'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n'


def entry(string_id, *lines):
    """One strings.po entry for the id, from its msgid and msgstr lines."""
    return f'msgctxt "#{string_id}"\n' + "\n".join(lines) + "\n\n"


class TestBrokenStrings(unittest.TestCase):
    """Faults reported once per field, each with what Kodi shows for it."""

    def faults(self, text, source=True):
        """The faults in the text, line and string id dropped where they add nothing."""
        return [(problem, effect) for _line, _id, problem, effect in broken_strings(text, source)]

    def test_well_formed_file_has_none(self):
        text = HEADER + entry(31000, 'msgid ""', '"one "', '"two"', 'msgstr ""')
        self.assertEqual(self.faults(text), [])

    def test_strings_side_by_side_are_valid(self):
        self.assertEqual(self.faults(HEADER + entry(31000, 'msgid "a" "b"', 'msgstr ""')), [])

    def test_broken_header_counts_once_and_kodi_ignores_it(self):
        text = 'msgid ""\nmsgstr ""\n"Project-Id-Version: x\n"\n"Language: en_GB\n"\n\n'
        self.assertEqual(list(broken_strings(text, True)), [(3, None, "unclosed", None)])

    def test_source_msgid_reads_empty_or_cut(self):
        self.assertEqual(self.faults(entry(31000, 'msgid "Sort', '"', 'msgstr ""')), [("unclosed", "empty")])
        self.assertEqual(self.faults(entry(31000, 'msgid ""', '"Sort', '"', 'msgstr ""')),
                         [("unclosed", "empty")])
        self.assertEqual(self.faults(entry(31000, 'msgid ""', '"Sort "', '"by', 'msgstr ""')),
                         [("unclosed", "cut")])

    def test_source_msgstr_and_msgctxt_are_not_read(self):
        self.assertEqual(self.faults(entry(31000, 'msgid "Ok"', 'msgstr "x')), [("unclosed", None)])
        self.assertEqual(self.faults('msgctxt "#31000\nmsgid "Ok"\nmsgstr ""\n'), [("unclosed", None)])

    def test_translation_falls_back_to_english(self):
        self.assertEqual(self.faults(entry(31000, 'msgid "Ok"', 'msgstr "Gut'), source=False),
                         [("unclosed", "english")])
        self.assertEqual(self.faults(entry(31000, 'msgid ""', '"Ok "', '"x', 'msgstr "Gut"'), source=False),
                         [("unclosed", "english")])

    def test_translation_msgid_broken_on_its_first_line_keeps_the_translation(self):
        self.assertEqual(self.faults(entry(31000, 'msgid "Ok', 'msgstr "Gut"'), source=False),
                         [("unclosed", None)])

    def test_spaces_outside_the_quotes_only_matter_where_kodi_reads(self):
        self.assertEqual(self.faults(entry(31000, 'msgid "Ok" ', 'msgstr ""')), [("spaces", "empty")])
        self.assertEqual(self.faults(entry(31000, 'msgid  "Ok"', 'msgstr ""')), [("spaces", "empty")])
        self.assertEqual(self.faults(entry(31000, 'msgid "Ok"', 'msgstr "" ')), [])

    def test_unescaped_quote_is_read_whole_by_kodi(self):
        self.assertEqual(self.faults(entry(31000, 'msgid "Press "OK" now"', 'msgstr ""')), [("text", None)])

    def test_escaped_quote_at_the_end_is_read_whole_by_kodi(self):
        self.assertEqual(self.faults(entry(31000, 'msgid "Ok\\"', 'msgstr ""')), [("unclosed", None)])


class TestBrokenStringRows(unittest.TestCase):
    """Broken string rows: label errors where Kodi misreads, file integrity rows for the rest."""

    def test_rows(self):
        files = {
            "addon.xml": '<addon id="skin.t" version="1.0.0"><requires><import addon="xbmc.gui" '
                         'version="5.17.0"/></requires><extension point="xbmc.gui.skin">'
                         '<res folder="16x9" default="true"/></extension></addon>',
            "16x9/Home.xml": "<window><controls/></window>",
            "language/resource.language.en_gb/strings.po": (
                'msgid ""\nmsgstr ""\n"Language: en_GB\n"\n\n'
                + entry(31000, 'msgid "Sort', '"', 'msgstr ""')),
            "language/resource.language.de_de/strings.po": (
                HEADER + entry(31000, 'msgid "Sort"', 'msgstr "Nach "A" sortieren"')),
        }
        with tempfile.TemporaryDirectory() as path:
            for rel, text in files.items():
                os.makedirs(os.path.dirname(os.path.join(path, rel)), exist_ok=True)
                with open(os.path.join(path, rel), "w", encoding="utf-8") as f:
                    f.write(text)
            provider = InfoProvider()
            provider.settings = {}
            provider.init_addon(path)
            rows = provider.get_check_listitems("filecheck") + provider.get_check_listitems("label")
            found = sorted((r["rule"], r["severity"], os.path.basename(os.path.dirname(r["file"])), r["line"],
                            r["subject"]) for r in rows if r.get("rule", "").split(".")[-1] in (
                                "broken-string", "po-unclosed", "po-trailing-text"))
        self.assertEqual(found, [
            ("files.po-trailing-text", "warning", "resource.language.de_de", 7, "31000"),
            ("files.po-unclosed", "error", "resource.language.en_gb", 3, ""),
            ("labels.broken-string", "error", "resource.language.en_gb", 7, "31000"),
        ])


if __name__ == "__main__":
    unittest.main()
