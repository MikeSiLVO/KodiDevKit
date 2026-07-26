"""Bundled Kodi reference resolution: the snapshot path taken when `kodi_path`
is unset.

Skips when snapshots are absent, since they are fetched at build time.
"""

import os
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs import kodi_refs, utils
from libs.addon import Addon
from libs.kodi_refs import kodi_colors_xml, kodi_strings_po
from libs.skin import Skin

# Resolved by the module itself, so this works from either repo layout.
SNAPSHOTS_PRESENT = kodi_refs._BUNDLED_DATA.is_dir()

ADDON_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<addon id="skin.reftest" version="1.0.0" name="Ref Test" provider-name="test">
    <requires><import addon="xbmc.gui" version="{gui}"/></requires>
    <extension point="xbmc.gui.skin">
        <res width="1920" height="1080" aspect="16:9" default="true" folder="16x9"/>
    </extension>
</addon>"""


def make_skin(tmpdir, gui_version="5.18.0"):
    os.makedirs(os.path.join(tmpdir, "16x9"), exist_ok=True)
    with open(os.path.join(tmpdir, "addon.xml"), "w", encoding="utf-8") as f:
        f.write(ADDON_XML.format(gui=gui_version))
    return Skin(path=tmpdir, settings={})


@unittest.skipUnless(SNAPSHOTS_PRESENT, "bundled Kodi snapshots not fetched")
class TestBundledReferences(unittest.TestCase):
    """kodi_refs falls back to bundled snapshots when kodi_path is unset."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.skin = make_skin(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_core_colors_load_without_kodi_path(self):
        """Core colors must be present; Kodi always loads system/colors.xml."""
        path = kodi_colors_xml(self.skin, None)
        assert path is not None, "no bundled colors.xml resolved"
        self.assertTrue(os.path.isfile(path))
        self.assertGreater(len(self.skin.colors), 0, "skin loaded zero colors")

    def test_core_string_resolves_without_kodi_path(self):
        """A core string id must resolve, or core $LOCALIZE ids read as undefined."""
        path = kodi_strings_po(self.skin, None)
        assert path is not None, "no bundled strings.po resolved"
        po = utils.get_po_file(path)
        assert po is not None
        self.assertTrue(
            any(entry.msgctxt == "#13050" for entry in po),
            "core string 13050 missing from bundled strings.po",
        )

    def test_snapshot_matches_skin_target_release(self):
        """Each skin gets the snapshot for the release its xbmc.gui import targets."""
        for gui_version, expected in [("5.17.0", "omega"), ("5.18.0", "piers")]:
            with tempfile.TemporaryDirectory() as tmp:
                skin = make_skin(tmp, gui_version)
                self.assertEqual(skin.api_version, expected)
                path = kodi_colors_xml(skin, None)
                if path is None:
                    self.skipTest(f"no bundled snapshot for {expected}")
                self.assertIn(
                    expected, path.replace("\\", "/").split("/"),
                    f"gui {gui_version} should resolve to the {expected} snapshot, got {path}",
                )

    def test_every_po_file_carries_a_language(self):
        """Tooltip rendering reads .language on every PO file it is handed."""
        from libs.infoprovider.provider import InfoProvider

        provider = InfoProvider()
        provider.addon = self.skin
        po_files = provider.get_po_files()
        self.assertTrue(po_files, "no PO files returned")
        for po in po_files:
            self.assertTrue(
                getattr(po, "language", None),
                f"PO file {getattr(po, 'fpath', po)!r} has no .language",
            )

    def test_installed_kodi_wins_over_snapshot(self):
        """A valid kodi_path outranks the bundle (kodi_refs priority 1)."""
        with tempfile.TemporaryDirectory() as fake_kodi:
            system = os.path.join(fake_kodi, "system")
            os.makedirs(system)
            marker = os.path.join(system, "colors.xml")
            with open(marker, "w", encoding="utf-8") as f:
                f.write('<colors><color name="marker">FFFFFFFF</color></colors>')
            self.assertEqual(kodi_colors_xml(self.skin, fake_kodi), marker)


@unittest.skipUnless(SNAPSHOTS_PRESENT, "bundled Kodi snapshots not fetched")
class TestReleaseOverride(unittest.TestCase):
    """The kodi_release setting outranks detection from addon.xml."""

    def test_explicit_override_selects_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "16x9"))
            with open(os.path.join(tmp, "addon.xml"), "w", encoding="utf-8") as f:
                f.write(ADDON_XML.format(gui="5.17.0"))  # would detect omega
            skin = Skin(path=tmp, settings={"kodi_release": "piers"})
            self.assertEqual(skin.api_version, "piers")

    def test_unknown_override_falls_back_to_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "16x9"))
            with open(os.path.join(tmp, "addon.xml"), "w", encoding="utf-8") as f:
                f.write(ADDON_XML.format(gui="5.17.0"))
            skin = Skin(path=tmp, settings={"kodi_release": "nonsuch"})
            self.assertEqual(skin.api_version, "omega")

    def test_addon_without_gui_import_gets_newest_release(self):
        """Scripts take the newest release; xbmc.python cannot tell releases apart."""
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "addon.xml"), "w", encoding="utf-8") as f:
                f.write(
                    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                    '<addon id="script.reftest" version="1.0.0" name="Ref" provider-name="test">\n'
                    '    <requires><import addon="xbmc.python" version="3.0.1"/></requires>\n'
                    '    <extension point="xbmc.python.script" library="default.py"/>\n'
                    "</addon>"
                )
            addon = Addon(path=tmp, settings={})
            self.assertEqual(addon.api_version, Addon.RELEASES[-1]["name"])


if __name__ == "__main__":
    unittest.main()
