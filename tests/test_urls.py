"""Runtime values in xsp filters and plugin URLs: which need URL encoding and which are reported."""

import os
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.infoprovider.provider import InfoProvider
from libs.validation.urls import RAW, TYPED, UNTRACED, UrlValues, value_sources

PATH = "videodb://movies/titles/?xsp=%7B%22rules%22%3A%7B%22and%22%3A%5B%7B%22field%22%3A%22{field}%22%2C" \
       "%22operator%22%3A%22is%22%2C%22value%22%3A{value}%7D%5D%7D%2C%22type%22%3A%22movies%22%7D"


def path(value, field="title"):
    """An xsp path with a single "is" rule, percent-encoded as skins write it."""
    return PATH.format(field=field, value=value)


class TestUrlValues(unittest.TestCase):
    """Sorting of each runtime value in a rule's value list into raw, untraced or safe."""

    def kinds(self, value, sources=None, variables=None):
        """The (expression, kind) pairs xsp_faults reports once the text is wrapped in a filter."""
        values = UrlValues(sources or {}, variables or {})
        return [(expression, kind) for expression, _keyword, kind in values.xsp_faults(path(value))]

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
        self.assertEqual(list(UrlValues({}, {}).xsp_faults(text)), [])

    def test_plain_json_counts_too(self):
        text = '{"rules":{"and":[{"field":"title","operator":"is","value":["$INFO[ListItem.Title]"]}]}}'
        self.assertEqual([kind for _e, _k, kind in UrlValues({}, {}).xsp_faults(text)], [RAW])


class TestUrlRows(unittest.TestCase):
    """Xsp and plugin URL rows: errors for raw or escaped typed values, warnings for the rest."""

    def test_rows(self):
        """Check the rule, severity and subject of every URL fault in one window."""
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
            '<control type="list" id="53"><content>plugin://plugin.video.x/?query=$INFO[ListItem.Title]</content>'
            '</control>'
            '<control type="list" id="54"><content>plugin://plugin.program.autocompletion?info=autocomplete'
            '&amp;id=$INFO[Control.GetLabel(312).Index(1)]</content></control>'
            '<control type="list" id="55"><content>plugin://plugin.video.x/?q=$ESCINFO[Control.GetLabel(312).Index(1)]'
            '</content></control>'
            '<control type="list" id="56"><content>' + path("%5B%22$INFO[Control.GetLabel(9).Index(1)]%22%5D").replace("&", "&amp;")
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
            rows = [r for r in provider.check_values() if r.get("rule", "").startswith(("xml.xsp", "xml.plugin"))]
        found = sorted((r["rule"], r["severity"], r["subject"]) for r in rows)
        self.assertEqual(found, [
            ("xml.plugin-typed-text", "warning", "$INFO[Control.GetLabel(312).Index(1)]"),
            ("xml.plugin-unencoded", "error", "$ESCINFO[Control.GetLabel(312).Index(1)]"),
            ("xml.plugin-unencoded", "error", "$INFO[ListItem.Title]"),
            ("xml.xsp-typed-text", "warning", "$INFO[Control.GetLabel(9).Index(1)]"),
            ("xml.xsp-unencoded", "error", "$INFO[Window(Home).Property(pick)]"),
            ("xml.xsp-untraced", "warning", "$ESCINFO[Window(Home).Property(other)]"),
        ])
        typed = next(r["message"] for r in rows if r["rule"] == "xml.plugin-typed-text")
        self.assertIn("typing 'Law & Order' reaches the add-on cut short", typed)
        error = next(r["message"] for r in rows if r["rule"] == "xml.xsp-unencoded")
        self.assertIn("'Law & Order' empties the list", error)
        self.assertIn("URL-encode it first", error)


class TestPluginValues(unittest.TestCase):
    """Runtime values in a plugin URL's query, which the add-on splits on & and decodes."""

    def kinds(self, text, sources=None, variables=None):
        """The (expression, kind, variable) triples the text gives inside plugin queries."""
        return [(expression, kind, variable) for expression, _keyword, kind, variable
                in UrlValues(sources or {}, variables or {}).plugin_faults(text)]

    def test_text_values_are_raw_in_either_form(self):
        text = "plugin://plugin.video.x/?info=search&query=$INFO[ListItem.Title]&year=$INFO[ListItem.Year]"
        self.assertEqual(self.kinds(text), [("$INFO[ListItem.Title]", RAW, None)])
        self.assertEqual(self.kinds("RunPlugin(plugin://plugin.video.x/?q=$ESCINFO[ListItem.Label])"),
                         [("$ESCINFO[ListItem.Label]", RAW, None)])

    def test_encoded_and_plain_values_pass(self):
        sources = {"property:titleenc": ["encoded"]}
        self.assertEqual(self.kinds("plugin://x/?a=$INFO[Window(Home).Property(TitleEnc)]&b=$INFO[ListItem.DBID]",
                                    sources), [])

    def test_the_encoder_call_takes_the_raw_value(self):
        text = 'RunPlugin("plugin://script.skinvariables/?info=get_encoded_string&window_prop=E&&$INFO[ListItem.Label]")'
        self.assertEqual(self.kinds(text), [])

    def test_only_the_query_counts(self):
        self.assertEqual(self.kinds("plugin://x/$INFO[ListItem.Title]/"), [])
        self.assertEqual(self.kinds("RunPlugin(plugin://x/?a=b) + $INFO[ListItem.Title]"), [])

    def test_values_set_outside_the_skin_are_untraced(self):
        self.assertEqual(self.kinds("ActivateWindow(Videos,plugin://x/?a=$INFO[ListItem.Property(cast.0)],return)"),
                         [("$INFO[ListItem.Property(cast.0)]", UNTRACED, None)])

    def test_variables_holding_pairs_are_scanned_for_their_values(self):
        variables = {"Defaults": ["nextpage=false&fanarttv=false"], "Pairs": ["&query=$INFO[ListItem.Label]"],
                     "Title": ["$INFO[ListItem.Title]"], "Genre": ["Action & Adventure"]}
        self.assertEqual(self.kinds("plugin://p/?info=x&$VAR[Defaults]", variables=variables), [])
        self.assertEqual(self.kinds("plugin://p/?info=x$VAR[Pairs]", variables=variables),
                         [("$INFO[ListItem.Label]", RAW, "$VAR[Pairs]")])
        self.assertEqual(self.kinds("plugin://p/?query=$VAR[Title]", variables=variables),
                         [("$INFO[ListItem.Title]", RAW, "$VAR[Title]")])
        self.assertEqual(self.kinds("plugin://p/?genre=$VAR[Genre]", variables=variables),
                         [("$VAR[Genre]", RAW, None)])

    def test_time_date_and_sort_words_need_no_encoding(self):
        self.assertEqual(self.kinds("plugin://p/?t=$INFO[System.Time(hh)]&d=$INFO[System.Date]"
                                    "&s=$INFO[Container.SortMethod]&o=$INFO[Container.SortOrder]"), [])

    def test_edit_control_text_is_typed(self):
        """An edit control's typed text, read through Index(1), is its own kind."""
        typed = "$INFO[Control.GetLabel(312).Index(1)]"
        self.assertEqual(self.kinds(f"plugin://plugin.program.autocompletion?info=autocomplete&id={typed}&limit=8"),
                         [(typed, TYPED, None)])
        self.assertEqual(self.kinds("plugin://p/?q=$INFO[Control.GetLabel(312)]"),
                         [("$INFO[Control.GetLabel(312)]", RAW, None)])

    def test_a_reload_token_is_never_read_as_data(self):
        self.assertEqual(self.kinds("plugin://p/?info=x&reload=$INFO[Window(Home).Property(Widgets.Reload)]"), [])

    def test_a_pair_opened_in_an_info_prefix(self):
        self.assertEqual(self.kinds("plugin://p/?info=search$INFO[ListItem.Label,&query=,]"),
                         [("$INFO[ListItem.Label,&query=,]", RAW, None)])
        self.assertEqual(self.kinds("plugin://p/?info=search&$INFO[ListItem.Year,year=,]"), [])


if __name__ == "__main__":
    unittest.main()
