"""KodiDevKit Sublime Text plugin: Kodi skinning helpers."""

from __future__ import annotations

import os
import re
import pickle
import copy
import time
from pathlib import Path

from .. import utils
from .. import addon
from ..skin.include import SkinInclude
from .maps import SkinMaps, INCLUDE_MAPS_VERSION
from .resolution import SkinResolution
from .resources import SkinResources
import logging

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.propagate = True

try:
    import sublime
    _debug = bool(sublime.load_settings('kodidevkit.sublime-settings').get('debug_mode', False))
    logger.setLevel(logging.DEBUG if _debug else logging.INFO)
except Exception:
    logger.setLevel(logging.INFO)

FILE_PREVIEW_SIZE = 50_000


class Skin(addon.Addon):
    """A Kodi skin: includes, colors, fonts, and resolved windows."""

    LANG_START_ID = 31000
    LANG_OFFSET = 0

    def __init__(self, *args, **kwargs):
        """Load addon.xml, includes, colors, and fonts for the skin at `path`."""
        super().__init__(*args, **kwargs)
        self.type = "skin"

        # Kodi-aligned include caches mirroring CGUIIncludes' five maps.
        # folder -> {name -> (Include, default_params, file_path)}
        self.include_map = {}
        # folder -> {control_type -> (Include, file_path)}
        self.default_map = {}
        # folder -> {name -> str}
        self.constant_map = {}
        # folder -> {name -> (file, line)} for jump-to-definition.
        self.constant_source_map = {}
        # folder -> {name -> (Include, file_path)}
        self.variable_map = {}
        # folder -> {name -> str (already wrapped in [...])}
        self.expression_map = {}
        # folder -> {name -> (file, line)} for jump-to-definition (expression_map
        # only stores the value, not where it came from).
        self.expression_source_map = {}

        # folder -> {include_name -> [{'params': {...}, 'file', 'line'}]}
        # for context-aware validation; built lazily.
        self.include_usages = {}
        self._include_usages_built = False

        self._resolved_windows_cache: dict = {}

        api_version = self.root.find(".//import[@addon='xbmc.gui']").attrib.get("version")
        logger.info("xbmc.gui API version: %s", api_version)
        parsed_api_version = self._safe_version_tuple(api_version)
        if parsed_api_version is not None:
            for item in self.RELEASES:
                target_version = self._safe_version_tuple(item["gui_version"])
                if target_version is None:
                    continue
                if parsed_api_version <= target_version:
                    self.api_version = item["name"]
                    break
        self.load_xml_folders()
        self.update_include_list()

        self._load_colors_and_fonts()

        self.validation_index = None

        self.builtin_controls, self.builtin_filename_map = self._load_builtin_controls()

        self._resolver = None
        self._index_builder = None
        self._resource_loader = None
        self._include_param_roles = None

    @property
    def resolver(self) -> "SkinResolution":
        """Lazy-built include/constant/expression resolver."""
        if not hasattr(self, '_resolver'):
            self._resolver = None
        if self._resolver is None:
            include_maps = SkinMaps()
            include_maps.includes = self.include_map
            include_maps.defaults = self.default_map
            include_maps.constants = self.constant_map
            include_maps.variables = self.variable_map
            include_maps.expressions = self.expression_map

            self._resolver = SkinResolution(include_maps, self.path)
        return self._resolver

    @property
    def index_builder(self):
        """Lazy-built validation index over all windows."""
        if not hasattr(self, '_index_builder'):
            self._index_builder = None
        if self._index_builder is None:
            from .index import SkinIndex
            self._index_builder = SkinIndex(self)
        return self._index_builder

    @property
    def resource_loader(self) -> "SkinResources":
        """Lazy-built loader for colors, fonts, and media files."""
        if not hasattr(self, '_resource_loader'):
            self._resource_loader = None
        if self._resource_loader is None:
            self._resource_loader = SkinResources(self.path, self.xml_folders)
        return self._resource_loader

    def _build_include_param_roles(self):
        """Scan every <include name=...> body for $PARAM[X] usages and record
        the role each parameter plays.

        Role is one of:
            ("tag", tag_name)              -- $PARAM[X] is text of <tag_name>
            ("attr", attr_name)            -- $PARAM[X] is value of an attribute
            ("forward", inc_name, pname)   -- $PARAM[X] is forwarded to a nested
                                              <include content="inc_name">'s
                                              <param name="pname">
            "multi"                        -- $PARAM[X] appears in 2+ distinct
                                              roles (no single context)

        Returns: {folder: {include_name: {param_name: role}}}
        """
        result = {}
        param_re = re.compile(r"\$PARAM\[([^,\]]+)")

        def mark(roles, pname, new_role):
            existing = roles.get(pname)
            if existing is None:
                roles[pname] = new_role
            elif existing == "multi" or existing == new_role:
                return
            else:
                roles[pname] = "multi"

        def role_for(node):
            # `<param>` inside a nested `<include content="X">` call is a forward.
            parent = node.getparent() if hasattr(node, "getparent") else None
            if (node.tag == "param" and parent is not None
                    and parent.tag == "include" and parent.get("content")):
                target_inc = parent.get("content")
                target_param = node.get("name") or ""
                if target_inc and target_param:
                    return ("forward", target_inc, target_param)
            return None

        for folder, includes_for_folder in self.include_map.items():
            folder_result = {}
            for inc_name, (inc_node, _defaults, _file) in includes_for_folder.items():
                roles: dict = {}
                for node in inc_node.iter():
                    # Skip the top-level <include> wrapper itself.
                    if node is inc_node:
                        continue
                    # Skip top-level <param> defaults (no $PARAM in defaults in practice).
                    parent = node.getparent() if hasattr(node, "getparent") else None
                    if (node.tag == "param" and parent is inc_node):
                        continue
                    text = (node.text or "")
                    if "$PARAM[" in text:
                        forward_role = role_for(node)
                        for match in param_re.finditer(text):
                            pname = match.group(1).strip()
                            mark(roles, pname, forward_role or ("tag", node.tag))
                    for attr_name, attr_value in node.attrib.items():
                        if attr_name.startswith("_kdk_") or "$PARAM[" not in attr_value:
                            continue
                        for match in param_re.finditer(attr_value):
                            pname = match.group(1).strip()
                            mark(roles, pname, ("attr", attr_name))
                if roles:
                    folder_result[inc_name] = roles
            if folder_result:
                result[folder] = folder_result
        return result

    @property
    def include_param_roles(self):
        """Lazy `{folder: {include_name: {param_name: role}}}` map. See
        `_build_include_param_roles` for role tuple shape."""
        if not hasattr(self, "_include_param_roles"):
            self._include_param_roles = None
        if self._include_param_roles is None:
            self._include_param_roles = self._build_include_param_roles()
        return self._include_param_roles

    def resolve_param_role(self, folder, include_name, param_name, _visited=None):
        """Resolve `<param name=param_name>` inside `<include content=include_name>`
        to its terminal role, following forwarding chains.

        Returns the role tuple, "multi", or None if unresolved or cyclic.
        """
        if _visited is None:
            _visited = set()
        key = (folder, include_name, param_name)
        if key in _visited:
            return None
        _visited.add(key)

        roles_for_folder = self.include_param_roles.get(folder, {})
        include_roles = roles_for_folder.get(include_name, {})
        role = include_roles.get(param_name)

        if role is None or role == "multi":
            return role

        if isinstance(role, tuple) and role and role[0] == "forward":
            _, target_inc, target_param = role
            return self.resolve_param_role(folder, target_inc, target_param, _visited)

        return role

    def _load_colors_and_fonts(self):
        """Load colors (from defines.xml) and fonts (from Font.xml)."""
        try:
            import sublime
        except Exception:
            sublime = None

        self.validation_index = None

        kodi_path = getattr(self, "kodi_path", None)
        if not kodi_path and getattr(self, "settings", None):
            try:
                kodi_path = self.settings.get("kodi_path")
            except Exception:
                kodi_path = None
        if not kodi_path and sublime:
            try:
                kodi_path = sublime.load_settings('kodidevkit.sublime-settings').get("kodi_path")
            except Exception:
                kodi_path = None

        self.colors, self.color_labels = self.resource_loader.load_colors(kodi_path)
        self.fonts, self.font_file = self.resource_loader.load_fonts(self.resolver)

    def _load_builtin_controls(self):
        """Load built-in control IDs from data/kodi_builtin_controls.xml.

        Returns (window_name -> {control_id -> description},
                 filename -> window_name).
        """
        builtin_controls = {}
        filename_to_window = {}

        try:
            builtin_path = Path(__file__).parent.parent.parent / 'data' / 'kodi_builtin_controls.xml'

            if not builtin_path.exists():
                logger.warning("Built-in controls file not found: %s", builtin_path)
                return builtin_controls, filename_to_window

            root = utils.get_root_from_file(str(builtin_path))
            if root is None:
                logger.warning("Failed to parse built-in controls file")
                return builtin_controls, filename_to_window

            for window_elem in root.findall('window'):
                window_name = window_elem.get('name')
                window_xml = window_elem.get('xml')

                if not window_name:
                    continue

                builtin_controls[window_name] = {}

                if window_xml:
                    filename_to_window[window_xml.lower()] = window_name

                for control_elem in window_elem.findall('control'):
                    control_id = control_elem.get('id')
                    description = control_elem.get('description', '')

                    if control_id:
                        control_id = utils.normalize_control_id(control_id)
                        builtin_controls[window_name][control_id] = description

            logger.info("Loaded built-in controls for %d windows", len(builtin_controls))
            return builtin_controls, filename_to_window

        except Exception as e:
            logger.warning("Failed to load built-in controls: %s", e)
            return builtin_controls, filename_to_window

    def _discover_addon_root(self):
        """
        Find a Kodi addon root by locating an addon.xml.
        Strategy:
          1) Active file, walk upward.
          2) Open folders, walk upward.
          3) Project folders, walk upward.
          4) If still not found, shallow walk (max 3 levels) under open folders.
        Returns a directory path or None.
        """
        import os
        try:
            import sublime
        except Exception:
            sublime = None

        def upward_find(start):
            d = start
            for _ in range(10):
                if os.path.isfile(os.path.join(d, "addon.xml")):
                    return d
                parent = os.path.dirname(d)
                if not parent or parent == d:
                    break
                d = parent
            return None

        candidates = []

        if sublime:
            try:
                win = sublime.active_window()
                view = win.active_view() if win else None
                if view:
                    fn = view.file_name()
                    if fn:
                        candidates.append(os.path.dirname(fn))
            except Exception:
                pass

        if sublime:
            try:
                win = sublime.active_window()
                if win:
                    candidates.extend(win.folders() or [])
            except Exception:
                pass

        if sublime:
            try:
                win = sublime.active_window()
                pdata = win.project_data() if win else None
                if isinstance(pdata, dict):
                    for folder in pdata.get("folders", []):
                        pf = folder.get("path")
                        if pf:
                            candidates.append(pf)
            except Exception:
                pass

        try:
            candidates.append(os.getcwd())
        except Exception:
            pass

        norm = []
        seen = set()
        for c in candidates:
            if not c:
                continue
            p = os.path.abspath(c)
            if p not in seen:
                seen.add(p)
                norm.append(p)

        packages_dir = None
        if sublime:
            try:
                packages_dir = os.path.abspath(sublime.packages_path())
            except Exception:
                packages_dir = None

        for start in norm:
            if packages_dir and os.path.commonpath([packages_dir, os.path.abspath(start)]) == packages_dir:
                continue
            found = upward_find(start)
            if found:
                return found

        for root in norm:
            if packages_dir and os.path.commonpath([packages_dir, os.path.abspath(root)]) == packages_dir:
                continue
            try:
                for dirpath, dirnames, filenames in os.walk(root):
                    rel = os.path.relpath(dirpath, root)
                    depth = 0 if rel == "." else rel.count(os.sep) + 1
                    if depth > 3:
                        dirnames[:] = []
                        continue
                    if "addon.xml" in filenames:
                        return dirpath
            except Exception:
                continue

        return None

    def load_xml_folders(self):
        """Read xml folder names from addon.xml's <res folder=...> entries."""
        self.xml_folders = list(dict.fromkeys(
            node.attrib["folder"] for node in self.root.findall('.//res')
        ))

    @property
    def lang_path(self):
        """Path to the skin's language folder."""
        return os.path.join(self.path, "language")

    @property
    def theme_path(self):
        """Path to the skin's themes folder."""
        return os.path.join(self.path, "themes")

    @property
    def primary_lang_folder(self):
        """Path to the first folder in `language_folders` setting (created if missing)."""
        lang_folders = self.settings.get("language_folders")
        if not lang_folders:
            lang_folders = ["resource.language.en_gb"]
        lang_folder = lang_folders[0]
        lang_path = os.path.join(self.path, "language", lang_folder)
        if not os.path.exists(lang_path):
            os.makedirs(lang_path)
        return lang_path

    @property
    def default_xml_folder(self):
        """Folder name of the <res default="true"> entry in addon.xml, or None."""
        folder = self.root.find(".//res[@default='true']")
        if folder is not None and "folder" in folder.attrib:
            return folder.attrib["folder"]
        return None

    @property
    def media_path(self):
        """Path to the skin's media folder."""
        return os.path.join(self.path, "media")

    def update_include_list(self):
        """Parse every Includes.xml and rebuild the five include maps."""
        start_time = time.time()
        logger.debug("update_include_list START")

        if not hasattr(self, "include_files"):
            self.include_files = {}

        if not hasattr(self, "include_map"):
            self.include_map = {}
        if not hasattr(self, "default_map"):
            self.default_map = {}
        if not hasattr(self, "constant_map"):
            self.constant_map = {}
        if not hasattr(self, "constant_source_map"):
            self.constant_source_map = {}
        if not hasattr(self, "variable_map"):
            self.variable_map = {}
        if not hasattr(self, "expression_map"):
            self.expression_map = {}
        if not hasattr(self, "expression_source_map"):
            self.expression_source_map = {}

        self.validation_index = None
        self._include_param_roles = None

        for folder in self.xml_folders:
            xml_folder = os.path.join(self.path, folder)
            paths = [os.path.join(xml_folder, "Includes.xml"),
                     os.path.join(xml_folder, "includes.xml")]
            self.include_files[folder] = []

            # Wipe stale per-folder entries before reloading so renamed/deleted
            # includes don't linger in long-running Sublime sessions.
            self.include_map[folder] = {}
            self.default_map[folder] = {}
            self.constant_map[folder] = {}
            self.constant_source_map[folder] = {}
            self.variable_map[folder] = {}
            self.expression_map[folder] = {}
            self.expression_source_map[folder] = {}

            include_file = utils.check_paths(paths)
            if include_file:
                self.update_includes(include_file)
            else:
                logger.info("Could not find include file in %s", xml_folder)

            prev = getattr(self, "_last_include_count", {}).get(folder)
            curr = (len(self.include_map.get(folder, {})) +
                    len(self.default_map.get(folder, {})) +
                    len(self.constant_map.get(folder, {})) +
                    len(self.variable_map.get(folder, {})) +
                    len(self.expression_map.get(folder, {})))
            if prev != curr:
                logger.info("Include caches: %d total items in '%s' folder.", curr, folder)
                store = getattr(self, "_last_include_count", None)
                if not isinstance(store, dict):
                    store = {}
                    setattr(self, "_last_include_count", store)
                store[folder] = curr

        duration = time.time() - start_time
        total_files = sum(len(files) for files in self.include_files.values())
        logger.debug("update_include_list COMPLETE: %d include files loaded, duration=%.3fs", total_files, duration)

    def update_includes(self, xml_file):
        """Load `xml_file` and any files it references into the five maps.

        Mirrors CGUIIncludes::Load_Internal: <include>, <default>, <constant>,
        <variable>, <expression>.
        """
        if not hasattr(self, "include_map"):
            self.include_map = {}
        if not hasattr(self, "default_map"):
            self.default_map = {}
        if not hasattr(self, "constant_map"):
            self.constant_map = {}
        if not hasattr(self, "constant_source_map"):
            self.constant_source_map = {}
        if not hasattr(self, "variable_map"):
            self.variable_map = {}
        if not hasattr(self, "expression_map"):
            self.expression_map = {}
        if not hasattr(self, "expression_source_map"):
            self.expression_source_map = {}

        if not os.path.exists(xml_file):
            logger.info("Could not find include file %s", xml_file)
            return None

        folder = xml_file.split(os.sep)[-2]

        root = utils.get_root_from_file(xml_file)
        if root is None:
            return []

        self.include_files[folder].append(xml_file)

        if folder not in self.include_map:
            self.include_map[folder] = {}
        if folder not in self.default_map:
            self.default_map[folder] = {}
        if folder not in self.constant_map:
            self.constant_map[folder] = {}
        if folder not in self.constant_source_map:
            self.constant_source_map[folder] = {}
        if folder not in self.variable_map:
            self.variable_map[folder] = {}
        if folder not in self.expression_map:
            self.expression_map[folder] = {}
        if folder not in self.expression_source_map:
            self.expression_source_map[folder] = {}

        self._load_defaults(root, folder, xml_file)
        self._load_constants(root, folder, xml_file)
        self._load_expressions(root, folder, xml_file)
        self._load_variables(root, folder, xml_file)
        self._load_includes(root, folder, xml_file)

        # Recurse into <include file="..."/> references (CGUIIncludes::LoadIncludes)
        for node in root.findall("include"):
            if "file" in node.attrib and node.attrib["file"] != "script-skinshortcuts-includes.xml":
                include_file = os.path.join(self.path, folder, node.attrib["file"])
                self.update_includes(include_file)

    def _load_defaults(self, root, folder, xml_file):
        """Index <default type="X"> entries (CGUIIncludes::LoadDefaults)."""
        for node in root.findall("default"):
            control_type = node.attrib.get("type")
            if control_type and node.find("*") is not None:
                self.default_map[folder][control_type] = (node, xml_file)

    def _load_constants(self, root, folder, xml_file):
        """Index <constant name="X">value</constant> (CGUIIncludes::LoadConstants)."""
        for node in root.findall("constant"):
            name = node.attrib.get("name")
            if name and node.text:
                self.constant_map[folder][name] = node.text.strip()
                self.constant_source_map[folder][name] = (
                    xml_file, node.sourceline if hasattr(node, 'sourceline') else 0)

    def _load_expressions(self, root, folder, xml_file):
        """Index <expression name="X">cond</expression>, wrapped in [...] like Kodi
        does (GUIIncludes.cpp:119)."""
        for node in root.findall("expression"):
            name = node.attrib.get("name")
            if name and node.text:
                self.expression_map[folder][name] = "[" + node.text.strip() + "]"
                self.expression_source_map[folder][name] = (
                    xml_file, node.sourceline if hasattr(node, 'sourceline') else 0)

    def _load_variables(self, root, folder, xml_file):
        """Index <variable name="X"> entries (CGUIIncludes::LoadVariables)."""
        for node in root.findall("variable"):
            name = node.attrib.get("name")
            if name and node.find("*") is not None:
                self.variable_map[folder][name] = (node, xml_file)

    def _load_includes(self, root, folder, xml_file):
        """Index <include name="X"> entries with their default params
        (CGUIIncludes::LoadIncludes)."""
        for node in root.findall("include"):
            name = node.attrib.get("name")
            if not name or node.find("*") is None:
                continue

            params = {}
            for p in node.findall("param"):
                param_name = p.attrib.get("name")
                if not param_name:
                    continue
                param_value = p.attrib.get("default")
                if param_value is None and p.text:
                    param_value = p.text.strip()
                params[param_name] = param_value or ""

            self.include_map[folder][name] = (node, params, xml_file)

    def update_xml_files(self):
        """Refresh window/include file lists and invalidate the validation index."""
        super().update_xml_files()
        self.validation_index = None

    def reload(self, path):
        """Reload caches affected by an edit to `path`."""
        folder = path.split(os.sep)[-2]

        if folder in self.include_files:
            if path in self.include_files[folder]:
                self.update_include_list()
            else:
                # Untracked file may be a previously-broken include just made valid;
                # peek at the root tag instead of reparsing every window save.
                root = utils.get_root_from_file(path)
                if root is not None and root.tag == "includes":
                    logger.info("Recovered include file detected: %s", path)
                    self.update_include_list()

        if path.endswith("colors/defaults.xml"):
            self._load_colors_and_fonts()
        if path.endswith(("Font.xml", "font.xml")):
            self._load_colors_and_fonts()

    def get_themes(self):
        """List subfolder names under `themes/`."""
        return [folder for folder in os.listdir(os.path.join(self.path, "themes"))]

    def build_include_map(self, folder):
        """Return the include map for `folder`: {name -> (node, params, file)}."""
        return self.include_map.get(folder, {})

    def get_constants(self, folder):
        """List defined constant names for `folder`."""
        return list(self.constant_map.get(folder, {}).keys())

    def return_node(self, keyword=None, folder=False):
        """Look up `keyword` as font, include, variable, default, constant, or expression.

        Strips any param tail (`Name,arg1,arg2` -> `Name`). Returns
        {"name", "content", "file", "line", "type"} or None.
        """
        if not keyword or not folder:
            return None

        lookup_name = keyword.split(',')[0] if ',' in keyword else keyword

        if folder in self.fonts:
            for node in self.fonts[folder]:
                if node["name"] == lookup_name:
                    return node

        includes_for_folder = self.include_map.get(folder, {})
        if lookup_name in includes_for_folder:
            node, _params, file_path = includes_for_folder[lookup_name]
            return {
                "name": lookup_name,
                "content": node,
                "file": file_path,
                "line": node.sourceline if hasattr(node, 'sourceline') else 0,
                "type": node.tag
            }

        variables_for_folder = self.variable_map.get(folder, {})
        if lookup_name in variables_for_folder:
            node, file_path = variables_for_folder[lookup_name]
            return {
                "name": lookup_name,
                "content": node,
                "file": file_path,
                "line": node.sourceline if hasattr(node, 'sourceline') else 0,
                "type": node.tag
            }

        defaults_for_folder = self.default_map.get(folder, {})
        if lookup_name in defaults_for_folder:
            node, file_path = defaults_for_folder[lookup_name]
            return {
                "name": lookup_name,
                "content": node,
                "file": file_path,
                "line": node.sourceline if hasattr(node, 'sourceline') else 0,
                "type": node.tag
            }

        if folder in self.constant_map and lookup_name in self.constant_map[folder]:
            source = self.constant_source_map.get(folder, {}).get(lookup_name, (None, 0))
            return {
                "name": lookup_name,
                "type": "constant",
                "content": self.constant_map[folder][lookup_name],
                "file": source[0],
                "line": source[1],
            }

        if folder in self.expression_map and lookup_name in self.expression_map[folder]:
            source = self.expression_source_map.get(folder, {}).get(lookup_name, (None, 0))
            return {
                "name": lookup_name,
                "type": "expression",
                "content": self.expression_map[folder][lookup_name],
                "file": source[0],
                "line": source[1],
            }

        return None

    def get_expanded_root(self, path, folder):
        """Parse `path` and apply Kodi's resolve pipeline (uncached).

        Returns the resolved root, or the unexpanded root on failure, or None
        if the file can't be parsed.
        """
        root = utils.get_root_from_file(path)
        if root is None:
            return None

        try:
            self.resolver.resolve(root, folder)
            return root
        except Exception as e:
            logger.warning("Failed to expand %s: %s", os.path.basename(path), e)
            return root

    def build_include_maps(self, progress_callback=None):
        """Build the lightweight skin-startup map (includes, fonts, builtin controls).

        Mirrors Kodi's startup phase only; windows are resolved lazily during
        validation, not here. Cached to disk; rebuilt if the cache is missing
        or its version differs.
        """
        cache_path = self._get_include_maps_cache_path()
        if cache_path and cache_path.exists():
            try:
                if progress_callback:
                    progress_callback("Loading include maps from cache...")
                with open(cache_path, 'rb') as f:
                    maps = pickle.load(f)

                if hasattr(maps, 'version') and maps.version == INCLUDE_MAPS_VERSION:
                    if progress_callback:
                        progress_callback("Include maps cache loaded")
                    return maps
            except Exception as e:
                logger.warning("Failed to load include maps cache, rebuilding: %s", e)

        if progress_callback:
            progress_callback("Building include maps (first time)...")

        maps = SkinMaps()

        for folder in self.xml_folders:
            maps.includes[folder] = {}
            if folder in self.include_map:
                for name, (node, default_params, file_path) in self.include_map[folder].items():
                    definition = node.find("definition")
                    include_body = definition if definition is not None else node
                    inc_obj = SkinInclude(node=include_body, file=file_path)
                    maps.includes[folder][name] = {
                        'content': inc_obj.content,
                        'default_params': default_params
                    }

            maps.defaults[folder] = {}
            if folder in self.default_map:
                for ctrl_type, (node, file_path) in self.default_map[folder].items():
                    inc_obj = SkinInclude(node=node, file=file_path)
                    maps.defaults[folder][ctrl_type] = inc_obj.content

            maps.constants[folder] = self.constant_map.get(folder, {}).copy()

            maps.variables[folder] = {}
            if folder in self.variable_map:
                for name, (node, file_path) in self.variable_map[folder].items():
                    inc_obj = SkinInclude(node=node, file=file_path)
                    maps.variables[folder][name] = inc_obj.content

            maps.expressions[folder] = self.expression_map.get(folder, {}).copy()

            include_file_paths = getattr(self, 'include_files', {}).get(folder, [])
            maps.include_files[folder] = [os.path.basename(p) for p in include_file_paths]

        if hasattr(self, 'fonts') and self.fonts:
            for folder, font_list in self.fonts.items():
                maps.fonts_defined[folder] = {}
                for font_data in font_list:
                    font_name = font_data.get('name', '').strip()
                    if font_name:
                        maps.fonts_defined[folder][font_name] = {
                            'file': font_data.get('file', ''),
                            'line': font_data.get('line', 0),
                            'filename': font_data.get('filename', ''),
                            'size': font_data.get('size', '')
                        }

        maps.builtin_controls = self.builtin_controls.copy() if hasattr(self, 'builtin_controls') else {}
        maps.builtin_filename_map = self.builtin_filename_map.copy() if hasattr(self, 'builtin_filename_map') else {}

        if cache_path:
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                self._cleanup_old_cache_files(cache_path)
                with open(cache_path, 'wb') as f:
                    pickle.dump(maps, f, protocol=pickle.HIGHEST_PROTOCOL)
                if progress_callback:
                    progress_callback("Include maps built and cached")
            except Exception as e:
                logger.warning("Failed to cache include maps: %s", e)

        return maps

    def _get_include_maps_cache_path(self):
        """Get path for include maps cache file."""
        if not hasattr(self, 'path') or not self.path:
            return None

        try:
            skin_name = Path(self.path).name.replace('.', '_')
            cache_dir = Path.home() / '.kodidevkit' / 'cache'
            cache_filename = f"skin_{skin_name}_include_maps_v{INCLUDE_MAPS_VERSION}.pkl"
            return cache_dir / cache_filename
        except Exception as e:
            logger.warning("Failed to determine include maps cache path: %s", e)
            return None

    def _cleanup_old_cache_files(self, current_cache_path):
        """Remove old version cache files and stale caches."""
        try:
            cache_dir = current_cache_path.parent
            if not cache_dir.exists():
                return

            skin_name = Path(self.path).name.replace('.', '_')
            current_prefix = f"skin_{skin_name}_include_maps"
            current_time = time.time()

            for cache_file in cache_dir.glob("skin_*_include_maps_v*.pkl"):
                if cache_file.stem.startswith(current_prefix):
                    version_match = re.search(r'_v(\d+)$', cache_file.stem)
                    if version_match and int(version_match.group(1)) < INCLUDE_MAPS_VERSION:
                        cache_file.unlink()
                        logger.info("Removed old cache version: %s", cache_file.name)

                if current_time - cache_file.stat().st_mtime > 30 * 86400:
                    cache_file.unlink()
                    logger.info("Removed stale cache (>30 days): %s", cache_file.name)
        except Exception as e:
            logger.debug("Cache cleanup error: %s", e)

    def validate_single_file(self, file_path, include_maps=None, progress_callback=None):
        """Validate one window/include file using lazy resolution.

        Mirrors Kodi's window-activation lifecycle: load, resolve includes,
        cache resolved tree, validate. Returns {'issues': [...], 'file': path}.
        """
        if include_maps is None:
            if progress_callback:
                progress_callback("Loading include maps...")
            include_maps = self.build_include_maps(progress_callback)

        folder = self._get_folder_for_file(file_path)
        if not folder:
            logger.warning("Could not determine folder for file: %s", file_path)
            return {'issues': [], 'file': file_path}

        basename = os.path.basename(file_path)

        cache_key = (folder, basename)
        if cache_key in self._resolved_windows_cache:
            if progress_callback:
                progress_callback(f"Using cached resolution for {basename}...")
            resolved_root, source_root = self._resolved_windows_cache[cache_key]
            logger.debug("Using cached resolved XML for %s", basename)
        else:
            if progress_callback:
                progress_callback(f"Loading {basename}...")

            source_root = utils.get_root_from_file(file_path)
            if source_root is None:
                logger.warning("Failed to parse file: %s", file_path)
                return {'issues': [], 'file': file_path}

            if utils.tree_needs_expansion(source_root):
                if progress_callback:
                    progress_callback(f"Resolving includes in {basename}...")

                resolved_root = copy.deepcopy(source_root)
                self.resolver.resolve(resolved_root, folder)
                logger.debug("Resolved includes in %s", basename)
            else:
                resolved_root = source_root

            self._resolved_windows_cache[cache_key] = (resolved_root, source_root)
            logger.debug("Cached resolved XML for %s", basename)

        extraction_results = {
            'ids_defined': {folder: {}},
            'ids_referenced': {folder: {}},
            'window_ids': {folder: []},
            'view_ids': set(),  # Flat set, not folder-nested
            'fonts_used': {folder: {}},
            'labels_used': {folder: {}},
            'labels_untranslated': [],
        }

        if progress_callback:
            progress_callback(f"Extracting IDs from {basename}...")

        self.index_builder._extract_id_definitions_from_xml(resolved_root, file_path, folder, extraction_results)

        if progress_callback:
            progress_callback(f"Extracting references from {basename}...")

        self.index_builder._extract_id_references_from_xml(source_root, file_path, folder, extraction_results)
        self.index_builder._extract_fonts_from_xml(source_root, file_path, folder, extraction_results)
        self.index_builder._extract_labels_from_xml(source_root, file_path, folder, extraction_results)

        window_ids_set = set(extraction_results['ids_defined'][folder].keys())

        single_file_index = {
            'ids_defined': extraction_results['ids_defined'],
            'ids_referenced': extraction_results['ids_referenced'],
            'window_ids': extraction_results['window_ids'],
            'view_ids': {folder: extraction_results['view_ids']},  # Convert back to folder-nested
            'window_base_ids': {folder: {basename: window_ids_set}},
            'window_expanded_ids': {folder: {basename: window_ids_set}},
            'window_includes': {folder: {}},
            'include_to_windows': {folder: {}},
            'include_files': include_maps.include_files,
            'fonts_defined': include_maps.fonts_defined,
            'fonts_used': extraction_results['fonts_used'],
            'labels_used': extraction_results['labels_used'],
            'labels_untranslated': extraction_results['labels_untranslated'],
            'builtin_controls': include_maps.builtin_controls,
            'builtin_filename_map': include_maps.builtin_filename_map,
        }

        if progress_callback:
            progress_callback(f"Validating {basename}...")

        from ..validation import ValidationIds, ValidationFont, ValidationLabel, ValidationExpression

        issues = []

        try:
            id_checker = ValidationIds(self, window_ids=[], window_names=[], validation_index=single_file_index)
            id_issues = id_checker.check()
            issues.extend(id_issues)
        except Exception as e:
            logger.error("ID validation failed for %s: %s", basename, e)

        try:
            font_checker = ValidationFont(self, validation_index=single_file_index)
            font_issues = font_checker.check()
            issues.extend(font_issues)
        except Exception as e:
            logger.error("Font validation failed for %s: %s", basename, e)

        try:
            label_checker = ValidationLabel(self, get_po_files_fn=lambda: self.get_po_files(folder), validation_index=single_file_index)
            label_issues = label_checker.check()
            issues.extend(label_issues)
        except Exception as e:
            logger.error("Label validation failed for %s: %s", basename, e)

        try:
            expression_checker = ValidationExpression(self, validation_index=single_file_index)
            expression_issues = expression_checker.check()
            issues.extend(expression_issues)
        except Exception as e:
            logger.error("Expression validation failed for %s: %s", basename, e)

        if progress_callback:
            issue_count = len(issues)
            progress_callback(f"Validation complete: {issue_count} issue(s) found")

        return {'issues': issues, 'file': file_path}

    def _get_folder_for_file(self, file_path):
        """Return the xml folder (e.g. '1080i') containing `file_path`, or None."""
        try:
            file_path_obj = Path(file_path)

            for folder in self.xml_folders:
                folder_path = Path(self.path) / folder
                try:
                    file_path_obj.relative_to(folder_path)
                    return folder
                except ValueError:
                    continue

            logger.warning("File not in any known XML folder: %s", file_path)
            return None
        except Exception as e:
            logger.error("Error determining folder for file %s: %s", file_path, e)
            return None

