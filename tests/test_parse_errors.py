"""A window file that fails to parse is reported, not skipped."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

from lxml import etree as ET

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.infoprovider.provider import InfoProvider
from libs.utils import xml
from libs.validation.repo import ValidationRepo

ADDON_XML = ('<addon id="skin.test" version="1.0.0"><requires>'
             '<import addon="xbmc.gui" version="5.18.0"/></requires>'
             '<extension point="xbmc.gui.skin"><res folder="16x9" default="true"/></extension></addon>')


class TestParseErrors(unittest.TestCase):
    """XML Validation carries one error row per unparseable file."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = self.temp_dir.name
        os.makedirs(os.path.join(self.path, "16x9"))
        for rel, text in (("addon.xml", ADDON_XML), ("16x9/Includes.xml", "<includes/>"),
                          ("16x9/Home.xml", "<window><controls/></window>"),
                          ("16x9/MyVideoNav.xml", "<window>\n<controls>\n<label>a & b</label>\n</controls>\n</window>")):
            with open(os.path.join(self.path, rel), "w", encoding="utf-8") as f:
                f.write(text)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_broken_window_is_reported(self):
        provider = InfoProvider()
        provider.settings = {}
        provider.init_addon(self.path)
        rows = [r for r in provider.get_check_listitems("general") if r.get("message", "").startswith("XML parse")]
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["file"].endswith("MyVideoNav.xml"))
        self.assertEqual((rows[0]["line"], rows[0]["severity"]), (3, "error"))

    def _write(self, name, text):
        path = os.path.join(self.path, "16x9", name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_nested_grouplist_keeps_the_real_error(self):
        path = self._write("Nested.xml", '<window>\n<control type="grouplist">\n<control type="grouplist">\n'
                                         '<onclick>a < b</onclick>\n</control>\n</control>\n</window>')
        self.assertIsNone(xml.get_root_from_file(path))
        self.assertEqual(xml.parse_error_issue(path)["line"], 4)

    def test_escape_message_names_the_character(self):
        cases = (("<v>a=1&b=2</v>", "Unescaped '&'", True), ("<v>a & b</v>", "Unescaped '&'", True),
                 ("<v>a&nbsp;b</v>", "Unknown entity '&nbsp;'", True),
                 ("<v>a < b</v>", "Unescaped '<'", False),
                 ('<c a="x<y"/>', "Unescaped '<' in an attribute", True),
                 ('<c a="x"y"/>', "Broken attribute", False),
                 ("<v>a]]>b</v>", "Unescaped ']]>'", True))
        for n, (text, expected, loads) in enumerate(cases):
            path = self._write(f"Escape{n}.xml", f"<window>{text}</window>")
            self.assertEqual(xml.get_root_from_file(path) is not None, loads, text)
            self.assertTrue(xml.parse_error_issue(path)["message"].startswith(f"XML parse error: {expected}"), text)

    def test_kodi_tolerated_faults_load_as_tinyxml_reads_them(self):
        path = self._write("Tolerated.xml", '  <?xml version="1.0"?>\n<window>\n<!---note--->\n'
                                            '<onclick>Play(a=1&b=2)</onclick>\n<c a="x<y"/>\n</window>')
        root = xml.get_root_from_file(path)
        assert root is not None
        self.assertEqual(root.findtext("onclick"), "Play(a=1b=2)")
        self.assertEqual(root.find("c").get("a"), "x<y")
        self.assertEqual(root.find("onclick").sourceline, 4)
        self.assertEqual(xml.parse_error_issue(path)["line"], 1)

    def test_the_fault_is_the_subject(self):
        """Two different faults in one file are two findings, never one that moved."""
        subjects = []
        for text in ("<window>\n<v>a < b</v>\n</window>", "<window>\n<v>\n</window>"):
            path = self._write("Fault.xml", text)
            xml.get_root_from_file(path)
            issue = xml.parse_error_issue(path)
            self.assertEqual("XML parse error: " + issue["subject"], issue["message"])
            subjects.append(issue["subject"])
        self.assertNotEqual(*subjects)

    def test_a_strings_po_fault_is_the_subject(self):
        """Each strings.po parse fault is its own subject, alike for one fault in every language."""
        repo = ValidationRepo(type("Addon", (), {"path": self.path})())
        header = 'msgid ""\nmsgstr ""\n\n'
        for name, body in (("quote.po", 'msgctxt "#31000"\nmsgid "a "b" c"\nmsgstr ""\n'),
                           ("order.po", 'msgctxt "#31087"\nmsgstr "x"\n')):
            with open(os.path.join(self.path, name), "w", encoding="utf-8") as f:
                f.write(header + body)
            repo._check_po(name, os.path.join(self.path, name))
        self.assertEqual([r["subject"] for r in repo.issues if r["rule"] == "repo.po-parse"],
                         ["unescaped double quote found", 'msgstr cannot follow msgctxt "#31087"'])

    def test_a_later_fatal_fault_still_fails(self):
        path = self._write("Mixed.xml", "<window>\n<v>a&b</v>\n<v>a < b</v>\n</window>")
        self.assertIsNone(xml.get_root_from_file(path))

    def test_declared_entities_are_never_expanded(self):
        """Neither a local file nor an internal value reaches the tree through a DTD entity."""
        secret = Path(self.path, "secret.txt")
        secret.write_text("SECRET", encoding="utf-8")
        for n, (entity, value) in enumerate(((f'SYSTEM "{secret.as_uri()}"', "SECRET"),
                                             ('"INTERNAL"', "INTERNAL"))):
            path = self._write(f"Entity{n}.xml", f"<!DOCTYPE window [<!ENTITY x {entity}>]>\n"
                                                 "<window><a>&x;</a></window>")
            root = xml.get_root_from_file(path)
            self.assertNotIn(value, "" if root is None else ET.tostring(root, encoding="unicode"))


if __name__ == "__main__":
    unittest.main()
