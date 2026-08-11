"""Skin map (`<map>` / `$MAP[]`) validation tests."""

import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.base import ValidationTestCase, MapCheck
from libs.infoprovider import InfoProvider
from libs.validation.interpreter import XmlInterpreter
from libs.validation.skinmap import extract_map_args
from libs.utils.xml import PARSER
from lxml import etree as ET


ADDON_XML = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test Skin" provider-name="test">
    <requires>
        <import addon="xbmc.gui" version="{gui_version}"/>
    </requires>
    <extension point="xbmc.gui.skin" defaultthemename="Textures.xbt" debugging="false">
        <res width="1920" height="1080" aspect="16x9" default="true" folder="16x9" />
    </extension>
</addon>"""


class MapTestCase(ValidationTestCase):
    """Builds a throwaway skin whose includes and windows each test writes."""

    gui_version = "5.18.0"

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.provider = InfoProvider()
        self.provider.settings = {}
        os.makedirs(os.path.join(self.test_dir, "16x9"))
        self._write("../addon.xml", ADDON_XML.format(gui_version=self.gui_version))

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def _write(self, name, content):
        path = os.path.normpath(os.path.join(self.test_dir, "16x9", name))
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def _includes(self, body):
        self._write("Includes.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n<includes>\n{body}\n</includes>')

    def _window(self, body):
        self._write("Home.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n<window>\n{body}\n</window>')

    def _check(self):
        self.provider.init_addon(self.test_dir)
        return MapCheck(self.provider.addon).check()

    def _messages(self, needle):
        return [i for i in self._check() if needle in i["message"]]


CODEC_MAP = """    <map name="CodecMap">
        <entry key="ac3">Dolby Digital</entry>
        <entry key="eac3">Dolby Digital+</entry>
    </map>"""

CODEC_LABEL = """    <controls>
        <control type="label">
            <label>$MAP[CodecMap, ListItem.AudioCodec]</label>
        </control>
    </controls>"""


class TestMapUsage(MapTestCase):
    """`$MAP[]` references against the maps a skin defines."""

    def test_defined_map_used_is_clean(self):
        self._includes(CODEC_MAP)
        self._window(CODEC_LABEL)
        self.assertEqual(self._check(), [])

    def test_escmap_counts_as_a_usage(self):
        self._includes(CODEC_MAP)
        self._window("""    <controls>
        <control type="label">
            <label>$ESCMAP[CodecMap, ListItem.AudioCodec]</label>
        </control>
    </controls>""")
        self.assertEqual(self._check(), [])

    def test_prefix_and_postfix_are_allowed(self):
        self._includes(CODEC_MAP)
        self._window("""    <controls>
        <control type="label">
            <label>$MAP[CodecMap, ListItem.AudioCodec, (, )]</label>
        </control>
    </controls>""")
        self.assertEqual(self._check(), [])

    def test_undefined_map_reported(self):
        self._includes(CODEC_MAP)
        self._window("""    <controls>
        <control type="label">
            <label>$MAP[NoSuchMap, ListItem.AudioCodec]</label>
        </control>
    </controls>""")
        issues = self._messages("Map not defined: NoSuchMap")
        self.assertEqual(len(issues), 1)
        self.assertTrue(issues[0]["file"].endswith("Home.xml"))

    def test_missing_infolabel_reported(self):
        self._includes(CODEC_MAP)
        self._window("""    <controls>
        <control type="label">
            <label>$MAP[CodecMap]</label>
        </control>
    </controls>""")
        self.assertEqual(len(self._messages("needs both a map name and an infolabel")), 1)

    def test_empty_block_reported(self):
        self._includes(CODEC_MAP)
        self._window("""    <controls>
        <control type="label">
            <label>$MAP[]</label>
        </control>
    </controls>""")
        self.assertEqual(len(self._messages("needs both a map name and an infolabel")), 1)

    def test_blank_argument_reported(self):
        self._includes(CODEC_MAP)
        self._window("""    <controls>
        <control type="label">
            <label>$MAP[ , ListItem.AudioCodec]</label>
        </control>
    </controls>""")
        self.assertEqual(len(self._messages("needs both a map name and an infolabel")), 1)

    def test_missing_closing_bracket_reported(self):
        self._includes(CODEC_MAP)
        self._window("""    <controls>
        <control type="label">
            <label>$MAP[CodecMap, ListItem.AudioCodec</label>
        </control>
    </controls>""")
        self.assertEqual(len(self._messages("missing its closing")), 1)

    def test_map_name_supplied_by_an_include_param(self):
        self._includes(CODEC_MAP + """
    <include name="CodecLabel">
        <param name="mapname" default="CodecMap"/>
        <definition>
            <control type="label">
                <label>$MAP[$PARAM[mapname], ListItem.AudioCodec]</label>
            </control>
        </definition>
    </include>""")
        self._window("""    <controls>
        <include content="CodecLabel">
            <param name="mapname" value="CodecMap"/>
        </include>
    </controls>""")
        self.assertEqual(self._check(), [])

    def test_usage_in_a_comment_does_not_count(self):
        self._includes(CODEC_MAP)
        self._window("""    <controls>
        <!-- <label>$MAP[CodecMap, ListItem.AudioCodec]</label> -->
    </controls>""")
        self.assertEqual(len(self._messages("Unused map: CodecMap")), 1)

    def test_line_number_survives_a_multiline_comment(self):
        self._includes(CODEC_MAP)
        self._window("""    <!--
        a comment
        spanning lines
    -->
    <controls>
        <control type="label">
            <label>$MAP[NoSuchMap, ListItem.AudioCodec]</label>
        </control>
    </controls>""")
        issues = self._messages("Map not defined")
        self.assertEqual(issues[0]["line"], 9)


class TestMapDefinitions(MapTestCase):
    """Definitions Kodi drops or loads differently than the skinner expects."""

    def test_unused_map_reported(self):
        self._includes(CODEC_MAP)
        self._window("    <controls/>")
        self.assertEqual(len(self._messages("Unused map: CodecMap")), 1)

    def test_map_reached_through_a_ref_is_used(self):
        self._includes(CODEC_MAP + """
    <map name="AltCodecMap" ref="CodecMap">
        <entry key="ac3">DD</entry>
    </map>""")
        self._window("""    <controls>
        <control type="label">
            <label>$MAP[AltCodecMap, ListItem.AudioCodec]</label>
        </control>
    </controls>""")
        self.assertEqual(self._check(), [])

    def test_unreached_ref_chain_reported_for_both_maps(self):
        self._includes(CODEC_MAP + """
    <map name="AltCodecMap" ref="CodecMap"/>""")
        self._window("    <controls/>")
        self.assertEqual(len(self._messages("Unused map")), 2)

    def test_map_without_name_reported(self):
        self._includes("""    <map>
        <entry key="ac3">Dolby Digital</entry>
    </map>""")
        self._window("    <controls/>")
        self.assertEqual(len(self._messages("has no name attribute")), 1)

    def test_padded_name_reported(self):
        self._includes("""    <map name=" CodecMap ">
        <entry key="ac3">Dolby Digital</entry>
    </map>""")
        self._window(CODEC_LABEL)
        self.assertEqual(len(self._messages("padded with whitespace")), 1)

    def test_duplicate_name_reported_once(self):
        self._includes(CODEC_MAP + """
    <map name="CodecMap">
        <entry key="dts">DTS</entry>
    </map>""")
        self._window(CODEC_LABEL)
        self.assertEqual(len(self._messages("Duplicate map name: CodecMap")), 1)

    def test_duplicate_entry_key_reported(self):
        self._includes("""    <map name="CodecMap">
        <entry key="ac3">Dolby Digital</entry>
        <entry key="ac3">AC3</entry>
    </map>""")
        self._window(CODEC_LABEL)
        self.assertEqual(len(self._messages("Duplicate entry key 'ac3'")), 1)

    def test_entry_without_key_reported(self):
        self._includes("""    <map name="CodecMap">
        <entry key="ac3">Dolby Digital</entry>
        <entry>DTS</entry>
    </map>""")
        self._window(CODEC_LABEL)
        self.assertEqual(len(self._messages("has no key attribute")), 1)

    def test_entry_without_value_reported(self):
        self._includes("""    <map name="CodecMap">
        <entry key="ac3">Dolby Digital</entry>
        <entry key="dts"/>
    </map>""")
        self._window(CODEC_LABEL)
        self.assertEqual(len(self._messages("has no value")), 1)

    def test_keys_differing_only_in_case_are_distinct(self):
        self._includes("""    <map name="CodecMap">
        <entry key="ac3">Dolby Digital</entry>
        <entry key="AC3">Dolby Digital</entry>
    </map>""")
        self._window(CODEC_LABEL)
        self.assertEqual(self._check(), [])

    def test_entry_opening_with_a_child_element_has_no_value(self):
        self._includes("""    <map name="CodecMap">
        <entry key="ac3">Dolby Digital</entry>
        <entry key="dts"><b>DTS</b></entry>
    </map>""")
        self._window(CODEC_LABEL)
        self.assertEqual(len(self._messages("Entry 'dts' in map 'CodecMap' has no value")), 1)

    def test_map_without_entries_or_ref_reported(self):
        self._includes("""    <map name="CodecMap"/>""")
        self._window(CODEC_LABEL)
        self.assertEqual(len(self._messages("no usable entries and no ref")), 1)

    def test_unknown_ref_reported(self):
        self._includes("""    <map name="CodecMap" ref="NoSuchMap">
        <entry key="ac3">Dolby Digital</entry>
    </map>""")
        self._window(CODEC_LABEL)
        self.assertEqual(len(self._messages("references a map that is not defined: NoSuchMap")), 1)

    def test_circular_ref_reported_once(self):
        self._includes("""    <map name="MapA" ref="MapB">
        <entry key="ac3">A</entry>
    </map>
    <map name="MapB" ref="MapA">
        <entry key="dts">B</entry>
    </map>""")
        self._window("""    <controls>
        <control type="label">
            <label>$MAP[MapA, ListItem.AudioCodec]</label>
        </control>
    </controls>""")
        self.assertEqual(len(self._messages("Circular map reference")), 1)

    def test_self_ref_reported(self):
        self._includes("""    <map name="CodecMap" ref="CodecMap">
        <entry key="ac3">Dolby Digital</entry>
    </map>""")
        self._window(CODEC_LABEL)
        self.assertEqual(len(self._messages("Circular map reference")), 1)


class TestMapReleaseGate(MapTestCase):
    """Maps arrived in Kodi 22, so an Omega skin cannot use them."""

    gui_version = "5.17.0"

    def test_omega_skin_reported_once(self):
        self._includes(CODEC_MAP)
        self._window(CODEC_LABEL)
        self.assertEqual(len(self._messages("Skin maps need Kodi 22")), 1)


class TestMapLookup(MapTestCase):
    """`Skin.lookup_skin_map` against CSkinMapManager::Lookup."""

    def _skin(self, body):
        self._includes(body)
        self._window("    <controls/>")
        self.provider.init_addon(self.test_dir)
        return self.provider.addon

    def test_own_entry_wins(self):
        skin = self._skin(CODEC_MAP)
        self.assertEqual(skin.lookup_skin_map("16x9", "CodecMap", "ac3"), "Dolby Digital")

    def test_unmapped_key_returns_itself(self):
        skin = self._skin(CODEC_MAP)
        self.assertEqual(skin.lookup_skin_map("16x9", "CodecMap", "dts"), "dts")

    def test_unknown_map_returns_the_key(self):
        skin = self._skin(CODEC_MAP)
        self.assertEqual(skin.lookup_skin_map("16x9", "NoSuchMap", "ac3"), "ac3")

    def test_ref_chain_is_followed(self):
        skin = self._skin(CODEC_MAP + """
    <map name="AltCodecMap" ref="CodecMap">
        <entry key="dts">DTS</entry>
    </map>""")
        self.assertEqual(skin.lookup_skin_map("16x9", "AltCodecMap", "ac3"), "Dolby Digital")
        self.assertEqual(skin.lookup_skin_map("16x9", "AltCodecMap", "dts"), "DTS")

    def test_own_entry_overrides_the_ref(self):
        skin = self._skin(CODEC_MAP + """
    <map name="AltCodecMap" ref="CodecMap">
        <entry key="ac3">DD</entry>
    </map>""")
        self.assertEqual(skin.lookup_skin_map("16x9", "AltCodecMap", "ac3"), "DD")

    def test_circular_chain_returns_the_key(self):
        skin = self._skin("""    <map name="MapA" ref="MapB">
        <entry key="x">A</entry>
    </map>
    <map name="MapB" ref="MapA">
        <entry key="y">B</entry>
    </map>""")
        self.assertEqual(skin.lookup_skin_map("16x9", "MapA", "zzz"), "zzz")


class TestMapArgSplitting(ValidationTestCase):
    """`extract_map_args` against CGUIInfoLabel::Parse."""

    def test_two_arguments(self):
        self.assertEqual(
            extract_map_args("$MAP[CodecMap, ListItem.AudioCodec]"),
            ["CodecMap", " ListItem.AudioCodec"],
        )

    def test_empty_block(self):
        self.assertEqual(extract_map_args("$MAP[]"), [])

    def test_blank_prefix_is_kept(self):
        self.assertEqual(
            extract_map_args("$MAP[CodecMap, ListItem.AudioCodec, , )]"),
            ["CodecMap", " ListItem.AudioCodec", " ", " )"],
        )

    def test_nested_brackets_do_not_end_the_block(self):
        self.assertEqual(
            extract_map_args("$MAP[$PARAM[name], ListItem.AudioCodec] tail"),
            ["$PARAM[name]", " ListItem.AudioCodec"],
        )

    def test_missing_close_bracket(self):
        self.assertIsNone(extract_map_args("$MAP[CodecMap, ListItem.AudioCodec"))


class TestMapHierarchy(ValidationTestCase):
    """`<map>` placement rules the interpreter enforces."""

    @staticmethod
    def _interpret(xml):
        return XmlInterpreter().interpret(ET.fromstring(xml.encode("utf-8"), PARSER))

    def test_map_is_valid_inside_includes(self):
        issues = self._interpret("""<includes>
            <map name="CodecMap">
                <entry key="ac3">Dolby Digital</entry>
            </map>
        </includes>""")
        self.assertEqual(issues, [])

    def test_only_entry_is_valid_inside_map(self):
        issues = self._interpret("""<includes>
            <map name="CodecMap">
                <entry key="ac3">Dolby Digital</entry>
                <value>Nope</value>
            </map>
        </includes>""")
        self.assertEqual(len(issues), 1)
        self.assertIn("<value> is not valid inside <map>", issues[0]["message"])


if __name__ == "__main__":
    import unittest
    unittest.main()
