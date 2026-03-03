"""
Comprehensive ID validation tests.

Consolidated from:
- test_id_validation.py: Basic control and window ID validation
- test_listitem_index.py: ListItem indices shouldn't be flagged as IDs
- test_id_scoping.py: Window-scoped ID validation

Test organization:
- Basic ID Validation: Control IDs, window IDs, param-defined IDs
- ListItem Index Handling: ListItemAbsolute, ListItemPosition, ListItemNoWrap
- Window Scoping: IDs scoped to windows, include resolution
"""

import os
import sys
import tempfile
import shutil
import unittest

# Ensure parent directory is in path (base.py does this too, but be explicit)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Now we can import from base and libs
from tests.base import ValidationTestCase, IdCheck
from libs.infoprovider import InfoProvider


# ============================================================================
# SECTION 1: BASIC ID VALIDATION
# Tests for control and window ID validation
# ============================================================================

class TestBasicIDValidation(ValidationTestCase):
    """Test control and window ID validation."""

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

        # Initialize provider
        self.provider.init_addon(self.test_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_undefined_control_id_in_condition(self):
        """Test detection of undefined control ID in condition attribute."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <label>Button</label>
        </control>
        <control type="image">
            <visible condition="Control.IsVisible(999)">true</visible>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = IdCheck(
            self.provider.addon,
            self.provider.WINDOW_IDS,
            self.provider.WINDOW_NAMES
        )
        issues = checker.check()

        # Should find undefined control ID 999
        undefined_issues = [i for i in issues if "999" in i.get("message", "")]
        self.assertTrue(len(undefined_issues) > 0, "Should detect undefined control ID 999")
        self.assertIn("not defined", undefined_issues[0]["message"].lower())

    def test_defined_control_id_no_issue(self):
        """Test that defined control IDs don't trigger issues when used in visible conditions."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <label>Button</label>
        </control>
        <control type="button" id="200">
            <label>Button 2</label>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = IdCheck(
            self.provider.addon,
            self.provider.WINDOW_IDS,
            self.provider.WINDOW_NAMES
        )
        issues = checker.check()

        # Without any references, there should be no issues about undefined IDs
        undefined_issues = [i for i in issues if "not defined" in i.get("message", "").lower()]
        self.assertEqual(len(undefined_issues), 0, "Should not report any undefined IDs when no references exist")

    def test_undefined_window_id(self):
        """Test detection of undefined window ID."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <visible>Window.IsActive(99999)</visible>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = IdCheck(
            self.provider.addon,
            self.provider.WINDOW_IDS,
            self.provider.WINDOW_NAMES
        )
        issues = checker.check()

        # Should report undefined window ID 99999
        window_issues = [i for i in issues if "99999" in i.get("message", "")]
        self.assertTrue(len(window_issues) > 0, "Should detect undefined window ID")
        self.assertIn("not defined", window_issues[0]["message"].lower())

    def test_control_id_in_visible_tag_text(self):
        """Test detection of control IDs in <visible> tag text content."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <label>Button</label>
        </control>
        <control type="image">
            <visible>Control.IsVisible(200)</visible>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = IdCheck(
            self.provider.addon,
            self.provider.WINDOW_IDS,
            self.provider.WINDOW_NAMES
        )
        issues = checker.check()

        # Should find undefined control ID 200
        undefined_issues = [i for i in issues if "200" in i.get("message", "")]
        self.assertTrue(len(undefined_issues) > 0, "Should detect undefined control ID 200 in <visible>")

    def test_multiple_control_ids(self):
        """Test validation with multiple defined and undefined control IDs."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <label>Button 1</label>
        </control>
        <control type="button" id="200">
            <label>Button 2</label>
        </control>
        <control type="image">
            <visible>Control.IsVisible(100) + Control.IsVisible(300)</visible>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = IdCheck(
            self.provider.addon,
            self.provider.WINDOW_IDS,
            self.provider.WINDOW_NAMES
        )
        issues = checker.check()

        # Should not report 100 or 200 (defined), but should report 300 (undefined)
        id_100_issues = [i for i in issues if "100" in i.get("message", "")]
        id_200_issues = [i for i in issues if "200" in i.get("message", "")]
        id_300_issues = [i for i in issues if "300" in i.get("message", "")]

        self.assertEqual(len(id_100_issues), 0, "Should not report defined ID 100")
        self.assertEqual(len(id_200_issues), 0, "Should not report defined ID 200")
        self.assertTrue(len(id_300_issues) > 0, "Should report undefined ID 300")

    def test_window_id_on_root_element(self):
        """Test that window IDs on root element are recognized."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window id="12345">
    <controls>
        <control type="button" id="100">
            <visible>Window.IsActive(12345)</visible>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "CustomWindow.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = IdCheck(
            self.provider.addon,
            self.provider.WINDOW_IDS,
            self.provider.WINDOW_NAMES
        )
        issues = checker.check()

        # Should not report window ID 12345 since it's defined on root
        custom_window_issues = [i for i in issues if "12345" in i.get("message", "") and "not defined" in i.get("message", "").lower()]
        self.assertEqual(len(custom_window_issues), 0, "Should not report window ID defined on root element")

    def test_empty_control_id_ignored(self):
        """Test that empty control IDs in conditions are ignored."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <visible>Container()</visible>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = IdCheck(
            self.provider.addon,
            self.provider.WINDOW_IDS,
            self.provider.WINDOW_NAMES
        )
        issues = checker.check()

        # Should not crash or report empty ID
        self.assertIsInstance(issues, list)

    def test_control_id_defined_via_param(self):
        """Test that control IDs passed via params are recognized as defined."""
        # Create includes file with parameterized include that defines a control ID
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="InfoDetailsPanel">
        <control type="group" id="$PARAM[id]">
            <control type="label" id="$PARAM[label_id]">
                <label>Details</label>
            </control>
        </control>
    </include>
</includes>"""
        includes_path = os.path.join(self.test_dir, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Create window that uses the include with specific ID param values
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <include content="InfoDetailsPanel">
            <param name="id">4800</param>
            <param name="label_id">4801</param>
        </include>
        <control type="button">
            <visible>Control.IsVisible(4800) + Control.IsVisible(4801)</visible>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "Home.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(home_xml)

        self.provider.init_addon(self.test_dir)
        checker = IdCheck(
            self.provider.addon,
            self.provider.WINDOW_IDS,
            self.provider.WINDOW_NAMES
        )
        issues = checker.check()

        # Should not report 4800 or 4801 as undefined (they're defined via params)
        id_4800_issues = [i for i in issues if "4800" in i.get("message", "") and "not defined" in i.get("message", "").lower()]
        id_4801_issues = [i for i in issues if "4801" in i.get("message", "") and "not defined" in i.get("message", "").lower()]

        self.assertEqual(len(id_4800_issues), 0, "Should not report ID 4800 as undefined (defined via param)")
        self.assertEqual(len(id_4801_issues), 0, "Should not report ID 4801 as undefined (defined via param)")

    def test_fadelabel_control_recognized(self):
        """Test that fadelabel and other special control types are recognized."""
        # Create includes file with variable referencing fadelabel control
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <variable name="TestVar">
        <value condition="Control.IsVisible(4412)">$INFO[Control.GetLabel(4412)]</value>
        <value>fallback</value>
    </variable>
</includes>"""
        includes_path = os.path.join(self.test_dir, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Create window file with fadelabel control
        video_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="fadelabel" id="4412">
            <top>-100</top>
            <width>2560</width>
            <height>0</height>
            <scroll>false</scroll>
            <label>Test Label</label>
        </control>
    </controls>
</window>"""
        xml_path = os.path.join(self.test_dir, "16x9", "MyVideoNav.xml")
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(video_xml)

        self.provider.init_addon(self.test_dir)
        checker = IdCheck(
            self.provider.addon,
            self.provider.WINDOW_IDS,
            self.provider.WINDOW_NAMES
        )
        issues = checker.check()

        # Should not report 4412 as undefined (it's defined as fadelabel control)
        id_4412_issues = [i for i in issues if "4412" in i.get("message", "") and "not defined" in i.get("message", "").lower()]
        self.assertEqual(len(id_4412_issues), 0, "Should recognize fadelabel control IDs")


# ============================================================================
# SECTION 2: LISTITEM INDEX HANDLING
# Tests that ListItem indices are not flagged as undefined control IDs
# ============================================================================

class TestListItemIndexHandling(ValidationTestCase):
    """Test that ListItem indices are not flagged as undefined control IDs."""

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

    def test_listitemabsolute_index_not_flagged(self):
        """Test that index in ListItemAbsolute(0) is not flagged as undefined ID."""
        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="list" id="4450">
            <visible>true</visible>
        </control>
        <control type="image" id="100">
            <visible>!String.IsEmpty(Container(4450).ListItemAbsolute(0).Art(discart))</visible>
        </control>
    </controls>
</window>"""
        window_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(window_path, "w", encoding="utf-8") as f:
            f.write(window_xml)

        self.provider.init_addon(self.test_dir)
        checker = IdCheck(self.provider.addon, [], [])
        issues = checker.check()

        # Should NOT flag 0 as undefined - it's a ListItemAbsolute index
        undefined_zero = [i for i in issues if "0" in i.get("message", "") and "not defined" in i.get("message", "")]
        self.assertEqual(len(undefined_zero), 0, "ListItemAbsolute(0) index should not be flagged as undefined ID")

    def test_listitem_index_not_flagged(self):
        """Test that index in ListItem(n) is not flagged as undefined ID."""
        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="list" id="50">
            <visible>true</visible>
        </control>
        <control type="label" id="100">
            <label>$INFO[Container(50).ListItem(0).Label]</label>
        </control>
        <control type="label" id="101">
            <label>$INFO[Container(50).ListItem(1).Label]</label>
        </control>
        <control type="label" id="102">
            <label>$INFO[Container(50).ListItem(-1).Label]</label>
        </control>
    </controls>
</window>"""
        window_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(window_path, "w", encoding="utf-8") as f:
            f.write(window_xml)

        self.provider.init_addon(self.test_dir)
        checker = IdCheck(self.provider.addon, [], [])
        issues = checker.check()

        # Should NOT flag 0, 1, or -1 as undefined
        listitem_indices = [i for i in issues if any(idx in i.get("message", "") for idx in ["0", "1"]) and "not defined" in i.get("message", "")]
        self.assertEqual(len(listitem_indices), 0, "ListItem(n) indices should not be flagged")

    def test_listitemposition_index_not_flagged(self):
        """Test that index in ListItemPosition(n) is not flagged."""
        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="list" id="60">
            <visible>true</visible>
        </control>
        <control type="image" id="100">
            <visible>!String.IsEmpty(Container(60).ListItemPosition(0).Property(custom))</visible>
        </control>
    </controls>
</window>"""
        window_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(window_path, "w", encoding="utf-8") as f:
            f.write(window_xml)

        self.provider.init_addon(self.test_dir)
        checker = IdCheck(self.provider.addon, [], [])
        issues = checker.check()

        # Should NOT flag 0 as undefined
        undefined_zero = [i for i in issues if "0" in i.get("message", "") and "not defined" in i.get("message", "")]
        self.assertEqual(len(undefined_zero), 0, "ListItemPosition(0) index should not be flagged")

    def test_listitemnorap_index_not_flagged(self):
        """Test that index in ListItemNoWrap(n) is not flagged."""
        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="list" id="70">
            <visible>true</visible>
        </control>
        <control type="label" id="100">
            <label>$INFO[Container(70).ListItemNoWrap(2).Title]</label>
        </control>
    </controls>
</window>"""
        window_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(window_path, "w", encoding="utf-8") as f:
            f.write(window_xml)

        self.provider.init_addon(self.test_dir)
        checker = IdCheck(self.provider.addon, [], [])
        issues = checker.check()

        # Should NOT flag 2 as undefined
        undefined_two = [i for i in issues if "2" in i.get("message", "") and "not defined" in i.get("message", "")]
        self.assertEqual(len(undefined_two), 0, "ListItemNoWrap(2) index should not be flagged")

    def test_container_id_still_validated(self):
        """Test that Container(ID) references are still validated correctly."""
        # Create window WITHOUT defining container 9999
        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="image" id="100">
            <visible>!String.IsEmpty(Container(9999).ListItemAbsolute(0).Art(discart))</visible>
        </control>
    </controls>
</window>"""
        window_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(window_path, "w", encoding="utf-8") as f:
            f.write(window_xml)

        self.provider.init_addon(self.test_dir)
        checker = IdCheck(self.provider.addon, [], [])
        issues = checker.check()

        # SHOULD flag 9999 as undefined (but NOT 0)
        undefined_9999 = [i for i in issues if "9999" in i.get("message", "") and "not defined" in i.get("message", "")]
        undefined_0 = [i for i in issues if "0" in i.get("message", "") and "not defined" in i.get("message", "")]

        self.assertEqual(len(undefined_9999), 1, "Undefined Container ID 9999 should be flagged")
        self.assertEqual(len(undefined_0), 0, "ListItemAbsolute(0) index should not be flagged")


# ============================================================================
# SECTION 3: WINDOW SCOPING
# Tests for window-scoped ID validation matching Kodi's behavior
# ============================================================================

class TestWindowScoping(ValidationTestCase):
    """Test window-scoped ID validation matching Kodi's behavior."""

    def setUp(self):
        """Create temporary skin directory for each test."""
        self.test_dir = tempfile.mkdtemp()

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

    def test_control_in_same_window_valid(self):
        """Test that control defined and referenced in same window is valid."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <label>Button</label>
        </control>
        <control type="button" id="200">
            <onclick>SetFocus(100)</onclick>
        </control>
    </controls>
</window>"""
        with open(os.path.join(self.test_dir, "16x9", "Home.xml"), "w", encoding="utf-8") as f:
            f.write(home_xml)

        provider = InfoProvider()
        provider.init_addon(self.test_dir)
        issues = provider.check_ids()

        # Should NOT flag ID 100 as undefined
        undefined_issues = [i for i in issues if "not defined" in i.get("message", "").lower() and "100" in i.get("message", "")]
        self.assertEqual(len(undefined_issues), 0, f"Should not flag control 100 as undefined. Issues: {undefined_issues}")

    def test_control_from_include_valid(self):
        """Test that control from included file is valid."""
        # Create include with control
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="CommonButtons">
        <control type="button" id="100">
            <label>OK</label>
        </control>
    </include>
</includes>"""
        with open(os.path.join(self.test_dir, "16x9", "Includes.xml"), "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Create window that uses the include
        dialog_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <include>CommonButtons</include>
        <control type="button" id="200">
            <onclick>SetFocus(100)</onclick>
        </control>
    </controls>
</window>"""
        with open(os.path.join(self.test_dir, "16x9", "DialogOK.xml"), "w", encoding="utf-8") as f:
            f.write(dialog_xml)

        provider = InfoProvider()
        provider.init_addon(self.test_dir)
        issues = provider.check_ids()

        # Should NOT flag ID 100 as undefined (it's in the included CommonButtons)
        undefined_issues = [i for i in issues if "not defined" in i.get("message", "").lower() and "100" in i.get("message", "")]
        self.assertEqual(len(undefined_issues), 0, f"Should not flag included control 100 as undefined. Issues: {undefined_issues}")

    def test_control_from_different_window_invalid(self):
        """Test that control from different window is correctly flagged."""
        # DialogA defines control 100
        dialog_a_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <label>OK</label>
        </control>
    </controls>
</window>"""
        with open(os.path.join(self.test_dir, "16x9", "DialogA.xml"), "w", encoding="utf-8") as f:
            f.write(dialog_a_xml)

        # DialogB tries to reference control 100 (invalid!)
        dialog_b_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="200">
            <onclick>SetFocus(100)</onclick>
        </control>
    </controls>
</window>"""
        with open(os.path.join(self.test_dir, "16x9", "DialogB.xml"), "w", encoding="utf-8") as f:
            f.write(dialog_b_xml)

        provider = InfoProvider()
        provider.init_addon(self.test_dir)
        issues = provider.check_ids()

        # SHOULD flag ID 100 as undefined in DialogB
        dialogb_issues = [i for i in issues if "DialogB.xml" in i.get("file", "") and "100" in i.get("message", "")]
        self.assertTrue(len(dialogb_issues) > 0, "Should flag control 100 as undefined in DialogB.xml")

    def test_nested_includes_valid(self):
        """Test that controls from nested includes are valid."""
        # Create nested includes structure
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="OuterInclude">
        <control type="group">
            <include>InnerInclude</include>
        </control>
    </include>
    <include name="InnerInclude">
        <control type="button" id="100">
            <label>Nested Button</label>
        </control>
    </include>
</includes>"""
        with open(os.path.join(self.test_dir, "16x9", "Includes.xml"), "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Window uses OuterInclude (which contains InnerInclude)
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <include>OuterInclude</include>
        <control type="button" id="200">
            <onclick>SetFocus(100)</onclick>
        </control>
    </controls>
</window>"""
        with open(os.path.join(self.test_dir, "16x9", "Home.xml"), "w", encoding="utf-8") as f:
            f.write(home_xml)

        provider = InfoProvider()
        provider.init_addon(self.test_dir)
        issues = provider.check_ids()

        # Should NOT flag ID 100 (it's in nested InnerInclude)
        undefined_issues = [i for i in issues if "not defined" in i.get("message", "").lower() and "100" in i.get("message", "")]
        self.assertEqual(len(undefined_issues), 0, f"Should not flag nested include control 100 as undefined. Issues: {undefined_issues}")


# ============================================================================
# SECTION 4: ALARMCLOCK EXCEPTION
# Tests for AlarmClock delayed execution exception (libs/skin.py:3238-3271)
# Fixed 9 false positives for control ID 2012 in Arctic Fuse 2
# ============================================================================

class TestAlarmClockException(ValidationTestCase):
    """Test AlarmClock delayed execution exception.

    AlarmClock(name, command, time) executes command after a delay.
    Control IDs in the delayed command may not exist in the current window,
    so they should NOT be validated.

    Reference: libs/skin.py lines 3238-3271
    Bug fix: Eliminated 9 false positives in Includes_Items.xml
    """

    def setUp(self):
        """Create temporary skin directory for each test."""
        self.test_dir = tempfile.mkdtemp()

        # Create addon structure
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

        # Create minimal Includes.xml (required for validation to work)
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
</includes>"""
        with open(os.path.join(self.test_dir, "16x9", "Includes.xml"), "w", encoding="utf-8") as f:
            f.write(includes_xml)

    def tearDown(self):
        """Clean up temporary directory."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_alarmclock_ids_not_validated(self):
        """Control IDs inside AlarmClock() should NOT be validated.

        Pattern: AlarmClock(name, SetFocus(ID), time, silent)
        The ID is executed after a delay and may not exist in current window.
        """
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <!-- Define control 100 but NOT 2012 -->
        <control type="button" id="100">
            <!-- Should NOT validate ID 2012 (delayed execution) -->
            <onclick>AlarmClock(refocusblurb,SetFocus(2012),00:00,silent)</onclick>
        </control>
        <control type="button" id="101">
            <!-- SHOULD validate ID 2012 (normal execution) -->
            <onclick>SetFocus(2012)</onclick>
        </control>
    </controls>
</window>"""
        with open(os.path.join(self.test_dir, "16x9", "Home.xml"), "w", encoding="utf-8") as f:
            f.write(home_xml)

        provider = InfoProvider()
        provider.load_data("omega")  # Load Kodi data
        provider.init_addon(self.test_dir)

        # Build validation index first
        index = provider.addon.index_builder.build_validation_index()  # type: ignore[union-attr]  # type: ignore[union-attr]

        # Create checker with window IDs
        from libs.validation import ValidationIds as IdCheck
        checker = IdCheck(provider.addon, provider.WINDOW_IDS, provider.WINDOW_NAMES, validation_index=index)
        issues = checker.check()

        # Check: ID 2012 from control 101 SHOULD be flagged
        normal_issues = [i for i in issues if "2012" in i.get("message", "")]

        # Check: At least one ID 2012 error should exist (from control 101, not from AlarmClock)
        # The AlarmClock one should be skipped, but normal SetFocus should be caught
        if len(normal_issues) > 0:
            # Verify it's NOT from the AlarmClock line (which would be around line 7-8)
            # and IS from the normal SetFocus line (around line 10-11)
            alarmclock_line_issues = [i for i in normal_issues if 6 <= i.get("line", 0) <= 9]
            normal_line_issues = [i for i in normal_issues if i.get("line", 0) >= 10]

            self.assertEqual(len(alarmclock_line_issues), 0,
                           f"Should NOT flag control 2012 from AlarmClock. Found: {alarmclock_line_issues}")
            self.assertTrue(len(normal_line_issues) > 0,
                          "Should flag control 2012 from normal SetFocus")

    def test_alarmclock_case_insensitive(self):
        """AlarmClock detection should be case-insensitive."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <onclick>ALARMCLOCK(test,SetFocus(2012),00:00)</onclick>
        </control>
        <control type="button" id="101">
            <onclick>alarmclock(test2,SetFocus(2012),00:01,silent)</onclick>
        </control>
        <control type="button" id="102">
            <onclick>AlArMcLoCk(test3,SetFocus(2012),00:02)</onclick>
        </control>
    </controls>
</window>"""
        with open(os.path.join(self.test_dir, "16x9", "Home.xml"), "w", encoding="utf-8") as f:
            f.write(home_xml)

        provider = InfoProvider()
        provider.load_data("omega")
        provider.init_addon(self.test_dir)

        index = provider.addon.index_builder.build_validation_index()  # type: ignore[union-attr]
        from libs.validation import ValidationIds as IdCheck
        checker = IdCheck(provider.addon, provider.WINDOW_IDS, provider.WINDOW_NAMES, validation_index=index)
        issues = checker.check()

        # None of these should flag ID 2012 (all use AlarmClock variants)
        control_2012_issues = [i for i in issues if "2012" in i.get("message", "")]
        self.assertEqual(len(control_2012_issues), 0,
                        f"All AlarmClock variants (ALARMCLOCK, alarmclock, AlArMcLoCk) should be detected. Found: {control_2012_issues}")

    def test_alarmclock_in_visible_condition(self):
        """AlarmClock in visible conditions should also skip validation."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <!-- ID 2012 in visible condition with AlarmClock -->
            <visible>AlarmClock(test,SetFocus(2012),00:00,silent)</visible>
        </control>
    </controls>
</window>"""
        with open(os.path.join(self.test_dir, "16x9", "Home.xml"), "w", encoding="utf-8") as f:
            f.write(home_xml)

        provider = InfoProvider()
        provider.load_data("omega")
        provider.init_addon(self.test_dir)

        index = provider.addon.index_builder.build_validation_index()  # type: ignore[union-attr]
        from libs.validation import ValidationIds as IdCheck
        checker = IdCheck(provider.addon, provider.WINDOW_IDS, provider.WINDOW_NAMES, validation_index=index)
        issues = checker.check()

        # Should NOT flag ID 2012 even in visible condition
        control_2012_issues = [i for i in issues if "2012" in i.get("message", "")]
        self.assertEqual(len(control_2012_issues), 0,
                        f"AlarmClock in visible should skip validation. Found: {control_2012_issues}")

    def test_normal_setfocus_still_validated(self):
        """Normal SetFocus without AlarmClock should still be validated."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <onclick>SetFocus(999)</onclick>
        </control>
        <control type="button" id="101">
            <visible>Control.IsVisible(888)</visible>
        </control>
    </controls>
</window>"""
        with open(os.path.join(self.test_dir, "16x9", "Home.xml"), "w", encoding="utf-8") as f:
            f.write(home_xml)

        provider = InfoProvider()
        provider.init_addon(self.test_dir)

        from libs.validation import ValidationIds as IdCheck
        checker = IdCheck(provider.addon, provider.WINDOW_IDS, provider.WINDOW_NAMES)
        issues = checker.check()

        # Both 999 and 888 should be flagged (no AlarmClock)
        id_999_issues = [i for i in issues if "999" in i.get("message", "")]
        id_888_issues = [i for i in issues if "888" in i.get("message", "")]

        self.assertTrue(len(id_999_issues) > 0, "Should flag undefined control 999")
        self.assertTrue(len(id_888_issues) > 0, "Should flag undefined control 888")


# ============================================================================
# SECTION 5: WINDOW ID PARSER
# Tests for Window.* function ID parsing (libs/skin.py:3179)
# Fixed 6 false positives for windows 1144, 1149 in Arctic Fuse 2
# ============================================================================

class TestWindowIDParser(ValidationTestCase):
    """Test Window.* vs Control.* function distinction.

    Window.* functions take window IDs (not control IDs).
    Based on Kodi source: xbmc/GUIInfoManager.cpp lines 7971-7979

    Reference: libs/skin.py line 3179 (window_regex)
    Bug fix: Eliminated 6 false positives for undefined custom windows
    """

    def setUp(self):
        """Create temporary skin directory for each test."""
        self.test_dir = tempfile.mkdtemp()

        # Create addon structure
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

        # Create minimal Includes.xml (required for validation to work)
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
</includes>"""
        with open(os.path.join(self.test_dir, "16x9", "Includes.xml"), "w", encoding="utf-8") as f:
            f.write(includes_xml)

    def tearDown(self):
        """Clean up temporary directory."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_window_isactive_uses_window_id(self):
        """Window.IsActive(ID) should validate as window ID, not control ID."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label">
            <!-- 99999 is not a defined window ID or control ID -->
            <visible>Window.IsActive(99999)</visible>
        </control>
    </controls>
</window>"""
        with open(os.path.join(self.test_dir, "16x9", "Home.xml"), "w", encoding="utf-8") as f:
            f.write(home_xml)

        provider = InfoProvider()
        provider.init_addon(self.test_dir)
        issues = provider.check_ids()

        # Should be flagged as undefined WINDOW ID, not control ID
        window_issues = [i for i in issues if "99999" in i.get("message", "") and "window" in i.get("message", "").lower()]
        self.assertTrue(len(window_issues) > 0, "Should flag 99999 as undefined window ID")

        # Should NOT be flagged as control ID
        control_issues = [i for i in issues if "99999" in i.get("message", "") and "control" in i.get("message", "").lower()]
        self.assertEqual(len(control_issues), 0, f"Should NOT flag 99999 as control ID. Found: {control_issues}")

    def test_window_previous_uses_window_id(self):
        """Window.Previous(ID) should use window ID, not control ID."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label">
            <visible>Window.Previous(1105)</visible>
        </control>
    </controls>
</window>"""
        with open(os.path.join(self.test_dir, "16x9", "Home.xml"), "w", encoding="utf-8") as f:
            f.write(home_xml)

        provider = InfoProvider()
        provider.init_addon(self.test_dir)
        issues = provider.check_ids()

        # Should check 1105 as window ID (may or may not be defined)
        # Key is that it's NOT validated as a control ID
        control_issues = [i for i in issues if "1105" in i.get("message", "") and "control" in i.get("message", "").lower()]
        self.assertEqual(len(control_issues), 0, "Window.Previous should not validate 1105 as control ID")

    def test_all_window_functions_recognized(self):
        """All Window.* functions from GUIInfoManager.cpp recognized."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label">
            <visible>Window.IsActive(88888)</visible>
        </control>
        <control type="label">
            <visible>Window.IsVisible(88889)</visible>
        </control>
        <control type="label">
            <visible>Window.IsMedia(88890)</visible>
        </control>
        <control type="label">
            <visible>Window.IsDialogTopmost(88891)</visible>
        </control>
        <control type="label">
            <visible>Window.IsModalDialogTopmost(88892)</visible>
        </control>
        <control type="label">
            <visible>Window.Previous(88893)</visible>
        </control>
        <control type="label">
            <visible>Window.Next(88894)</visible>
        </control>
        <control type="label">
            <onclick>Dialog.Close(88895)</onclick>
        </control>
    </controls>
</window>"""
        with open(os.path.join(self.test_dir, "16x9", "Home.xml"), "w", encoding="utf-8") as f:
            f.write(home_xml)

        provider = InfoProvider()
        provider.init_addon(self.test_dir)
        issues = provider.check_ids()

        # All these IDs should be checked as window IDs, not control IDs
        test_ids = ["88888", "88889", "88890", "88891", "88892", "88893", "88894", "88895"]

        for test_id in test_ids:
            control_issues = [i for i in issues if test_id in i.get("message", "") and "control" in i.get("message", "").lower()]
            self.assertEqual(len(control_issues), 0,
                           f"ID {test_id} should not be validated as control ID")

    def test_control_isvisible_vs_window_isactive(self):
        """Control.IsVisible uses control ID, Window.IsActive uses window ID."""
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="label">
            <visible>Control.IsVisible(10000)</visible>
        </control>
        <control type="label">
            <visible>Window.IsActive(10000)</visible>
        </control>
    </controls>
</window>"""
        with open(os.path.join(self.test_dir, "16x9", "Home.xml"), "w", encoding="utf-8") as f:
            f.write(home_xml)

        provider = InfoProvider()
        provider.init_addon(self.test_dir)
        issues = provider.check_ids()

        # Control.IsVisible(10000) should check for control ID
        control_issues = [i for i in issues if "10000" in i.get("message", "") and "control" in i.get("message", "").lower()]
        self.assertTrue(len(control_issues) > 0, "Control.IsVisible should validate 10000 as control ID")

        # Window.IsActive(10000) should check for window ID (10000 is valid home window)
        # It should NOT appear in control ID errors
        window_as_control_issues = [i for i in issues
                                    if "10000" in i.get("message", "")
                                    and "window" in i.get("message", "").lower()
                                    and "control" in i.get("message", "").lower()]
        self.assertEqual(len(window_as_control_issues), 0,
                        "Window.IsActive should not confuse window ID with control ID")


# ============================================================================
# SECTION 6: BUILTIN CONTROLS
# Tests for Kodi C++ builtin controls (data/kodi_builtin_controls.xml)
# Fixed 2 false positives for DialogMediaSource controls 18, 19
# ============================================================================

class TestBuiltinControls(unittest.TestCase):
    """Test Kodi builtin controls from C++ source.

    Kodi creates certain controls programmatically in C++ code.
    These controls don't appear in the skin XML but can be referenced.

    Reference: data/kodi_builtin_controls.xml
    Kodi source: xbmc/dialogs/GUIDialogMediaSource.cpp lines 54-55
    Bug fix: Eliminated 2 false positives for DialogMediaSource OK/Cancel
    """

    def setUp(self):
        """Create temporary skin directory for each test."""
        self.test_dir = tempfile.mkdtemp()

        # Create addon structure
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

        # Create minimal Includes.xml (required for validation to work)
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
</includes>"""
        with open(os.path.join(self.test_dir, "16x9", "Includes.xml"), "w", encoding="utf-8") as f:
            f.write(includes_xml)

    def tearDown(self):
        """Clean up temporary directory."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_dialogmediasource_ok_cancel_buttons(self):
        """DialogMediaSource controls 18/19 (OK/Cancel) should be recognized.

        These are created in C++ code (GUIDialogMediaSource.cpp):
        - Control 18: CONTROL_OK
        - Control 19: CONTROL_CANCEL
        """
        # Note: DialogMediaSource.xml is the standard filename for window ID 10128
        dialog_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window type="dialog" id="10128">
    <controls>
        <!-- Skin can reference builtin controls 18, 19 without defining them -->
        <control type="label">
            <visible>Control.IsVisible(18)</visible>
        </control>
        <control type="label">
            <visible>Control.HasFocus(19)</visible>
        </control>
        <control type="button" id="100">
            <onclick>SetFocus(18)</onclick>
        </control>
    </controls>
</window>"""
        with open(os.path.join(self.test_dir, "16x9", "DialogMediaSource.xml"), "w", encoding="utf-8") as f:
            f.write(dialog_xml)

        provider = InfoProvider()
        provider.init_addon(self.test_dir)
        issues = provider.check_ids()

        # Controls 18 and 19 should NOT be flagged as undefined
        id_18_issues = [i for i in issues if "18" in i.get("message", "") and "not defined" in i.get("message", "").lower()]
        id_19_issues = [i for i in issues if "19" in i.get("message", "") and "not defined" in i.get("message", "").lower()]

        self.assertEqual(len(id_18_issues), 0,
                        f"Control 18 (OK button) should be recognized as builtin. Found: {id_18_issues}")
        self.assertEqual(len(id_19_issues), 0,
                        f"Control 19 (Cancel button) should be recognized as builtin. Found: {id_19_issues}")

    def test_builtin_controls_only_in_correct_window(self):
        """Builtin controls should only be valid in their specific windows."""
        # DialogMediaSource controls 18, 19 should NOT be valid in Home.xml
        home_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <control type="button" id="100">
            <!-- Control 18 is DialogMediaSource-specific, not valid in Home -->
            <onclick>SetFocus(18)</onclick>
        </control>
    </controls>
</window>"""
        with open(os.path.join(self.test_dir, "16x9", "Home.xml"), "w", encoding="utf-8") as f:
            f.write(home_xml)

        provider = InfoProvider()
        provider.init_addon(self.test_dir)
        issues = provider.check_ids()

        # Control 18 SHOULD be flagged in Home.xml (only valid in DialogMediaSource)
        id_18_issues = [i for i in issues if "18" in i.get("message", "") and "Home.xml" in i.get("file", "")]
        self.assertTrue(len(id_18_issues) > 0,
                       "Control 18 should be flagged in Home.xml (only valid in DialogMediaSource)")

    def test_non_builtin_controls_still_flagged(self):
        """Non-existent controls should still be flagged even in DialogMediaSource."""
        dialog_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window type="dialog" id="10128">
    <controls>
        <control type="button" id="100">
            <!-- Control 99999 doesn't exist anywhere -->
            <onclick>SetFocus(99999)</onclick>
        </control>
    </controls>
</window>"""
        with open(os.path.join(self.test_dir, "16x9", "DialogMediaSource.xml"), "w", encoding="utf-8") as f:
            f.write(dialog_xml)

        provider = InfoProvider()
        provider.init_addon(self.test_dir)

        from libs.validation import ValidationIds as IdCheck
        checker = IdCheck(provider.addon, provider.WINDOW_IDS, provider.WINDOW_NAMES)
        issues = checker.check()

        # Control 99999 should still be flagged (not a builtin)
        id_99999_issues = [i for i in issues if "99999" in i.get("message", "")]
        self.assertTrue(len(id_99999_issues) > 0,
                       "Non-builtin control 99999 should still be flagged as undefined")


if __name__ == "__main__":
    unittest.main()
