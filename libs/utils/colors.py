"""Color utilities for Kodi skinning."""

from __future__ import annotations

import colorsys
import string
from typing import Optional


def is_kodi_hex(text: str) -> bool:
    """Check if text is Kodi AARRGGBB hex format (8 hex characters)."""
    return len(text) == 8 and all(c in string.hexdigits for c in text)


def to_hex(red: int, green: int, blue: int, alpha: Optional[int] = None) -> str:
    """Convert RGB(A) values to hex string for Sublime Text tooltips."""
    r = max(0, min(255, red))
    g = max(0, min(255, green))
    b = max(0, min(255, blue))
    a = max(0, min(255, alpha if alpha is not None else 255))
    return f"#{r:02X}{g:02X}{b:02X}{a:02X}"


def get_contrast_color(col: str) -> str:
    """Calculate contrasting color to ensure readability against given color."""
    MIN_CONTRAST = 0.15
    (hue, lum, saturation) = colorsys.rgb_to_hls(
        int(col[1:3], 16) / 255.0,
        int(col[3:5], 16) / 255.0,
        int(col[5:7], 16) / 255.0
    )
    lightness = 1 - lum
    if abs(lightness - lum) < MIN_CONTRAST:
        lightness = 1.0 - MIN_CONTRAST if lum < 0.5 else MIN_CONTRAST
    (red, green, blue) = colorsys.hls_to_rgb(hue, lightness, saturation)
    return to_hex(int(red * 255), int(green * 255), int(blue * 255))
