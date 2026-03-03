"""
BOM and line ending validation for Kodi skins.

Kodi repo submission requires no BOM and Unix line endings.
"""

from __future__ import annotations

import os
import logging

from .. import utils
from .constants import SEVERITY_ERROR

logger = logging.getLogger(__name__)


class ValidationFileCheck:
    """Validates file encoding (BOM) and line endings."""

    def __init__(self, addon):
        self.addon = addon

    def check(self, progress_callback=None):
        issues = []

        if not self.addon:
            return issues

        xml_files = list(self.addon.get_xml_files())

        if progress_callback:
            progress_callback(f"Checking {len(xml_files)} files for BOM and line endings...")

        # BOM check
        for path in xml_files:
            if utils.check_bom(path):
                issues.append({
                    "message": f"found BOM. File: {os.path.basename(path)}",
                    "file": path,
                    "line": 1,
                    "severity": SEVERITY_ERROR,
                })

        # EOL check — scan entire skin directory for all file types
        result = utils.eol_info_from_path_patterns(
            [self.addon.path],
            recursive=True,
            excludes=['.svn', '.git'],
        )
        for path, eol in result:
            if eol == '\r\n':
                issues.append({
                    "message": f"Windows Line Endings detected in {os.path.basename(path)}",
                    "file": path,
                    "line": 0,
                    "severity": SEVERITY_ERROR,
                })
            elif eol == '\r':
                issues.append({
                    "message": f"MAC Line Endings detected in {os.path.basename(path)}",
                    "file": path,
                    "line": 0,
                    "severity": SEVERITY_ERROR,
                })

        if progress_callback:
            progress_callback(f"Complete: {len(issues)} file encoding issues found")

        return issues


def check(addon, validation_index):
    """Module-level check function for file encoding validation."""
    checker = ValidationFileCheck(addon)
    return checker.check()
