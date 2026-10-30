"""Kodi skin model: the include maps, colors, fonts and resolver for one skin."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

from ..utils.expressions import resolve_params_in_text
from ..utils.files import check_paths, is_inside
from ..utils.infobool import condition_states
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



def _same_definition(a, b):
    """Whether two definition elements have the same text and attributes."""
    return b is not None and (a.text or "").strip() == (b.text or "").strip() and dict(a.attrib) == dict(b.attrib)


_PARAM_REF = re.compile(r"\$PARAM\[([^,\]]+)")


def _param_uses(include_node):
    """Yield (param, use) per $PARAM in the spliced body; forwards flag a bare $PARAM value."""
    definition = include_node.find("definition")
    body = definition if definition is not None else include_node
    for node in body.iterdescendants():
        if not isinstance(node.tag, str):
            continue
        parent = node.getparent()
        target = parent.get("content", "") if parent.tag == "include" else ""
        forward = node.get("name") if node.tag == "param" and target and "$" not in target else None
        texts = [(None, node.text or "")]
        texts += [(a, v) for a, v in node.attrib.items() if not a.startswith("_kdk_")]
        for attr, value in texts:
            if "$PARAM[" not in value:
                continue
            if forward and attr in (None, "value"):
                use = ("forward", target, forward,
                       resolve_params_in_text(value)[1] == "SINGLE_UNDEFINED")
            elif attr is None:
                use = ("tag", node.tag)
            else:
                use = ("attr", attr)
            for match in _PARAM_REF.finditer(value):
                yield match.group(1).strip(), use


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
        # each <default> per type with its include conditions; a setting can swap which one wins
        self.default_loads: dict[str, dict[str, list[tuple[Any, tuple[str, ...]]]]] = {}
        # files include calls name, which Kodi loads once a window resolves the call
        self.window_calls: dict[str, dict[str, list[str]]] = {}
        self.called_files: dict[str, list[str]] = {}

        self.include_usages: dict = {}
        self._include_usages_built = False

        self.update_include_list()
        self._load_colors_and_fonts()
        self.builtin_controls, self.builtin_ranges, self.builtin_filename_map = self._load_builtin_controls()

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
        """Build each include body's $PARAM roles: tag, attribute, forward to nested call, multi."""
        result = {}

        def mark(roles, pname, new_role):
            existing = roles.get(pname)
            if existing is None:
                roles[pname] = new_role
            elif existing == "multi" or existing == new_role:
                return
            else:
                roles[pname] = "multi"

        for folder, includes_for_folder in self.include_map.items():
            folder_result = {}
            for inc_name, (inc_node, _defaults, _file) in includes_for_folder.items():
                roles: dict = {}
                for pname, use in _param_uses(inc_node):
                    mark(roles, pname, use[:3])
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

    def include_params(self, folder, include_name):
        """Each param the include declares or uses, as (name, default, used directly, forwards)."""
        entry = self.include_map.get(folder, {}).get(include_name)
        if entry is None:
            return []
        node, defaults, _file = entry
        uses: dict[str, list] = {}
        for param, use in _param_uses(node):
            uses.setdefault(param, []).append(use)
        for param in defaults:
            uses.setdefault(param, [])
        rows = []
        for param, found in uses.items():
            default = defaults.get(param)
            forwards = []
            for use in found:
                if use[0] != "forward":
                    continue
                _, target, target_param, alone = use
                # what the target gets when a call leaves the param out; a default passes itself
                value = None
                if default is None and alone:
                    value = self._omitted_value(folder, target, target_param, {(include_name, param)})
                if (target, target_param, value) not in forwards:
                    forwards.append((target, target_param, value))
            direct = any(use[0] != "forward" for use in found)
            rows.append((param, default, direct, forwards))
        return rows

    def _omitted_value(self, folder, include_name, param, seen):
        """Value a param takes when a call omits it; None unless one default reaches every use."""
        entry = self.include_map.get(folder, {}).get(include_name)
        if entry is None or (include_name, param) in seen:
            return None
        node, defaults, _file = entry
        if param in defaults:
            return defaults[param]
        values = set()
        for found, use in _param_uses(node):
            if found != param:
                continue
            if use[0] != "forward" or not use[3]:
                return None
            values.add(self._omitted_value(folder, use[1], use[2], seen | {(include_name, param)}))
        return values.pop() if len(values) == 1 else None

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
        """Load Kodi's control ids and runtime ranges per window, plus filename to window name."""
        builtin_controls = {}
        builtin_ranges = {}
        filename_to_window = {}

        try:
            builtin_path = Path(__file__).parent.parent.parent / 'data' / 'kodi_builtin_controls.xml'

            if not builtin_path.exists():
                logger.warning("Built-in controls file not found: %s", builtin_path)
                return builtin_controls, builtin_ranges, filename_to_window

            root = get_root_from_file(str(builtin_path))
            if root is None:
                logger.warning("Failed to parse built-in controls file")
                return builtin_controls, builtin_ranges, filename_to_window

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

                for range_elem in window_elem.findall('range'):
                    upper = range_elem.get('to')
                    builtin_ranges.setdefault(window_name, []).append(
                        (int(range_elem.get('from', 0)), int(upper) if upper else None))

            logger.info("Loaded built-in controls for %d windows", len(builtin_controls))
            return builtin_controls, builtin_ranges, filename_to_window

        except Exception as e:
            logger.warning("Failed to load built-in controls: %s", e)
            return builtin_controls, builtin_ranges, filename_to_window

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
        """Update every folder's maps from its Includes.xml and called files, dropping the index."""
        start_time = time.time()
        logger.debug("update_include_list START")

        self.validation_index = None
        self._include_param_roles = None

        for folder in self.xml_folders:
            xml_folder = os.path.join(self.path, folder)
            paths = [os.path.join(xml_folder, "Includes.xml"),
                     os.path.join(xml_folder, "includes.xml")]
            self.include_files[folder] = []
            self.called_files[folder] = []

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
            self.default_loads[folder] = {}

            include_file = check_paths(paths)
            if include_file:
                self.update_includes(include_file, folder)
            else:
                logger.info("Could not find include file in %s", xml_folder)
            self._load_called_files(folder)

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

    def _called_files(self, root, folder):
        """Include files the tree's include calls name, which Kodi loads as it resolves a call."""
        if root is None:
            return []
        # a direct child of <includes> is a load, not a call
        calls = root.xpath("./*//include[@file]" if root.tag == "includes" else ".//include[@file]")
        folder_path = os.path.join(self.path, folder)
        return [os.path.normpath(os.path.join(folder_path, node.get("file")))
                for node in calls if "$" not in node.get("file")]

    def _load_called_files(self, folder):
        """Load the files the folder's windows and include files call, window calls scanned once."""
        if folder not in self.window_calls:
            self.window_calls[folder] = {}
            for rel in self.window_files.get(folder, []):
                path = os.path.normpath(os.path.join(self.path, folder, rel))
                root = get_root_from_file(path)
                if root is not None and root.tag != "includes":
                    self.window_calls[folder][path] = self._called_files(root, folder)
        queue = self.called_files[folder]
        queue.extend(called for calls in self.window_calls[folder].values() for called in calls)
        # each load queues the calls in its own bodies
        for called in queue:
            if called not in self.include_files[folder]:
                self.update_includes(called, folder)

    def update_includes(self, xml_file, folder, conditions=()):
        """Update maps from an include file and nested ones, noting if conditional; queue calls."""
        xml_file = os.path.normpath(xml_file)
        if not os.path.exists(xml_file) or not is_inside(xml_file, self.path):
            logger.info("Could not find include file %s", xml_file)
            return None

        root = get_root_from_file(xml_file)
        if root is None:
            return []

        self.include_files[folder].append(xml_file)
        self.called_files.setdefault(folder, []).extend(self._called_files(root, folder))
        if conditions:
            self.conditional_files[folder].add(xml_file)

        self._load_defaults(root, folder, xml_file, conditions)
        self._load_constants(root, folder, xml_file)
        self._load_expressions(root, folder, xml_file)
        self._load_variables(root, folder, xml_file)
        self._load_includes(root, folder, xml_file, conditions)
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

    def _load_defaults(self, root, folder, xml_file, conditions=()):
        """Load <default type="X"> entries, the first winning, each recorded with its conditions."""
        for node in root.findall("default"):
            control_type = node.attrib.get("type")
            if control_type and node.find("*") is not None:
                self._keep_first("default", self.default_map, folder, control_type, node, xml_file,
                                 (node, xml_file))
                self.default_loads[folder].setdefault(control_type, []).append((node, conditions))

    def settled_default_tags(self, folder):
        """Tags of each conditional default whose kept value holds in every setting state."""
        conditional = {control_type: loads for control_type, loads in self.default_loads.get(folder, {}).items()
                       if loads[0][1]}
        states = condition_states([c for loads in conditional.values() for _, chain in loads for c in chain])
        settled = {}
        for control_type, loads in conditional.items():
            kept = loads[0][0]
            winners = [next((node for node, chain in loads if all(state[c] for c in chain)), None)
                       for state in states or []]
            tags = {c.tag for c in kept if isinstance(c.tag, str)} if winners else set()
            settled[control_type] = {tag for tag in tags if all(
                w is not None and _same_definition(kept.find(tag), w.find(tag)) for w in winners)}
        return settled

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

    def _load_includes(self, root, folder, xml_file, conditions=()):
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
                nested = conditions + ((node.attrib["condition"],) if "condition" in node.attrib else ())
                self.update_includes(os.path.join(self.path, folder, node.attrib["file"]), folder, nested)

    def reload(self, *paths):
        """Reload the caches edits to the files affect, each once; include usages rebuilt on use."""
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
                    elif root is not None and folder in self.window_calls:
                        calls = self._called_files(root, folder)
                        if calls != self.window_calls[folder].get(os.path.normpath(path), []):
                            self.window_calls[folder][os.path.normpath(path)] = calls
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
