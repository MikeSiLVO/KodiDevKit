"""Schema entries that exist for one Kodi release but not the one before it."""

import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import libs
from libs.infoprovider import InfoProvider


ADDON_XML = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test Skin" provider-name="test">
    <requires>
        <import addon="xbmc.gui" version="{gui_version}"/>
    </requires>
    <extension point="xbmc.gui.skin" defaultthemename="Textures.xbt" debugging="false">
        <res width="1920" height="1080" aspect="16x9" default="true" folder="16x9" />
    </extension>
</addon>"""

GUI_OMEGA = "5.17.0"
GUI_PIERS = "5.18.0"


class ReleaseGatedTestCase(unittest.TestCase):
    """Runs one window through the checker against a chosen release."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.test_dir, "16x9"))

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def _provider(self, gui_version):
        with open(os.path.join(self.test_dir, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(ADDON_XML.format(gui_version=gui_version))
        provider = InfoProvider()
        provider.settings = {}
        provider.init_addon(self.test_dir)
        return provider

    def _check(self, gui_version, controls):
        path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f'<?xml version="1.0" encoding="UTF-8"?>\n<window>\n<controls>\n{controls}\n</controls>\n</window>')
        return self._provider(gui_version).check_file(path) or []


FIXEDLIST = """    <control type="fixedlist" id="6">
        <focusposition>4</focusposition>
        <startmovement>4</startmovement>
        <endmovement>5</endmovement>
        <aligny>top</aligny>
    </control>"""


class TestFixedListMovementTags(ReleaseGatedTestCase):
    """`<startmovement>`, `<endmovement>` and `<aligny>` on fixedlist, new in Kodi 22."""

    def test_accepted_on_piers(self):
        self.assertEqual(self._check(GUI_PIERS, FIXEDLIST), [])

    def test_rejected_on_omega(self):
        messages = [i["message"] for i in self._check(GUI_OMEGA, FIXEDLIST)]
        self.assertEqual(len(messages), 3)
        for tag in ("startmovement", "endmovement", "aligny"):
            self.assertTrue(any(f"<{tag}>" in m for m in messages), tag)

    def test_aligny_value_still_checked_on_piers(self):
        controls = FIXEDLIST.replace("<aligny>top</aligny>", "<aligny>middle</aligny>")
        messages = [i["message"] for i in self._check(GUI_PIERS, controls)]
        self.assertTrue(any("aligny" in m and "middle" in m for m in messages), messages)


IMAGE_FILTERS = """    <control type="image">
        <texture>a.png</texture>
        <imagefilter>nearest</imagefilter>
        <diffusefilter>linear</diffusefilter>
    </control>"""


class TestImageFilters(ReleaseGatedTestCase):
    """`<imagefilter>` and `<diffusefilter>` on image, new in Kodi 22."""

    def test_accepted_on_piers(self):
        self.assertEqual(self._check(GUI_PIERS, IMAGE_FILTERS), [])

    def test_rejected_on_omega(self):
        messages = [i["message"] for i in self._check(GUI_OMEGA, IMAGE_FILTERS)]
        self.assertEqual(len(messages), 2)
        for tag in ("imagefilter", "diffusefilter"):
            self.assertTrue(any(f"<{tag}>" in m for m in messages), tag)

    def test_only_linear_and_nearest_are_valid(self):
        controls = IMAGE_FILTERS.replace("nearest", "bilinear")
        messages = [i["message"] for i in self._check(GUI_PIERS, controls)]
        self.assertEqual(len(messages), 1)
        self.assertIn("linear, nearest", messages[0])

    def test_infolabel_value_is_left_alone(self):
        controls = IMAGE_FILTERS.replace("nearest", "$VAR[MyFilter]")
        self.assertEqual(self._check(GUI_PIERS, controls), [])


class TestEpgGridMinutesPerBlock(ReleaseGatedTestCase):
    """`<minspertimeblock>` on epggrid, new in Kodi 22."""

    CONTROLS = '    <control type="epggrid" id="9"><timeblocks>3</timeblocks><minspertimeblock>5</minspertimeblock></control>'

    def test_accepted_on_piers(self):
        self.assertEqual(self._check(GUI_PIERS, self.CONTROLS), [])

    def test_rejected_on_omega(self):
        messages = [i["message"] for i in self._check(GUI_OMEGA, self.CONTROLS)]
        self.assertEqual(len(messages), 1)
        self.assertIn("<minspertimeblock>", messages[0])


class TestStreamSelectWindows(ReleaseGatedTestCase):
    """The stream-select dialogs, new in Kodi 22."""

    def test_known_on_piers_only(self):
        for gui_version, expected in ((GUI_PIERS, True), (GUI_OMEGA, False)):
            provider = self._provider(gui_version)
            for name in ("dialogselectvideo", "dialogselectaudio", "dialogselectsubtitle"):
                self.assertEqual(name in provider.WINDOW_NAMES, expected, f"{name} on {gui_version}")

    def test_versions_and_extras_dialogs_dropped_on_piers(self):
        piers = self._provider(GUI_PIERS)
        omega = self._provider(GUI_OMEGA)
        for name in ("selectvideoversion", "selectvideoextra"):
            self.assertIn(name, omega.WINDOW_NAMES)
            self.assertNotIn(name, piers.WINDOW_NAMES)


class TestPlayerBookmarks(ReleaseGatedTestCase):
    """`Player.HasBookmarks` / `Player.Bookmarks`, new in Kodi 22."""

    NEW_BOOLEANS = (
        "Player.HasBookmarks",
        "Player.IsLive",
        "RetroPlayer.AchievementsLoggedIn",
        "RetroPlayer.DiscEjected",
        "RetroPlayer.EmptyTray",
        "RetroPlayer.SupportsEject",
    )

    def test_new_booleans_offered_on_piers_only(self):
        for gui_version, expected in ((GUI_PIERS, True), (GUI_OMEGA, False)):
            provider = self._provider(gui_version)
            offered = {code for code, _help in provider.conditions}
            for name in self.NEW_BOOLEANS:
                self.assertEqual(name in offered, expected, f"{name} on {gui_version}")

    def test_bookmarks_infolabel_fits_the_ranges_control(self):
        controls = '    <control type="ranges"><info>Player.Bookmarks</info></control>'
        self.assertEqual(self._check(GUI_PIERS, controls), [])


class TestWindowTableShape(unittest.TestCase):
    """`windows.json` maps one name to one id, which the id lookups rely on."""

    # Resolved from the engine package, which sits beside data/ in both layouts.
    DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(libs.__file__))), "data")

    def _rows(self, release):
        import json
        with open(os.path.join(self.DATA, release, "windows.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_ids_and_names_are_unique(self):
        for release in ("omega", "piers"):
            rows = self._rows(release)
            ids = [r[1] for r in rows]
            names = [r[0] for r in rows]
            self.assertEqual(len(ids), len(set(ids)), f"{release} has a duplicate window id")
            self.assertEqual(len(names), len(set(names)), f"{release} has a duplicate window name")

    def test_rows_are_name_id_filename(self):
        for release in ("omega", "piers"):
            for row in self._rows(release):
                self.assertEqual(len(row), 3, row)
                self.assertIsInstance(row[0], str)
                self.assertIsInstance(row[1], int)
                # Blank where Kodi resolves the window to no XML of its own.
                self.assertIsInstance(row[2], str)


if __name__ == "__main__":
    unittest.main()
