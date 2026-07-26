"""Resolve Kodi reference data (`colors.xml`, `strings.po`) for a skin.

Priority order:
  1. User's installed Kodi (`kodi_path` setting, when set + valid).
  2. Bundled snapshot for the release the skin targets (from `<import addon="xbmc.python">`).
  3. Bundled snapshot for the most recent supported release.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("kdk.kodi_refs")

_BUNDLED_DATA = Path(__file__).resolve().parent.parent / "data" / "kodi"


def _bundled_dir(release_name: str) -> Optional[Path]:
    """Path to the bundled snapshot for `release_name`, or `None` if not present."""
    candidate = _BUNDLED_DATA / release_name
    return candidate if candidate.is_dir() else None


def _latest_bundled_dir() -> Optional[Path]:
    """Fallback: the bundled release matching the last entry in `Addon.RELEASES`."""
    from .addon.addon import Addon
    for rel in reversed(Addon.RELEASES):
        d = _bundled_dir(rel["name"])
        if d:
            return d
    return None


def kodi_colors_xml(addon, kodi_path: str | None) -> Optional[str]:
    """Return a path to `colors.xml` for `addon`'s target release, or `None`."""
    if kodi_path:
        candidate = os.path.join(kodi_path, "system", "colors.xml")
        if os.path.isfile(candidate):
            return candidate

    release_name = getattr(addon, "api_version", None) if addon else None
    target = _bundled_dir(release_name) if release_name else None
    if target is None:
        target = _latest_bundled_dir()

    if target is None:
        logger.debug("No bundled Kodi colors snapshot available")
        return None

    path = target / "colors.xml"
    return str(path) if path.is_file() else None


def kodi_strings_po(addon, kodi_path: str | None) -> Optional[str]:
    """Return a path to Kodi-core `strings.po` for `addon`'s target release, or `None`.

    Only English (`resource.language.en_gb`) is bundled; the user's local Kodi may
    have other languages, but for validation purposes the en_gb msgctxt set is what
    matters (label IDs are language-independent).
    """
    if kodi_path:
        candidate = os.path.join(
            kodi_path, "addons", "resource.language.en_gb",
            "resources", "strings.po",
        )
        if os.path.isfile(candidate):
            return candidate

    release_name = getattr(addon, "api_version", None) if addon else None
    target = _bundled_dir(release_name) if release_name else None
    if target is None:
        target = _latest_bundled_dir()

    if target is None:
        logger.debug("No bundled Kodi strings snapshot available")
        return None

    path = target / "strings.po"
    return str(path) if path.is_file() else None
