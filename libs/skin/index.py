"""
Validation index builder for Kodi skin validation.

This module provides the ValidationIndexBuilder class that builds a comprehensive
validation index by scanning all XML files in a skin and extracting:
- Font definitions and usages
- Label references (localized strings)
- Image paths
- Control ID definitions and references
"""

from __future__ import annotations
from typing import TYPE_CHECKING
import copy
import os
import re
import json
import time
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

if TYPE_CHECKING:
    pass

from .. import utils

logger = logging.getLogger(__name__)

_LABEL_TAGS = frozenset(['label', 'altlabel', 'label2', 'hinttext'])
_LOCALIZE_PATTERN = re.compile(r"\$LOCALIZE\[([0-9].*?)\]")

_INFOLABEL_WHITELIST = None
_CONTROL_REGEX_PATTERN = None
_EXCLUDED_FUNCTIONS = None


def _load_infolabel_whitelist():
    """Load InfoLabel function whitelist from data file."""
    global _INFOLABEL_WHITELIST
    if _INFOLABEL_WHITELIST is not None:
        return _INFOLABEL_WHITELIST

    whitelist_path = Path(__file__).parent.parent.parent / 'data' / 'kodi_infolabel_functions.json'

    try:
        with open(whitelist_path, 'r', encoding='utf-8') as f:
            _INFOLABEL_WHITELIST = json.load(f)
            logger.debug(f"Loaded InfoLabel whitelist from {whitelist_path}")
    except Exception as e:
        logger.warning(f"Failed to load InfoLabel whitelist: {e}")
        _INFOLABEL_WHITELIST = {'functions_with_integer_params': [], 'standalone_functions_with_integers': []}

    return _INFOLABEL_WHITELIST


def _build_control_regex():
    """
    Build control ID regex with InfoLabel function exclusions.

    Generates a regex that matches control ID references in conditions,
    but excludes InfoLabel functions that take integer parameters
    (like Container.Position(5) where 5 is an index, not a control ID).

    Returns:
        Regex pattern string for control ID references
    """
    global _CONTROL_REGEX_PATTERN, _EXCLUDED_FUNCTIONS
    if _CONTROL_REGEX_PATTERN is not None and _EXCLUDED_FUNCTIONS is not None:
        return _CONTROL_REGEX_PATTERN

    whitelist = _load_infolabel_whitelist()

    # Build list of function names to exclude (these take integer parameters but are not control IDs)
    # E.g., Container.Position(5), Window.IsVisible(10), ListItem(5)
    # Window.* functions based on Kodi source: xbmc/GUIInfoManager.cpp lines 7971-7979
    # All entries lowercase — matched case-insensitively at lookup time
    excluded_functions = {
        'window', 'window.is', 'window.isactive', 'window.isvisible', 'window.ismedia',
        'window.isdialogtopmost', 'window.ismodaldialogtopmost', 'window.previous', 'window.next',
        'dialog.close'
    }

    for func_entry in whitelist.get('functions_with_integer_params', []):
        function = func_entry.get('function', '')
        for param in func_entry.get('params', []):
            excluded_functions.add(param.lower())
            excluded_functions.add(f"{function}.{param}".lower())

    for func_entry in whitelist.get('standalone_functions_with_integers', []):
        excluded_functions.add(func_entry['function'].lower())

    excluded_functions.add('listitem')

    _CONTROL_REGEX_PATTERN = r'(\w+(?:\.\w+)?)\(([0-9]+)\)'

    logger.debug(f"Built control regex with {len(excluded_functions)} excluded functions")

    _EXCLUDED_FUNCTIONS = excluded_functions

    return _CONTROL_REGEX_PATTERN


class SkinIndex:
    """
    Builds comprehensive validation index for Kodi skin.

    Scans all XML files in skin and extracts metadata for validation:
    - Font definitions and usages
    - Label references (localized strings)
    - Image paths and texture pack detection
    - Control ID definitions and references
    """

    def __init__(self, skin):
        """
        Initialize index builder.

        Args:
            skin: Skin instance with all necessary data
        """
        self.skin = skin
        self.skin_path = skin.path
        self.xml_folders = skin.xml_folders
        self.include_maps = None  # Not used in new implementation

    def build_validation_index(self, progress_callback=None):
        """
        Build comprehensive validation index by parsing all XML files once.
        Fast uncached build (~1 second) thanks to Kodi-aligned architecture.

        Args:
            progress_callback: Optional callback function(message: str) for progress updates

        Returns:
            dict: Validation index with fonts, labels, IDs, etc.
        """
        if progress_callback:
            progress_callback("Building validation index...")

        index = {
            'fonts_defined': {},   # {folder: {font_name: {'file': path, 'line': num, ...}}}
            'fonts_used': {},      # {folder: {font_name: [{'file': path, 'line': num}]}}
            'labels_used': {},     # {folder: {label_id: [{'file': path, 'line': num, 'type': tag}]}}
            'labels_untranslated': [],  # [{message, file, line, ...}]
            'ids_defined': {},     # {folder: {id: {'file': path, 'line': num, 'type': control_type}}}
            'ids_referenced': {},  # {folder: {id: [{'file': path, 'line': num}]}}
            'window_ids': {},      # {folder: [id1, id2, ...]}
            'view_ids': {},        # {folder: set(view_id1, view_id2)} - IDs of list/panel/wraplist controls
            'window_includes': {}, # {folder: {window_file: [inc_names]}}
            'window_base_ids': {}, # {folder: {window_file: {id1, id2}}} - IDs from raw XML
            'window_expanded_ids': {},  # {folder: {window_file: set(ids)}} - IDs from resolved tree
            # Track which files are include files (from Kodi's <include file="..."/> declarations)
            'include_files': {},   # {folder: [file basenames]} - files loaded via Includes.xml
            # Variables metadata (for VariableCheck optimization)
            'variables_defined': {},  # {folder: {var_name: {'file': path, 'line': num}}}
            'images_referenced': {},  # {folder: {image_path: [{'file': str, 'line': int, 'tag': str}]}}
            # Built-in controls from Kodi C++ code
            'builtin_controls': self.skin.builtin_controls if hasattr(self.skin, 'builtin_controls') else {},
            'builtin_filename_map': self.skin.builtin_filename_map if hasattr(self.skin, 'builtin_filename_map') else {},
        }

        for folder in self.skin.xml_folders:
            index['fonts_defined'][folder] = {}
            index['fonts_used'][folder] = {}
            index['labels_used'][folder] = {}
            index['ids_defined'][folder] = {}
            index['ids_referenced'][folder] = {}
            index['window_ids'][folder] = []
            index['view_ids'][folder] = set()
            index['window_includes'][folder] = {}
            index['window_base_ids'][folder] = {}
            index['window_expanded_ids'][folder] = {}
            # Copy include files list from skin.include_files (loaded via Includes.xml)
            # Convert full paths to basenames for easier comparison
            include_file_paths = getattr(self.skin, 'include_files', {}).get(folder, [])
            index['include_files'][folder] = [os.path.basename(p) for p in include_file_paths]
            index['variables_defined'][folder] = {}
            index['images_referenced'][folder] = {}

        if hasattr(self.skin, 'fonts') and self.skin.fonts:
            for folder, font_list in self.skin.fonts.items():
                for font_data in font_list:
                    font_name = font_data.get('name', '').strip()
                    if font_name:
                        index['fonts_defined'][folder][font_name] = {
                            'file': font_data.get('file', ''),
                            'line': font_data.get('line', 0),
                            'filename': font_data.get('filename', ''),
                            'size': font_data.get('size', '')
                        }

        if hasattr(self.skin, 'variable_map') and self.skin.variable_map:
            for folder, variables_dict in self.skin.variable_map.items():
                for var_name, (node, file_path) in variables_dict.items():
                    index['variables_defined'][folder][var_name] = {
                        'file': file_path,
                        'line': getattr(node, 'sourceline', 0) or 0,
                        'name': var_name
                    }

        file_count = 0
        total_files = sum(len(files) for files in self.skin.window_files.values())

        for folder in self.skin.xml_folders:
            if progress_callback:
                progress_callback(f"Loading includes for {folder}...")
            include_map = self.skin.build_include_map(folder)

            if progress_callback:
                progress_callback(f"Processing {len(self.skin.window_files.get(folder, []))} files in {folder}...")

            max_workers = self._get_optimal_workers()
            file_paths = [
                os.path.join(self.skin.path, folder, xml_file)
                for xml_file in self.skin.window_files.get(folder, [])
            ]


            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_path = {
                    executor.submit(self._process_window_file, path, folder): path
                    for path in file_paths
                }

                pending_futures = set(future_to_path.keys())
                last_progress_time = time.time()
                heartbeat_interval = 2.0  # Show status every 2 seconds

                while pending_futures:
                    done, pending_futures = wait(pending_futures, timeout=heartbeat_interval, return_when=FIRST_COMPLETED)

                    for future in done:
                        file_count += 1
                        path = future_to_path[future]

                        if progress_callback and (file_count % 3 == 0 or file_count == len(file_paths)):
                            xml_file = os.path.basename(path)
                            progress_callback(f"Parsed {xml_file} ({file_count}/{total_files})")
                            last_progress_time = time.time()

                        results = future.result()
                        if results:
                            for font_name, usages in results['fonts_used'][folder].items():
                                if font_name not in index['fonts_used'][folder]:
                                    index['fonts_used'][folder][font_name] = []
                                index['fonts_used'][folder][font_name].extend(usages)

                            for label_id, usages in results['labels_used'][folder].items():
                                if label_id not in index['labels_used'][folder]:
                                    index['labels_used'][folder][label_id] = []
                                index['labels_used'][folder][label_id].extend(usages)

                            index['labels_untranslated'].extend(results['labels_untranslated'])

                            index['ids_defined'][folder].update(results['ids_defined'][folder])
                            for ref_id, usages in results['ids_referenced'][folder].items():
                                if ref_id not in index['ids_referenced'][folder]:
                                    index['ids_referenced'][folder][ref_id] = []
                                index['ids_referenced'][folder][ref_id].extend(usages)

                            for window_id in results['window_ids'][folder]:
                                if window_id not in index['window_ids'][folder]:
                                    index['window_ids'][folder].append(window_id)

                            window_file = os.path.basename(path)
                            index['window_includes'][folder][window_file] = results['window_includes']
                            index['window_base_ids'][folder][window_file] = results['base_ids']

                            if 'view_ids' in results:
                                index['view_ids'][folder].update(results['view_ids'])

                            for img_path, usages in results.get('images_referenced', {}).get(folder, {}).items():
                                if img_path not in index['images_referenced'][folder]:
                                    index['images_referenced'][folder][img_path] = []
                                index['images_referenced'][folder][img_path].extend(usages)

                    if not done and progress_callback:
                        elapsed = time.time() - last_progress_time
                        if elapsed >= heartbeat_interval:
                            in_progress_files = [os.path.basename(future_to_path[f]) for f in list(pending_futures)[:3]]
                            files_str = ", ".join(in_progress_files)
                            remaining = len(pending_futures)

                            if remaining > 3:
                                progress_callback(f"Processing {files_str}, +{remaining-3} more ({file_count}/{total_files} done)")
                            else:
                                progress_callback(f"Processing {files_str} ({file_count}/{total_files} done)")
                            last_progress_time = time.time()

            if progress_callback:
                progress_callback(f"Processing {len(include_map)} include definitions...")
            include_count = 0
            total_includes = len(include_map)
            for inc_name, inc_tuple in include_map.items():
                include_count += 1
                if progress_callback and total_includes > 200:
                    if include_count % 25 == 0:
                        progress_callback(f"Processing includes... ({include_count}/{total_includes})")
                if isinstance(inc_tuple, tuple) and len(inc_tuple) >= 3:
                    inc_node, _default_params, file_path = inc_tuple
                elif isinstance(inc_tuple, tuple) and len(inc_tuple) == 2:
                    inc_node, _default_params = inc_tuple
                    file_path = getattr(inc_node, 'file', None)
                else:
                    inc_node = inc_tuple
                    file_path = getattr(inc_node, 'file', None)

                if isinstance(inc_node, tuple):
                    continue

                if hasattr(inc_node, 'node'):
                    inc_obj = inc_node
                else:
                    from ..skin.include import SkinInclude
                    definition = inc_node.find("definition")
                    include_body = definition if definition is not None else inc_node
                    inc_obj = SkinInclude(node=include_body, file=file_path)

                if inc_obj and file_path:
                    try:
                        if hasattr(inc_obj, 'cached_fonts'):
                            for font_name, font_data in inc_obj.cached_fonts.items():  # type: ignore[attr-defined]
                                if font_name not in index['fonts_used'][folder]:
                                    index['fonts_used'][folder][font_name] = []
                                index['fonts_used'][folder][font_name].append(font_data)

                        if hasattr(inc_obj, 'cached_labels'):
                            for label_id, usages in inc_obj.cached_labels.items():  # type: ignore[attr-defined]
                                if label_id not in index['labels_used'][folder]:
                                    index['labels_used'][folder][label_id] = []
                                index['labels_used'][folder][label_id].extend(usages)
                    except Exception as e:
                        logger.debug("Failed to process include %s: %s", inc_name, e)

            if progress_callback:
                progress_callback(f"Processed {include_count} include definitions")

            index['include_to_windows'] = {}
            for folder in self.skin.xml_folders:
                index['include_to_windows'][folder] = {}
                for window_file, inc_usages in index['window_includes'].get(folder, {}).items():
                    for inc_usage in inc_usages:
                        inc_name = inc_usage.get('name') if isinstance(inc_usage, dict) else inc_usage
                        if inc_name:
                            if inc_name not in index['include_to_windows'][folder]:
                                index['include_to_windows'][folder][inc_name] = []
                            if window_file not in index['include_to_windows'][folder][inc_name]:
                                index['include_to_windows'][folder][inc_name].append(window_file)

        # Resolve each window and extract IDs from the resolved tree.
        # This replaces the old manual _resolve_include_ids_recursive() approach
        # with actual include expansion, giving accurate ID sets.
        # Runs sequentially (resolver's _source_file is not thread-safe).
        if hasattr(self.skin, 'resolver') and self.skin.resolver:
            if progress_callback:
                progress_callback("Resolving windows for ID extraction...")
            resolve_count = 0
            for folder in self.skin.xml_folders:
                basenames = list(index['window_base_ids'].get(folder, {}).keys())
                for basename in basenames:
                    path = os.path.join(self.skin.path, folder, basename)
                    root = utils.get_root_from_file(path)
                    if root is None:
                        index['window_expanded_ids'][folder][basename] = \
                            index['window_base_ids'][folder].get(basename, set())
                        continue

                    if utils.tree_needs_expansion(root):
                        try:
                            resolved = copy.deepcopy(root)
                            self.skin.resolver.resolve(resolved, folder)
                        except Exception:
                            logger.debug("Resolution failed for %s, using base IDs", basename)
                            index['window_expanded_ids'][folder][basename] = \
                                index['window_base_ids'][folder].get(basename, set())
                            continue
                    else:
                        resolved = root

                    expanded_ids = set()
                    for node in resolved.iter('control'):
                        ctrl_id = node.get('id')
                        if ctrl_id and not utils.is_dynamic_expression(ctrl_id):
                            expanded_ids.add(utils.normalize_control_id(ctrl_id))
                    for node in resolved.iter('item'):
                        item_id = node.get('id')
                        if item_id:
                            expanded_ids.add(utils.normalize_control_id(item_id))

                    # View IDs from resolved tree (parameterized types now concrete)
                    for node in resolved.iter('control'):
                        ctrl_id = node.get('id')
                        if ctrl_id and node.find('viewtype') is not None:
                            index['view_ids'][folder].add(utils.normalize_control_id(ctrl_id))

                    index['window_expanded_ids'][folder][basename] = expanded_ids
                    resolve_count += 1

                    if progress_callback and resolve_count % 10 == 0:
                        progress_callback(f"Resolved {resolve_count} windows...")

            logger.info("Resolved %d windows for ID extraction", resolve_count)

        if progress_callback:
            progress_callback(f"Index built successfully ({file_count} files processed)")
        logger.info("✓ Validation index built successfully (%d files + includes processed)", file_count)

        # Pre-check image files (eliminates I/O during ImageCheck validation)
        if 'images_referenced' in index:
            self._check_image_files(index, progress_callback)

        # Pre-check font files (eliminates I/O during FontCheck validation)
        if 'fonts_defined' in index:
            self._check_font_files(index, progress_callback)

        return index

    def _get_optimal_workers(self):
        """
        Calculate optimal thread count for I/O-bound XML parsing.

        For I/O-bound tasks, more threads than cores is beneficial since threads
        spend most time waiting for disk I/O. ThreadPoolExecutor can overlap these waits.

        Returns:
            int: Optimal number of worker threads
        """
        cpu_count = os.cpu_count() or 1

        # Adaptive sizing based on CPU capabilities
        if cpu_count == 1:
            return 3  # Still helps with I/O overlap on single-core
        elif cpu_count == 2:
            return 4
        else:
            return min(cpu_count + 4, 8)  # Cap at 8 to avoid overhead

    def _process_window_file(self, path, folder):
        """
        Process single window file (thread-safe extraction).

        Called by ThreadPoolExecutor workers. Must not mutate shared state.

        Returns:
            dict: Local results with fonts, labels, IDs or None if failed
        """
        try:
            if "script-skinshortcuts-includes.xml" in path.lower():
                return None

            root = utils.get_root_from_file(path)
            if root is None:
                return None

            results = {
                'path': path,
                'fonts_used': {folder: {}},
                'labels_used': {folder: {}},
                'labels_untranslated': [],
                'ids_defined': {folder: {}},
                'ids_referenced': {folder: {}},
                'window_ids': {folder: []},  # Window IDs extracted from root element
                'window_includes': [],  # List of include usages: [{'name': str, 'params': dict}]
                'base_ids': set(),       # IDs defined directly in window (from raw XML)
                'view_ids': set()        # View control IDs (detected by <viewtype> tag)
            }

            if 'id' in root.attrib:
                window_id = root.attrib['id']
                if window_id:
                    window_id = utils.normalize_control_id(window_id)
                    results['window_ids'][folder].append(window_id)

            self._extract_fonts_from_xml(root, path, folder, results)
            self._extract_labels_from_xml(root, path, folder, results)
            self._extract_images_from_xml(root, path, folder, results)

            for elem in root.iter('include'):
                inc_name = None

                if elem.text and elem.text.strip():
                    inc_name = elem.text.strip()
                elif 'content' in elem.attrib:
                    inc_name = elem.attrib['content']

                if inc_name:
                    results['window_includes'].append({'name': inc_name})

            # This includes both <control> and <item> elements (list items in <content> blocks)
            for elem in root.iter('control'):
                ctrl_id = elem.get('id')
                if ctrl_id:
                    ctrl_id = utils.normalize_control_id(ctrl_id)
                    results['base_ids'].add(ctrl_id)

            # These are list item IDs that can be referenced with Container().HasFocus()
            for item_elem in root.iter('item'):
                item_id = item_elem.get('id')
                if item_id:
                    item_id = utils.normalize_control_id(item_id)
                    results['base_ids'].add(item_id)

            has_controls = root.find('.//control[@id]') is not None

            self._extract_id_references_from_xml(root, path, folder, results)

            if has_controls:
                self._extract_id_definitions_from_xml(root, path, folder, results)

            return results
        except Exception as e:
            logger.debug("Failed to process %s: %s", os.path.basename(path), e)
            return None

    def build_include_usages(self, progress_callback=None):
        """
        Scan all window/include files to track where includes are USED with what parameters.

        This enables context-aware variable validation where variables containing $PARAM
        can be resolved with actual parameter values from usage sites.

        Example:
            Variable defined as: <variable name="Label_Title_C$PARAM[id]3">
            Used in include with: <param name="id">50</param>
            Resolution: Label_Title_C$PARAM[id]3 → Label_Title_C503

        Args:
            progress_callback: Optional callback function(message: str)
        """
        if self.skin._include_usages_built:
            return  # Already built

        for folder in self.skin.xml_folders:
            if folder not in self.skin.include_usages:
                self.skin.include_usages[folder] = {}

            files_to_scan = self.skin.window_files.get(folder, [])

            for xml_file in files_to_scan:
                file_path = os.path.join(self.skin.path, folder, xml_file)
                root = utils.get_root_from_file(file_path)
                if root is None:
                    continue

                for elem in root.iter('include'):
                    inc_name = None
                    params = {}

                    if elem.text and elem.text.strip():
                        inc_name = elem.text.strip()
                    elif 'content' in elem.attrib:
                        inc_name = elem.attrib['content']
                        for param_elem in elem.findall('param'):
                            param_name = param_elem.get('name')
                            param_value = (param_elem.text or '').strip()
                            if param_name and param_value:
                                params[param_name] = param_value

                    if inc_name:
                        if inc_name not in self.skin.include_usages[folder]:
                            self.skin.include_usages[folder][inc_name] = []

                        self.skin.include_usages[folder][inc_name].append({
                            'params': params,
                            'file': file_path,
                            'line': getattr(elem, 'sourceline', 0)
                        })

        self.skin._include_usages_built = True

    def _extract_fonts_from_xml(self, root, path, folder, index):
        """Extract font usage from an XML file."""
        for node in root.xpath(".//font"):
            font_name = (node.text or "").strip()
            if font_name and not utils.is_dynamic_expression(font_name):
                if font_name not in index['fonts_used'][folder]:
                    index['fonts_used'][folder][font_name] = []
                index['fonts_used'][folder][font_name].append({
                    'file': path,
                    'line': getattr(node, 'sourceline', 0) or 0
                })

    def _extract_labels_from_xml(self, root, path, folder, index):
        """Extract label usage from an XML file."""
        for element in root.iter():
            if element.tag not in _LABEL_TAGS:
                continue

            text = element.text
            if not text:
                continue

            for match in _LOCALIZE_PATTERN.finditer(text):
                label_id = match.group(1)
                if label_id not in index['labels_used'][folder]:
                    index['labels_used'][folder][label_id] = []
                index['labels_used'][folder][label_id].append({
                    'file': path,
                    'line': getattr(element, 'sourceline', 0) or 0,
                    'type': element.tag
                })

            if text.isdigit():
                label_id = text
                if label_id not in index['labels_used'][folder]:
                    index['labels_used'][folder][label_id] = []
                index['labels_used'][folder][label_id].append({
                    'file': path,
                    'line': getattr(element, 'sourceline', 0) or 0,
                    'type': element.tag
                })

            elif (
                len(text) > 2
                and not text.endswith(".xml")
                and text[0].isalpha()
                and not text.startswith("$")
                and "$INFO[" not in text
                and "$VAR[" not in text
                and "$PARAM[" not in text
                and "$NUMBER[" not in text
                and "$ADDON[" not in text
            ):
                index['labels_untranslated'].append({
                    'name': text,
                    'type': element.tag,
                    'file': path,
                    'identifier': text,
                    'message': f"Label in <{element.tag}> not translated: {text}",
                    'line': getattr(element, 'sourceline', 0) or 0
                })

    def _extract_images_from_xml(self, root, path, folder, index):
        """Extract image references from an XML file (element text + attributes)."""
        image_tags = frozenset(['texture', 'icon', 'thumb', 'bordertexture', 'alttexture'])
        # Always image paths regardless of parent tag
        universal_attrs = ('diffuse', 'texturefocus', 'texturenofocus')
        # Only image paths on texture elements (fallback on <label> is text, not an image)
        texture_only_attrs = ('fallback', 'texture', 'thumb', 'icon')

        if 'images_referenced' not in index:
            index['images_referenced'] = {}
        if folder not in index['images_referenced']:
            index['images_referenced'][folder] = {}

        def _track(image_path, node, attr=None):
            if not image_path or utils.is_dynamic_expression(image_path):
                return
            if image_path.startswith('special://skin/'):
                image_path = image_path[len('special://skin/'):]
            elif image_path.startswith(('special://', 'resource://')):
                return
            low = image_path.lower()
            if any(m in low for m in ('$info[', '$var[', '$escinfo[', '$escvar[',
                                       '$param[', '$addon[',
                                       'plugin://', 'http://', 'https://')):
                return
            if image_path not in index['images_referenced'][folder]:
                index['images_referenced'][folder][image_path] = []
            entry = {
                'file': path,
                'line': getattr(node, 'sourceline', 0) or 0,
                'tag': node.tag
            }
            if attr:
                entry['attr'] = attr
            index['images_referenced'][folder][image_path].append(entry)

        for node in root.iter():
            tag_low = node.tag.lower() if isinstance(node.tag, str) else ''
            is_texture_tag = tag_low in image_tags
            if is_texture_tag and node.text:
                _track(node.text.strip(), node)
            for attr in universal_attrs:
                val = node.attrib.get(attr)
                if val:
                    _track(val.strip(), node, attr)
            # Texture-only attrs (fallback on <label> is text, not an image)
            if is_texture_tag:
                for attr in texture_only_attrs:
                    val = node.attrib.get(attr)
                    if val:
                        _track(val.strip(), node, attr)

    def _check_image_files(self, index, progress_callback=None):
        """
        Check existence of all referenced image files in the filesystem.
        Pre-validates all images during index build to eliminate I/O during ImageCheck.

        This matches ImageCheck's logic but runs once during index build instead of
        repeatedly during validation.

        Args:
            index: Validation index containing 'images_referenced'
            progress_callback: Optional callback for progress updates
        """
        if 'images_referenced' not in index:
            return

        if progress_callback:
            progress_callback("Checking image files on disk...")

        def build_fs_index(root_dir):
            """Build case-insensitive filesystem index for image lookups."""
            exact_relpaths = set()
            cf_rel_to_exact = {}  # case-folded relative path -> exact path
            cf_base_to_relpaths = {}  # case-folded basename -> list of exact paths

            search_dirs = [
                root_dir,
                os.path.join(root_dir, "media"),
                os.path.join(root_dir, "resources", "media"),
                os.path.join(root_dir, "extras"),
                os.path.join(root_dir, "images"),
                os.path.join(root_dir, "textures"),
                os.path.join(root_dir, "fonts"),
            ]

            for search_dir in search_dirs:
                if not os.path.isdir(search_dir):
                    continue
                for dirpath, _, files in os.walk(search_dir):
                    for filename in files:
                        full_path = os.path.join(dirpath, filename)
                        try:
                            rel_path = os.path.relpath(full_path, root_dir)
                        except Exception:
                            rel_path = os.path.basename(full_path)

                        rel_path = rel_path.replace("\\", "/")
                        exact_relpaths.add(rel_path)

                        cf_rel = rel_path.casefold()
                        if cf_rel not in cf_rel_to_exact:
                            cf_rel_to_exact[cf_rel] = rel_path

                        basename = os.path.basename(rel_path)
                        cf_base = basename.casefold()
                        if cf_base not in cf_base_to_relpaths:
                            cf_base_to_relpaths[cf_base] = set()
                        cf_base_to_relpaths[cf_base].add(rel_path)

            return exact_relpaths, cf_rel_to_exact, cf_base_to_relpaths

        exact_relpaths, cf_rel_to_exact, cf_base_to_relpaths = build_fs_index(self.skin.path)
        logger.info(f"  → Indexed {len(exact_relpaths)} files in media directories")
        has_packed_textures = self._detect_textures_xbt()
        if has_packed_textures:
            logger.info("  → Textures.xbt detected - missing images may be in archive")

        def normalize_ref(val: str) -> str:
            """Normalize image reference to relative path."""
            v = (val or "").strip().replace("\\", "/")

            if v.startswith("special://skin/"):
                v = v[len("special://skin/"):]

            while v.startswith("./") or v.startswith("/"):
                v = v[1:]

            known_roots = (
                "media/", "resources/media/", "extras/",
                "images/", "textures/", "fonts/"
            )
            if not any(v.lower().startswith(r) for r in known_roots):
                v = "media/" + v

            return v

        def classify_path(val_norm: str):
            """
            Classify image path existence.
            Returns: (status, detail)
            - exact: File exists with exact case
            - case_mismatch: File exists but different case (detail = correct path)
            - wrong_path: File exists elsewhere (detail = list of correct paths)
            - missing: File not found
            """
            if val_norm in exact_relpaths:
                return "exact", None

            cf_rel = val_norm.casefold()
            if cf_rel in cf_rel_to_exact:
                return "case_mismatch", cf_rel_to_exact[cf_rel]

            cf_base = os.path.basename(val_norm).casefold()
            candidates = sorted(cf_base_to_relpaths.get(cf_base, []))
            if candidates:
                return "wrong_path", candidates

            return "missing", None

        index['image_files_checked'] = {}
        index['has_packed_textures'] = has_packed_textures

        total_images = sum(
            len(imgs) for folder_imgs in index['images_referenced'].values()
            for imgs in folder_imgs.values()
        )
        checked_count = 0

        for folder, images_dict in index['images_referenced'].items():
            index['image_files_checked'][folder] = {}

            for image_path, usages in images_dict.items():
                checked_count += 1

                if progress_callback and total_images > 100 and checked_count % 50 == 0:
                    progress_callback(f"Checking images... ({checked_count}/{total_images})")

                normalized = normalize_ref(image_path)
                status, detail = classify_path(normalized)

                index['image_files_checked'][folder][image_path] = {
                    'status': status,  # exact, case_mismatch, wrong_path, missing
                    'detail': detail,  # Correct path or candidates
                    'normalized': normalized,  # Normalized path used for checking
                }

        logger.info(f"  → Checked {checked_count} unique image references")
    def _detect_textures_xbt(self):
        """
        Detect if skin uses packed textures (Textures.xbt).

        Returns:
            bool: True if Textures.xbt exists
        """
        xbt_locations = [
            os.path.join(self.skin.path, 'media', 'Textures.xbt'),
            os.path.join(self.skin.path, 'resources', 'media', 'Textures.xbt'),
            os.path.join(self.skin.path, 'textures', 'Textures.xbt'),
        ]

        for xbt_path in xbt_locations:
            if os.path.exists(xbt_path):
                return True

        return False

    def _check_font_files(self, index, progress_callback=None):
        """
        Check existence of all font files referenced in font definitions.
        Pre-validates font files during index build to eliminate I/O during FontCheck.

        Note: Only checks skin fonts directory, not Kodi core fonts (which require
        runtime settings). FontCheck will still check core fonts at validation time.

        Args:
            index: Validation index containing 'fonts_defined'
            progress_callback: Optional callback for progress updates
        """
        if 'fonts_defined' not in index:
            return

        if progress_callback:
            progress_callback("Checking font files on disk...")
        logger.info("Pre-checking font file existence...")

        skin_fonts_dir = os.path.join(self.skin.path, "fonts")
        skin_files = {}  # {casefold_name: actual_name}

        if os.path.isdir(skin_fonts_dir):
            try:
                for filename in os.listdir(skin_fonts_dir):
                    file_path = os.path.join(skin_fonts_dir, filename)
                    if os.path.isfile(file_path):
                        skin_files[filename.casefold()] = filename
            except Exception as e:
                logger.warning(f"Failed to list font files: {e}")

        logger.info(f"  → Indexed {len(skin_files)} font files in fonts/ directory")

        index['font_files_checked'] = {}

        checked_count = 0

        for folder, fonts_dict in index['fonts_defined'].items():
            index['font_files_checked'][folder] = {}

            for font_name, font_info in fonts_dict.items():
                checked_count += 1
                filename = font_info.get('filename', '').strip()

                if not filename:
                    index['font_files_checked'][folder][font_name] = {
                        'status': 'no_filename',
                        'detail': None
                    }
                    continue

                if utils.is_dynamic_expression(filename):
                    index['font_files_checked'][folder][font_name] = {
                        'status': 'dynamic',
                        'detail': None
                    }
                    continue

                rel_path = filename.replace("\\", "/").strip()
                basename = os.path.basename(rel_path)

                actual_filename = None
                status = 'missing'
                detail = None

                if "/" not in rel_path:
                    actual_filename = skin_files.get(basename.casefold())
                    if actual_filename:
                        if actual_filename != basename:
                            status = 'case_mismatch'
                            detail = actual_filename
                        else:
                            status = 'exact'
                else:
                    full_path = os.path.join(skin_fonts_dir, rel_path)
                    if os.path.isfile(full_path):
                        actual_filename = os.path.basename(full_path)
                        if actual_filename != basename:
                            status = 'case_mismatch'
                            detail = actual_filename
                        else:
                            status = 'exact'

                index['font_files_checked'][folder][font_name] = {
                    'status': status,  # exact, case_mismatch, missing, no_filename, dynamic
                    'detail': detail,  # Actual filename if case mismatch
                    'filename': filename,  # Original filename from Font.xml
                }

        logger.info(f"  → Checked {checked_count} font file references")

    def _extract_id_definitions_from_xml(self, root, path, folder, index):
        """Extract control and window ID definitions from an XML file."""
        control_tags = {
            "button", "edit", "fadelabel", "fixedlist", "group", "grouplist",
            "image", "label", "list", "mover", "multiimage", "panel", "progress",
            "radiobutton", "rss", "scrollbar", "selectbutton", "slider",
            "spincontrol", "spincontrolex", "textbox", "togglebutton",
            "videowindow", "visualisation", "wraplist", "epggrid", "ranges",
            "sliderex", "panelcontainer", "gamewindow"
        }

        if "id" in root.attrib:
            window_id = root.attrib["id"]
            if window_id not in index['window_ids'][folder]:
                index['window_ids'][folder].append(window_id)

        # View control types that users check with Control.IsVisible()
        view_types = {'list', 'panel', 'fixedlist', 'wraplist', 'epggrid'}

        for node in root.iter():
            tag = node.tag.lower()

            if "id" in node.attrib:
                control_id = node.attrib["id"]

                if utils.is_dynamic_expression(control_id):
                    continue

                normalized_id = utils.normalize_control_id(control_id)

                # Check if this is a view control (has <viewtype> child)
                # This is more reliable than checking type attribute (which can be $PARAM[])
                is_view = False
                if tag == "control" or tag in view_types:
                    viewtype_elem = node.find("viewtype")
                    if viewtype_elem is not None:
                        is_view = True
                        if 'view_ids' in index:
                            index['view_ids'].add(normalized_id)

                if tag in control_tags:
                    index['ids_defined'][folder][control_id] = {
                        'file': path,
                        'line': getattr(node, 'sourceline', 0) or 0,
                        'type': tag
                    }
                    if not is_view and tag in view_types:
                        if 'view_ids' in index:
                            index['view_ids'].add(normalized_id)

                elif tag == "control" and "type" in node.attrib:
                    control_type = node.attrib["type"].lower()
                    index['ids_defined'][folder][control_id] = {
                        'file': path,
                        'line': getattr(node, 'sourceline', 0) or 0,
                        'type': control_type
                    }
                    if not is_view and control_type in view_types:
                        if 'view_ids' in index:
                            index['view_ids'].add(normalized_id)

    def _extract_id_references_from_xml(self, root, path, folder, index):
        """Extract control and window ID references from an XML file (from original source for correct line numbers)."""
        # Regex patterns for ID references
        # Window functions that take window IDs (not control IDs)
        # Based on Kodi source: xbmc/GUIInfoManager.cpp lines 7971-7979
        # Maps to: WINDOW_IS_MEDIA, WINDOW_IS, WINDOW_IS_ACTIVE, WINDOW_IS_VISIBLE,
        #          WINDOW_IS_DIALOG_TOPMOST, WINDOW_IS_MODAL_DIALOG_TOPMOST, WINDOW_PREVIOUS, WINDOW_NEXT
        window_regex = r"(?:Window\.IsMedia|Window\.Is(?:Active|Visible|DialogTopmost|ModalDialogTopmost)?|Window\.(?:Previous|Next)|Dialog\.Close)\(([0-9]+)\)"
        control_regex = _build_control_regex()

        for node in root.xpath(".//*[@condition]"):
            condition_text = node.attrib.get("condition", "")

            for match in re.finditer(window_regex, condition_text, re.IGNORECASE):
                window_id = match.group(1)
                window_id = utils.normalize_control_id(window_id)
                if window_id not in index['ids_referenced'][folder]:
                    index['ids_referenced'][folder][window_id] = []
                index['ids_referenced'][folder][window_id].append({
                    'file': path,
                    'line': getattr(node, 'sourceline', 0) or 0,
                    'type': 'window'
                })

            for match in re.finditer(control_regex, condition_text, re.IGNORECASE):
                function_name = match.group(1)  # e.g., "Control.IsVisible" or "Container"
                control_id = match.group(2)      # e.g., "52"

                if not control_id:
                    continue

                # Case-insensitive: regex uses IGNORECASE but exclusion set is lowercase
                if _EXCLUDED_FUNCTIONS and function_name.lower() in _EXCLUDED_FUNCTIONS:
                    continue

                control_id = utils.normalize_control_id(control_id)

                context = None
                fn_lower = function_name.lower()
                if fn_lower == 'control.isvisible':
                    context = 'Control.IsVisible'
                elif fn_lower == 'control.hasfocus':
                    context = 'Control.HasFocus'

                if control_id not in index['ids_referenced'][folder]:
                    index['ids_referenced'][folder][control_id] = []
                index['ids_referenced'][folder][control_id].append({
                    'file': path,
                    'line': getattr(node, 'sourceline', 0) or 0,
                    'type': 'control',
                    'context': context
                })

        bracket_tags = ["visible", "enable", "usealttexture", "selected", "onclick", "onback"]
        for tag_name in bracket_tags:
            for node in root.xpath(f".//{tag_name}"):
                text = (node.text or "").strip()
                if not text:
                    continue

                # Check if this is a delayed execution context (AlarmClock)
                # AlarmClock(name, command, time) executes command after delay
                # Control IDs in the command may not exist in current window
                is_delayed_execution = bool(re.search(r'\bAlarmClock\s*\(', text, re.IGNORECASE))

                for match in re.finditer(window_regex, text, re.IGNORECASE):
                    window_id = match.group(1)
                    window_id = utils.normalize_control_id(window_id)
                    if window_id not in index['ids_referenced'][folder]:
                        index['ids_referenced'][folder][window_id] = []
                    index['ids_referenced'][folder][window_id].append({
                        'file': path,
                        'line': getattr(node, 'sourceline', 0) or 0,
                        'type': 'window'
                    })

                for match in re.finditer(control_regex, text, re.IGNORECASE):
                    function_name = match.group(1)  # e.g., "Control.IsVisible" or "SetFocus"
                    control_id = match.group(2)      # e.g., "52"

                    if not control_id:
                        continue

                    if _EXCLUDED_FUNCTIONS and function_name.lower() in _EXCLUDED_FUNCTIONS:
                        continue

                    # Skip validation for control IDs inside delayed execution contexts
                    # These controls may exist in different windows or be created later
                    if is_delayed_execution:
                        continue

                    control_id = utils.normalize_control_id(control_id)

                    context = None
                    fn_lower = function_name.lower()
                    if fn_lower == 'control.isvisible':
                        context = 'Control.IsVisible'
                    elif fn_lower == 'control.hasfocus':
                        context = 'Control.HasFocus'

                    if control_id not in index['ids_referenced'][folder]:
                        index['ids_referenced'][folder][control_id] = []
                    index['ids_referenced'][folder][control_id].append({
                        'file': path,
                        'line': getattr(node, 'sourceline', 0) or 0,
                        'type': 'control',
                        'context': context
                    })
