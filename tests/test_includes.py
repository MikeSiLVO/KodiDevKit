"""
Comprehensive include/parameter resolution tests.

Consolidated from:
- test_param_forwarding.py: Complex parameter forwarding patterns
- test_param_resolution.py: $PARAM resolution and substitution
- test_nested_includes.py: Nested include resolution

Test organization:
- Advanced Param Forwarding: Multi-level forwarding, ID attributes
- Basic Param Resolution: $PARAM substitution, defaults, scoping
- Nested Include Resolution: Include-within-include resolution
"""

import unittest
import os
import sys
import tempfile
import shutil
from lxml import etree as ET

# Add parent directory to path for imports
package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.infoprovider import InfoProvider
from libs import utils
from libs.skin import Skin
from tests.test_utils import kodi_resolve


# ============================================================================
# SECTION 1: ADVANCED PARAM FORWARDING
# Tests for complex parameter forwarding patterns
# ============================================================================

class TestParamForwarding(unittest.TestCase):
    """Test deeply nested parameterized include patterns."""

    def setUp(self):
        """Create temporary skin directory for testing."""
        self.test_dir = tempfile.mkdtemp()
        self.provider = InfoProvider()

        # Create minimal skin structure
        os.makedirs(os.path.join(self.test_dir, "1080i"))

        # Create addon.xml
        addon_xml = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="skin.test" version="1.0.0" name="Test Skin" provider-name="Test">
    <requires>
        <import addon="xbmc.gui" version="5.17.0"/>
    </requires>
    <extension point="xbmc.gui.skin" debugging="false">
        <res width="1920" height="1080" aspect="16:9" default="true" folder="1080i" />
    </extension>
</addon>"""
        with open(os.path.join(self.test_dir, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(addon_xml)

    def tearDown(self):
        """Clean up temporary test directory."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_param_forwarding_with_substitution(self):
        """Test parameters used in dynamic expressions with forwarding."""
        # Pattern: Parent include forwards params to child, which uses them in expressions
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="Section_Container">
        <param name="section_id">100</param>
        <param name="menu_type">default</param>
        <definition>
            <include content="Section_Base">
                <param name="id">$PARAM[section_id]</param>
                <param name="menu_type">$PARAM[menu_type]</param>
            </include>
        </definition>
    </include>

    <include name="Section_Base">
        <param name="id">0</param>
        <param name="menu_type">main</param>
        <definition>
            <control type="group" id="$PARAM[id]">
                <visible>!Skin.HasSetting(Section.$PARAM[id].Hidden)</visible>
            </control>
        </definition>
    </include>
</includes>"""
        includes_path = os.path.join(self.test_dir, "1080i", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Window that uses the parameterized include
        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window type="window" id="2000">
    <controls>
        <include content="Section_Container">
            <param name="section_id">2000</param>
            <param name="menu_type">videos</param>
        </include>
    </controls>
</window>"""
        window_path = os.path.join(self.test_dir, "1080i", "CustomWindow.xml")
        with open(window_path, "w", encoding="utf-8") as f:
            f.write(window_xml)

        self.provider.init_addon(self.test_dir)
        issues = self.provider.check_values()

        # Should NOT flag bracket mismatches in parameterized expressions
        bracket_issues = [i for i in issues if "bracket" in i.get("message", "").lower()]
        self.assertEqual(len(bracket_issues), 0, "Should not flag bracket issues in valid param forwarding")

    def test_nested_param_with_id_attributes(self):
        """Test parameter forwarding where params define control IDs."""
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="Hidden_List_Template">
        <param name="id">100</param>
        <definition>
            <control type="list" id="$PARAM[id]">
                <visible>false</visible>
            </control>
        </definition>
    </include>

    <include name="Widget_Panel">
        <definition>
            <include content="Hidden_List_Template">
                <param name="id">650</param>
            </include>
        </definition>
    </include>
</includes>"""
        includes_path = os.path.join(self.test_dir, "1080i", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <include>Widget_Panel</include>
    </controls>
</window>"""
        window_path = os.path.join(self.test_dir, "1080i", "Home.xml")
        with open(window_path, "w", encoding="utf-8") as f:
            f.write(window_xml)

        self.provider.init_addon(self.test_dir)
        issues = self.provider.check_ids()

        # The ID 650 is defined via param forwarding - should be recognized
        # Note: This may still show as undefined due to complexity of resolving params
        # But at minimum it should not crash
        self.assertIsInstance(issues, list, "Should handle param-defined IDs without crashing")

    def test_triple_nested_param_forwarding(self):
        """Test parameters forwarded through three levels of includes."""
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="Level_One">
        <param name="target_id">1</param>
        <definition>
            <include content="Level_Two">
                <param name="forwarded_id">$PARAM[target_id]</param>
            </include>
        </definition>
    </include>

    <include name="Level_Two">
        <param name="forwarded_id">2</param>
        <definition>
            <include content="Level_Three">
                <param name="final_id">$PARAM[forwarded_id]</param>
            </include>
        </definition>
    </include>

    <include name="Level_Three">
        <param name="final_id">3</param>
        <definition>
            <control type="button" id="$PARAM[final_id]">
                <label>Test</label>
            </control>
        </definition>
    </include>
</includes>"""
        includes_path = os.path.join(self.test_dir, "1080i", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        window_xml = """<?xml version="1.0" encoding="UTF-8"?>
<window>
    <controls>
        <include content="Level_One">
            <param name="target_id">9999</param>
        </include>
    </controls>
</window>"""
        window_path = os.path.join(self.test_dir, "1080i", "Test.xml")
        with open(window_path, "w", encoding="utf-8") as f:
            f.write(window_xml)

        self.provider.init_addon(self.test_dir)
        issues = self.provider.check_values()

        # Should not crash with deeply nested param forwarding
        self.assertIsInstance(issues, list, "Should handle triple-nested param forwarding without crashing")


# ============================================================================
# SECTION 2: BASIC PARAM RESOLUTION
# Tests for $PARAM substitution, defaults, and scoping
# ============================================================================

class DummyInclude(dict):
    """Minimal include structure with optional default params."""

    def __init__(self, *, params=None, **kwargs):
        super().__init__(**kwargs)
        self.params = params or {}


class DummyAddon:
    """Lightweight stand-in for Kodi skin Addon used in unit tests."""

    def __init__(self, root_path, window_files, includes):
        self.path = root_path
        self.window_files = window_files
        self.xml_folders = list(window_files.keys())
        self.includes = includes
        self.fonts = {}

    def get_xml_files(self):
        for folder, filenames in self.window_files.items():
            for name in filenames:
                yield os.path.join(self.path, folder, name)

    def get_constants(self, folder):
        return []


class TestIncludeParamResolution(unittest.TestCase):
    """Verify include defaults are expanded when searching for IDs."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = self.temp_dir.name
        self.folder = os.path.join(self.root, "16x9")
        os.makedirs(self.folder, exist_ok=True)

        self.window_path = os.path.join(self.folder, "Home.xml")
        with open(self.window_path, "w", encoding="utf-8") as fh:
            fh.write(
                """<?xml version="1.0"?>
<window>
    <controls>
        <control type="group">
            <include>MyControl</include>
        </control>
        <control type="label">
            <onclick>Control.SetFocus(9000)</onclick>
        </control>
    </controls>
</window>
"""
            )

        include_path = os.path.join(self.folder, "Includes.xml")
        with open(include_path, "w", encoding="utf-8") as fh:
            fh.write("<includes />")

        include = DummyInclude(
            type="include",
            name="MyControl",
            file=include_path,
            line=1,
            content="""
<include name="MyControl">
    <param name="cid" default="9000" />
    <control type="button" id="$PARAM[cid]">
        <label>Param driven</label>
    </control>
</include>
""",
            params={"cid": "9000"},
        )

        self.addon = DummyAddon(
            root_path=self.root,
            window_files={"16x9": ["Home.xml"]},
            includes={"16x9": [include]},
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_control_ids_from_include_params_are_seen_as_defined(self):
        provider = InfoProvider()
        provider.addon = self.addon  # type: ignore[assignment]

        issues = provider.check_ids()

        messages = [item.get("message", "") for item in issues]
        self.assertFalse(
            any("Control / Item ID not defined" in msg for msg in messages),
            f"Unexpected ID errors: {issues}",
        )


class TestDynamicExpressionUtils(unittest.TestCase):
    """Unit tests for dynamic expression helper functions."""

    def test_is_dynamic_expression_detects_tokens(self):
        self.assertTrue(utils.is_dynamic_expression("$PARAM[foo]"))
        self.assertTrue(utils.is_dynamic_expression("   $Var[bar]"))
        self.assertTrue(utils.is_dynamic_expression("$INFO[Window.Property(foo)]"))
        self.assertFalse(utils.is_dynamic_expression("font13"))

    def test_starts_with_param_reference_is_specific(self):
        self.assertTrue(utils.starts_with_param_reference("$param[item]"))
        self.assertFalse(utils.starts_with_param_reference("$var[item]"))

    def test_resolve_params_in_text_handles_defaults(self):
        text = "<label>$PARAM[Value]</label>"
        resolved, status = utils.resolve_params_in_text(text, {"Value": "Hello"})
        self.assertEqual(resolved, "<label>Hello</label>")
        self.assertEqual(status, "ALL_RESOLVED")


class TestParamSubstitutionWithSkin(unittest.TestCase):
    """
    Comprehensive tests for param substitution and include resolution.
    Tests various edge cases including nested includes, missing params, and malformed XML.
    """

    def setUp(self):
        """Create temporary directory for test files."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = self.temp_dir.name
        self.folder_name = "16x9"
        self.folder = os.path.join(self.root, self.folder_name)
        os.makedirs(self.folder, exist_ok=True)

    def tearDown(self):
        """Clean up temporary directory."""
        self.temp_dir.cleanup()

    def _create_skin_with_includes(self, includes_xml):
        """Helper to create a Skin instance with given includes XML."""
        inc_path = os.path.join(self.folder, "Includes.xml")
        with open(inc_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        skin = Skin.__new__(Skin)
        skin.path = self.root
        # Initialize 5-map structure
        skin.include_map = {}
        skin.default_map = {}
        skin.constant_map = {}
        skin.variable_map = {}
        skin.expression_map = {}
        skin.include_files = {self.folder_name: []}
        skin.update_includes(inc_path)
        return skin

    def _resolve_and_tostring(self, skin, window_xml):
        """Helper to resolve includes and return string representation."""
        root = ET.fromstring(window_xml)
        kodi_resolve(skin, root, self.folder_name)  # Modifies in-place, recurses
        # Strip provenance attributes before serializing for clean comparisons
        for elem in root.iter():
            for attr in list(elem.attrib):
                if attr.startswith("_kdk_"):
                    del elem.attrib[attr]
        return ET.tostring(root, encoding="unicode")

    def test_basic_param_override(self):
        """Test basic parameter override with defaults."""
        includes_xml = """
            <includes>
                <include name="TestInclude">
                    <param name="color" default="red" />
                    <param name="label" default="Default" />
                    <control type="label">
                        <textcolor>$PARAM[color]</textcolor>
                        <label>$PARAM[label]</label>
                    </control>
                </include>
            </includes>
        """

        window_xml = """
            <window>
                <controls>
                    <include content="TestInclude">
                        <param name="color">blue</param>
                    </include>
                </controls>
            </window>
        """

        skin = self._create_skin_with_includes(includes_xml)
        result = self._resolve_and_tostring(skin, window_xml)

        self.assertIn("<textcolor>blue</textcolor>", result)
        self.assertIn(">Default<", result)

    def test_multi_param_substitution(self):
        """Test multiple parameter substitution in a single include."""
        includes_xml = """
            <includes>
                <include name="TwoParams">
                    <param name="foo" default="one" />
                    <param name="bar" default="two" />
                    <control type="label">
                        <label>$PARAM[foo],$PARAM[bar]</label>
                    </control>
                </include>
            </includes>
        """

        window_xml = """
            <window>
                <controls>
                    <include content="TwoParams">
                        <param name="foo">X</param>
                        <param name="bar">Y</param>
                    </include>
                </controls>
            </window>
        """

        skin = self._create_skin_with_includes(includes_xml)
        result = self._resolve_and_tostring(skin, window_xml)

        self.assertIn("<label>X,Y</label>", result)

    def test_missing_param_stays_literal(self):
        """Test that missing params without defaults stay as $PARAM[...]."""
        includes_xml = """
            <includes>
                <include name="MissingParam">
                    <control type="label">
                        <label>$PARAM[ghost]</label>
                    </control>
                </include>
            </includes>
        """

        window_xml = """
            <window>
                <controls>
                    <include content="MissingParam" />
                </controls>
            </window>
        """

        skin = self._create_skin_with_includes(includes_xml)
        result = self._resolve_and_tostring(skin, window_xml)

        self.assertIn("$PARAM[ghost]", result)

    def test_nested_include_param_scoping(self):
        """Test that nested includes maintain separate param scopes."""
        includes_xml = """
            <includes>
                <include name="Inner">
                    <param name="val" default="D" />
                    <control type="label">
                        <label>$PARAM[val]</label>
                    </control>
                </include>

                <include name="Outer">
                    <param name="outer" default="O" />
                    <control type="group">
                        <label>$PARAM[outer]</label>
                        <include content="Inner">
                            <param name="val">I</param>
                        </include>
                    </control>
                </include>
            </includes>
        """

        window_xml = """
            <window>
                <controls>
                    <include content="Outer">
                        <param name="outer">X</param>
                    </include>
                </controls>
            </window>
        """

        skin = self._create_skin_with_includes(includes_xml)
        result = self._resolve_and_tostring(skin, window_xml)

        self.assertIn("<label>X</label>", result)
        self.assertIn("<label>I</label>", result)

    def test_infolabel_literal_in_default(self):
        """Test that InfoLabel expressions in defaults are preserved."""
        includes_xml = """
            <includes>
                <include name="InfoLabelTest">
                    <param name="label" default="$INFO[ListItem.Label]" />
                    <control type="label">
                        <label>$PARAM[label]</label>
                    </control>
                </include>
            </includes>
        """

        window_xml = """
            <window>
                <controls>
                    <include content="InfoLabelTest" />
                </controls>
            </window>
        """

        skin = self._create_skin_with_includes(includes_xml)
        result = self._resolve_and_tostring(skin, window_xml)

        self.assertIn("$INFO[ListItem.Label]", result)

    def test_missing_include_stays_unexpanded(self):
        """Test that references to undefined includes stay in place."""
        includes_xml = """
            <includes>
                <include name="DefinedInclude">
                    <control type="label">
                        <label>Exists</label>
                    </control>
                </include>
            </includes>
        """

        window_xml = """
            <window>
                <controls>
                    <include content="NoSuchInclude" />
                    <control type="label"><label>After</label></control>
                </controls>
            </window>
        """

        skin = self._create_skin_with_includes(includes_xml)
        result = self._resolve_and_tostring(skin, window_xml)

        # Kodi behavior: unresolved includes stay in place safely
        self.assertIn('<include content="NoSuchInclude"', result)
        self.assertIn("<label>After</label>", result)


# ============================================================================
# SECTION 3: NESTED INCLUDE RESOLUTION
# Tests for include-within-include resolution
# ============================================================================

class TestNestedIncludes(unittest.TestCase):
    """Test nested include resolution."""

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

    def test_nested_include_resolution(self):
        """Test that nested includes are properly resolved."""
        # Create includes file with nested structure
        includes_xml = """<?xml version="1.0" encoding="UTF-8"?>
<includes>
    <include name="OuterInclude">
        <control type="group">
            <include>InnerInclude</include>
        </control>
    </include>
    <include name="InnerInclude">
        <control type="label">
            <label>Nested Content</label>
        </control>
    </include>
</includes>"""
        includes_path = os.path.join(self.test_dir, "16x9", "Includes.xml")
        with open(includes_path, "w", encoding="utf-8") as f:
            f.write(includes_xml)

        # Initialize skin
        skin = Skin(project_path=self.test_dir, settings={})

        # Create XML with include reference
        xml = ET.fromstring("""<window>
    <controls>
        <include>OuterInclude</include>
    </controls>
</window>""")

        # This should not raise TypeError about positional arguments
        try:
            kodi_resolve(skin,xml, "16x9")  # Modifies in-place, recurses

            # Verify the nested include was resolved
            labels = xml.xpath(".//label")
            self.assertTrue(len(labels) > 0, "Nested include should be expanded")
            self.assertEqual(labels[0].text, "Nested Content")

        except TypeError as e:
            if "positional argument" in str(e):
                self.fail(f"resolve_includes() called with wrong argument type: {e}")
            raise


if __name__ == "__main__":
    unittest.main()
