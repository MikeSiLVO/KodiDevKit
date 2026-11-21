"""Every check finishes quickly on a skin built to make regexes backtrack and recursion run deep."""

import os
import signal
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from libs.infoprovider.provider import InfoProvider

ADDON_XML = ('<addon id="skin.stress" version="1.0.0"><requires><import addon="xbmc.gui" version="5.18.0"/>'
             '</requires><extension point="xbmc.gui.skin"><res width="1920" height="1080" default="true" '
             'folder="16x9"/></extension></addon>')
CHECKS = ("variable", "include", "font", "label", "id", "image", "map", "general", "filecheck", "repo")


def _stress_files():
    """Files of a skin full of shapes that are slow to scan or deep to resolve."""
    chain = "".join(f'<include name="Chain{i}"><include>Chain{i + 1}</include></include>' for i in range(300))
    comments = "<!-- c -->" * 3000
    # Many: comments before a child, no comment-only element after them to end the scan early
    includes = (f'<includes>{chain}<include name="Chain300"><width>1</width></include>'
                f'<include name="Only">{comments}</include>'
                '<variable name="V"><value condition="String.Contains(' + "(" * 500 + 'a">x</value></variable>'
                f'<include name="Many">{comments}<width>1</width></include></includes>')
    nested = '<control type="group">' * 150 + "<include>Chain0</include>" + "</control>" * 150
    url = "plugin://plugin.x/?" + "&".join(f"k{i}=$INFO[ListItem.Label]" for i in range(2000)) + "x" * 50000
    long_key = "plugin://plugin.y/?q" + "x" * 50000 + "=$INFO[ListItem.Label]"
    window = ('<window><controls>' + nested
              + f'<control type="label"><label>{"x" * 200000}</label>'
              + '<visible>' + '[[[[' * 300 + 'Player.HasVideo</visible></control>'
              + f'<control type="list"><content>{url}</content></control>'
              + f'<control type="list"><content>{long_key}</content></control></controls></window>')
    po = 'msgid ""\nmsgstr ""\n' + "".join(f'msgctxt "#{31000 + i}"\nmsgid "s{i}"\nmsgstr ""\n' for i in range(2000))
    return {"addon.xml": ADDON_XML, "16x9/Includes.xml": includes, "16x9/Home.xml": window,
            "16x9/Clean.xml": '<window><controls><control type="group">' + nested + "</control></controls></window>",
            "16x9/Broken.xml": "<window><controls><!-- " + "-" * 20000 + "</controls></window>",
            "16x9/Notes.xml": "<!-- n -->\n" * 60 + "<window/>",
            "language/resource.language.en_gb/strings.po": po}


class TestStress(unittest.TestCase):
    """Pathological skin input that no check may hang or crash on."""

    def test_every_check_finishes(self):
        """Every check finishes within the time limit, returning rows with no exception."""
        if hasattr(signal, "SIGALRM"):
            signal.signal(signal.SIGALRM, lambda *_: self.fail("a check ran past 120 s"))
            signal.alarm(120)
            self.addCleanup(signal.alarm, 0)
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        for rel, text in _stress_files().items():
            path = os.path.join(temp_dir.name, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        start = time.time()
        provider = InfoProvider()
        provider.settings = {}
        provider.load_data("piers")
        provider.init_addon(temp_dir.name)
        for check in CHECKS:
            with self.subTest(check=check):
                self.assertIsInstance(provider.get_check_listitems(check), list)
        self.assertLess(time.time() - start, 60)


if __name__ == "__main__":
    unittest.main()
