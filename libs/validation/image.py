"""Checks image references against the index's findings, one issue per usage site."""

from __future__ import annotations

import logging
import os
from .constants import SEVERITY_ERROR, SEVERITY_WARNING

logger = logging.getLogger(__name__)


class ValidationImage:
    """Checker for missing, miscased and misplaced images, and for texture bundles."""

    def __init__(self, addon, validation_index=None, window_filenames=()):
        self.addon = addon
        self._validation_index = validation_index
        self._kodi_files = {name.lower() for name in window_filenames if name}

    def _in_addon_window(self, file_path, folder):
        """True for a window file an addon opens, which also searches the addon's own media."""
        name = os.path.relpath(file_path, os.path.join(self.addon.path, folder)).lower()
        if not self._kodi_files or name in self._kodi_files or name.startswith("custom"):
            return False
        index = self._validation_index or {}
        shared = {n.lower() for folder in index.get('include_files', {}).values() for n in folder}
        shared |= {n.lower() for folder in index.get('non_window_files', {}).values() for n in folder}
        return name not in shared

    def check(self, progress_callback=None):
        """Check bundles and image usages, a row per bad one, or one saying the check cannot run."""
        if not self.addon:
            return [{"message": "Image checker unavailable (no addon)", "file": "", "line": 0,
                     "rule": "images.unavailable", "subject": ""}]

        index = self._validation_index
        if not index or 'image_files_checked' not in index:
            return [{"message": "Image validation unavailable (no index)", "file": "", "line": 0,
                     "rule": "images.unavailable", "subject": ""}]

        issues = []
        for path in index.get('xbt_beside_sources', []):
            issues.append({
                "message": f"Kodi repo: {os.path.basename(path)} ships beside the source images in media/",
                "file": path,
                "line": 0,
                "severity": SEVERITY_WARNING,
                "rule": "images.bundle-beside-sources",
                "subject": "",
            })
        for path in index.get('xbt_unreadable', []):
            issues.append({
                "message": f"{os.path.basename(path)} is not a texture bundle Kodi can read",
                "file": path,
                "line": 0,
                "severity": SEVERITY_ERROR,
                "rule": "images.bundle-unreadable",
                "subject": "",
            })

        if progress_callback:
            progress_callback("Checking images using cached data...")

        image_files_checked = index.get('image_files_checked', {})
        images_referenced = index.get('images_referenced', {})

        total_images = sum(len(imgs) for imgs in image_files_checked.values())
        checked_count = 0

        for folder, images_dict in image_files_checked.items():
            for image_path, check_result in images_dict.items():
                checked_count += 1

                if progress_callback and total_images > 100 and checked_count % 50 == 0:
                    progress_callback(f"Validating images... ({checked_count}/{total_images})")

                status = check_result.get('status')
                detail = check_result.get('detail')

                usages = images_referenced.get(folder, {}).get(image_path, [])
                if not usages:
                    continue

                placeholder = image_path.strip().lower() in ("-", "noop")

                for usage in usages:
                    file_path = usage.get('file', '')
                    line_num = usage.get('line', 0)
                    attr = usage.get('attr')
                    attr_suffix = f" in @{attr}" if attr else ""

                    if status == 'external':
                        continue

                    if status == 'missing' and placeholder:
                        issues.append({
                            "message": f"'{image_path}'{attr_suffix} is not an empty texture in Kodi; "
                                       f"leave the value empty",
                            "file": file_path,
                            "line": line_num,
                            "severity": SEVERITY_ERROR,
                            "rule": "images.not-empty",
                            "subject": image_path,
                        })

                    elif status == 'missing' and self._in_addon_window(file_path, folder):
                        continue

                    elif status == 'missing':
                        issues.append({
                            "message": f"Missing image '{image_path}'{attr_suffix}",
                            "file": file_path,
                            "line": line_num,
                            "severity": SEVERITY_ERROR,
                            "rule": "images.missing",
                            "subject": image_path,
                        })

                    elif status == 'packed_only':
                        issues.append({
                            "message": f"'{image_path}'{attr_suffix} is only in Textures.xbt, not among the "
                                       f"loose images. Kodi finds it, but the Kodi repo expects loose images "
                                       f"and packs Textures.xbt itself, so a repo build drops it",
                            "file": file_path,
                            "line": line_num,
                            "severity": SEVERITY_WARNING,
                            "rule": "images.not-in-sources",
                            "subject": image_path,
                        })

                    elif status == 'case_mismatch':
                        issues.append({
                            "message": f"Case mismatch for '{image_path}'{attr_suffix} (actual '{detail}')",
                            "file": file_path,
                            "line": line_num,
                            "severity": SEVERITY_WARNING,
                            "rule": "images.case-mismatch",
                            "subject": image_path,
                        })

                    elif status == 'case_mismatch_unbundled':
                        issues.append({
                            "message": f"Case mismatch for '{image_path}'{attr_suffix} (actual '{detail}'); this "
                                       f"path skips Textures.xbt, so it fails where file names are case-sensitive, "
                                       f"such as Linux",
                            "file": file_path,
                            "line": line_num,
                            "severity": SEVERITY_ERROR,
                            "rule": "images.unbundled-case-mismatch",
                            "subject": image_path,
                        })

                    elif status == 'wrong_path':
                        if detail:
                            hint = ", ".join(detail[:5]) if isinstance(detail, list) else detail
                            issues.append({
                                "message": f"Wrong path '{image_path}'{attr_suffix}: Kodi looks for "
                                           f"{check_result.get('normalized')}, the file is at {hint}",
                                "file": file_path,
                                "line": line_num,
                                "severity": SEVERITY_WARNING,
                                "rule": "images.wrong-path",
                                "subject": image_path,
                            })

        if progress_callback:
            progress_callback(f"Complete: {len(issues)} issues found")

        return issues
