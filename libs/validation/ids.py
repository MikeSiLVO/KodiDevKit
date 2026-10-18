"""Checks every control and window id a skin refers to against the ids it defines."""

from __future__ import annotations

import os
import logging

from ..utils.validation import deduplicate_issues
from .constants import SEVERITY_ERROR, SEVERITY_WARNING

logger = logging.getLogger(__name__)

class ValidationIds:
    """Checker for undefined ids, core window ids used by number, and windows Kodi will not load."""

    def __init__(self, addon, window_ids, window_names, validation_index=None,
                 window_filenames=(), modeless_ids=(), dialog_ids=()):
        self.addon = addon
        self.window_ids = window_ids
        self.window_names = window_names
        self.window_filenames = window_filenames
        self.modeless_ids = modeless_ids
        self.dialog_ids = dialog_ids
        self._validation_index = validation_index

    def _window_ref_message(self, ref_id, window_ids_in_skin, usage_file):
        """Rule and message for a bad window id reference, or None for a fine one."""
        if ref_id in window_ids_in_skin:
            return None
        # Kodi reads any id up to 9999 as an offset from the home window
        full_id = str(int(ref_id) + 10000) if ref_id.isdigit() and int(ref_id) <= 9999 else ref_id
        if full_id in window_ids_in_skin:
            return None
        if full_id not in self.window_ids:
            return "ids.undefined-window", f"Window ID not defined: {ref_id}"
        name = self.window_names[self.window_ids.index(full_id)]
        if not name or "script-skinshortcuts-includes.xml" in usage_file.replace("\\", "/").lower():
            return None
        return "ids.use-name", f"Window id {ref_id} works, but its name {name} is preferred"

    def _custom_window_issues(self, folder, custom_windows):
        """Custom windows Kodi refuses to load, or whose id sits outside the reviewed range."""
        issues = []
        by_id = {}
        for window_file, window_id in sorted(custom_windows.items()):
            path = os.path.join(self.addon.path, folder, window_file)
            if window_id is None or window_id.startswith("root:"):
                if window_id is None:
                    issues.append((path, "Custom window has no id, so Kodi does not load it", SEVERITY_ERROR,
                                   "ids.custom-window-no-id", ""))
                else:
                    issues.append((path, f"Custom window root is <{window_id[5:]}>, not <window>, so Kodi does "
                                         f"not load it", SEVERITY_ERROR, "ids.custom-window-root", window_id[5:]))
                continue
            by_id.setdefault(window_id, []).append(window_file)
            full_id = str(int(window_id) + 10000)
            if full_id in self.window_ids:
                name = self.window_names[self.window_ids.index(full_id)] or full_id
                issues.append((path, f"Custom window id {window_id} is Kodi's {name} window, so Kodi "
                                     f"does not load it", SEVERITY_ERROR, "ids.custom-window-taken", window_id))
            elif not 1100 <= int(window_id) <= 1199:
                issues.append((path, f"Custom window id {window_id} is outside 1100-1199", SEVERITY_WARNING,
                               "ids.custom-window-range", window_id))
        for window_id, files in by_id.items():
            for window_file in files if len(files) > 1 else ():
                others = ", ".join(f for f in files if f != window_file)
                issues.append((os.path.join(self.addon.path, folder, window_file),
                               f"Custom window id {window_id} is also used by {others}; Kodi loads one",
                               SEVERITY_ERROR, "ids.custom-window-shared", window_id))
        return [{"message": m, "file": p, "line": 1, "severity": sev, "rule": rule, "subject": subject}
                for p, m, sev, rule, subject in issues]

    def _window_name_message(self, name):
        """Rule and message for a window name Kodi does not know, or None when it does."""
        key = name.lower()
        if key.endswith(".xml"):
            key = key[:-4]
        if len(key) > 6 and key.startswith("window"):
            key = key[6:]
        if key.startswith("my"):
            key = key[2:]
        if key.isdigit() or key in {n.lower() for n in self.window_names if n}:
            return None
        return "ids.unknown-window-name", f"Window name not recognized by Kodi: {name}"

    def _modeless_files(self, custom, window_files):
        """Window files Kodi may open modeless; addon windows count, since their type is unknown."""
        kodi_names = {name.lower() for name in self.window_filenames if name}
        modeless_names = {name.lower() for name, wid in zip(self.window_filenames, self.window_ids)
                          if name and wid in self.modeless_ids}
        return {f for f in window_files
                if f in custom or f.lower() in modeless_names
                or (f.lower() not in kodi_names and not f.lower().startswith("custom"))}

    def check(self, progress_callback=None):
        """Check id references, window names and custom windows, one issue row per problem."""
        if not self._validation_index:
            return []
        total_ids = sum(len(ids) for ids in self._validation_index.get('ids_defined', {}).values())
        total_files = sum(len(files) for files in self._validation_index.get('window_includes', {}).values())

        if progress_callback:
            progress_callback(f"Checking {total_ids} control/window IDs in {total_files} files...")

        listitems = []

        for folder in self.addon.xml_folders:
            window_ids_in_skin = self._validation_index.get('window_ids', {}).get(folder, [])
            listitems.extend(self._custom_window_issues(
                folder, self._validation_index.get('custom_windows', {}).get(folder, {})))
            ids_referenced = self._validation_index.get('ids_referenced', {}).get(folder, {})

            window_expanded_ids = self._validation_index.get('window_expanded_ids', {}).get(folder, {})
            window_base_ids = self._validation_index.get('window_base_ids', {}).get(folder, {})

            window_to_ids = {}
            for window_file in window_expanded_ids:
                expanded_ids = window_expanded_ids.get(window_file, set())
                window_to_ids[window_file] = set(expanded_ids or window_base_ids.get(window_file, set()))

            modeless_files = self._modeless_files(
                self._validation_index.get('custom_modeless_files', {}).get(folder, set()), window_to_ids)
            dialog_names = {name.lower() for name, wid in zip(self.window_filenames, self.window_ids)
                            if name and wid in self.dialog_ids}
            dialog_files = modeless_files | {f for f in window_to_ids if f.lower() in dialog_names} | set(
                self._validation_index.get('custom_dialog_files', {}).get(folder, set()))
            builtin_controls = self._validation_index.get('builtin_controls', {})
            builtin_filename_map = self._validation_index.get('builtin_filename_map', {})
            defined_anywhere = set(self._validation_index.get('ids_defined', {}).get(folder, {}))
            for ids in window_to_ids.values():
                defined_anywhere |= ids
            for ids in builtin_controls.values():
                defined_anywhere |= set(ids)
            all_view_ids = set()
            for folder_views in self._validation_index.get('view_ids', {}).values():
                all_view_ids.update(folder_views)
            # shared files and non-window roots have no control scope of their own
            unscoped = (set(self._validation_index.get('include_files', {}).get(folder, []))
                        | self._validation_index.get('non_window_files', {}).get(folder, set()))

            for ref_id, usages in ids_referenced.items():
                for usage in usages:
                    usage_file = usage.get('file', '')
                    if usage.get('type', 'control') == 'window':
                        found = self._window_ref_message(ref_id, window_ids_in_skin, usage_file)
                    elif usage['type'] == 'window_name':
                        found = self._window_name_message(ref_id)
                    elif not ref_id:
                        continue
                    else:
                        usage_name = os.path.relpath(usage_file, os.path.join(self.addon.path, folder))
                        window_name = builtin_filename_map.get(usage_name.lower())
                        if (usage_name in unscoped
                                or ref_id in window_to_ids.get(usage_name, set())
                                or ref_id in builtin_controls.get(window_name, ())
                                or (usage.get('context') in ('Control.IsVisible', 'Control.HasFocus')
                                    and ref_id in all_view_ids)):
                            continue
                        # a dialog leaves the stack before its onunload runs
                        unload_below = usage.get('unload') and usage_name in dialog_files
                        if ref_id not in defined_anywhere:
                            found = "ids.undefined-control", f"Control ID {ref_id} not defined"
                        elif (usage.get('context') != 'navigation'
                              and (usage_name in modeless_files or usage.get('after_switch') or unload_below)):
                            # Kodi resolves it in the topmost modal dialog or the active window
                            continue
                        else:
                            found = "ids.out-of-scope", f"Control ID {ref_id} not defined in {usage_name}'s scope"
                    if found:
                        listitems.append({
                            "message": found[1],
                            "file": usage_file,
                            "line": usage.get('line', 0),
                            "severity": SEVERITY_WARNING if found[0] == "ids.use-name" else SEVERITY_ERROR,
                            "rule": found[0],
                            "subject": ref_id,
                        })

        return deduplicate_issues(listitems)
