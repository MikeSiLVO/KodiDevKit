"""Tests for the font check: definitions, files, fontsets and where fonts are used."""

import os
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.infoprovider.provider import InfoProvider


class TestFontValidation(unittest.TestCase):
    """Font check cases, each run on a fresh skin folder."""

    def setUp(self):
        """Create temporary skin structure for testing."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.skin_path = self.temp_dir.name

        self.xml_dir = os.path.join(self.skin_path, "16x9")
        self.fonts_dir = os.path.join(self.skin_path, "fonts")
        os.makedirs(self.xml_dir, exist_ok=True)
        os.makedirs(self.fonts_dir, exist_ok=True)

        addon_xml = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test Skin" provider-name="Test">
    <requires>
        <import addon="xbmc.gui" version="5.15.0"/>
    </requires>
    <extension point="xbmc.gui.skin" debugging="false">
        <res width="1920" height="1080" aspect="16:9" default="true" folder="16x9" />
    </extension>
</addon>
"""
        with open(os.path.join(self.skin_path, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(addon_xml)

    def tearDown(self):
        """Clean up temporary directory."""
        self.temp_dir.cleanup()

    def create_font_file(self, filename):
        """Create a dummy font file."""
        path = os.path.join(self.fonts_dir, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"FAKE TTF FILE")
        return path

    def create_includes_xml(self, content):
        """Create Includes.xml in the xml directory."""
        path = os.path.join(self.xml_dir, "Includes.xml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def create_fonts_xml(self, content):
        """Create Font.xml in the xml directory."""
        path = os.path.join(self.xml_dir, "Font.xml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def create_window_xml(self, content):
        """Create a window XML file."""
        path = os.path.join(self.xml_dir, "Home.xml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def init_provider(self):
        """Initialize InfoProvider with test skin."""
        provider = InfoProvider()
        provider.settings = {}
        provider.init_addon(self.skin_path)
        return provider

    def test_valid_single_fontset(self):
        """Test valid single fontset with all required elements."""
        self.create_font_file("font.ttf")

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font13</name>
            <filename>font.ttf</filename>
            <size>13</size>
        </font>
        <font>
            <name>font16</name>
            <filename>font.ttf</filename>
            <size>16</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)

        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label">
            <font>font13</font>
            <label>Test</label>
        </control>
        <control type="label">
            <font>font16</font>
            <label>Test</label>
        </control>
    </controls>
</window>
"""
        self.create_window_xml(window_xml)

        provider = self.init_provider()
        issues = provider.check_fonts()

        errors = [i for i in issues if "no" not in i["message"].lower() and "unused" not in i["message"].lower()]
        self.assertEqual(len(errors), 0, f"Should have no errors, got: {errors}")

    def test_param_font_in_an_include_resolves_per_call(self):
        """A $PARAM font name is checked as each call fills it; the fonts it names count as used."""
        self.create_font_file("font.ttf")
        self.create_fonts_xml("""<fonts><fontset id="Default">
    <font><name>font13</name><filename>font.ttf</filename><size>13</size></font>
    <font><name>Key_1</name><filename>font.ttf</filename><size>13</size></font>
</fontset></fonts>""")
        self.create_includes_xml("""<includes>
    <include name="Key">
        <param name="position" />
        <definition><control type="label"><font>Key_$PARAM[position]</font></control></definition>
    </include>
</includes>""")
        self.create_window_xml("""<window><controls>
    <include content="Key"><param name="position" value="1" /></include>
    <include content="Key"><param name="position" value="2" /></include>
</controls></window>""")
        messages = [i["message"] for i in self.init_provider().check_fonts()]
        self.assertIn("Font 'Key_2' is used but not defined in Font.xml", messages)
        self.assertFalse([m for m in messages if "Key_1" in m or "$PARAM" in m], messages)

    def test_font_named_wholly_by_param_resolves_per_call(self):
        """<font>$PARAM[f]</font> takes each call's font, or its default where a call drops it."""
        self.create_font_file("font.ttf")
        self.create_fonts_xml("""<fonts><fontset id="Default">
    <font><name>font13</name><filename>font.ttf</filename><size>13</size></font>
    <font><name>Key_1</name><filename>font.ttf</filename><size>13</size></font>
    <font><name>Fallback</name><filename>font.ttf</filename><size>13</size></font>
</fontset></fonts>""")
        self.create_includes_xml("""<includes>
    <include name="Key">
        <param name="f" default="Fallback" />
        <definition><control type="label"><font>$PARAM[f]</font></control></definition>
    </include>
    <include name="Outer">
        <definition>
            <include content="Key"><param name="f" value="$PARAM[unset]" /></include>
        </definition>
    </include>
</includes>""")
        self.create_window_xml("""<window><controls>
    <include content="Key"><param name="f" value="Key_1" /></include>
    <include content="Outer" />
</controls></window>""")
        messages = [i["message"] for i in self.init_provider().check_fonts()]
        self.assertFalse([m for m in messages if "Key_1" in m or "Fallback" in m or "Font ''" in m], messages)

    def test_missing_font13(self):
        """Test detection of missing required font13."""
        self.create_font_file("font.ttf")

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font16</name>
            <filename>font.ttf</filename>
            <size>16</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)
        provider = self.init_provider()

        issues = provider.check_fonts()

        has_font13_error = any("font13" in issue["message"].lower() for issue in issues)
        self.assertTrue(has_font13_error, "Should detect missing font13")

    def test_unicode_attribute_obsolete(self):
        """A unicode attribute is a warning, and leaving it out is fine."""
        self.create_font_file("font.ttf")
        font = "<font><name>font13</name><filename>font.ttf</filename><size>13</size></font>"
        self.create_fonts_xml(f'<fonts><fontset id="A" unicode="true">{font}</fontset>'
                              f'<fontset id="B">{font}</fontset></fonts>')
        issues = [i for i in self.init_provider().check_fonts() if "unicode" in i["message"].lower()]
        self.assertEqual([(i["message"], i["severity"]) for i in issues],
                         [("Obsolete unicode attribute on fontset 'A', Kodi ignores it", "warning")])

    def test_missing_size_keeps_font(self):
        """A font without <size> is defined, since Kodi defaults the size to 20."""
        self.create_font_file("font.ttf")
        self.create_fonts_xml('<fonts><fontset id="Default"><font><name>font13</name>'
                              '<filename>font.ttf</filename></font>'
                              '<font><name>Big</name><filename>font.ttf</filename></font>'
                              '</fontset></fonts>')
        self.create_window_xml('<window><controls><control type="label"><font>Big</font>'
                               '</control></controls></window>')
        issues = self.init_provider().check_fonts()
        self.assertFalse([i for i in issues if i.get("severity") == "error"], issues)

    def test_missing_font_file(self):
        """Test detection of missing font file."""
        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font13</name>
            <filename>missing.ttf</filename>
            <size>13</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)
        provider = self.init_provider()

        issues = provider.check_fonts()

        has_missing_file = any("missing.ttf" in issue["message"].lower() for issue in issues)
        self.assertTrue(has_missing_file, "Should detect missing font file")

    def test_case_mismatch_font_file(self):
        """Test detection of case mismatch in font filename."""
        self.create_font_file("Font.ttf")

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font13</name>
            <filename>font.ttf</filename>
            <size>13</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)
        provider = self.init_provider()

        issues = provider.check_fonts()

        has_case_error = any("case" in issue["message"].lower() for issue in issues)
        self.assertTrue(has_case_error, "Should detect case mismatch in filename")

    def test_case_mismatch_font_file_in_subdirectory(self):
        """Case mismatch below the fonts dir must report as such, not as a missing file."""
        self.create_font_file("lyrics/theboldfont.ttf")

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font13</name>
            <filename>lyrics/Theboldfont.ttf</filename>
            <size>13</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)
        provider = self.init_provider()

        issues = provider.check_fonts()

        case_issues = [i for i in issues if "case mismatch" in i["message"].lower()]
        self.assertEqual(len(case_issues), 1, f"Should report one case mismatch, got: {issues}")
        self.assertIn("lyrics/theboldfont.ttf", case_issues[0]["message"])
        self.assertFalse(
            any("missing font file" in i["message"].lower() for i in issues),
            "Case mismatch must not also report as a missing file",
        )

    def test_case_mismatch_in_font_subdirectory_name(self):
        """A miscased directory component resolves the same way a miscased filename does."""
        self.create_font_file("lyrics/theboldfont.ttf")

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font13</name>
            <filename>Lyrics/theboldfont.ttf</filename>
            <size>13</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)
        provider = self.init_provider()

        issues = provider.check_fonts()

        case_issues = [i for i in issues if "case mismatch" in i["message"].lower()]
        self.assertEqual(len(case_issues), 1, f"Should report one case mismatch, got: {issues}")
        self.assertIn("lyrics/theboldfont.ttf", case_issues[0]["message"])

    def test_font_from_include_reported_against_include_file(self):
        """A font spliced in from an include is reported once, against the include's file."""
        self.create_font_file("font.ttf")

        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="LyricsFonts">
        <font>
            <name>lyr1</name>
            <filename>missing.ttf</filename>
            <size>30</size>
        </font>
    </include>
</includes>
"""
        self.create_includes_xml(includes_xml)

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font13</name>
            <filename>font.ttf</filename>
            <size>13</size>
        </font>
        <include>LyricsFonts</include>
    </fontset>
    <fontset id="Arial">
        <font>
            <name>font13</name>
            <filename>font.ttf</filename>
            <size>13</size>
        </font>
        <include>LyricsFonts</include>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)

        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label">
            <font>lyr1</font>
            <label>Test</label>
        </control>
    </controls>
</window>
"""
        self.create_window_xml(window_xml)

        provider = self.init_provider()
        issues = provider.check_fonts()

        missing = [i for i in issues if "missing font file" in i["message"].lower()]
        self.assertEqual(len(missing), 1, f"Two fontsets share one definition, expected one issue, got: {missing}")
        self.assertTrue(
            missing[0]["file"].endswith("Includes.xml"),
            f"Should point at the include's file, got: {missing[0]['file']}",
        )

    def test_invalid_font_size(self):
        """Test detection of invalid font size."""
        self.create_font_file("font.ttf")

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font13</name>
            <filename>font.ttf</filename>
            <size>-5</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)
        provider = self.init_provider()

        issues = provider.check_fonts()

        has_size_error = any("size" in issue["message"].lower() and "negative" in issue["message"].lower() for issue in issues)
        self.assertTrue(has_size_error, "Should detect invalid font size")

    def test_zero_font_size_allowed(self):
        """Kodi does not reject a size 0 font, so it is not flagged."""
        self.create_font_file("font.ttf")

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font13</name>
            <filename>font.ttf</filename>
            <size>0</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)
        provider = self.init_provider()

        issues = provider.check_fonts()

        size_issues = [i for i in issues if "size" in i["message"].lower()]
        self.assertEqual(size_issues, [])

    def test_duplicate_font_name_in_fontset(self):
        """Test detection of duplicate font name within a fontset."""
        self.create_font_file("font.ttf")

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font13</name>
            <filename>font.ttf</filename>
            <size>13</size>
        </font>
        <font>
            <name>font13</name>
            <filename>font.ttf</filename>
            <size>16</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)
        provider = self.init_provider()

        issues = provider.check_fonts()

        has_duplicate_error = any("duplicate" in issue["message"].lower() for issue in issues)
        self.assertTrue(has_duplicate_error, "Should detect duplicate font name")

    def test_duplicate_font_name_through_conditional_includes(self):
        """Copies from conditional includes clash only after a copy that is always there."""
        self.create_font_file("font.ttf")
        font = "<font><name>{}</name><filename>font.ttf</filename><size>13</size></font>"
        self.create_includes_xml(
            '<includes><include name="SetA">' + font.format("plot") + font.format("late") +
            font.format("font13") +
            '</include><include name="SetB">' + font.format("plot") + font.format("late") +
            "</include></includes>")
        self.create_fonts_xml(
            '<fonts><fontset id="Default">' + font.format("font13") +
            '<include condition="Skin.HasSetting(a)">SetA</include>'
            '<include condition="!Skin.HasSetting(a)">SetB</include>' + font.format("late") +
            "</fontset></fonts>")
        self.create_window_xml("<window><controls/></window>")

        issues = self.init_provider().check_fonts()

        duplicates = {i["message"] for i in issues if i["message"].startswith("Duplicate")}
        self.assertEqual(duplicates, {"Duplicate font name 'font13' within fontset 'Default'"})

    def test_missing_font_name(self):
        """Test detection of missing <name> element."""
        self.create_font_file("font.ttf")

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <filename>font.ttf</filename>
            <size>13</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)
        provider = self.init_provider()

        issues = provider.check_fonts()

        has_name_error = any("missing" in issue["message"].lower() and "name" in issue["message"].lower() for issue in issues)
        self.assertTrue(has_name_error, "Should detect missing font name")

    def test_cross_fontset_consistency(self):
        """Test detection of inconsistent font names across fontsets."""
        self.create_font_file("font.ttf")

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font13</name>
            <filename>font.ttf</filename>
            <size>13</size>
        </font>
        <font>
            <name>font16</name>
            <filename>font.ttf</filename>
            <size>16</size>
        </font>
    </fontset>
    <fontset id="Alternative">
        <font>
            <name>font13</name>
            <filename>font.ttf</filename>
            <size>13</size>
        </font>
        <!-- Missing font16 -->
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)
        provider = self.init_provider()

        issues = provider.check_fonts()

        has_consistency_error = any("missing font" in issue["message"].lower() and "compared to" in issue["message"].lower() for issue in issues)
        self.assertTrue(has_consistency_error, "Should detect cross-fontset inconsistency")

    def test_used_but_undefined_font(self):
        """Test detection of font used in window but not defined in Font.xml."""
        self.create_font_file("font.ttf")

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font13</name>
            <filename>font.ttf</filename>
            <size>13</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)

        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label">
            <font>UndefinedFont</font>
            <label>Test</label>
        </control>
    </controls>
</window>
"""
        self.create_window_xml(window_xml)

        provider = self.init_provider()
        issues = provider.check_fonts()

        has_undefined_error = any("undefinedfont" in issue["message"].lower() and "not defined" in issue["message"].lower() for issue in issues)
        self.assertTrue(has_undefined_error, "Should detect used but undefined font")

    def test_font_name_case_mismatch(self):
        """A miscased font name is a case mismatch, not undefined, and the font counts as used."""
        self.create_font_file("font.ttf")
        self.create_fonts_xml('<fonts><fontset id="Default"><font><name>font13</name>'
                              '<filename>font.ttf</filename></font>'
                              '<font><name>Title</name><filename>font.ttf</filename></font>'
                              '</fontset></fonts>')
        self.create_window_xml('<window><controls><control type="label"><font>TITLE</font>'
                               '</control></controls></window>')
        messages = [i["message"] for i in self.init_provider().check_fonts()]
        self.assertIn("Case mismatch in font name 'TITLE' (defined as 'Title')", messages)
        self.assertFalse([m for m in messages if "not defined" in m or "Unused" in m], messages)

    def test_noop_font_is_not_empty(self):
        """A noop font gets its own message, not undefined."""
        self.create_font_file("font.ttf")
        self.create_fonts_xml('<fonts><fontset id="Default"><font><name>font13</name>'
                              '<filename>font.ttf</filename></font></fontset></fonts>')
        self.create_window_xml('<window><controls><control type="label"><font>noop</font>'
                               '</control></controls></window>')
        messages = [i["message"] for i in self.init_provider().check_fonts()]
        self.assertIn("'noop' is not an empty font in Kodi; leave the tag out", messages)
        self.assertFalse([m for m in messages if "not defined" in m])

    def test_non_ttf_font_is_never_loaded(self):
        """An .otf font is an error where defined and where used; .ttf in any case loads."""
        self.create_font_file("font.otf")
        self.create_font_file("Big.TTF")
        self.create_fonts_xml('<fonts><fontset id="Default"><font><name>font13</name>'
                              '<filename>Big.TTF</filename></font>'
                              '<font><name>Fancy</name><filename>font.otf</filename></font></fontset></fonts>')
        self.create_window_xml('<window><controls><control type="label"><font>Fancy</font>'
                               '</control></controls></window>')
        messages = [i["message"] for i in self.init_provider().check_fonts()]
        self.assertIn("Kodi only loads .ttf fonts, so 'Fancy' (font.otf) is never loaded", messages)
        self.assertIn("Font 'Fancy' is never loaded: Kodi only loads .ttf fonts", messages)
        self.assertFalse([m for m in messages if "font13" in m or "Big.TTF" in m], messages)

    def test_font_file_with_no_extension_is_never_loaded(self):
        """A file name with no extension gets the same never-loaded error as any other non-.ttf."""
        self.create_font_file("Plain")
        self.create_fonts_xml('<fonts><fontset id="Default"><font><name>font13</name>'
                              '<filename>Plain</filename></font></fontset></fonts>')
        messages = [i["message"] for i in self.init_provider().check_fonts()]
        self.assertIn("Kodi only loads .ttf fonts, so 'font13' (Plain) is never loaded", messages)

    def test_fontset_without_font13_says_what_it_costs(self):
        """A fontset lacking font13 while another has it gets a warning naming the fallback."""
        self.create_font_file("font.ttf")
        self.create_fonts_xml('<fonts><fontset id="Default"><font><name>font13</name><filename>font.ttf'
                              '</filename></font></fontset><fontset id="Small"><font><name>font10</name>'
                              '<filename>font.ttf</filename></font></fontset></fonts>')
        messages = [i["message"] for i in self.init_provider().check_fonts()]
        self.assertIn("Fontset 'Small' has no font13, which Kodi uses for any font name the fontset lacks",
                      messages)

    def test_defined_but_unused_font(self):
        """Test detection of font defined but never used."""
        self.create_font_file("font.ttf")

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font13</name>
            <filename>font.ttf</filename>
            <size>13</size>
        </font>
        <font>
            <name>UnusedFont</name>
            <filename>font.ttf</filename>
            <size>20</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)

        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label">
            <font>font13</font>
            <label>Test</label>
        </control>
    </controls>
</window>
"""
        self.create_window_xml(window_xml)

        provider = self.init_provider()
        issues = provider.check_fonts()

        has_unused_error = any("unusedfont" in issue["message"].lower() and "unused" in issue["message"].lower() for issue in issues)
        self.assertTrue(has_unused_error, "Should detect defined but unused font")

    def test_monofont_counts_as_a_use(self):
        """A textbox <monofont> uses its font, and names one that must be defined."""
        self.create_font_file("font.ttf")
        self.create_fonts_xml("""<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default">
        <font><name>font13</name><filename>font.ttf</filename><size>13</size></font>
        <font><name>Mono26</name><filename>font.ttf</filename><size>26</size></font>
    </fontset>
</fonts>
""")
        self.create_window_xml("""<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="textbox">
            <font>font13</font>
            <monofont>Mono26</monofont>
        </control>
        <control type="textbox">
            <font>font13</font>
            <monofont>Mono99</monofont>
        </control>
    </controls>
</window>
""")
        issues = self.init_provider().check_fonts()

        self.assertEqual(sorted((i["rule"], i["subject"]) for i in issues), [("fonts.undefined", "Mono99")])

    def test_dynamic_param_values_ignored(self):
        """Test that $PARAM[...] values are ignored in validation."""
        self.create_font_file("font.ttf")

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font13</name>
            <filename>$PARAM[fontfile]</filename>
            <size>$PARAM[fontsize]</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)
        provider = self.init_provider()

        issues = provider.check_fonts()

        has_false_positive = any(
            "param[fontfile]" in issue["message"].lower() or
            "param[fontsize]" in issue["message"].lower()
            for issue in issues
        )
        self.assertFalse(has_false_positive, "Should ignore $PARAM[] in validation")

    def test_font13_not_flagged_as_unused(self):
        """Test that font13 is never flagged as unused (it's a required Kodi font)."""
        self.create_font_file("font.ttf")

        fonts_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font13</name>
            <filename>font.ttf</filename>
            <size>13</size>
        </font>
        <font>
            <name>font16</name>
            <filename>font.ttf</filename>
            <size>16</size>
        </font>
    </fontset>
</fonts>
"""
        self.create_fonts_xml(fonts_xml)

        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label">
            <font>font16</font>
            <label>Test</label>
        </control>
    </controls>
</window>
"""
        self.create_window_xml(window_xml)

        provider = self.init_provider()
        issues = provider.check_fonts()

        font13_unused = any("font13" in issue["message"].lower() and "unused" in issue["message"].lower() for issue in issues)
        self.assertFalse(font13_unused, "font13 should not be flagged as unused (it's a required Kodi font)")


if __name__ == "__main__":
    unittest.main()
