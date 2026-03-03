"""
Comprehensive variable validation tests.

Consolidated from:
- test_variable_validation.py: Basic variable definition/usage validation
- test_variable_comments.py: Variable usage in commented code detection
- test_variable_value_validation.py: Validation of values within variable definitions

Test organization:
- Basic Validation: Definition, usage, undefined variables
- Comment Handling: Variables in comments not counted as used
- Value Validation: Color values, integer values, dynamic expressions
"""

import os
import sys
import tempfile
import shutil
import unittest

# Ensure parent directory is in path (base.py does this too, but be explicit)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Now we can import from base and libs
from tests.base import ValidationTestCase, VariableCheck
from libs.infoprovider import InfoProvider


# ============================================================================
# SECTION 1: BASIC VARIABLE VALIDATION
# Tests for variable definition, usage, and undefined variable detection
# ============================================================================

class TestVariableBasicValidation(ValidationTestCase):
    """Test basic variable definition and usage validation."""

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

    def test_undefined_variable_detected(self):
        """Test detection of undefined variable reference."""
        # Create includes file with one variable
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <variable name="DefinedVar">
        <value>SomeValue</value>
    </variable>
</includes>"""
        includes_path = os.path.join(self.test_dir, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Create window that references undefined variable
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label">
            <label>$VAR[UndefinedVar]</label>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = VariableCheck(self.provider.addon)
        issues = checker.check()

        # Should detect undefined variable
        undefined_issues = [i for i in issues if "UndefinedVar" in i.get("message", "") and "not defined" in i.get("message", "").lower()]
        self.assertTrue(len(undefined_issues) > 0, "Should detect undefined variable")

    def test_defined_variable_no_issue(self):
        """Test that defined variables don't trigger issues when used."""
        # Create includes file with variable
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <variable name="MyVar">
        <value>TestValue</value>
    </variable>
</includes>"""
        includes_path = os.path.join(self.test_dir, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Create window that uses the variable
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label">
            <label>$VAR[MyVar]</label>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = VariableCheck(self.provider.addon)
        issues = checker.check()

        # Should not report MyVar as undefined
        myvar_issues = [i for i in issues if "MyVar" in i.get("message", "") and "not defined" in i.get("message", "").lower()]
        self.assertEqual(len(myvar_issues), 0, "Should not report defined variable as undefined")

    def test_unused_variable_detected(self):
        """Test detection of defined but unused variables."""
        # Create includes file with unused variable
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <variable name="UnusedVar">
        <value>TestValue</value>
    </variable>
</includes>"""
        includes_path = os.path.join(self.test_dir, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Create window without using the variable
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label">
            <label>Static text</label>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = VariableCheck(self.provider.addon)
        issues = checker.check()

        # Should detect unused variable
        unused_issues = [i for i in issues if "UnusedVar" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertTrue(len(unused_issues) > 0, "Should detect unused variable")

    def test_escvar_syntax_detected(self):
        """Test detection of $ESCVAR syntax variable references."""
        # Create includes file with variable
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <variable name="EscapedVar">
        <value>EscapedValue</value>
    </variable>
</includes>"""
        includes_path = os.path.join(self.test_dir, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Create window using $ESCVAR syntax
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label">
            <label>$ESCVAR[EscapedVar]</label>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = VariableCheck(self.provider.addon)
        issues = checker.check()

        # Should recognize $ESCVAR syntax and not report as undefined
        escapedvar_issues = [i for i in issues if "EscapedVar" in i.get("message", "") and "not defined" in i.get("message", "").lower()]
        self.assertEqual(len(escapedvar_issues), 0, "Should handle $ESCVAR syntax")

    def test_variable_with_parameters(self):
        """Test that variable references with parameters extract the base name correctly."""
        # Create includes file with parameterized variable
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <variable name="ParamVar">
        <value condition="String.IsEqual($PARAM[id],1)">Value1</value>
        <value condition="String.IsEqual($PARAM[id],2)">Value2</value>
    </variable>
</includes>"""
        includes_path = os.path.join(self.test_dir, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Create window using variable with parameters
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label">
            <label>$VAR[ParamVar,1]</label>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = VariableCheck(self.provider.addon)
        issues = checker.check()

        # Should extract base name "ParamVar" before the comma and match it
        paramvar_issues = [i for i in issues if "ParamVar" in i.get("message", "") and "not defined" in i.get("message", "").lower()]
        self.assertEqual(len(paramvar_issues), 0, "Should extract base variable name from parameterized reference")

    def test_multiple_variables(self):
        """Test validation with multiple defined and used variables."""
        # Create includes file with multiple variables
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <variable name="UsedVar1">
        <value>Value1</value>
    </variable>
    <variable name="UsedVar2">
        <value>Value2</value>
    </variable>
    <variable name="UnusedVar">
        <value>UnusedValue</value>
    </variable>
</includes>"""
        includes_path = os.path.join(self.test_dir, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Create window using some variables
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label">
            <label>$VAR[UsedVar1]</label>
        </control>
        <control type="label">
            <label>$VAR[UsedVar2]</label>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = VariableCheck(self.provider.addon)
        issues = checker.check()

        # Should not report used variables as undefined or unused
        usedvar1_issues = [i for i in issues if "UsedVar1" in i.get("message", "")]
        usedvar2_issues = [i for i in issues if "UsedVar2" in i.get("message", "")]
        self.assertEqual(len(usedvar1_issues), 0, "Should not report UsedVar1")
        self.assertEqual(len(usedvar2_issues), 0, "Should not report UsedVar2")

        # Should report unused variable
        unused_issues = [i for i in issues if "UnusedVar" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertTrue(len(unused_issues) > 0, "Should report UnusedVar as unused")

    def test_variables_used_in_skinshortcuts_template(self):
        """Test that variables referenced in shortcuts/template.xml are not flagged as unused."""
        # Create includes file with variables that will be used only in template.xml
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <variable name="WidgetPosterArt">
        <value>$INFO[Container(8011).ListItem.Art(poster)]</value>
    </variable>
    <variable name="WidgetFanArt">
        <value>$INFO[Container(8011).ListItem.Art(fanart)]</value>
    </variable>
    <variable name="DynamicWidgetVar">
        <value>This has dynamic placeholder</value>
    </variable>
    <variable name="UnusedVariable">
        <value>Not used anywhere</value>
    </variable>
</includes>"""
        includes_path = os.path.join(self.test_dir, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Create empty window (no variables used directly)
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        # Create shortcuts/template.xml that references some variables
        shortcuts_dir = os.path.join(self.test_dir, "shortcuts")
        os.makedirs(shortcuts_dir, exist_ok=True)
        template_xml = """<?xml version="1.0" encoding="UTF-8"?>
<template>
    <other include="widget1">
        <property name="artwork" tag="property" attribute="name|widgetArt" value="Poster">$VAR[WidgetPosterArt]</property>
        <property name="artwork" tag="property" attribute="name|widgetArt" value="FanArt">$VAR[WidgetFanArt]</property>
        <property name="artwork" tag="property" attribute="name|widgetArt" value="Dynamic">$VAR[DynamicWidget$SKINSHORTCUTS[id]Var]</property>
    </other>
</template>"""
        template_path = os.path.join(shortcuts_dir, "template.xml")
        with open(template_path, "w", encoding="utf-8") as f:
            f.write(template_xml)

        self.provider.init_addon(self.test_dir)
        checker = VariableCheck(self.provider.addon)
        issues = checker.check()

        # Should not report WidgetPosterArt as unused (it's in template.xml without $SKINSHORTCUTS)
        poster_unused = [i for i in issues if "WidgetPosterArt" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertEqual(len(poster_unused), 0, "Should not flag variables used in template.xml as unused")

        # Should not report WidgetFanArt as unused (it's in template.xml without $SKINSHORTCUTS)
        fanart_unused = [i for i in issues if "WidgetFanArt" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertEqual(len(fanart_unused), 0, "Should not flag variables used in template.xml as unused")

        # SHOULD report DynamicWidgetVar as unused (referenced with $SKINSHORTCUTS, so skipped)
        dynamic_unused = [i for i in issues if "DynamicWidgetVar" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertEqual(len(dynamic_unused), 1, "Should flag variables with $SKINSHORTCUTS as unused (runtime placeholders ignored)")

        # Should report UnusedVariable as unused (not in template.xml or anywhere else)
        truly_unused = [i for i in issues if "UnusedVariable" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertEqual(len(truly_unused), 1, "Should still flag actually unused variables")

    def test_variables_used_in_skinshortcuts_v3_template(self):
        """Test that variables referenced in v3 shortcuts/templates.xml are not flagged as unused."""
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <variable name="HomeWidgetBackColor">
        <value>FF0B0B0B</value>
    </variable>
    <variable name="HomeWidgetFanArtVar">
        <value>$INFO[Container(8011).ListItem.Art(fanart)]</value>
    </variable>
    <variable name="UnusedV3Var">
        <value>not used</value>
    </variable>
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

        # v3 templates.xml — variables in text content AND attributes
        shortcuts_dir = os.path.join(self.test_dir, "shortcuts")
        os.makedirs(shortcuts_dir, exist_ok=True)
        templates_xml = """<?xml version="1.0" encoding="UTF-8"?>
<templates>
    <template include="widget1" idprefix="8011" build="menu" menu="mainmenu">
        <controls>
            <control type="image">
                <texture colordiffuse="$VAR[HomeWidgetBackColor]" border="40">bg.png</texture>
                <texture fallback="default.png">$VAR[HomeWidgetFanArtVar]</texture>
                <texture>$VAR[HomeWidget$PROPERTY[id]CaseVar]</texture>
            </control>
        </controls>
    </template>
</templates>"""
        template_path = os.path.join(shortcuts_dir, "templates.xml")
        with open(template_path, "w", encoding="utf-8") as f:
            f.write(templates_xml)

        self.provider.init_addon(self.test_dir)
        checker = VariableCheck(self.provider.addon)
        issues = checker.check()

        # Found via attribute value colordiffuse="$VAR[...]"
        backcolor_unused = [i for i in issues if "HomeWidgetBackColor" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertEqual(len(backcolor_unused), 0, "Should find variables in attribute values")

        # Found via text content $VAR[...]
        fanart_unused = [i for i in issues if "HomeWidgetFanArtVar" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertEqual(len(fanart_unused), 0, "Should find variables in text content")

        # $PROPERTY[id] is a runtime placeholder — skipped
        # UnusedV3Var is genuinely unused
        truly_unused = [i for i in issues if "UnusedV3Var" in i.get("message", "") and "unused" in i.get("message", "").lower()]
        self.assertEqual(len(truly_unused), 1, "Should still flag actually unused variables")

    def test_variables_defined_in_skinshortcuts_template_not_undefined(self):
        """Variables defined inside a SkinShortcuts template are generated at runtime.
        References to them in skin XML should not be flagged as undefined."""
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <variable name="SkinDefinedVar">
        <value>local</value>
    </variable>
</includes>"""
        includes_path = os.path.join(self.test_dir, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Window references a variable that only exists in the template
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="image">
            <texture>$VAR[MainMenuBackgroundPathVar]</texture>
            <texture>$VAR[SkinDefinedVar]</texture>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        # Template defines the variable that will be generated at runtime
        shortcuts_dir = os.path.join(self.test_dir, "shortcuts")
        os.makedirs(shortcuts_dir, exist_ok=True)
        templates_xml = """<?xml version="1.0" encoding="UTF-8"?>
<templates>
    <template include="BackgroundVars" menu="mainmenu" templateonly="true">
        <variables>
            <variable name="MainMenuBackgroundPathVar">
                <value condition="String.IsEqual(Container(9000).ListItem.Property(name),$PROPERTY[name])">$PROPERTY[backgroundPath]</value>
            </variable>
        </variables>
    </template>
</templates>"""
        template_path = os.path.join(shortcuts_dir, "templates.xml")
        with open(template_path, "w", encoding="utf-8") as f:
            f.write(templates_xml)

        self.provider.init_addon(self.test_dir)
        checker = VariableCheck(self.provider.addon)
        issues = checker.check()

        undefined = [i for i in issues if "not defined" in i.get("message", "").lower() and "MainMenuBackgroundPathVar" in i.get("message", "")]
        self.assertEqual(len(undefined), 0, "Template-defined variable should not be flagged as undefined")

        # Skin-defined variable should also work fine
        skin_undefined = [i for i in issues if "not defined" in i.get("message", "").lower() and "SkinDefinedVar" in i.get("message", "")]
        self.assertEqual(len(skin_undefined), 0, "Skin-defined variable should not be flagged as undefined")


# ============================================================================
# SECTION 2: VARIABLE COMMENT HANDLING
# Tests for variable usage detection in commented code
# ============================================================================

class TestVariableCommentHandling(ValidationTestCase):
    """Test that variables referenced only in comments are flagged as unused."""

    def setUp(self):
        """Create temporary skin directory for each test."""
        self.test_dir = tempfile.mkdtemp()
        self.provider = InfoProvider()
        self.provider.settings = {}

        # Create basic addon structure
        os.makedirs(os.path.join(self.test_dir, "1080i"))

        # Write addon.xml
        addon_xml = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test Skin" provider-name="test">
    <requires>
        <import addon="xbmc.gui" version="5.16.0"/>
    </requires>
    <extension point="xbmc.gui.skin" defaultthemename="Textures.xbt" debugging="false">
        <res width="1920" height="1080" aspect="16x9" default="true" folder="1080i" />
    </extension>
</addon>"""
        with open(os.path.join(self.test_dir, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(addon_xml)

        # Initialize provider
        self.provider.init_addon(self.test_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_variable_only_used_in_single_line_comment(self):
        """Test that variable only used in single-line comment is flagged as unused."""
        # Define a variable
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <variable name="UnusedVar">
        <value>Test</value>
    </variable>
</includes>"""
        includes_path = os.path.join(self.test_dir, "1080i", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Use it only in a comment
        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <!-- This is commented: <label>$VAR[UnusedVar]</label> -->
        <control type="label" id="100">
            <label>Active</label>
        </control>
    </controls>
</window>"""
        window_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(window_path, "w", encoding="utf-8") as f:
            f.write(window_xml)

        self.provider.init_addon(self.test_dir)
        checker = VariableCheck(self.provider.addon)
        issues = checker.check()

        # SHOULD flag UnusedVar as unused (not used in actual code)
        unused_issues = [i for i in issues if "UnusedVar" in i.get("message", "") and "Unused" in i.get("message", "")]
        self.assertEqual(len(unused_issues), 1, "Variable only used in comment should be flagged as unused")

    def test_variable_only_used_in_multiline_comment(self):
        """Test that variable only used in multi-line comment is flagged as unused."""
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <variable name="CommentedVar">
        <value>Test</value>
    </variable>
</includes>"""
        includes_path = os.path.join(self.test_dir, "1080i", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <!--
        This is a multi-line comment
        <control type="label" id="100">
            <label>$VAR[CommentedVar]</label>
        </control>
        End of comment
        -->
        <control type="label" id="101">
            <label>Active</label>
        </control>
    </controls>
</window>"""
        window_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(window_path, "w", encoding="utf-8") as f:
            f.write(window_xml)

        self.provider.init_addon(self.test_dir)
        checker = VariableCheck(self.provider.addon)
        issues = checker.check()

        # SHOULD flag CommentedVar as unused
        unused_issues = [i for i in issues if "CommentedVar" in i.get("message", "") and "Unused" in i.get("message", "")]
        self.assertEqual(len(unused_issues), 1, "Variable only used in multi-line comment should be flagged as unused")

    def test_variable_used_in_code_and_comment(self):
        """Test that variable used in both code and comment is NOT flagged as unused."""
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <variable name="UsedVar">
        <value>Test</value>
    </variable>
</includes>"""
        includes_path = os.path.join(self.test_dir, "1080i", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <!-- Comment reference: $VAR[UsedVar] -->
        <control type="label" id="100">
            <label>$VAR[UsedVar]</label>
        </control>
    </controls>
</window>"""
        window_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(window_path, "w", encoding="utf-8") as f:
            f.write(window_xml)

        self.provider.init_addon(self.test_dir)
        checker = VariableCheck(self.provider.addon)
        issues = checker.check()

        # Should NOT flag UsedVar as unused (used in actual code)
        unused_issues = [i for i in issues if "UsedVar" in i.get("message", "") and "Unused" in i.get("message", "")]
        self.assertEqual(len(unused_issues), 0, "Variable used in active code should not be flagged even if also in comments")

    def test_variable_used_after_comment_on_same_line(self):
        """Test variable used after comment end on same line is recognized."""
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <variable name="ActiveVar">
        <value>Test</value>
    </variable>
</includes>"""
        includes_path = os.path.join(self.test_dir, "1080i", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label" id="100">
            <!-- comment --> <label>$VAR[ActiveVar]</label>
        </control>
    </controls>
</window>"""
        window_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(window_path, "w", encoding="utf-8") as f:
            f.write(window_xml)

        self.provider.init_addon(self.test_dir)
        checker = VariableCheck(self.provider.addon)
        issues = checker.check()

        # Should NOT flag ActiveVar as unused
        unused_issues = [i for i in issues if "ActiveVar" in i.get("message", "") and "Unused" in i.get("message", "")]
        self.assertEqual(len(unused_issues), 0, "Variable used after comment end should be recognized as used")


# ============================================================================
# SECTION 3: VARIABLE VALUE VALIDATION
# Tests for validating values within variable definitions
# ============================================================================

class TestVariableValueValidation(ValidationTestCase):
    """Test validation of values within variable definitions."""

    def setUp(self):
        """Create temporary skin directory for each test."""
        self.test_dir = tempfile.mkdtemp()
        self.provider = InfoProvider()
        self.provider.settings = {}

        # Create basic addon structure
        os.makedirs(os.path.join(self.test_dir, "1080i"))

        # Write addon.xml
        addon_xml = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test Skin" provider-name="test">
    <requires>
        <import addon="xbmc.gui" version="5.16.0"/>
    </requires>
    <extension point="xbmc.gui.skin" defaultthemename="Textures.xbt" debugging="false">
        <res width="1920" height="1080" aspect="16x9" default="true" folder="1080i" />
    </extension>
</addon>"""
        with open(os.path.join(self.test_dir, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(addon_xml)

        # Initialize provider
        self.provider.init_addon(self.test_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_variable_with_valid_color_values(self):
        """Test variable with all valid color values passes validation."""
        # Create variable with valid colors
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <variable name="HighlightColor">
        <value condition="Skin.HasSetting(RedTheme)">FFFF0000</value>
        <value condition="Skin.HasSetting(GreenTheme)">FF00FF00</value>
        <value>FF0000FF</value>
    </variable>
</includes>"""
        includes_path = os.path.join(self.test_dir, "1080i", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Create window using the variable in a color-type tag
        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="progress" id="100">
            <colordiffuse>$VAR[HighlightColor]</colordiffuse>
        </control>
    </controls>
</window>"""
        window_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(window_path, "w", encoding="utf-8") as f:
            f.write(window_xml)

        self.provider.init_addon(self.test_dir)
        issues = self.provider.check_file(window_path)

        # Should NOT flag - all values are valid colors
        color_issues = [i for i in issues if "invalid color value" in i.get("message", "").lower()]
        self.assertEqual(len(color_issues), 0, "Variable with valid color values should pass")

    def test_variable_with_invalid_color_value(self):
        """Test variable with invalid color value is flagged."""
        # Create variable with one invalid color
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <variable name="HighlightColor">
        <value condition="Skin.HasSetting(RedTheme)">FFFF0000</value>
        <value condition="Skin.HasSetting(GreenTheme)">InvalidColorName</value>
        <value>red</value>
    </variable>
</includes>"""
        includes_path = os.path.join(self.test_dir, "1080i", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Create window using the variable
        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="progress" id="100">
            <colordiffuse>$VAR[HighlightColor]</colordiffuse>
        </control>
    </controls>
</window>"""
        window_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(window_path, "w", encoding="utf-8") as f:
            f.write(window_xml)

        self.provider.init_addon(self.test_dir)
        issues = self.provider.check_file(window_path)

        # SHOULD flag InvalidColorName
        color_issues = [i for i in issues if "invalid color value" in i.get("message", "").lower() and "InvalidColorName" in i.get("message", "")]
        self.assertEqual(len(color_issues), 1, "Variable with invalid color value should be flagged")
        self.assertIn("HighlightColor", color_issues[0]["message"])

    def test_variable_with_valid_integer_values(self):
        """Test variable with valid integer values in width tag."""
        # Create variable with valid integers
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <variable name="ControlWidth">
        <value condition="Skin.HasSetting(WideView)">500</value>
        <value condition="Skin.HasSetting(MediumView)">300</value>
        <value>200</value>
    </variable>
</includes>"""
        includes_path = os.path.join(self.test_dir, "1080i", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Create window using the variable in width tag
        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <width>$VAR[ControlWidth]</width>
            <label>Test</label>
        </control>
    </controls>
</window>"""
        window_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(window_path, "w", encoding="utf-8") as f:
            f.write(window_xml)

        self.provider.init_addon(self.test_dir)
        issues = self.provider.check_file(window_path)

        # Should NOT flag - all values are valid integers
        int_issues = [i for i in issues if "invalid integer value" in i.get("message", "").lower()]
        self.assertEqual(len(int_issues), 0, "Variable with valid integer values should pass")

    def test_variable_with_invalid_integer_value(self):
        """Test variable with invalid integer value is flagged."""
        # Create variable with one invalid integer
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <variable name="ControlWidth">
        <value condition="Skin.HasSetting(WideView)">500</value>
        <value condition="Skin.HasSetting(MediumView)">NotANumber</value>
        <value>200</value>
    </variable>
</includes>"""
        includes_path = os.path.join(self.test_dir, "1080i", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Create window using the variable
        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <width>$VAR[ControlWidth]</width>
            <label>Test</label>
        </control>
    </controls>
</window>"""
        window_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(window_path, "w", encoding="utf-8") as f:
            f.write(window_xml)

        self.provider.init_addon(self.test_dir)
        issues = self.provider.check_file(window_path)

        # SHOULD flag NotANumber
        int_issues = [i for i in issues if "invalid integer value" in i.get("message", "").lower() and "NotANumber" in i.get("message", "")]
        self.assertEqual(len(int_issues), 1, "Variable with invalid integer value should be flagged")
        self.assertIn("ControlWidth", int_issues[0]["message"])

    def test_variable_with_dynamic_expression_values(self):
        """Test variable with dynamic expressions in values are not flagged."""
        # Create variable with values containing dynamic expressions
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <variable name="DynamicColor">
        <value condition="Skin.HasSetting(UseTheme)">$INFO[Skin.String(ThemeColor)]</value>
        <value>FFFF0000</value>
    </variable>
</includes>"""
        includes_path = os.path.join(self.test_dir, "1080i", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Create window using the variable
        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="progress" id="100">
            <colordiffuse>$VAR[DynamicColor]</colordiffuse>
        </control>
    </controls>
</window>"""
        window_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(window_path, "w", encoding="utf-8") as f:
            f.write(window_xml)

        self.provider.init_addon(self.test_dir)
        issues = self.provider.check_file(window_path)

        # Should NOT flag - dynamic expressions should be skipped
        color_issues = [i for i in issues if "invalid color value" in i.get("message", "").lower()]
        self.assertEqual(len(color_issues), 0, "Variable values with dynamic expressions should be skipped")

    def test_variable_with_number_expression_in_value(self):
        """Test variable value containing $NUMBER[] expression validates correctly."""
        # Create variable with $NUMBER[] in value
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <variable name="DynamicWidth">
        <value condition="Skin.HasSetting(CustomWidth)">$NUMBER[500]</value>
        <value>300</value>
    </variable>
</includes>"""
        includes_path = os.path.join(self.test_dir, "1080i", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Create window using the variable
        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <width>$VAR[DynamicWidth]</width>
            <label>Test</label>
        </control>
    </controls>
</window>"""
        window_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(window_path, "w", encoding="utf-8") as f:
            f.write(window_xml)

        self.provider.init_addon(self.test_dir)
        issues = self.provider.check_file(window_path)

        # Should NOT flag - $NUMBER[500] should extract to valid integer
        int_issues = [i for i in issues if "invalid integer value" in i.get("message", "").lower()]
        self.assertEqual(len(int_issues), 0, "Variable value with $NUMBER[] should validate correctly")

    def test_variable_multiple_invalid_values(self):
        """Test variable with multiple invalid values flags all of them."""
        # Create variable with multiple invalid colors
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <variable name="BadColors">
        <value condition="Skin.HasSetting(Theme1)">InvalidColor1</value>
        <value condition="Skin.HasSetting(Theme2)">InvalidColor2</value>
        <value>FFFF0000</value>
    </variable>
</includes>"""
        includes_path = os.path.join(self.test_dir, "1080i", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Create window using the variable
        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="progress" id="100">
            <colordiffuse>$VAR[BadColors]</colordiffuse>
        </control>
    </controls>
</window>"""
        window_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(window_path, "w", encoding="utf-8") as f:
            f.write(window_xml)

        self.provider.init_addon(self.test_dir)
        issues = self.provider.check_file(window_path)

        # SHOULD flag both InvalidColor1 and InvalidColor2
        color_issues = [i for i in issues if "invalid color value" in i.get("message", "").lower() and "BadColors" in i.get("message", "")]
        self.assertEqual(len(color_issues), 2, "Should flag all invalid values in variable")

    def test_escvar_expression_validation(self):
        """Test that $ESCVAR[] expressions are also validated."""
        # Create variable with invalid color
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <variable name="MyColor">
        <value>InvalidColorName</value>
    </variable>
</includes>"""
        includes_path = os.path.join(self.test_dir, "1080i", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Create window using $ESCVAR[]
        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="progress" id="100">
            <colordiffuse>$ESCVAR[MyColor]</colordiffuse>
        </control>
    </controls>
</window>"""
        window_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(window_path, "w", encoding="utf-8") as f:
            f.write(window_xml)

        self.provider.init_addon(self.test_dir)
        issues = self.provider.check_file(window_path)

        # SHOULD flag InvalidColorName
        color_issues = [i for i in issues if "invalid color value" in i.get("message", "").lower() and "InvalidColorName" in i.get("message", "")]
        self.assertEqual(len(color_issues), 1, "$ESCVAR[] should also be validated")

    def test_variable_in_tag_text_content(self):
        """Test variable validation works for tag text content (not just attributes)."""
        # Create variable with invalid value for an enum type
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <variable name="AspectRatio">
        <value condition="Skin.HasSetting(Wide)">keep</value>
        <value>invalidaspect</value>
    </variable>
</includes>"""
        includes_path = os.path.join(self.test_dir, "1080i", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Create window using variable in tag text
        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="image" id="100">
            <aspectratio>$VAR[AspectRatio]</aspectratio>
        </control>
    </controls>
</window>"""
        window_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(window_path, "w", encoding="utf-8") as f:
            f.write(window_xml)

        self.provider.init_addon(self.test_dir)
        issues = self.provider.check_file(window_path)

        # SHOULD flag invalidaspect
        aspect_issues = [i for i in issues if "invalid value" in i.get("message", "").lower() and "AspectRatio" in i.get("message", "")]
        self.assertEqual(len(aspect_issues), 1, "Variable in tag text content should be validated")


if __name__ == "__main__":
    unittest.main()
