"""Kodi-core colors.xml and strings.po: the installed Kodi, else the target release's snapshot."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_BUNDLED_DATA = Path(__file__).resolve().parent.parent / "data" / "kodi"


def _bundled_dir(release_name: str) -> Optional[Path]:
    """Path to the release's bundled snapshot, or None when absent."""
    candidate = _BUNDLED_DATA / release_name
    return candidate if candidate.is_dir() else None


def _latest_bundled_dir() -> Optional[Path]:
    """Newest supported release that has a bundled snapshot, or None."""
    from .addon.addon import Addon
    for rel in reversed(Addon.RELEASES):
        d = _bundled_dir(rel["name"])
        if d:
            return d
    return None


def _core_file(addon, kodi_path, installed, name, what):
    """Path to a Kodi-core file under kodi_path, else in the release's snapshot; None if neither."""
    if kodi_path:
        candidate = os.path.join(kodi_path, *installed)
        if os.path.isfile(candidate):
            return candidate

    release_name = getattr(addon, "api_version", None) if addon else None
    target = (_bundled_dir(release_name) if release_name else None) or _latest_bundled_dir()
    if target is None:
        logger.warning("No Kodi reference data: %s will be reported as undefined. Set kodi_path.",
                       what)
        return None

    path = target / name
    return str(path) if path.is_file() else None


def kodi_colors_xml(addon, kodi_path: str | None) -> Optional[str]:
    """Return a path to Kodi-core `colors.xml` for the add-on's release, or None."""
    return _core_file(addon, kodi_path, ("system", "colors.xml"), "colors.xml", "core colors")


def kodi_strings_po(addon, kodi_path: str | None) -> Optional[str]:
    """Return a path to Kodi-core `strings.po` for the add-on's release, or None; en_gb only."""
    installed = ("addons", "resource.language.en_gb", "resources", "strings.po")
    return _core_file(addon, kodi_path, installed, "strings.po", "core label ids")
