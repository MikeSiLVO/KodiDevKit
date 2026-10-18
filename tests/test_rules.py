"""The rule id registry against the ids the engine's checks emit."""

import ast
import os
import re
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.infoprovider.provider import InfoProvider
from libs.validation import rules
from libs.validation.rules import ADDON_CHECKER, PREFIXES, RULES

CHECKS = {"check_variables": "Variables", "check_maps": "Maps", "check_includes": "Includes",
          "check_labels": "Labels", "check_fonts": "Fonts", "check_ids": "IDs", "check_images": "Images",
          "check_values": "XML Validation", "check_file_integrity": "File Integrity", "check_repo": "Kodi Repo"}
ADDON_XML = ('<addon id="skin.test" version="1.0"><requires><import addon="xbmc.gui" version="5.17.0"/>'
             '</requires><extension point="xbmc.gui.skin"><res folder="16x9" default="true"/></extension>'
             '</addon>')
HOME_XML = ('<window><controls><control type="label"><font>Nope</font><label>Hello there</label>'
            '<visible>Foo.Bar</visible><onup>9999</onup></control>'
            '<control type="image"><texture>missing.png</texture><label>$VAR[Gone]</label></control>'
            '</controls></window>\n')

# a file extension after the dot is a file name such as fonts.xml, never a problem
RULE_ID = re.compile(rf"({'|'.join(PREFIXES)})\.(?!(xml|po|py)$)[a-z0-9]+(-[a-z0-9]+)*")


def _engine_literals():
    """Every string literal in the engine shaped like a rule id, with where it is written."""
    libs_dir = os.path.dirname(os.path.dirname(os.path.abspath(rules.__file__)))
    found = {}
    for dirpath, dirnames, filenames in os.walk(libs_dir):
        dirnames[:] = [d for d in dirnames if d != "polib"]
        for name in filenames:
            if not name.endswith(".py") or os.path.join(dirpath, name) == os.path.abspath(rules.__file__):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and RULE_ID.fullmatch(node.value):
                    found.setdefault(node.value, f"{name}:{node.lineno}")
    return found


class TestRules(unittest.TestCase):
    """Tests of the rule id registry and the rule ids the engine's checks emit."""

    def test_ids_are_check_and_problem_in_kebab_case(self):
        """Every registered id is a known check prefix and a lowercase kebab-case problem."""
        self.assertEqual([r for r in RULES if not RULE_ID.fullmatch(r)], [])

    def test_every_emitted_id_is_registered(self):
        """A rule id written in the engine is in the registry."""
        self.assertEqual({r: where for r, where in _engine_literals().items() if r not in RULES}, {})

    def test_every_registered_id_is_emitted(self):
        """A registered rule id appears in the engine, except kdk's own ones its front ends emit."""
        emitted = _engine_literals()
        self.assertEqual([r for r in RULES if r not in emitted and not r.startswith("kdk.")], [])

    def test_every_row_of_a_run_carries_a_registered_rule_and_a_subject(self):
        """Each row carries a registered rule of the check it appears in, and a string subject."""
        with tempfile.TemporaryDirectory() as skin:
            os.makedirs(os.path.join(skin, "16x9"))
            with open(os.path.join(skin, "addon.xml"), "w", encoding="utf-8") as f:
                f.write(ADDON_XML)
            with open(os.path.join(skin, "16x9", "Home.xml"), "w", encoding="utf-8", newline="\r\n") as f:
                f.write(HOME_XML)
            provider = InfoProvider()
            provider.settings = {}
            provider.init_addon(skin)
            rows = [(check, row) for name, check in CHECKS.items() for row in getattr(provider, name)() or []]
        self.assertGreater(len({row["rule"] for _, row in rows}), 5)
        self.assertEqual([row for check, row in rows if row.get("rule") not in RULES
                          or PREFIXES[row["rule"].split(".")[0]] != check
                          or not isinstance(row.get("subject"), str)], [])

    def test_addon_checker_levels_name_registered_rules(self):
        """Each add-on checker level names a registered rule and is a problem or a warning."""
        self.assertLessEqual(set(ADDON_CHECKER), set(RULES))
        self.assertLessEqual(set(ADDON_CHECKER.values()), {"problem", "warning"})

    def test_every_rule_says_what_it_reports(self):
        """Each description is one line ending in a full stop."""
        self.assertEqual([r for r, text in RULES.items() if not text.endswith(".") or "\n" in text], [])


if __name__ == "__main__":
    unittest.main()
