"""Tests for finding string ids under the cursor in add-on Python, wrappers included."""

import os
import shutil
import sys
import tempfile
import unittest

package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from libs.infoprovider.pystrings import (
    SOURCE_ADDON,
    SOURCE_KODI,
    FileFacts,
    Resolver,
    WrapperIndex,
    dependency_roots,
    label_at,
    lookup_source,
)


def _at(line, needle, wrappers=None):
    """Label found with the cursor on the start of the needle, wrappers matched by last name."""
    table = wrappers or {}
    return label_at(line, line.index(needle), lambda c: lookup_source(c) or table.get(c.rsplit(".", 1)[-1]))


def _resolve(files):
    """Resolver over in-memory files given as {path: source}."""
    return Resolver({path: FileFacts(src) for path, src in files.items()})


def _wrappers(src):
    """Wrapper names one file defines, with their sources."""
    r = _resolve({"/a/m.py": src})
    found = {name: source for (_, name), source in r.names.items()}
    found.update(r.attrs)
    return found


class TestLabelAt(unittest.TestCase):
    """Only ids that a string lookup receives as its first argument get a hover."""

    def test_addon_instance_call(self):
        """An Addon instance reads the add-on's own strings."""
        found = (None, "32001", SOURCE_ADDON)
        self.assertEqual(_at("x = ADDON.getLocalizedString(32001)", "32001"), found)

    def test_inline_addon_instance_call(self):
        """A call on Addon() itself also reads the add-on's strings."""
        line = "xbmcaddon.Addon().getLocalizedString(32001)"
        self.assertEqual(_at(line, "32001"), (None, "32001", SOURCE_ADDON))

    def test_attribute_chain_call(self):
        """An Addon kept on an attribute reads the add-on's strings."""
        found = (None, "32001", SOURCE_ADDON)
        self.assertEqual(_at("self.addon.getLocalizedString( 32001 )", "32001"), found)

    def test_xbmc_call(self):
        """The xbmc module reads Kodi's strings."""
        self.assertEqual(_at("xbmc.getLocalizedString(137)", "137"), (None, "137", SOURCE_KODI))

    def test_cursor_at_end_of_number(self):
        """The cursor just past the last digit still counts."""
        line = "ADDON.getLocalizedString(32001)"
        found = label_at(line, line.index(")"), lookup_source)
        self.assertEqual(found, (None, "32001", SOURCE_ADDON))

    def test_ternary_first_argument(self):
        """Both ids of a conditional first argument get a hover."""
        line = "ADDON.getLocalizedString(32032 if cancelled else 32279)"
        self.assertEqual(_at(line, "32032"), (None, "32032", SOURCE_ADDON))
        self.assertEqual(_at(line, "32279"), (None, "32279", SOURCE_ADDON))

    def test_known_wrapper(self):
        """A wrapper call takes the source of the lookup it forwards to."""
        wrappers = {"localize": SOURCE_ADDON}
        found = (None, "32010", SOURCE_ADDON)
        self.assertEqual(_at("label = localize(32010)", "32010", wrappers), found)
        self.assertEqual(_at("utils.localize(32010).format(x)", "32010", wrappers), found)

    def test_other_calls_ignored(self):
        """Numbers passed to anything else, or outside the call, get no hover."""
        self.assertIsNone(_at("xbmc.sleep(30000)", "30000"))
        self.assertIsNone(_at("ADDON.getLocalizedString(32001) + 5", "5"))
        self.assertIsNone(_at("limit = 32001", "32001"))

    def test_later_argument_ignored(self):
        """Only the first argument is an id."""
        wrappers = {"localize": SOURCE_ADDON}
        self.assertIsNone(_at("localize(heading, 32001)", "32001", wrappers))
        self.assertIsNone(_at("localize(x, [32001])", "32001", wrappers))

    def test_nested_call_argument(self):
        """An id inside a nested call belongs to that inner call."""
        wrappers = {"localize": SOURCE_ADDON}
        self.assertIsNone(_at("localize(pick(32001))", "32001", wrappers))

    def test_digits_inside_a_name_ignored(self):
        """Digits that belong to an identifier, a float or an exponent are not ids."""
        wrappers = {"localize": SOURCE_ADDON}
        self.assertIsNone(_at("localize(x32001)", "32001", wrappers))
        self.assertIsNone(_at("localize(1.5)", "5", wrappers))
        self.assertIsNone(_at("localize(1e5)", "1", wrappers))

    def test_addon_macro(self):
        """$ADDON[...] in a string names its add-on."""
        line = 'li.setLabel("$ADDON[plugin.video.test 32001]")'
        self.assertEqual(_at(line, "32001"), ("plugin.video.test", "32001", SOURCE_ADDON))

    def test_localize_macro(self):
        """$LOCALIZE[...] in a string reads Kodi's strings."""
        line = 'li.setLabel("$LOCALIZE[137]")'
        self.assertEqual(_at(line, "137"), (None, "137", SOURCE_KODI))


class TestWrappers(unittest.TestCase):
    """Functions, lambdas and aliases that forward their first param become wrappers."""

    def test_function(self):
        """A function passing its param to getLocalizedString is a wrapper."""
        src = "def localize(i):\n    return ADDON.getLocalizedString(i)\n"
        self.assertEqual(_wrappers(src), {"localize": SOURCE_ADDON})

    def test_function_through_int_and_format(self):
        """int() around the param and work on the result still count."""
        src = "def lang(i, *a):\n    return ADDON.getLocalizedString(int(i)).format(*a)\n"
        self.assertEqual(_wrappers(src), {"lang": SOURCE_ADDON})

    def test_method(self):
        """A method forwarding to self.addon is a wrapper, self excluded."""
        src = ("class A:\n    def get_string(self, i):\n"
               "        return self.addon.getLocalizedString(i)\n")
        self.assertEqual(_wrappers(src), {"get_string": SOURCE_ADDON})

    def test_lambda_and_aliases(self):
        """Lambdas and bound-method aliases, plain or on self, are wrappers."""
        src = ("_ = lambda i: ADDON.getLocalizedString(i)\n"
               "LANGUAGE = ADDON.getLocalizedString\n"
               "class A:\n    def setup(self):\n        self.lang = self.addon.getLocalizedString\n")
        found = {"_": SOURCE_ADDON, "LANGUAGE": SOURCE_ADDON, "lang": SOURCE_ADDON}
        self.assertEqual(_wrappers(src), found)

    def test_xbmc_wrapper(self):
        """A wrapper around xbmc.getLocalizedString reads Kodi's strings."""
        src = "def core(i):\n    return xbmc.getLocalizedString(i)\n"
        self.assertEqual(_wrappers(src), {"core": SOURCE_KODI})

    def test_wrapper_of_wrapper(self):
        """A function forwarding to a wrapper is a wrapper too."""
        src = ("def outer(i):\n    return inner(i)\n"
               "def inner(i):\n    return ADDON.getLocalizedString(i)\n")
        self.assertEqual(_wrappers(src), {"outer": SOURCE_ADDON, "inner": SOURCE_ADDON})

    def test_mixed_sources_show_all(self):
        """A wrapper that can reach both tables reads as a Kodi lookup, showing every source."""
        src = ("def label(i):\n    if i >= 32000:\n        return ADDON.getLocalizedString(i)\n"
               "    return xbmc.getLocalizedString(i)\n")
        self.assertEqual(_wrappers(src), {"label": SOURCE_KODI})

    def test_later_param_is_no_wrapper(self):
        """Hover reads a call's first argument, so only the first param may carry the id."""
        src = "def prompt(heading, error_id):\n    return ADDON.getLocalizedString(error_id)\n"
        self.assertEqual(_wrappers(src), {})

    def test_dunder_is_no_wrapper(self):
        """A constructor forwarding an id is no call site anyone hovers."""
        src = "class A:\n    def __init__(self, i):\n        self.label = ADDON.getLocalizedString(i)\n"
        self.assertEqual(_wrappers(src), {})

    def test_non_forwarding_function(self):
        """A function using a fixed id or another call is no wrapper."""
        src = ("def title():\n    return ADDON.getLocalizedString(32001)\n"
               "def wait(ms):\n    xbmc.sleep(ms)\n")
        self.assertEqual(_wrappers(src), {})

    def test_syntax_error(self):
        """A file that does not parse contributes nothing."""
        facts = FileFacts("def broken(:\n")
        self.assertEqual((facts.names, facts.attrs, facts.imports), ({}, {}, {}))


class TestResolution(unittest.TestCase):
    """Calls resolve from the file they are written in, as Python would."""

    UTILS = "def loc(i):\n    return xbmc.getLocalizedString(i)\n"
    CONFIG = "def loc(location_id):\n    return fetch(location_id)\n"

    def test_same_name_in_two_files(self):
        """A bare name means the file's own def, not a same-named wrapper elsewhere."""
        r = _resolve({"/a/utils.py": self.UTILS, "/a/config.py": self.CONFIG})
        self.assertEqual(r.source("/a/utils.py", "loc"), SOURCE_KODI)
        self.assertIsNone(r.source("/a/config.py", "loc"))

    def test_from_import(self):
        """A name brought in with from-import resolves to its module, alias or not."""
        r = _resolve({"/a/utils.py": self.UTILS, "/a/config.py": self.CONFIG,
                      "/a/menu.py": "from .utils import loc as L\nfrom . import config\n"})
        self.assertEqual(r.source("/a/menu.py", "L"), SOURCE_KODI)
        self.assertIsNone(r.source("/a/menu.py", "config.loc"))

    def test_module_attribute(self):
        """module.name resolves through an absolute import by module path."""
        r = _resolve({"/a/lib/utils.py": self.UTILS, "/a/menu.py": "from lib import utils\n"})
        self.assertEqual(r.source("/a/menu.py", "utils.loc"), SOURCE_KODI)

    def test_unknown_bare_name(self):
        """A bare name neither defined nor imported in the file is no lookup."""
        r = _resolve({"/a/utils.py": self.UTILS, "/a/menu.py": "x = 1\n"})
        self.assertIsNone(r.source("/a/menu.py", "loc"))

    def test_star_import(self):
        """A name brought in by a star import resolves through the imported module."""
        r = _resolve({"/a/lib/utils.py": "LANGUAGE = ADDON.getLocalizedString\n",
                      "/a/default.py": "from lib.utils import *\n"})
        self.assertEqual(r.source("/a/default.py", "LANGUAGE"), SOURCE_ADDON)

    def test_import_cycle(self):
        """Star imports that loop back end the search instead of recursing forever."""
        r = _resolve({"/a/x.py": "from .y import *\n", "/a/y.py": "from .x import *\n"})
        self.assertIsNone(r.source("/a/x.py", "anything"))

    def test_alias_to_method_of_other_file(self):
        """An alias to an instance method resolves by the method name, across files."""
        dep = ("class KodiPlugin:\n    def get_localized(self, i=0):\n"
               "        if i < 30000:\n            return xbmc.getLocalizedString(i)\n"
               "        return self._addon.getLocalizedString(i)\n")
        plugin = "KODIPLUGIN = KodiPlugin('x')\nget_localized = KODIPLUGIN.get_localized\n"
        user = "from pkg.lib.addon.plugin import get_localized\n"
        r = _resolve({"/dep/jm/plugin.py": dep, "/a/pkg/lib/addon/plugin.py": plugin,
                      "/a/pkg/lib/items.py": user})
        self.assertEqual(r.source("/a/pkg/lib/items.py", "get_localized"), SOURCE_KODI)


ADDON_XML = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="plugin.video.test" name="Test" version="1.0.0" provider-name="test">
    <requires>
        <import addon="xbmc.python" version="3.0.0"/>
    </requires>
    <extension point="xbmc.python.pluginsource" library="default.py"/>
</addon>"""


class TestWrapperIndex(unittest.TestCase):
    """The index joins wrappers across the add-on's files and its Python dependencies."""

    def setUp(self):
        """Create an add-on and a module dependency beside it, with a hidden folder to skip."""
        self.addons = tempfile.mkdtemp()
        self.root = os.path.join(self.addons, "plugin.video.test")
        lib = os.path.join(self.root, "resources", "lib")
        os.makedirs(lib)
        os.makedirs(os.path.join(self.root, ".git"))
        requires = '<import addon="script.module.helper" version="1.0.0"/></requires>'
        self._write(self.root, "addon.xml", ADDON_XML.replace("</requires>", requires))
        self._write(lib, "utils.py", "def localize(i):\n    return ADDON.getLocalizedString(i)\n")
        self._write(lib, "menu.py", "from .utils import localize\ndef heading(i):\n    return localize(i)\n")
        self._write(os.path.join(self.root, ".git"), "hook.py",
                    "def hidden(i):\n    return ADDON.getLocalizedString(i)\n")
        dep = os.path.join(self.addons, "script.module.helper")
        mods = os.path.join(dep, "lib", "helper")
        os.makedirs(mods)
        self._write(dep, "addon.xml",
                    '<addon id="script.module.helper"><extension point="xbmc.python.module" library="lib"/></addon>')
        self._write(mods, "text.py", "def core(i):\n    return xbmc.getLocalizedString(i)\n")
        self._write(mods, "big.py", "def unrelated(i):\n    return i\n")

    def tearDown(self):
        """Remove the temporary add-ons."""
        shutil.rmtree(self.addons, ignore_errors=True)

    @staticmethod
    def _write(folder, name, text):
        """Write one file."""
        with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
            f.write(text)

    def test_dependency_roots(self):
        """A module dependency's library folder is found from addon.xml."""
        expected = [os.path.join(self.addons, "script.module.helper", "lib")]
        self.assertEqual(dependency_roots(self.root), expected)

    def test_cross_file_and_dependency_wrappers(self):
        """Wrappers resolve across files and dependencies; hidden dirs are skipped."""
        index = WrapperIndex(self.root, dependency_roots(self.root))
        index.refresh()
        r = index.resolver()
        menu = os.path.join(self.root, "resources", "lib", "menu.py")
        self.assertEqual(r.source(menu, "localize"), SOURCE_ADDON)
        self.assertEqual(r.source(menu, "heading"), SOURCE_ADDON)
        self.assertEqual(sorted(n for _, n in r.names), ["core", "heading", "localize"])

    def test_first_call_does_not_block(self):
        """Before any refresh the index answers with nothing instead of waiting."""
        self.assertEqual(WrapperIndex(self.root).resolver().names, {})


STRINGS_PO = """msgid ""
msgstr ""
"Language: en_GB\\n"

msgctxt "#32001"
msgid "Recently added"
msgstr ""
"""


class TestPythonLabelTooltip(unittest.TestCase):
    """The hover shows the strings the call actually reads."""

    def setUp(self):
        """Create a python add-on with one string of its own."""
        from libs.infoprovider.provider import InfoProvider

        self.root = tempfile.mkdtemp()
        lang = os.path.join(self.root, "resources", "language", "resource.language.en_gb")
        os.makedirs(lang)
        with open(os.path.join(self.root, "addon.xml"), "w", encoding="utf-8") as f:
            f.write(ADDON_XML)
        with open(os.path.join(lang, "strings.po"), "w", encoding="utf-8") as f:
            f.write(STRINGS_PO)
        self.default_py = os.path.join(self.root, "default.py")
        with open(self.default_py, "w", encoding="utf-8") as f:
            f.write("def localize(i):\n    return ADDON.getLocalizedString(i)\n")
        self.provider = InfoProvider()
        self.provider.settings = {"language_folders": ["resource.language.en_gb"]}
        self.provider.init_addon(self.root)
        self.provider.addon.update_labels()
        self.provider._python_wrappers = WrapperIndex(self.root)
        self.provider._python_wrappers.refresh()

    def tearDown(self):
        """Remove the temporary add-on."""
        shutil.rmtree(self.root, ignore_errors=True)

    def _hover(self, line, needle):
        """Tooltip HTML with the cursor on the needle, in the add-on's default.py."""
        return self.provider.python_label_tooltip(line, line.index(needle), self.default_py)

    def test_addon_string(self):
        """An add-on lookup shows the add-on's own translation."""
        self.assertIn("Recently added", self._hover("ADDON.getLocalizedString(32001)", "32001"))

    def test_wrapper_string(self):
        """A wrapper call shows the same translation as the lookup it wraps."""
        self.assertIn("Recently added", self._hover("title = localize(32001)", "32001"))

    def test_addon_string_missing(self):
        """An add-on lookup for an id the add-on lacks says so."""
        hover = self._hover("ADDON.getLocalizedString(32999)", "32999")
        self.assertIn("Not in this add-on's strings.po", hover)

    def test_plain_number(self):
        """A number no lookup receives gets no hover."""
        self.assertEqual(self._hover("xbmc.sleep(32001)", "32001"), "")


if __name__ == "__main__":
    unittest.main()
