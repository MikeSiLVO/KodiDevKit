"""Id references are read where Kodi reads them and scoped the way it looks them up."""

import os
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from lxml import etree as ET

from libs.infoprovider.provider import InfoProvider
from libs.skin.index import SkinIndex, custom_window

ADDON_XML = ('<addon id="skin.test" version="1.0.0"><requires>'
             '<import addon="xbmc.gui" version="5.18.0"/></requires>'
             '<extension point="xbmc.gui.skin"><res folder="16x9" default="true"/></extension></addon>')


def _refs(text):
    index = {'ids_referenced': {'f': {}}}
    SkinIndex._record_id_refs(text, ET.fromstring("<visible/>"), "Home.xml", "f", index)
    return {ref: usages[0]['type'] for ref, usages in index['ids_referenced']['f'].items()}


class TestExtraction(unittest.TestCase):
    """Only numbers Kodi reads as ids are recorded."""

    def test_item_indexes_are_not_control_ids(self):
        self.assertEqual(_refs("Container(9000).HasFocus(5)"), {"9000": "control"})
        self.assertEqual(_refs("String.StartsWith(Container.ListItemAbsolute(0).Label,*)"), {})
        self.assertEqual(_refs("String.IsEmpty(Control.GetLabel(312).index(1))"), {"312": "control"})

    def test_control_group_focus(self):
        self.assertEqual(_refs("ControlGroup(9101).HasFocus(100)"), {"9101": "control", "100": "control"})
        self.assertEqual(_refs("ControlGroup(9001).HasFocus(0) | ControlGroup(9002).HasFocus"),
                         {"9001": "control", "9002": "control"})

    def test_builtins(self):
        self.assertEqual(_refs("SetVolume(50)"), {})
        self.assertEqual(_refs("Seek(30)"), {})
        self.assertEqual(_refs("Container.SetSortMethod(1)"), {})
        self.assertEqual(_refs("SetFocus(50,3)"), {"50": "control"})
        self.assertEqual(_refs("SendClick(500)"), {"500": "control"})
        self.assertEqual(_refs("SendClick(videos,50)"), {"50": "control"})

    def test_window_is_topmost_is_a_window(self):
        self.assertEqual(_refs("Window.IsTopmost(1101)"), {"1101": "window"})


class TestCustomWindow(unittest.TestCase):
    """Custom window ids come from the attribute or a child, plus WINDOW_HOME."""

    def test_forms(self):
        self.assertEqual(custom_window(ET.fromstring('<window id="1101"/>'), "Custom_1101.xml"),
                         (["1101", "11101"], False))
        self.assertEqual(custom_window(ET.fromstring('<window><id>1102</id><type>dialog</type>'
                                                     '<visible>true</visible></window>'),
                                       "custom_x.xml"), (["1102", "11102"], True))
        self.assertEqual(custom_window(ET.fromstring('<window id="1103"/>'), "Home.xml"), ([], False))

    def test_modality(self):
        modal = '<window id="1" type="dialog" modality="modal"><visible>true</visible></window>'
        self.assertFalse(custom_window(ET.fromstring(modal), "custom_a.xml")[1])
        self.assertFalse(custom_window(ET.fromstring('<window id="1" type="dialog"/>'), "custom_b.xml")[1])


class TestScope(unittest.TestCase):
    """A reference is an error only where Kodi cannot find the id."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = self.temp_dir.name
        os.makedirs(os.path.join(self.path, "16x9"))
        self._write("addon.xml", ADDON_XML)
        self._write("16x9/Includes.xml", "<includes/>")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write(self, rel, text):
        with open(os.path.join(self.path, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def _rows(self):
        """Id check rows that point at a file, for the skin as written."""
        provider = InfoProvider()
        provider.settings = {}
        provider.load_data("piers")
        provider.init_addon(self.path)
        return [r for r in provider.get_check_listitems("id") if r.get("file")]

    def _messages(self):
        """Messages of the id check rows, sorted."""
        return sorted(r["message"] for r in self._rows())

    def test_scope_tiers(self):
        """Scope tiers flag only ids Kodi cannot find; a core window by number warns."""
        self._write("16x9/Home.xml", '<window><controls><control type="button" id="50"/>'
                                     '<control type="label"><visible>Control.HasFocus(60)</visible></control>'
                                     '<control type="label"><visible>Control.HasFocus(70)</visible></control>'
                                     '</controls></window>')
        self._write("16x9/MyVideoNav.xml", '<window><controls><control type="button" id="60"/>'
                                           '</controls></window>')
        self._write("16x9/DialogSeekBar.xml", '<window><controls><control type="label">'
                                              '<visible>Control.HasFocus(50)</visible></control>'
                                              '</controls></window>')
        self._write("16x9/service-Addon-Settings.xml", '<window><controls><control type="label">'
                                                       '<visible>Control.HasFocus(50)</visible></control>'
                                                       '</controls></window>')
        self._write("16x9/DialogMusicInfo.xml", '<window><controls><control type="label">'
                                                '<visible>Control.HasFocus(60)</visible></control>'
                                                '</controls></window>')
        self._write("16x9/Custom_1101_Info.xml", '<window id="1101" type="dialog"><controls>'
                                                 '<control type="button"><onclick>Dialog.Close(all)</onclick>'
                                                 '<onclick>SendClick(60)</onclick></control>'
                                                 '<control type="label"><visible>Window.IsVisible(11101) + '
                                                 'Window.IsVisible(100) + Window.IsVisible(10612)</visible>'
                                                 '</control></controls></window>')
        self.assertEqual(self._messages(), [
            "Control ID 60 not defined in DialogMusicInfo.xml's scope",
            "Control ID 60 not defined in Home.xml's scope",
            "Control ID 70 not defined",
            "Window id 100 works, but its name yesnodialog is preferred",
        ])
        self.assertEqual({r["severity"] for r in self._rows() if r["rule"] == "ids.use-name"}, {"warning"})


    def test_id_built_from_an_unpassed_param(self):
        self._write("16x9/Includes.xml", '<includes><include name="Btn"><definition>'
                                         '<control type="button" id="$PARAM[base]$PARAM[id]"/>'
                                         '</definition></include></includes>')
        self._write("16x9/Home.xml", '<window><controls><include content="Btn"><param name="id">6805</param>'
                                     '</include><control type="label"><visible>Control.HasFocus(6805)</visible>'
                                     '</control></controls></window>')
        self.assertEqual(self._messages(), [])

    def test_window_names_follow_the_translator(self):
        self._write("16x9/Home.xml", '<window><controls><control type="button">'
                                     '<onclick>ActivateWindow(Videos,return)</onclick>'
                                     '<onclick>ActivateWindow(MyVideos)</onclick>'
                                     '<onclick>ActivateWindow(window10025)</onclick>'
                                     '<onclick>Dialog.Close(all)</onclick>'
                                     '<onclick>ActivateWindow(programssettings)</onclick>'
                                     '<visible>Window.IsActive(MyVideoNav.xml) + '
                                     '!String.IsEmpty(Window(Hoem).Property(x))</visible>'
                                     '</control></controls></window>')
        self.assertEqual(self._messages(), ["Window name not recognized by Kodi: Hoem",
                                            "Window name not recognized by Kodi: programssettings"])

    def test_custom_window_ids(self):
        self._write("16x9/Home.xml", "<window><controls/></window>")
        for name, root in (("Custom_A.xml", "<window>"), ("Custom_B.xml", '<window id="25">'),
                           ("Custom_C.xml", '<window id="1150">'), ("Custom_D.xml", "<window><id>1150</id>"),
                           ("Custom_E.xml", '<window id="1300">'), ("Custom_F.xml", '<window id="1101">')):
            self._write(f"16x9/{name}", f"{root}<controls/></window>")
        self._write("16x9/Custom_G.xml", '<dialog id="1102"><controls/></dialog>')
        self.assertEqual(self._messages(), [
            "Custom window has no id, so Kodi does not load it",
            "Custom window id 1150 is also used by Custom_C.xml; Kodi loads one",
            "Custom window id 1150 is also used by Custom_D.xml; Kodi loads one",
            "Custom window id 1300 is outside 1100-1199",
            "Custom window id 25 is Kodi's videos window, so Kodi does not load it",
            "Custom window root is <dialog>, not <window>, so Kodi does not load it",
        ])

    def test_navigation_targets(self):
        self._write("16x9/Home.xml", '<window><controls><control type="button" id="50"><onup>51</onup>'
                                     '<ondown>50</ondown><onclick>SetFocus(52)</onclick></control>'
                                     '<control type="button" id="60"/></controls></window>')
        self._write("16x9/DialogSeekBar.xml", '<window><controls><control type="button" id="7">'
                                              '<onleft>60</onleft></control></controls></window>')
        self.assertEqual(self._messages(), [
            "Control ID 51 not defined",
            "Control ID 52 not defined",
            "Control ID 60 not defined in DialogSeekBar.xml's scope",
        ])

    def test_dialog_onunload_targets_the_window_below(self):
        self._write("16x9/Home.xml", '<window><onunload>SetFocus(61)</onunload><controls>'
                                     '<control type="button" id="50"/></controls></window>')
        self._write("16x9/MyVideoNav.xml", '<window><controls><control type="button" id="61"/>'
                                           '</controls></window>')
        self._write("16x9/DialogMusicInfo.xml", '<window><onunload>SetFocus(50)</onunload><controls>'
                                                '<control type="button" id="7"/></controls></window>')
        self.assertEqual(self._messages(), ["Control ID 61 not defined in Home.xml's scope"])

if __name__ == "__main__":
    unittest.main()
