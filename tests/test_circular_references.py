"""
Tests for circular reference detection and handling.

Ensures the validator doesn't get stuck in infinite loops when encountering:
- Circular includes (A→B→A)
- Circular variables
- Self-referencing includes

Kodi handles these by tracking processed nodes/depth limits.
Our validator must do the same to avoid hangs.
"""

import os
import sys
import tempfile
import unittest
from lxml import etree as ET

# Add parent directory to path for imports
package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.skin import Skin
from tests.test_utils import kodi_resolve


class TestCircularReferences(unittest.TestCase):
    """Test circular reference detection and handling."""

    def setUp(self):
        """Create temporary skin structure."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.skin_path = self.temp_dir.name
        os.makedirs(os.path.join(self.skin_path, "16x9"))

        # Create minimal addon.xml
        addon_xml = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test" provider-name="Test">
    <requires><import addon="xbmc.gui" version="5.15.0"/></requires>
    <extension point="xbmc.gui.skin" debugging="false">
        <res width="1920" height="1080" aspect="16:9" default="true" folder="16x9" />
    </extension>
</addon>"""
        with open(os.path.join(self.skin_path, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(addon_xml)

        self.skin = Skin(path=self.skin_path)

    def tearDown(self):
        """Clean up temporary directory."""
        self.temp_dir.cleanup()

    def test_simple_circular_include(self):
        """Test detection of simple circular include (A→A)."""
        # Include that references itself
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="SelfReference">
        <include>SelfReference</include>
    </include>
</includes>"""
        includes_path = os.path.join(self.skin_path, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.skin.update_include_list()

        test_xml = """<window>
    <include>SelfReference</include>
</window>"""
        root = ET.fromstring(test_xml)

        # Should not hang - validator tracks processed nodes
        try:
            kodi_resolve(self.skin,root, "16x9")
            # If we get here without hanging, the circular reference was handled
            self.assertTrue(True, "Circular include handled without infinite loop")
        except RecursionError:
            self.fail("Circular include caused infinite recursion")

    def test_mutual_circular_includes(self):
        """Test detection of mutual circular includes (A→B→A)."""
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="IncludeA">
        <control type="label">
            <label>A</label>
        </control>
        <include>IncludeB</include>
    </include>
    <include name="IncludeB">
        <control type="label">
            <label>B</label>
        </control>
        <include>IncludeA</include>
    </include>
</includes>"""
        includes_path = os.path.join(self.skin_path, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.skin.update_include_list()

        test_xml = """<window>
    <include>IncludeA</include>
</window>"""
        root = ET.fromstring(test_xml)

        # Should not hang
        try:
            kodi_resolve(self.skin,root, "16x9")
            self.assertTrue(True, "Mutual circular includes handled")
        except RecursionError:
            self.fail("Mutual circular includes caused infinite recursion")

    def test_deep_circular_chain(self):
        """Test detection of deep circular chain (A→B→C→A)."""
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="ChainA">
        <control type="label"><label>A</label></control>
        <include>ChainB</include>
    </include>
    <include name="ChainB">
        <control type="label"><label>B</label></control>
        <include>ChainC</include>
    </include>
    <include name="ChainC">
        <control type="label"><label>C</label></control>
        <include>ChainA</include>
    </include>
</includes>"""
        includes_path = os.path.join(self.skin_path, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.skin.update_include_list()

        test_xml = """<window>
    <include>ChainA</include>
</window>"""
        root = ET.fromstring(test_xml)

        # Should not hang
        try:
            kodi_resolve(self.skin,root, "16x9")
            self.assertTrue(True, "Deep circular chain handled")
        except RecursionError:
            self.fail("Deep circular chain caused infinite recursion")

    def test_non_circular_deep_nesting(self):
        """Test that legitimate deep nesting works without false positives."""
        # Create deeply nested includes WITHOUT circularity
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="Level1">
        <control type="label"><label>L1</label></control>
        <include>Level2</include>
    </include>
    <include name="Level2">
        <control type="label"><label>L2</label></control>
        <include>Level3</include>
    </include>
    <include name="Level3">
        <control type="label"><label>L3</label></control>
        <include>Level4</include>
    </include>
    <include name="Level4">
        <control type="label"><label>L4</label></control>
    </include>
</includes>"""
        includes_path = os.path.join(self.skin_path, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.skin.update_include_list()

        test_xml = """<window>
    <include>Level1</include>
</window>"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin,root, "16x9")

        # All 4 labels should be inserted
        labels = root.findall(".//label")
        self.assertEqual(len(labels), 4, "All 4 levels should be expanded")
        label_texts = [label.text for label in labels]
        self.assertIn("L1", label_texts)
        self.assertIn("L2", label_texts)
        self.assertIn("L3", label_texts)
        self.assertIn("L4", label_texts)

    def test_circular_with_params(self):
        """Test circular includes with parameters."""
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="ParamCircular">
        <param name="depth" default="1"/>
        <definition>
            <control type="label">
                <label>Depth $PARAM[depth]</label>
            </control>
            <include content="ParamCircular">
                <param name="depth" value="2"/>
            </include>
        </definition>
    </include>
</includes>"""
        includes_path = os.path.join(self.skin_path, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.skin.update_include_list()

        test_xml = """<window>
    <include>ParamCircular</include>
</window>"""
        root = ET.fromstring(test_xml)

        # Should not hang even with parameterized circular reference
        try:
            kodi_resolve(self.skin,root, "16x9")
            self.assertTrue(True, "Parameterized circular include handled")
        except RecursionError:
            self.fail("Parameterized circular include caused infinite recursion")

    def test_multiple_same_include_not_circular(self):
        """Test that using same include multiple times is NOT circular."""
        # This is valid - same include used multiple times in sequence
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="Button">
        <control type="button">
            <width>100</width>
        </control>
    </include>
    <include name="ButtonRow">
        <include>Button</include>
        <include>Button</include>
        <include>Button</include>
    </include>
</includes>"""
        includes_path = os.path.join(self.skin_path, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.skin.update_include_list()

        test_xml = """<window>
    <include>ButtonRow</include>
</window>"""
        root = ET.fromstring(test_xml)

        kodi_resolve(self.skin,root, "16x9")

        # Should have 3 button controls
        buttons = root.findall(".//control[@type='button']")
        self.assertEqual(len(buttons), 3, "Should expand same include 3 times")

    def test_circular_include_in_definition_tag(self):
        """Test circular reference inside <definition> tag."""
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="DefCircular">
        <definition>
            <control type="label">
                <label>Test</label>
            </control>
            <include>DefCircular</include>
        </definition>
    </include>
</includes>"""
        includes_path = os.path.join(self.skin_path, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.skin.update_include_list()

        test_xml = """<window>
    <include>DefCircular</include>
</window>"""
        root = ET.fromstring(test_xml)

        # Should not hang
        try:
            kodi_resolve(self.skin,root, "16x9")
            self.assertTrue(True, "Circular include in definition handled")
        except RecursionError:
            self.fail("Circular include in definition caused infinite recursion")

    def test_indirect_circular_through_multiple_files(self):
        """Test indirect circular reference across window and include file."""
        # This tests the case where a window includes something that tries to include
        # content already being processed
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="ContentA">
        <control type="label"><label>A</label></control>
        <include>ContentB</include>
    </include>
    <include name="ContentB">
        <control type="label"><label>B</label></control>
        <include>ContentA</include>
    </include>
</includes>"""
        includes_path = os.path.join(self.skin_path, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        self.skin.update_include_list()

        # Window file that includes ContentA
        test_xml = """<window>
    <controls>
        <include>ContentA</include>
    </controls>
</window>"""
        root = ET.fromstring(test_xml)

        # Should handle gracefully
        try:
            kodi_resolve(self.skin,root, "16x9")
            self.assertTrue(True, "Cross-file circular reference handled")
        except RecursionError:
            self.fail("Cross-file circular reference caused infinite recursion")


if __name__ == "__main__":
    unittest.main()
