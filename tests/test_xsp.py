"""Runtime values in smart playlist filters: which need URL encoding and which are reported."""

import os
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.infoprovider.provider import InfoProvider
from libs.validation.xsp import RAW, UNTRACED, XspValues, value_sources

PATH = "videodb://movies/titles/?xsp=%7B%22rules%22%3A%7B%22and%22%3A%5B%7B%22field%22%3A%22{field}%22%2C" \
       "%22operator%22%3A%22is%22%2C%22value%22%3A{value}%7D%5D%7D%2C%22type%22%3A%22movies%22%7D"


def path(value, field="title"):
    """An xsp path with a single "is" rule, percent-encoded as skins write it."""
    return PATH.format(field=field, value=value)


class TestXspValues(unittest.TestCase):
    """Sorting of each runtime value in a rule's value list into raw, untraced or safe."""

    def kinds(self, value, sources=None, variables=None):
        """The (expression, kind) pairs faults reports once the text is wrapped in a filter."""
        values = XspValues(sources or {}, variables or {})
        return [(expression, kind) for expression, _keyword, kind in values.faults(path(value))]

    def test_text_infos_are_raw_in_either_form(self):
        self.assertEqual(self.kinds("%5B%22$INFO[ListItem.Title]%22%5D"), [("$INFO[ListItem.Title]", RAW)])
        self.assertEqual(self.kinds("%5B$ESCINFO[ListItem.Genre]%5D"), [("$ESCINFO[ListItem.Genre]", RAW)])

    def test_numbers_and_fixed_words_need_no_encoding(self):
        self.assertEqual(self.kinds("%5B%22$INFO[Container(50).ListItem.Year]%22%5D"), [])
        self.assertEqual(self.kinds("%5B%22$INFO[ListItem.UniqueID(tmdb)]%22%5D"), [])
        self.assertEqual(self.kinds("%5B%22$INFO[ListItem.Property(year)]%22%5D"), [])
        self.assertEqual(self.kinds("%5B%22$INFO[ListItem.Property(tmdb_id)]%22%5D"), [])

    def test_property_takes_the_worst_value_the_skin_stores(self):
        raw = {"property:pick": ["$ESCINFO[ListItem.Label]"]}
        self.assertEqual(self.kinds("%5B%22$INFO[Window(Home).Property(Pick)]%22%5D", raw),
                         [("$INFO[Window(Home).Property(Pick)]", RAW)])
        literal = {"property:pick": ["Action", "Drama"]}
        self.assertEqual(self.kinds("%5B%22$INFO[Window.Property(pick)]%22%5D", literal), [])
        unsafe = {"property:pick": ["Action & Adventure"]}
        self.assertEqual(self.kinds("%5B%22$INFO[Window.Property(pick)]%22%5D", unsafe),
                         [("$INFO[Window.Property(pick)]", RAW)])

    def test_encoded_property_is_safe_under_every_name_it_sets(self):
        encoded = {"property:titleenc": ["encoded"]}
        self.assertEqual(self.kinds("%5B%22$INFO[Window(10000).Property(TitleEnc)]%22%5D", encoded), [])
        self.assertEqual(self.kinds("%5B%22$INFO[Window(10000).Property(TitleEnc.0)]%22%5D", encoded), [])
        self.assertEqual(self.kinds("%5B%22$INFO[Window(Home).Property(EncodedTitle)]%22%5D"), [])

    def test_values_set_outside_the_skin_are_untraced(self):
        self.assertEqual(self.kinds("%5B%22$INFO[Window(Home).Property(pick)]%22%5D"),
                         [("$INFO[Window(Home).Property(pick)]", UNTRACED)])
        self.assertEqual(self.kinds("%5B%22$INFO[Container(9).ListItem.Property(cast.0)]%22%5D"),
                         [("$INFO[Container(9).ListItem.Property(cast.0)]", UNTRACED)])
        self.assertEqual(self.kinds("%5B%22$INFO[Skin.String(search)]%22%5D"),
                         [("$INFO[Skin.String(search)]", UNTRACED)])

    def test_static_item_property_is_traced_through_its_items(self):
        sources = {"item:9110:dir": ["$INFO[Container(9101).ListItemAbsolute(0).Director]"], "item:9110:kind": ["movies"]}
        self.assertEqual(self.kinds("%5B%22$INFO[Container(9110).ListItem.Property(dir)]%22%5D", sources),
                         [("$INFO[Container(9110).ListItem.Property(dir)]", RAW)])
        self.assertEqual(self.kinds("%5B%22$INFO[Container(9110).ListItem.Property(kind)]%22%5D", sources), [])
        self.assertEqual(self.kinds("%5B%22$INFO[Container(9200).ListItem.Property(dir)]%22%5D", sources),
                         [("$INFO[Container(9200).ListItem.Property(dir)]", UNTRACED)])

    def test_scan_reads_static_item_properties(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "Home.xml")
            with open(path, "w", encoding="utf-8") as f:
                f.write('<window><controls><control type="list" id="9110"><content>'
                        '<item><label>a</label><property name="Dir">$INFO[ListItem.Director]</property></item>'
                        '</content></control></controls></window>')
            self.assertEqual(value_sources([path]), {"item:9110:dir": ["$INFO[ListItem.Director]"]})

    def test_keyboard_skin_string_is_raw(self):
        self.assertEqual(self.kinds("%5B%22$INFO[Skin.String(search)]%22%5D", {"skin:search": ["keyboard"]}),
                         [("$INFO[Skin.String(search)]", RAW)])

    def test_variable_takes_the_worst_of_its_values(self):
        variables = {"Pick": ["$INFO[ListItem.Year]", "$INFO[ListItem.Genre]"], "Plain": ["Action", "$INFO[ListItem.DBID]"]}
        self.assertEqual(self.kinds("%5B%22$VAR[Pick]%22%5D", variables=variables), [("$VAR[Pick]", RAW)])
        self.assertEqual(self.kinds("%5B%22$VAR[Plain]%22%5D", variables=variables), [])

    def test_only_values_inside_the_value_list_count(self):
        text = "%22value%22%3A%5B%22a%22%5D%2C%22field%22%3A%22$INFO[ListItem.Title]%22"
        self.assertEqual(list(XspValues({}, {}).faults(text)), [])

    def test_plain_json_counts_too(self):
        text = '{"rules":{"and":[{"field":"title","operator":"is","value":["$INFO[ListItem.Title]"]}]}}'
        self.assertEqual([kind for _e, _k, kind in XspValues({}, {}).faults(text)], [RAW])


class TestXspRows(unittest.TestCase):
    """Rows from a skin's filters: one error per raw value, one warning per untraced one."""

    def test_rows(self):
        home = (
            '<window><controls>'
            '<control type="button" id="10">'
            '<onclick>SetProperty(pick,$ESCINFO[ListItem.Label],home)</onclick>'
            '<onclick>RunPlugin(plugin://script.skinvariables/?info=get_encoded_string&amp;window_prop=PickEnc'
            '&amp;window_id=Home&amp;&amp;$INFO[ListItem.Label])</onclick>'
            '</control>'
            '<control type="list" id="50"><content>' + path("%5B%22$INFO[Window(Home).Property(pick)]%22%5D").replace("&", "&amp;")
            + '</content></control>'
            '<control type="list" id="51"><content>' + path("%5B%22$INFO[Window(Home).Property(PickEnc)]%22%5D").replace("&", "&amp;")
            + '</content></control>'
            '<control type="list" id="52"><content>' + path("%5B$ESCINFO[Window(Home).Property(other)]%5D").replace("&", "&amp;")
            + '</content></control>'
            '</controls></window>')
        files = {
            "addon.xml": '<addon id="skin.t" version="1.0.0"><requires><import addon="xbmc.gui" '
                         'version="5.17.0"/></requires><extension point="xbmc.gui.skin">'
                         '<res folder="16x9" default="true"/></extension></addon>',
            "16x9/Includes.xml": "<includes/>",
            "16x9/Home.xml": home,
        }
        with tempfile.TemporaryDirectory() as skin:
            for rel, text in files.items():
                os.makedirs(os.path.dirname(os.path.join(skin, rel)), exist_ok=True)
                with open(os.path.join(skin, rel), "w", encoding="utf-8") as f:
                    f.write(text)
            provider = InfoProvider()
            provider.settings = {}
            provider.init_addon(skin)
            rows = [r for r in provider.check_values() if r.get("rule", "").startswith("xml.xsp")]
        found = sorted((r["rule"], r["severity"], r["subject"]) for r in rows)
        self.assertEqual(found, [
            ("xml.xsp-unencoded", "error", "$INFO[Window(Home).Property(pick)]"),
            ("xml.xsp-untraced", "warning", "$ESCINFO[Window(Home).Property(other)]"),
        ])
        error = next(r["message"] for r in rows if r["rule"] == "xml.xsp-unencoded")
        self.assertIn("'Law & Order' empties the list", error)
        self.assertIn("URL-encode it first", error)


if __name__ == "__main__":
    unittest.main()
