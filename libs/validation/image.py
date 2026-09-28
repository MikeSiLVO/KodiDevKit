"""Image validation for Kodi skins."""

from __future__ import annotations

import logging
import os
from .constants import SEVERITY_ERROR, SEVERITY_WARNING

logger = logging.getLogger(__name__)


class ValidationImage:
    """Validates image references used by Kodi skins."""

    def __init__(self, addon, validation_index=None, window_filenames=()):
        self.addon = addon
        self._validation_index = validation_index
        self._kodi_files = {name.lower() for name in window_filenames if name}

    def _in_addon_window(self, file_path):
        """True for a window file an addon opens, which also searches the addon's own media."""
        name = os.path.basename(file_path).lower()
        if not self._kodi_files or name in self._kodi_files or name.startswith("custom"):
            return False
        index = self._validation_index or {}
        shared = {n.lower() for folder in index.get('include_files', {}).values() for n in folder}
        shared |= {n.lower() for folder in index.get('non_window_files', {}).values() for n in folder}
        return name not in shared

    def check(self, progress_callback=None):
        """
        Validate image references used by the current skin.
        Returns list of {"message": str, "file": str, "line": int, "severity": str}.
        """
        if not self.addon:
            return [{"message": "Image checker unavailable (no addon)", "file": "", "line": 0}]

        index = self._validation_index
        if not index or 'image_files_checked' not in index:
            return [{"message": "Image validation unavailable (no index)", "file": "", "line": 0}]

        issues = []
        if index.get('xbt_beside_sources'):
            issues.append({
                "message": "Textures.xbt ships beside the source images in media/; remove it before submitting",
                "file": index['xbt_beside_sources'],
                "line": 0,
                "severity": SEVERITY_WARNING,
            })
        if index.get('xbt_unreadable'):
            issues.append({
                "message": "Textures.xbt is not a texture bundle Kodi can read",
                "file": index['xbt_unreadable'],
                "line": 0,
                "severity": SEVERITY_ERROR,
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

                # Report for every usage location, not just the first
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
                        })

                    elif status == 'missing' and self._in_addon_window(file_path):
                        continue

                    elif status == 'missing':
                        issues.append({
                            "message": f"Missing image '{image_path}'{attr_suffix}",
                            "file": file_path,
                            "line": line_num,
                            "severity": SEVERITY_ERROR,
                        })

                    elif status == 'case_mismatch':
                        issues.append({
                            "message": f"Case mismatch for '{image_path}'{attr_suffix} (actual '{detail}')",
                            "file": file_path,
                            "line": line_num,
                            "severity": SEVERITY_WARNING,
                        })

                    elif status == 'wrong_path':
                        if detail:
                            hint = ", ".join(detail[:5]) if isinstance(detail, list) else detail
                            issues.append({
                                "message": f"Wrong path '{image_path}'{attr_suffix}. File exists at: {hint}",
                                "file": file_path,
                                "line": line_num,
                                "severity": SEVERITY_WARNING,
                            })

        if progress_callback:
            progress_callback(f"Complete: {len(issues)} issues found")

        return issues or [{"message": "No image issues found", "file": "", "line": 0}]
