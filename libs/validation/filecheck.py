"""
BOM and line ending validation for Kodi skins.

Kodi repo submission requires no BOM and Unix line endings.
"""

from __future__ import annotations

import os
import logging

from ..utils.files import check_bom, eol_info_from_path_patterns
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

        # Text types only: binaries such as PNGs routinely contain 0D 0A and
        # would otherwise be reported as having Windows line endings.
        result = eol_info_from_path_patterns(
            [self.addon.path],
            recursive=True,
            includes=['.xml', '.po', '.txt', '.py', '.md'],
            excludes=['.svn', '.git'],
        )

        if progress_callback:
            progress_callback(f"Checking {len(result)} files for BOM and line endings...")

        for path, _eol in result:
            if check_bom(path):
                issues.append({
                    "message": f"found BOM. File: {os.path.basename(path)}",
                    "file": path,
                    "line": 1,
                    "severity": SEVERITY_ERROR,
                })

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

        issues.extend(self._sixteen_bit_pngs())

        if progress_callback:
            progress_callback(f"Complete: {len(issues)} file encoding issues found")

        return issues


    def _sixteen_bit_pngs(self):
        """PNGs TexturePacker would pack whose IHDR says 16 bits per channel."""
        issues = []
        for folder in ("media", "themes"):
            for dirpath, _dirs, files in os.walk(os.path.join(self.addon.path, folder)):
                for name in files:
                    if not name.lower().endswith(".png"):
                        continue
                    path = os.path.join(dirpath, name)
                    try:
                        with open(path, "rb") as f:
                            header = f.read(25)
                    except OSError:
                        continue
                    # bit depth follows the 8-byte signature and the IHDR length, type, width, height
                    if len(header) == 25 and header[12:16] == b"IHDR" and header[24] == 16:
                        issues.append({
                            "message": f"16-bit PNG {name}: TexturePacker cannot pack it, save it as 8-bit",
                            "file": path,
                            "line": 0,
                            "severity": SEVERITY_ERROR,
                        })
        return issues


def check(addon, validation_index):
    """Module-level check function for file encoding validation."""
    checker = ValidationFileCheck(addon)
    return checker.check()
