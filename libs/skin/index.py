"""Builds the validation index: font/label/image/control-id usage across the skin."""

from __future__ import annotations
import copy
import os
import re
import time
import logging
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

from ..utils.files import read_xbt_names
from ..utils.xml import get_params, get_root_from_file, tree_needs_expansion
from ..utils.expressions import is_dynamic_expression
from ..utils.validation import normalize_control_id, skinshortcuts_files

logger = logging.getLogger(__name__)

_LABEL_TAGS = frozenset(['label', 'altlabel', 'label2', 'hinttext'])
# the replacer atoi()s the body, so only the leading digits name the string (GUIInfoLabel.cpp)
_LOCALIZE_PATTERN = re.compile(r"\$LOCALIZE\[\s*(\d+)")
_LABEL_BLOCK_MARKERS = ("$INFO[", "$VAR[", "$PARAM[", "$NUMBER[", "$ADDON[", "$MAP[")
_LABEL_ATTRS = {"viewtype": ("label",), "fontset": ("idloc",), "label": ("fallback",), "label2": ("fallback",),
                "altlabel": ("fallback",), "hinttext": ("fallback",)}
_UNKNOWN_PARAM = re.compile(r"\$PARAM\[[^\]]*\]")
_NAVIGATION_TAGS = ("onup", "ondown", "onleft", "onright", "onnext", "onprev")
_ACTION_TAGS = frozenset(_NAVIGATION_TAGS + ("onclick", "onback", "onfocus", "onunfocus", "oninfo", "ontextchange",
                                             "altclick", "onload", "onunload"))
# arguments Kodi passes through CWindowTranslator: window_bools, Window(x) and the window builtins
_WINDOW_REFS = re.compile(
    r"\b(?:Window\.(?:IsMedia|Is|IsActive|IsVisible|IsTopmost|IsDialogTopmost|IsModalDialogTopmost"
    r"|Previous|Next)\(|Window\((?=[^()]*\)\.)|(?:ActivateWindow|ActivateWindowAndFocus|ReplaceWindow"
    r"|ReplaceWindowAndFocus|Dialog\.Close)\()\s*([^,()\s]+)", re.I)
# where Kodi reads a control id (GUIInfoManager.cpp:8527, GUIControlBuiltins.cpp:222)
_CONTROL_REFS = (
    (re.compile(r"\bControl\.(HasFocus|IsVisible|IsEnabled|GetLabel)\(\s*(\d+)\s*\)", re.I), 2),
    (re.compile(r"\bControlGroup\(\s*(\d+)\s*\)", re.I), 1),
    (re.compile(r"\bControlGroup\(\s*\d+\s*\)\.HasFocus\(\s*(\d+)\s*\)", re.I), 1),
    (re.compile(r"\bContainer\(\s*(\d+)\s*\)", re.I), 1),
    (re.compile(r"\b(?:Control\.(?:Message|Move|ResetGroupList|SetFocus|SetHidden|SetVisible)"
                r"|SetFocus|PageUp|PageDown)\(\s*(\d+)\s*[,)]", re.I), 1),
    (re.compile(r"\bSendClick\(\s*(\d+)\s*\)", re.I), 1),
    (re.compile(r"\bSendClick\(\s*[^,()]+,\s*(\d+)\s*\)", re.I), 1),
)
# an action after one of these runs against a different window than the file it sits in
_WINDOW_SWITCH = re.compile(r"^\s*(?:Close|Dialog\.Close|ActivateWindow|ReplaceWindow|Action\(\s*(?:back|close"
                            r"|previousmenu)\s*\))\b", re.I)

def custom_window(root, filename):
    """Ids a custom window answers to and whether it is a modeless dialog; nothing otherwise."""
    if not filename.lower().startswith("custom") or root.tag.lower() != "window":
        return [], False
    raw = root.get("id")
    if raw is None:
        raw = root.findtext("id")
    kind = root.get("type")
    if kind is None:
        kind = root.findtext("type") or ""
    # a dialog with <visible> is modeless unless marked modal (ApplicationSkinHandling.cpp:392)
    modeless = (kind.strip().lower() == "dialog" and root.find("visible") is not None
                and (root.get("modality") or "").lower() != "modal")
    raw = (raw or "").strip()
    if not raw.isdigit():
        return [], modeless
    # Kodi registers it as id + WINDOW_HOME and translates any id below that the same way
    number = int(raw)
    return [str(number), str(number + 10000)], modeless


class SkinIndex:
    """Walks every skin xml file once to index fonts, labels, images and control ids."""

    def __init__(self, skin):
        self.skin = skin
        self.skin_path = skin.path
        self.xml_folders = skin.xml_folders
        self.include_maps = None

    def build_validation_index(self, progress_callback=None):
        """Build the validation index in one threaded pass over the skin's files."""
        if progress_callback:
            progress_callback("Building validation index...")

        # every per-folder key is keyed by xml folder, then by name or id
        index = {
            'fonts_defined': {},
            'fonts_used': {},
            'labels_used': {},
            'labels_untranslated': [],
            'ids_defined': {},
            'ids_referenced': {},
            'window_ids': {},
            'view_ids': {},
            'window_includes': {},
            'window_base_ids': {},
            'window_expanded_ids': {},
            'non_window_files': {},
            'custom_modeless_files': {},
            'custom_windows': {},
            'custom_dialog_files': {},
            'include_files': {},
            'variables_defined': {},
            'images_referenced': {},
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
            index['non_window_files'][folder] = set()
            index['custom_modeless_files'][folder] = set()
            index['custom_windows'][folder] = {}
            index['custom_dialog_files'][folder] = set()
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
                progress_callback(f"Processing {len(self.skin.window_files.get(folder, []))} files in {folder}...")

            max_workers = self._get_optimal_workers()
            file_paths = [
                os.path.join(self.skin.path, folder, xml_file)
                for xml_file in self.skin.window_files.get(folder, [])
            ]

            results_by_path = {}
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_path = {
                    executor.submit(self._process_window_file, path, folder): path
                    for path in file_paths
                }

                pending_futures = set(future_to_path.keys())
                last_progress_time = time.time()
                heartbeat_interval = 2.0

                while pending_futures:
                    done, pending_futures = wait(pending_futures, timeout=heartbeat_interval, return_when=FIRST_COMPLETED)

                    for future in done:
                        file_count += 1
                        path = future_to_path[future]

                        if progress_callback and (file_count % 3 == 0 or file_count == len(file_paths)):
                            xml_file = os.path.basename(path)
                            progress_callback(f"Parsed {xml_file} ({file_count}/{total_files})")
                            last_progress_time = time.time()

                        results_by_path[path] = future.result()

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

            # merge in file order, not completion order, so issue order is stable across runs
            for path in file_paths:
                results = results_by_path.get(path)
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
                    if results.get('root_tag') != 'window':
                        index['non_window_files'][folder].add(window_file)
                    if results.get('custom_modeless'):
                        index['custom_modeless_files'][folder].add(window_file)
                    if results.get('custom_dialog'):
                        index['custom_dialog_files'][folder].add(window_file)
                    if 'custom_id' in results:
                        index['custom_windows'][folder][window_file] = results['custom_id']

                    if 'view_ids' in results:
                        index['view_ids'][folder].update(results['view_ids'])

                    for img_path, usages in results.get('images_referenced', {}).get(folder, {}).items():
                        if img_path not in index['images_referenced'][folder]:
                            index['images_referenced'][folder][img_path] = []
                        index['images_referenced'][folder][img_path].extend(usages)

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

        # single-threaded: the resolver keeps _source_file on itself
        if hasattr(self.skin, 'resolver') and self.skin.resolver:
            if progress_callback:
                progress_callback("Resolving windows for ID extraction...")
            resolve_count = 0
            for folder in self.skin.xml_folders:
                basenames = list(index['window_base_ids'].get(folder, {}).keys())
                for basename in basenames:
                    path = os.path.join(self.skin.path, folder, basename)
                    root = get_root_from_file(path)
                    if root is None:
                        index['window_expanded_ids'][folder][basename] = \
                            index['window_base_ids'][folder].get(basename, set())
                        continue

                    if tree_needs_expansion(root):
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
                        # a param the call never passed is empty in Kodi
                        ctrl_id = _UNKNOWN_PARAM.sub("", node.get('id') or "")
                        if ctrl_id and not is_dynamic_expression(ctrl_id):
                            expanded_ids.add(normalize_control_id(ctrl_id))
                    for node in resolved.iter('item'):
                        item_id = node.get('id')
                        if item_id:
                            expanded_ids.add(normalize_control_id(item_id))

                    for node in resolved.iter('control'):
                        ctrl_id = node.get('id')
                        if ctrl_id and node.find('viewtype') is not None:
                            index['view_ids'][folder].add(normalize_control_id(ctrl_id))

                    index['window_expanded_ids'][folder][basename] = expanded_ids
                    resolve_count += 1

                    if progress_callback and resolve_count % 10 == 0:
                        progress_callback(f"Resolved {resolve_count} windows...")

            logger.info("Resolved %d windows for ID extraction", resolve_count)
        else:
            # an addon window has no includes of its own to expand
            for folder in self.skin.xml_folders:
                index['window_expanded_ids'][folder] = dict(index['window_base_ids'].get(folder, {}))

        if progress_callback:
            progress_callback(f"Index built successfully ({file_count} files processed)")
        logger.info("OK: Validation index built successfully (%d files + includes processed)", file_count)

        # Font.xml is no window file, but its fontset idloc attributes are string ids
        for folder in self.skin.xml_folders:
            font_path = os.path.join(self.skin.path, folder, "Font.xml")
            font_root = get_root_from_file(font_path) if os.path.isfile(font_path) else None
            if font_root is not None:
                self._extract_labels_from_xml(font_root, font_path, folder, index)

        if 'images_referenced' in index:
            self._check_image_files(index, progress_callback)

        if 'fonts_defined' in index:
            self._check_font_files(index, progress_callback)

        return index

    def _get_optimal_workers(self):
        """Thread count for the parse pass: a few above the core count, at most 8."""
        cpu_count = os.cpu_count() or 1

        if cpu_count == 1:
            return 3
        elif cpu_count == 2:
            return 4
        else:
            return min(cpu_count + 4, 8)

    def _process_window_file(self, path, folder):
        """Fonts, labels, images and ids of one file as a fresh dict, so threads share nothing."""
        try:
            if "script-skinshortcuts-includes.xml" in path.lower():
                return None

            root = get_root_from_file(path)
            if root is None:
                return None

            results = {
                'path': path,
                'root_tag': root.tag,
                'fonts_used': {folder: {}},
                'labels_used': {folder: {}},
                'labels_untranslated': [],
                'ids_defined': {folder: {}},
                'ids_referenced': {folder: {}},
                'window_ids': {folder: []},
                'window_includes': [],
                'base_ids': set(),
                'view_ids': set()
            }

            window_ids, results['custom_modeless'] = custom_window(root, os.path.basename(path))
            results['window_ids'][folder].extend(window_ids)
            if os.path.basename(path).lower().startswith("custom"):
                results['custom_id'] = window_ids[0] if window_ids else None
                kind = root.get("type") or root.findtext("type") or ""
                results['custom_dialog'] = kind.strip().lower() == "dialog"
                if root.tag.lower() != "window":
                    results['custom_id'] = "root:" + root.tag

            self._extract_fonts_from_xml(root, path, folder, results)
            self._extract_labels_from_xml(root, path, folder, results)
            self._extract_images_from_xml(root, path, folder, results)

            for elem in root.iter('include'):
                inc_name = elem.get('content') or (elem.text or '').strip()
                if inc_name:
                    results['window_includes'].append({'name': inc_name})

            # <item id> counts too, Container().HasFocus() can address it
            for elem in root.iter('control'):
                ctrl_id = elem.get('id')
                if ctrl_id:
                    ctrl_id = normalize_control_id(ctrl_id)
                    results['base_ids'].add(ctrl_id)

            for item_elem in root.iter('item'):
                item_id = item_elem.get('id')
                if item_id:
                    item_id = normalize_control_id(item_id)
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
        """Build the list of include calls, each with its params and the include it sits in."""
        if self.skin._include_usages_built:
            return

        for folder in self.skin.xml_folders:
            if folder not in self.skin.include_usages:
                self.skin.include_usages[folder] = {}

            files_to_scan = [os.path.join(self.skin.path, folder, xml_file)
                             for xml_file in self.skin.window_files.get(folder, [])]
            files_to_scan.extend(skinshortcuts_files(self.skin.path))

            for file_path in files_to_scan:
                root = get_root_from_file(file_path)
                if root is None:
                    continue

                for elem in root.iter('include'):
                    inc_name = None
                    params = {}

                    if 'content' in elem.attrib:
                        inc_name = elem.attrib['content']
                        params = get_params(elem, "value")
                    elif elem.text and elem.text.strip():
                        inc_name = elem.text.strip()

                    if inc_name:
                        if inc_name not in self.skin.include_usages[folder]:
                            self.skin.include_usages[folder][inc_name] = []

                        enclosing = next((a.get('name') for a in elem.iterancestors('include')
                                          if a.get('name')), None)
                        self.skin.include_usages[folder][inc_name].append({
                            'params': params,
                            'file': file_path,
                            'line': getattr(elem, 'sourceline', 0),
                            'enclosing': enclosing,
                        })

        self.skin._include_usages_built = True

    def _extract_fonts_from_xml(self, root, path, folder, index):
        """Extract every static <font> name in the file into the index."""
        for node in root.xpath(".//font"):
            font_name = (node.text or "").strip()
            if font_name and not is_dynamic_expression(font_name):
                if font_name not in index['fonts_used'][folder]:
                    index['fonts_used'][folder][font_name] = []
                index['fonts_used'][folder][font_name].append({
                    'file': path,
                    'line': getattr(node, 'sourceline', 0) or 0
                })

    def _extract_labels_from_xml(self, root, path, folder, index):
        """Extract label ids and untranslated label text in the file into the index."""
        used = index['labels_used'][folder]

        def use(label_id, element, kind):
            used.setdefault(label_id, []).append(
                {'file': path, 'line': getattr(element, 'sourceline', 0) or 0, 'type': kind})

        def untranslated(text, element, where):
            if (len(text) > 2 and not text.endswith(".xml") and text[0].isalpha() and not text.startswith("$")
                    and not any(block in text for block in _LABEL_BLOCK_MARKERS)):
                index['labels_untranslated'].append({
                    'name': text, 'type': element.tag, 'file': path, 'identifier': text,
                    'message': f"Label in {where} not translated: {text}",
                    'line': getattr(element, 'sourceline', 0) or 0,
                })

        for element in root.iter():
            if not isinstance(element.tag, str):
                continue
            for value in [element.text or ""] + [v for k, v in element.attrib.items() if not k.startswith("_kdk_")]:
                for match in _LOCALIZE_PATTERN.finditer(value):
                    use(match.group(1), element, element.tag)

            text = element.text or ""
            if element.tag in _LABEL_TAGS and text:
                if text.isdigit():
                    use(text, element, element.tag)
                else:
                    untranslated(text, element, f"<{element.tag}>")

            # attributes Kodi reads as a string id or as label text (GUIControlFactory FilterLabel)
            for attr in _LABEL_ATTRS.get(element.tag, ()):
                value = (element.get(attr) or "").strip()
                if value.isdigit():
                    use(value, element, f"@{attr}")
                elif value and attr != "idloc":
                    untranslated(value, element, f"attribute {attr}")

    def _extract_images_from_xml(self, root, path, folder, index):
        """Extract static image paths from texture tags and their attributes into the index."""
        image_tags = frozenset(['texture', 'icon', 'thumb', 'bordertexture', 'alttexture'])
        universal_attrs = ('diffuse', 'texturefocus', 'texturenofocus')
        # fallback on <label> is text, so these only count on texture tags
        texture_only_attrs = ('fallback', 'texture', 'thumb', 'icon')

        if 'images_referenced' not in index:
            index['images_referenced'] = {}
        if folder not in index['images_referenced']:
            index['images_referenced'][folder] = {}

        def _track(image_path, node, attr=None):
            if not image_path or is_dynamic_expression(image_path):
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
            if is_texture_tag:
                for attr in texture_only_attrs:
                    val = node.attrib.get(attr)
                    if val:
                        _track(val.strip(), node, attr)

    def _check_image_files(self, index, progress_callback=None):
        """Check referenced images and texture bundles on disk so image validation needs no I/O."""
        if 'images_referenced' not in index:
            return

        if progress_callback:
            progress_callback("Checking image files on disk...")

        def build_fs_index(root_dir):
            exact_relpaths = set()
            cf_rel_to_exact = {}
            cf_base_to_relpaths = {}

            for dirpath, _, files in os.walk(root_dir):
                for filename in files:
                    rel_path = os.path.relpath(os.path.join(dirpath, filename), root_dir)
                    rel_path = rel_path.replace("\\", "/")
                    exact_relpaths.add(rel_path)
                    cf_rel_to_exact.setdefault(rel_path.casefold(), rel_path)
                    cf_base_to_relpaths.setdefault(filename.casefold(), set()).add(rel_path)

            return exact_relpaths, cf_rel_to_exact, cf_base_to_relpaths

        exact_relpaths, cf_rel_to_exact, cf_base_to_relpaths = build_fs_index(self.skin.path)
        logger.info(f"  -> Indexed {len(exact_relpaths)} files in media directories")
        xbt_path = os.path.join(self.skin.path, "media", "Textures.xbt")
        xbt_names = read_xbt_names(xbt_path) if os.path.isfile(xbt_path) else None
        loose_media = any(p.startswith("media/") and not p.lower().endswith(".xbt") for p in exact_relpaths)

        def normalize_ref(val: str):
            v = (val or "").strip().replace("\\", "/")
            # Kodi loads a full path as written, outside the skin
            if v.startswith("/") or re.match(r"^[A-Za-z]:/", v):
                return None

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

        def classify_path(val_norm):
            if val_norm is None:
                return "external", None
            in_xbt = (xbt_names is not None and val_norm.startswith("media/")
                      and val_norm[len("media/"):].lower() in xbt_names)
            if xbt_names is not None and not loose_media and val_norm.startswith("media/"):
                return ("exact", None) if in_xbt else ("missing", None)
            if val_norm in exact_relpaths:
                return "exact", None

            cf_rel = val_norm.casefold()
            if cf_rel in cf_rel_to_exact:
                return "case_mismatch", cf_rel_to_exact[cf_rel]
            if in_xbt:
                return "packed_only", None

            cf_base = os.path.basename(val_norm).casefold()
            candidates = sorted(cf_base_to_relpaths.get(cf_base, []))
            if candidates:
                return "wrong_path", candidates

            return "missing", None

        index['image_files_checked'] = {}
        media_dir = os.path.join(self.skin.path, "media")
        bundle_paths = [os.path.join(media_dir, f) for f in (os.listdir(media_dir) if os.path.isdir(media_dir) else [])
                        if f.lower().endswith(".xbt")]
        bundles = {p: xbt_names if p == xbt_path else read_xbt_names(p) for p in bundle_paths}
        index['xbt_beside_sources'] = sorted(p for p, names in bundles.items() if names is not None and loose_media)
        index['xbt_unreadable'] = sorted(p for p, names in bundles.items() if names is None)

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
                    'status': status,
                    'detail': detail,
                    'normalized': normalized,
                }

        logger.info(f"  -> Checked {checked_count} unique image references")

    def _check_font_files(self, index, progress_callback=None):
        """Classify each font file against the skin's fonts folder; core fonts are checked later."""
        if 'fonts_defined' not in index:
            return

        if progress_callback:
            progress_callback("Checking font files on disk...")
        logger.info("Pre-checking font file existence...")

        skin_fonts_dir = os.path.join(self.skin.path, "fonts")
        skin_files = {}

        if os.path.isdir(skin_fonts_dir):
            try:
                for filename in os.listdir(skin_fonts_dir):
                    file_path = os.path.join(skin_fonts_dir, filename)
                    if os.path.isfile(file_path):
                        skin_files[filename.casefold()] = filename
            except Exception as e:
                logger.warning(f"Failed to list font files: {e}")

        logger.info(f"  -> Indexed {len(skin_files)} font files in fonts/ directory")

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

                if is_dynamic_expression(filename):
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
                    'status': status,
                    'detail': detail,
                    'filename': filename,
                }

        logger.info(f"  -> Checked {checked_count} font file references")

    def _extract_id_definitions_from_xml(self, root, path, folder, index):
        """Extract the window id and every control id the file defines into the index."""
        control_tags = {
            "button", "edit", "fadelabel", "fixedlist", "group", "grouplist",
            "image", "label", "list", "mover", "multiimage", "panel", "progress",
            "radiobutton", "rss", "scrollbar", "selectbutton", "slider",
            "spincontrol", "spincontrolex", "textbox", "togglebutton",
            "videowindow", "visualisation", "wraplist", "epggrid", "ranges",
            "sliderex", "panelcontainer", "gamewindow"
        }

        view_types = {'list', 'panel', 'fixedlist', 'wraplist', 'epggrid'}

        for node in root.iter():
            tag = node.tag.lower()

            if "id" in node.attrib:
                control_id = node.attrib["id"]

                if is_dynamic_expression(control_id):
                    continue

                normalized_id = normalize_control_id(control_id)

                # <viewtype> marks a view even when the type attribute is a $PARAM
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
        """Extract every window and control id the file's conditions and actions refer to."""
        for node in root.xpath(".//*[@condition]"):
            self._record_id_refs(node.attrib.get("condition", ""), node, path, folder, index)

        for node in root.iter(*_NAVIGATION_TAGS):
            target = (node.text or "").strip()
            # a bare number is where focus moves, in the control's own window (GUIAction.cpp:90)
            if target.isdigit() and target != "0":
                index['ids_referenced'][folder].setdefault(normalize_control_id(target), []).append(
                    {'file': path, 'line': getattr(node, 'sourceline', 0) or 0, 'type': 'control',
                     'context': 'navigation'})

        bracket_tags = ["visible", "enable", "usealttexture", "selected"] + sorted(_ACTION_TAGS)
        for tag_name in bracket_tags:
            for node in root.xpath(f".//{tag_name}"):
                text = (node.text or "").strip()
                if not text:
                    continue
                # an AlarmClock command runs later, maybe in another window
                delayed = bool(re.search(r'\bAlarmClock\s*\(', text, re.IGNORECASE))
                after_switch = any(_WINDOW_SWITCH.match(prev.text or "")
                                   for prev in node.itersiblings(tag_name, preceding=True))
                self._record_id_refs(text, node, path, folder, index, skip_controls=delayed,
                                     after_switch=after_switch, unload=tag_name == "onunload")

    @staticmethod
    def _record_id_refs(text, node, path, folder, index, skip_controls=False, after_switch=False, unload=False):
        """Record the window and control ids one condition or action text refers to."""
        refs = index['ids_referenced'][folder]
        line = getattr(node, 'sourceline', 0) or 0

        for match in _WINDOW_REFS.finditer(text):
            arg = match.group(1)
            if arg.isdigit():
                refs.setdefault(normalize_control_id(arg), []).append({'file': path, 'line': line, 'type': 'window'})
            elif "$" not in arg and "xml" not in arg.lower() and arg.lower() != "all":
                refs.setdefault(arg, []).append({'file': path, 'line': line, 'type': 'window_name'})

        if skip_controls:
            return

        for pattern, group in _CONTROL_REFS:
            for match in pattern.finditer(text):
                control_id = normalize_control_id(match.group(group))
                if control_id == "0":
                    continue
                context = None
                if group == 2:
                    context = {'isvisible': 'Control.IsVisible', 'hasfocus': 'Control.HasFocus'}.get(
                        match.group(1).lower())
                refs.setdefault(control_id, []).append(
                    {'file': path, 'line': line, 'type': 'control', 'context': context,
                     'after_switch': after_switch, 'unload': unload})
