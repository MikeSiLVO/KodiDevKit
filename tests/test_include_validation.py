"""Tests for IncludeCheck class (include definition and usage validation)."""

import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.base import ValidationTestCase, IncludeCheck
from libs.infoprovider.provider import InfoProvider


class TestIncludeValidation(ValidationTestCase):
    """Test include definition and usage validation."""

    def setUp(self):
        """Create temporary skin directory for each test."""
        self.test_dir = tempfile.mkdtemp()
        self.provider = InfoProvider()
        self.provider.settings = {}

        os.makedirs(os.path.join(self.test_dir, "16x9"))

        addon_xml = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test Skin" provider-name="test">
    <requires>
        <import addon="xbmc.gui" version="5.16.0"/>
    </requires>
    <extension point="xbmc.gui.skin" defaultthemename="Textures.xbt" debugging="false">
        <res width="1920" height="1080" aspect="16x9" default="true" folder="16x9" />
    </extension>
</addon>"""
        with open(os.path.join(self.test_dir, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(addon_xml)

    def tearDown(self):
        """Clean up temporary directory."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_undefined_include_detected(self):
        """Test detection of undefined include reference."""
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="DefinedInclude">
        <control type="label">
            <label>Test</label>
        </control>
    </include>
</includes>"""
        includes_path = os.path.join(self.test_dir, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <include>UndefinedInclude</include>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = IncludeCheck(self.provider.addon)
        issues = checker.check()

        undefined_issues = [i for i in issues if "UndefinedInclude" in i.get("message", "") and "not defined" in i.get("message", "").lower()]
        self.assertTrue(len(undefined_issues) > 0, "Should detect undefined include")

    def test_nested_undefined_include_reported_where_written(self):
        """An undefined include inside an include body is reported once, in the include file."""
        files = {
            "Includes.xml": '<includes>\n<include name="Outer">\n<include>Missing</include>\n'
                            '</include>\n</includes>',
            "Home.xml": "<window>\n<controls>\n<include>Outer</include>\n</controls>\n</window>",
            "MyVideoNav.xml": "<window>\n<controls>\n<include>Outer</include>\n</controls>\n</window>",
        }
        for name, text in files.items():
            with open(os.path.join(self.test_dir, "16x9", name), "w", encoding="utf-8") as f:
                f.write(text)

        self.provider.init_addon(self.test_dir)
        issues = IncludeCheck(self.provider.addon).check()

        found = [(os.path.basename(i["file"]), i["line"]) for i in issues
                 if i["message"] == "Include not defined: Missing"]
        self.assertEqual(found, [("Includes.xml", 3)])

    def test_unused_include_reported_at_its_name(self):
        """An unused include is reported on the line naming it."""
        for name, text in (("Includes.xml", '<includes>\n<include name="Spare">\n<definition>\n'
                                            '<control type="label"/>\n</definition>\n</include>\n</includes>'),
                           ("Home.xml", "<window><controls/></window>")):
            with open(os.path.join(self.test_dir, "16x9", name), "w", encoding="utf-8") as f:
                f.write(text)

        self.provider.init_addon(self.test_dir)
        lines = [i["line"] for i in IncludeCheck(self.provider.addon).check()
                 if i["message"] == "Unused include: Spare"]
        self.assertEqual(lines, [2])

    def test_content_call_with_blank_text_counts_as_usage(self):
        """A content call written across lines is a usage, its whitespace text is not a name."""
        for name, text in (("Includes.xml", '<includes>\n<include name="Weather.Item">\n<label>a</label>\n'
                                            '</include>\n</includes>'),
                           ("Home.xml", '<window><controls>\n<include content="Weather.Item">\n'
                                        '</include>\n</controls></window>')):
            with open(os.path.join(self.test_dir, "16x9", name), "w", encoding="utf-8") as f:
                f.write(text)

        self.provider.init_addon(self.test_dir)
        messages = [i["message"] for i in IncludeCheck(self.provider.addon).check()]
        self.assertNotIn("Unused include: Weather.Item", messages)

    def test_defined_include_no_issue(self):
        """Test that defined includes don't trigger issues when used."""
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="MyInclude">
        <control type="label">
            <label>Test</label>
        </control>
    </include>
</includes>"""
        includes_path = os.path.join(self.test_dir, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <include>MyInclude</include>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = IncludeCheck(self.provider.addon)
        issues = checker.check()

        myinclude_issues = [i for i in issues if "MyInclude" in i.get("message", "") and "not defined" in i.get("message", "").lower()]
        self.assertEqual(len(myinclude_issues), 0, "Should not report defined include as undefined")

    def test_unused_include_detected(self):
        """Test detection of defined but unused includes."""
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="UnusedInclude">
        <control type="label">
            <label>Test</label>
        </control>
    </include>
</includes>"""
        includes_path = os.path.join(self.test_dir, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label">
            <label>Direct control</label>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = IncludeCheck(self.provider.addon)
        issues = checker.check()

        unused_issues = [i for i in issues if "UnusedInclude" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertTrue(len(unused_issues) > 0, "Should detect unused include")

    def test_include_with_content_attribute(self):
        """Test include references using content attribute instead of text."""
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="ContentInclude">
        <control type="label">
            <label>Test</label>
        </control>
    </include>
</includes>"""
        includes_path = os.path.join(self.test_dir, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <include content="ContentInclude"/>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = IncludeCheck(self.provider.addon)
        issues = checker.check()

        content_issues = [i for i in issues if "ContentInclude" in i.get("message", "")]
        self.assertEqual(len(content_issues), 0, "Should handle include with content attribute")

    def test_skinshortcuts_includes_ignored(self):
        """Test that skinshortcuts- prefixed includes are ignored."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <include>skinshortcuts-template</include>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = IncludeCheck(self.provider.addon)
        issues = checker.check()

        skinshortcuts_issues = [i for i in issues if "skinshortcuts" in i.get("message", "").lower()]
        self.assertEqual(len(skinshortcuts_issues), 0, "Should ignore skinshortcuts- prefixed includes")

    def test_include_in_fontset(self):
        """Test that includes used in Font.xml fontsets are counted as used."""
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="FontInclude">
        <font>
            <name>font14</name>
            <filename>font.ttf</filename>
            <size>14</size>
        </font>
    </include>
</includes>"""
        includes_path = os.path.join(self.test_dir, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        font_xml = """<?xml version="1.0" encoding="UTF-8"?>
<fonts>
    <fontset id="Default" unicode="true">
        <font>
            <name>font13</name>
            <filename>font.ttf</filename>
            <size>13</size>
        </font>
        <include>FontInclude</include>
    </fontset>
</fonts>"""
        font_path = os.path.join(self.test_dir, "16x9", "Font.xml")
        with open(font_path, "w", encoding="utf-8") as f:
            f.write(font_xml)

        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = IncludeCheck(self.provider.addon)
        issues = checker.check()

        fontinclude_issues = [i for i in issues if "FontInclude" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertEqual(len(fontinclude_issues), 0, "Should count fontset includes as used")

    def test_dynamic_include_ignored(self):
        """Test that dynamic includes (starting with $) are ignored."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <include>$VAR[DynamicInclude]</include>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = IncludeCheck(self.provider.addon)
        issues = checker.check()

        self.assertIsInstance(issues, list)

    def test_include_referenced_via_param(self):
        """Test that includes referenced via <param> tags are counted as used."""
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="InfoDetailsPanel">
        <control type="group">
            <control type="panel" id="$PARAM[panel_id]">
                <content>
                    <include>$PARAM[include]</include>
                </content>
            </control>
        </control>
    </include>
    <include name="CustomInfoContentDetails">
        <include condition="true">CustomInfoContentMovies</include>
    </include>
    <include name="CustomInfoContentMovies">
        <control type="label">
            <label>Movies</label>
        </control>
    </include>
</includes>"""
        includes_path = os.path.join(self.test_dir, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <include content="InfoDetailsPanel">
            <param name="window_id">1102</param>
            <param name="panel_id">3000</param>
            <param name="include">CustomInfoContentDetails</param>
        </include>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = IncludeCheck(self.provider.addon)
        issues = checker.check()

        unused_issues = [i for i in issues if "CustomInfoContentDetails" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertEqual(len(unused_issues), 0, "Should count param-referenced includes as used")

    def test_param_with_id_not_treated_as_include(self):
        """Test that param values used for IDs are not treated as include references."""
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="SkinVariablesContentList">
        <definition>
            <control type="list" id="$PARAM[id]">
                <content>$PARAM[content]</content>
            </control>
        </definition>
    </include>
</includes>"""
        includes_path = os.path.join(self.test_dir, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <include content="SkinVariablesContentList">
            <param name="id">4800</param>
            <param name="content">$VAR[SomeVar]</param>
        </include>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = IncludeCheck(self.provider.addon)
        issues = checker.check()

        undefined_4800 = [i for i in issues if "4800" in i.get("message", "") and "not defined" in i.get("message", "").lower()]
        self.assertEqual(len(undefined_4800), 0, "Should not treat ID params as include references")

    def test_includes_used_in_skinshortcuts_template(self):
        """Test that includes referenced in shortcuts/template.xml are not flagged as unused."""
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="ListPortraitArt">
        <control type="image">
            <texture>$INFO[ListItem.Art(poster)]</texture>
        </control>
    </include>
    <include name="ListLandscapeArt">
        <control type="image">
            <texture>$INFO[ListItem.Art(landscape)]</texture>
        </control>
    </include>
    <include name="UnusedInclude">
        <control type="label">
            <label>Not used anywhere</label>
        </control>
    </include>
</includes>"""
        includes_path = os.path.join(self.test_dir, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        shortcuts_dir = os.path.join(self.test_dir, "shortcuts")
        os.makedirs(shortcuts_dir, exist_ok=True)
        template_xml = """<?xml version="1.0" encoding="UTF-8"?>
<template>
    <other include="widget1">
        <property name="artcontent" tag="property" attribute="name|widgetArt" value="Poster">ListPortraitArt</property>
        <property name="artcontent" tag="property" attribute="name|widgetArt" value="Landscape">ListLandscapeArt</property>
    </other>
</template>"""
        template_path = os.path.join(shortcuts_dir, "template.xml")
        with open(template_path, "w", encoding="utf-8") as f:
            f.write(template_xml)

        self.provider.init_addon(self.test_dir)
        checker = IncludeCheck(self.provider.addon)
        issues = checker.check()

        portrait_unused = [i for i in issues if "ListPortraitArt" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertEqual(len(portrait_unused), 0, "Should not flag includes used in template.xml as unused")

        landscape_unused = [i for i in issues if "ListLandscapeArt" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertEqual(len(landscape_unused), 0, "Should not flag includes used in template.xml as unused")

        truly_unused = [i for i in issues if "UnusedInclude" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertEqual(len(truly_unused), 1, "Should still flag actually unused includes")


    def test_includes_used_in_skinshortcuts_v3_template(self):
        """Test that includes referenced in v3 shortcuts/templates.xml are not flagged as unused."""
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="HomeWidgetFade">
        <animation effect="fade" start="100" end="0" time="300">Visible</animation>
    </include>
    <include name="PanelLabel">
        <control type="label"><label>$PARAM[Label]</label></control>
    </include>
    <include name="InfoPosterContent">
        <control type="image"><texture>$INFO[ListItem.Art(poster)]</texture></control>
    </include>
    <include name="UnusedV3Include">
        <control type="label"><label>Not used</label></control>
    </include>
</includes>"""
        includes_path = os.path.join(self.test_dir, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls/>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        shortcuts_dir = os.path.join(self.test_dir, "shortcuts")
        os.makedirs(shortcuts_dir, exist_ok=True)
        templates_xml = """<?xml version="1.0" encoding="UTF-8"?>
<templates>
    <template include="widget1" idprefix="8011" build="menu" menu="mainmenu">
        <controls>
            <include condition="!String.IsEmpty(Skin.String(Widget.Trans))">HomeWidgetFade</include>
            <include content="PanelLabel">
                <param name="Label">Test</param>
            </include>
            <skinshortcuts include="InfoPosterContent" condition="widgetArt=Poster" />
            <include content="$PROPERTY[artcontent]"/>
        </controls>
    </template>
</templates>"""
        template_path = os.path.join(shortcuts_dir, "templates.xml")
        with open(template_path, "w", encoding="utf-8") as f:
            f.write(templates_xml)

        self.provider.init_addon(self.test_dir)
        checker = IncludeCheck(self.provider.addon)
        issues = checker.check()

        fade_unused = [i for i in issues if "HomeWidgetFade" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertEqual(len(fade_unused), 0, "Should find includes in <include> text content")

        panel_unused = [i for i in issues if "PanelLabel" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertEqual(len(panel_unused), 0, "Should find includes in content attribute")

        poster_unused = [i for i in issues if "InfoPosterContent" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertEqual(len(poster_unused), 0, "Should find includes in skinshortcuts include attribute")

        truly_unused = [i for i in issues if "UnusedV3Include" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertEqual(len(truly_unused), 1, "Should still flag actually unused includes")


if __name__ == "__main__":
    unittest.main()
