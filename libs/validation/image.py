"""
KodiDevKit is a plugin to assist with Kodi skinning / scripting
using Sublime Text 4
Image validation for Kodi skins.
"""

from __future__ import annotations

import logging
from .constants import SEVERITY_ERROR, SEVERITY_WARNING

logger = logging.getLogger(__name__)


class ValidationImage:
    """Validates image references used by Kodi skins."""

    def __init__(self, addon, validation_index=None):
        """
        Args:
            addon: Addon/Skin instance with xml_folders, path
            validation_index: Pre-built validation index with image_files_checked
        """
        self.addon = addon
        self._validation_index = validation_index

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
        suppressed_count = 0

        has_packed_textures = index.get('has_packed_textures', False)

        if progress_callback:
            progress_callback("Checking images using cached data...")

        if has_packed_textures:
            return [{
                "message": "INFO: Image validation skipped (Textures.xbt detected - cannot verify packed textures)",
                "file": "",
                "line": 0
            }]

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

                if status == 'missing':
                    if has_packed_textures:
                        suppressed_count += 1
                        logger.debug(f"Image not verified (may be in Textures.xbt): {image_path}")
                        continue

                # Report for every usage location, not just the first
                for usage in usages:
                    file_path = usage.get('file', '')
                    line_num = usage.get('line', 0)
                    attr = usage.get('attr')
                    attr_suffix = f" in @{attr}" if attr else ""

                    if status == 'missing':
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

        if has_packed_textures and suppressed_count > 0:
            issues.append({
                "message": f"INFO: {suppressed_count} image(s) not verified (may be in Textures.xbt)",
                "file": "",
                "line": 0
            })

        error_count = len([i for i in issues if "INFO:" not in i.get("message", "")])
        if progress_callback:
            if has_packed_textures and suppressed_count > 0:
                progress_callback(f"Complete: {error_count} issues ({suppressed_count} suppressed by Textures.xbt)")
            else:
                progress_callback(f"Complete: {error_count} issues found")

        return issues or [{"message": "No image issues found", "file": "", "line": 0}]
