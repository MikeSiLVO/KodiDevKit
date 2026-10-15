"""Kodi skin model: the include maps, colors, fonts and resolver for one skin."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

from ..utils.files import check_paths, is_inside
from ..utils.xml import get_params, get_root_from_file
from ..utils.validation import normalize_control_id
from ..addon.addon import Addon
from .maps import SkinMaps
from .resolution import SkinResolution
from .resources import SkinResources
import logging
from typing import Any

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.propagate = True



class Skin(Addon):
    """A Kodi skin: includes, colors, fonts, and resolved windows."""

    LANG_START_ID = 31000
    LANG_OFFSET = 0

    def __init__(self, *args, **kwargs):
        self._resolver: SkinResolution | None = None
        self._resource_loader: SkinResources | None = None
        self._include_param_roles = None
        self._last_include_count: dict[str, int] = {}
        super().__init__(*args, **kwargs)
        self.type = "skin"

        # the five include maps plus <map>, keyed by xml folder then name
        self.include_map: dict[str, dict[str, tuple[Any, dict[str, str], str]]] = {}
        self.default_map: dict[str, dict[str, tuple[Any, str]]] = {}
        self.constant_map: dict[str, dict[str, str]] = {}
        self.constant_source_map: dict[str, dict[str, tuple[str, int]]] = {}
        self.variable_map: dict[str, dict[str, tuple[Any, str]]] = {}
        self.map_map: dict[str, dict[str, tuple[Any, str]]] = {}
        # every <map> in load order, so a shadowed one can still be reported
        self.map_defs: dict[str, list[tuple[Any, str]]] = {}
        self.expression_map: dict[str, dict[str, str]] = {}
        self.expression_source_map: dict[str, dict[str, tuple[str, int]]] = {}
        # definitions Kodi drops: a later duplicate of a first-wins name, or params with no body
        self.shadowed_defs: dict[str, list[dict]] = {}
        # include files loaded under a condition, which Kodi only reads when it holds
        self.conditional_files: dict[str, set[str]] = {}

        self.include_usages: dict = {}
        self._include_usages_built = False

        self.update_include_list()
        self._load_colors_and_fonts()
        self.builtin_controls, self.builtin_filename_map = self._load_builtin_controls()

    def _release_from_addon_xml(self) -> str | None:
        """Oldest release whose xbmc.gui version satisfies this skin's import."""
        node = self.root.find(".//import[@addon='xbmc.gui']")
        if node is None:
            return None
        wanted = self._safe_version_tuple(node.attrib.get("version"))
        logger.info("xbmc.gui API version: %s", node.attrib.get("version"))
        if wanted is None:
            return None
        for item in self.RELEASES:
            target = self._safe_version_tuple(item["gui_version"])
            if target is not None and wanted <= target:
                return item["name"]
        return None

    @property
    def resolver(self) -> "SkinResolution":
        """The resolver over this skin's maps, built on first use."""
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
    def resource_loader(self) -> "SkinResources":
        """The colors, fonts and media reader, built on first use."""
        if self._resource_loader is None:
            self._resource_loader = SkinResources(self.path, self.xml_folders)
        return self._resource_loader

    def _build_include_param_roles(self):
        """Role of each $PARAM per include body: tag, attribute, forward to a nested call, multi."""
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
                    if node is inc_node:
                        continue
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
        """Per-folder include parameter roles, built on first use."""
        if self._include_param_roles is None:
            self._include_param_roles = self._build_include_param_roles()
        return self._include_param_roles

    def resolve_param_role(self, folder, include_name, param_name, _visited=None):
        """Final role of a param on an include call, following forwards to nested includes."""
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
        """Load colors and fonts through the resource reader, dropping the validation index."""
        from ..coredata import kodi_colors_xml

        self.validation_index = None

        kodi_path = getattr(self, "kodi_path", None)
        if not kodi_path and getattr(self, "settings", None):
            try:
                kodi_path = self.settings.get("kodi_path")
            except Exception:
                kodi_path = None

        system_colors = kodi_colors_xml(self, kodi_path)
        self.colors, self.color_labels = self.resource_loader.load_colors(system_colors)
        self.fonts, self.font_file = self.resource_loader.load_fonts(self.resolver)

    def _load_builtin_controls(self):
        """Kodi's own control ids per window from the bundled data, plus filename to window name."""
        builtin_controls = {}
        filename_to_window = {}

        try:
            builtin_path = Path(__file__).parent.parent.parent / 'data' / 'kodi_builtin_controls.xml'

            if not builtin_path.exists():
                logger.warning("Built-in controls file not found: %s", builtin_path)
                return builtin_controls, filename_to_window

            root = get_root_from_file(str(builtin_path))
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
                        control_id = normalize_control_id(control_id)
                        builtin_controls[window_name][control_id] = description

            logger.info("Loaded built-in controls for %d windows", len(builtin_controls))
            return builtin_controls, filename_to_window

        except Exception as e:
            logger.warning("Failed to load built-in controls: %s", e)
            return builtin_controls, filename_to_window

    def load_xml_folders(self):
        """Read xml folder names from addon.xml's <res folder=...> entries."""
        self.xml_folders = list(dict.fromkeys(
            node.attrib["folder"] for node in self.root.findall('.//res')
        ))

    @property
    def lang_path(self):
        """The skin's `language` folder."""
        return os.path.join(self.path, "language")

    @property
    def theme_path(self):
        """The skin's `themes` folder."""
        return os.path.join(self.path, "themes")

    @property
    def primary_lang_folder(self):
        """First language folder from settings, created on disk if missing."""
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
        """Folder of the <res default="true"> entry in addon.xml, or None."""
        folder = self.root.find(".//res[@default='true']")
        if folder is not None and "folder" in folder.attrib:
            return folder.attrib["folder"]
        return None

    @property
    def media_path(self):
        """The skin's `media` folder."""
        return os.path.join(self.path, "media")

    def update_include_list(self):
        """Update every folder's maps from its Includes.xml, dropping the validation index."""
        start_time = time.time()
        logger.debug("update_include_list START")

        self.validation_index = None
        self._include_param_roles = None

        for folder in self.xml_folders:
            xml_folder = os.path.join(self.path, folder)
            paths = [os.path.join(xml_folder, "Includes.xml"),
                     os.path.join(xml_folder, "includes.xml")]
            self.include_files[folder] = []

            # start empty so a renamed or deleted include does not linger across reloads
            self.include_map[folder] = {}
            self.default_map[folder] = {}
            self.constant_map[folder] = {}
            self.constant_source_map[folder] = {}
            self.variable_map[folder] = {}
            self.map_map[folder] = {}
            self.map_defs[folder] = []
            self.expression_map[folder] = {}
            self.expression_source_map[folder] = {}
            self.shadowed_defs[folder] = []
            self.conditional_files[folder] = set()

            include_file = check_paths(paths)
            if include_file:
                self.update_includes(include_file, folder)
            else:
                logger.info("Could not find include file in %s", xml_folder)

            prev = self._last_include_count.get(folder)
            curr = (len(self.include_map.get(folder, {})) +
                    len(self.default_map.get(folder, {})) +
                    len(self.constant_map.get(folder, {})) +
                    len(self.variable_map.get(folder, {})) +
                    len(self.map_map.get(folder, {})) +
                    len(self.expression_map.get(folder, {})))
            if prev != curr:
                logger.info("Include caches: %d total items in '%s' folder.", curr, folder)
                self._last_include_count[folder] = curr

        duration = time.time() - start_time
        total_files = sum(len(files) for files in self.include_files.values())
        logger.debug("update_include_list COMPLETE: %d include files loaded, duration=%.3fs", total_files, duration)

    def update_includes(self, xml_file, folder, conditional=False):
        """Update maps from a skin include file and nested ones."""
        xml_file = os.path.normpath(xml_file)
        if not os.path.exists(xml_file) or not is_inside(xml_file, self.path):
            logger.info("Could not find include file %s", xml_file)
            return None

        root = get_root_from_file(xml_file)
        if root is None:
            return []

        self.include_files[folder].append(xml_file)
        if conditional:
            self.conditional_files[folder].add(xml_file)

        self._load_defaults(root, folder, xml_file)
        self._load_constants(root, folder, xml_file)
        self._load_expressions(root, folder, xml_file)
        self._load_variables(root, folder, xml_file)
        self._load_includes(root, folder, xml_file, conditional)
        self._load_maps(root, folder, xml_file)

    def _keep_first(self, kind, table, folder, name, node, xml_file, value):
        """Store the definition unless the name is taken; record the one that loses."""
        if name in table[folder]:
            self.shadowed_defs[folder].append({
                "kind": kind, "name": name, "file": xml_file,
                "line": getattr(node, "sourceline", 0) or 0,
            })
            return False
        table[folder][name] = value
        return True

    def _load_defaults(self, root, folder, xml_file):
        """Load <default type="X"> entries, the first definition winning."""
        for node in root.findall("default"):
            control_type = node.attrib.get("type")
            if control_type and node.find("*") is not None:
                self._keep_first("default", self.default_map, folder, control_type, node, xml_file,
                                 (node, xml_file))

    def _load_constants(self, root, folder, xml_file):
        """Load <constant name="X"> values, the first definition winning."""
        for node in root.findall("constant"):
            name = node.attrib.get("name")
            if name and node.text:
                if self._keep_first("constant", self.constant_map, folder, name, node, xml_file,
                                    node.text.strip()):
                    self.constant_source_map[folder][name] = (xml_file, node.sourceline or 0)

    def _load_expressions(self, root, folder, xml_file):
        """Load <expression> entries, each wrapped in [...], the first definition winning."""
        for node in root.findall("expression"):
            name = node.attrib.get("name")
            if name and node.text:
                if self._keep_first("expression", self.expression_map, folder, name, node, xml_file,
                                    "[" + node.text.strip() + "]"):
                    self.expression_source_map[folder][name] = (xml_file, node.sourceline or 0)

    def _load_variables(self, root, folder, xml_file):
        """Load <variable name="X"> entries, the first definition winning."""
        for node in root.findall("variable"):
            name = node.attrib.get("name")
            if name and node.find("*") is not None:
                self._keep_first("variable", self.variable_map, folder, name, node, xml_file,
                                 (node, xml_file))

    def _load_maps(self, root, folder, xml_file):
        """Load <map> entries, the last definition winning."""
        for node in root.findall("map"):
            self.map_defs[folder].append((node, xml_file))
            name = node.attrib.get("name")
            if name:
                self.map_map[folder][name] = (node, xml_file)

    def _load_includes(self, root, folder, xml_file, conditional=False):
        """Load named includes, the first definition winning, and <include file> ones in place."""
        for node in root.findall("include"):
            name = node.attrib.get("name")
            if name and node.find("*") is not None:
                definition = node.find("definition")
                params = get_params(node, "default")
                if node.find("param") is not None and definition is None:
                    self.shadowed_defs[folder].append({
                        "kind": "include without definition", "name": name, "file": xml_file,
                        "line": node.sourceline or 0,
                    })
                    continue
                self._keep_first("include", self.include_map, folder, name, node, xml_file,
                                 (node, params, xml_file))
            elif "file" in node.attrib:
                nested_conditional = conditional or "condition" in node.attrib
                self.update_includes(os.path.join(self.path, folder, node.attrib["file"]), folder,
                                     nested_conditional)

    def reload(self, *paths):
        """Reload the caches edits to the files affect, each once; include calls rebuilt on use."""
        self.include_usages = {}
        self._include_usages_built = False
        includes = colors_and_fonts = False
        for path in paths:
            folder = self.xml_folder_of(path)
            if folder in self.include_files:
                if os.path.normpath(path) in self.include_files[folder]:
                    includes = True
                else:
                    # an untracked file may be an include that just became parseable
                    root = get_root_from_file(path)
                    if root is not None and root.tag == "includes":
                        logger.info("Recovered include file detected: %s", path)
                        includes = True
            name = os.path.basename(path).lower()
            in_colors = os.path.basename(os.path.dirname(path)).lower() == "colors"
            if name == "font.xml" or (in_colors and name.endswith(".xml")):
                colors_and_fonts = True

        if includes:
            self.update_include_list()
        if colors_and_fonts:
            self._load_colors_and_fonts()

    def get_themes(self):
        """Get the theme names, one per folder under `themes`."""
        return [folder for folder in os.listdir(os.path.join(self.path, "themes"))]

    def get_constants(self, folder):
        """Get the constant names defined for the folder."""
        return list(self.constant_map.get(folder, {}).keys())

    def return_node(self, keyword=None, folder=None, kinds=None):
        """Look up a name in every definition kind, fonts first, or in those a caller picks."""
        if not keyword or not folder:
            return None

        lookup_name = keyword.split(',')[0] if ',' in keyword else keyword

        def wanted(kind):
            return kinds is None or kind in kinds

        if wanted("font") and folder in self.fonts:
            for node in self.fonts[folder]:
                if node["name"] == lookup_name:
                    return node

        includes_for_folder = self.include_map.get(folder, {})
        if wanted("include") and lookup_name in includes_for_folder:
            node, _params, file_path = includes_for_folder[lookup_name]
            return {
                "name": lookup_name,
                "content": node,
                "file": file_path,
                "line": node.sourceline if hasattr(node, 'sourceline') else 0,
                "type": node.tag
            }

        for kind, table in (("variable", self.variable_map), ("map", self.map_map),
                            ("default", self.default_map)):
            entries = table.get(folder, {})
            if wanted(kind) and lookup_name in entries:
                node, file_path = entries[lookup_name]
                return {
                    "name": lookup_name,
                    "content": node,
                    "file": file_path,
                    "line": node.sourceline if hasattr(node, 'sourceline') else 0,
                    "type": node.tag
                }

        for kind, table, sources in (("constant", self.constant_map, self.constant_source_map),
                                     ("expression", self.expression_map, self.expression_source_map)):
            if wanted(kind) and lookup_name in table.get(folder, {}):
                source = sources.get(folder, {}).get(lookup_name, (None, 0))
                return {
                    "name": lookup_name,
                    "type": kind,
                    "content": table[folder][lookup_name],
                    "file": source[0],
                    "line": source[1],
                }

        return None

    def lookup_skin_map(self, folder, map_name, key, _visited=None):
        """Look up a key: own entries, then the ref chain; the key itself on a miss."""
        visited = _visited or []
        if map_name in visited:
            logger.warning("Skin map '%s' has a circular ref chain", map_name)
            return key
        visited = visited + [map_name]

        entry = self.map_map.get(folder, {}).get(map_name)
        if entry is None:
            return key

        node, _file = entry
        for child in node.findall("entry"):
            if child.attrib.get("key") == key and child.text is not None:
                return child.text

        ref = node.attrib.get("ref")
        if ref:
            return self.lookup_skin_map(folder, ref, key, visited)
        return key
