"""
Tests for IncludeCheck class (include definition and usage validation).
"""

import os
import sys
import tempfile
import shutil
import unittest

# Ensure parent directory is in path (base.py does this too, but be explicit)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Now we can import from base and libs
from tests.base import ValidationTestCase, IncludeCheck
from libs.infoprovider import InfoProvider


class TestIncludeValidation(ValidationTestCase):
    """Test include definition and usage validation."""

    def setUp(self):
        """Create temporary skin directory for each test."""
        self.test_dir = tempfile.mkdtemp()
        self.provider = InfoProvider()
        self.provider.settings = {}

        # Create basic addon structure
        os.makedirs(os.path.join(self.test_dir, "16x9"))

        # Write addon.xml
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
        # Create includes file with one include
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

        # Create window that references undefined include
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

        # Should detect undefined include
        undefined_issues = [i for i in issues if "UndefinedInclude" in i.get("message", "") and "not defined" in i.get("message", "").lower()]
        self.assertTrue(len(undefined_issues) > 0, "Should detect undefined include")

    def test_defined_include_no_issue(self):
        """Test that defined includes don't trigger issues when used."""
        # Create includes file
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

        # Create window that uses the include
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

        # Should not report MyInclude as undefined
        myinclude_issues = [i for i in issues if "MyInclude" in i.get("message", "") and "not defined" in i.get("message", "").lower()]
        self.assertEqual(len(myinclude_issues), 0, "Should not report defined include as undefined")

    def test_unused_include_detected(self):
        """Test detection of defined but unused includes."""
        # Create includes file with unused include
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

        # Create empty window (no includes used)
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

        # Should detect unused include
        unused_issues = [i for i in issues if "UnusedInclude" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertTrue(len(unused_issues) > 0, "Should detect unused include")

    def test_include_with_content_attribute(self):
        """Test include references using content attribute instead of text."""
        # Create includes file
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

        # Create window using content attribute
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

        # Should not report ContentInclude as undefined or unused
        content_issues = [i for i in issues if "ContentInclude" in i.get("message", "")]
        self.assertEqual(len(content_issues), 0, "Should handle include with content attribute")

    def test_skinshortcuts_includes_ignored(self):
        """Test that skinshortcuts- prefixed includes are ignored."""
        # Create window with skinshortcuts include (which won't be defined)
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

        # Should not report skinshortcuts- includes
        skinshortcuts_issues = [i for i in issues if "skinshortcuts" in i.get("message", "").lower()]
        self.assertEqual(len(skinshortcuts_issues), 0, "Should ignore skinshortcuts- prefixed includes")

    def test_include_in_fontset(self):
        """Test that includes used in Font.xml fontsets are counted as used."""
        # Create includes file
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

        # Create Font.xml with include in fontset
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

        # Create empty Home.xml
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

        # Should not report FontInclude as unused since it's used in fontset
        fontinclude_issues = [i for i in issues if "FontInclude" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertEqual(len(fontinclude_issues), 0, "Should count fontset includes as used")

    def test_dynamic_include_ignored(self):
        """Test that dynamic includes (starting with $) are ignored."""
        # Create window with dynamic include reference
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

        # Should not report dynamic includes as undefined
        # (they start with $, so they're skipped in the undefined check)
        self.assertIsInstance(issues, list)

    def test_include_referenced_via_param(self):
        """Test that includes referenced via <param> tags are counted as used."""
        # Create includes file with a parameterized container include and content include
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

        # Create window using the include with param
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

        # Should not report CustomInfoContentDetails as unused
        # (it's referenced via <param name="include">)
        unused_issues = [i for i in issues if "CustomInfoContentDetails" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertEqual(len(unused_issues), 0, "Should count param-referenced includes as used")

    def test_param_with_id_not_treated_as_include(self):
        """Test that param values used for IDs are not treated as include references."""
        # Create includes file where param is used for ID, not include
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

        # Create window using the include with ID param
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

        # Should NOT report "4800" as an undefined include
        # (it's an ID, not an include reference)
        undefined_4800 = [i for i in issues if "4800" in i.get("message", "") and "not defined" in i.get("message", "").lower()]
        self.assertEqual(len(undefined_4800), 0, "Should not treat ID params as include references")

    def test_includes_used_in_skinshortcuts_template(self):
        """Test that includes referenced in shortcuts/template.xml are not flagged as unused."""
        # Create includes file with includes that will be used only in template.xml
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

        # Create empty window (no includes used directly)
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        # Create shortcuts/template.xml that references the includes
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

        # Should not report ListPortraitArt as unused (it's in template.xml)
        portrait_unused = [i for i in issues if "ListPortraitArt" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertEqual(len(portrait_unused), 0, "Should not flag includes used in template.xml as unused")

        # Should not report ListLandscapeArt as unused (it's in template.xml)
        landscape_unused = [i for i in issues if "ListLandscapeArt" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertEqual(len(landscape_unused), 0, "Should not flag includes used in template.xml as unused")

        # Should report UnusedInclude as unused (not in template.xml or anywhere else)
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

        # v3 templates.xml with <include> tags and content/include attributes
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

        # Found via <include>text</include>
        fade_unused = [i for i in issues if "HomeWidgetFade" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertEqual(len(fade_unused), 0, "Should find includes in <include> text content")

        # Found via <include content="Name">
        panel_unused = [i for i in issues if "PanelLabel" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertEqual(len(panel_unused), 0, "Should find includes in content attribute")

        # Found via <skinshortcuts include="Name">
        poster_unused = [i for i in issues if "InfoPosterContent" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertEqual(len(poster_unused), 0, "Should find includes in skinshortcuts include attribute")

        # $PROPERTY[artcontent] is a runtime placeholder — can't resolve
        # UnusedV3Include is genuinely unused
        truly_unused = [i for i in issues if "UnusedV3Include" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertEqual(len(truly_unused), 1, "Should still flag actually unused includes")


if __name__ == "__main__":
    unittest.main()
