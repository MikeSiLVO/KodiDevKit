"""
Image metadata helpers using only the Python standard library.
"""

from __future__ import annotations

import functools
import imghdr
import os
import re
import struct
from typing import List, Tuple

_InfoList = List[Tuple[str, str]]


@functools.lru_cache(maxsize=128)
def get_image_info(fname: str) -> _InfoList:
    """
    Return basic info for an image file.
    Output: list of (key, value), e.g. [("Type", "png"), ("Dimensions", "800x600")].
    Empty list means unknown or unreadable.
    """
    if not fname or not os.path.exists(fname):
        return []

    kind = imghdr.what(fname)
    info: _InfoList = []

    try:
        with open(fname, "rb") as fh:
            # Read a generous header to cover commented PGM headers.
            head = fh.read(2048)

            if kind == "png" and head.startswith(b"\x89PNG\r\n\x1a\n"):
                # PNG IHDR is at offset 16..24 (big-endian).
                width, height = struct.unpack(">II", head[16:24])
                info = [("Type", "png"), ("Dimensions", f"{width}x{height}")]

            elif kind == "gif" and head[:6] in (b"GIF87a", b"GIF89a"):
                # GIF width/height at offset 6..10 (little-endian).
                width, height = struct.unpack("<HH", head[6:10])
                info = [("Type", "gif"), ("Dimensions", f"{width}x{height}")]

            elif kind == "jpeg":
                fh.seek(0)
                width, height = _read_jpeg_size(fh)
                fh.seek(0)
                progressive = _is_jpeg_progressive(fh)
                info = [
                    ("Type", "jpeg"),
                    ("Dimensions", f"{width}x{height}"),
                    ("Progressive", str(progressive)),
                ]

            elif kind == "bmp":
                fh.seek(0)
                width, height, bpp = _read_bmp_header(fh)
                info = [
                    ("Type", "bmp"),
                    ("Dimensions", f"{width}x{height}"),
                    ("Depth", str(bpp)),
                ]

            else:
                pgm = _match_pgm_header(head)
                if pgm:
                    width, height, maxval = pgm
                    info = [
                        ("Type", "pgm"),
                        ("Dimensions", f"{width}x{height}"),
                        ("Maxval", str(maxval)),
                    ]
                elif kind:
                    info = [("Type", str(kind))]
                else:
                    info = []

    except Exception:
        return []

    try:
        size_bytes = os.path.getsize(fname)
        units = ("B", "KB", "MB")
        size = float(size_bytes)
        u = 0
        while size >= 1024 and u < len(units) - 1:
            size /= 1024.0
            u += 1
        if u == 0:
            info.append(("FileSize", f"{size_bytes} b"))
        else:
            info.append(("FileSize", f"{size:.1f} {units[u]}"))
    except OSError:
        pass

    return info


def _match_pgm_header(head: bytes) -> Tuple[int, int, int] | None:
    """
    Parse a P5 (binary) PGM header from the initial bytes.
    Returns (width, height, maxval) or None if not matched.
    Allows comment lines starting with '#'.
    """
    m = re.search(
        rb"(^P5\s+(?:#.*[\r\n])*\s*"
        rb"(\d+)\s+(?:#.*[\r\n])*\s*"
        rb"(\d+)\s+(?:#.*[\r\n])*\s*"
        rb"(\d+)\s)",
        head,
        flags=re.MULTILINE,
    )
    if not m:
        return None
    width = int(m.group(2))
    height = int(m.group(3))
    maxval = int(m.group(4))
    return width, height, maxval


def _read_bmp_header(fh) -> Tuple[int, int, int]:
    """Return (width, height, bits_per_pixel) from an open BMP file object."""
    fh.seek(0)
    header = fh.read(54)
    if len(header) < 54 or header[:2] != b"BM":
        raise ValueError("Not a BMP file")
    # Width @ 0x12, Height @ 0x16 (signed int), BitsPerPixel @ 0x1C (unsigned short).
    width, height = struct.unpack("<ii", header[18:26])
    bpp = struct.unpack("<H", header[28:30])[0]
    return width, height, bpp


def _read_jpeg_size(fh) -> Tuple[int, int]:
    """Parse JPEG frame header to get (width, height)."""
    fh.seek(0)
    if fh.read(2) != b"\xff\xd8":  # SOI
        raise ValueError("Not a JPEG file")

    while True:
        b = fh.read(1)
        if not b:
            raise ValueError("Unexpected EOF in JPEG")
        if b != b"\xff":
            continue

        # Collapse fill 0xFF bytes.
        while True:
            marker = fh.read(1)
            if marker != b"\xff":
                break
        if not marker:
            raise ValueError("Truncated JPEG")
        m = marker[0]

        # Restart markers have no length.
        if 0xD0 <= m <= 0xD7:
            continue
        if m == 0xD9:  # EOI without SOF
            raise ValueError("No frame header found")

        # Read segment length (includes these two bytes).
        seg_len_bytes = fh.read(2)
        if len(seg_len_bytes) != 2:
            raise ValueError("Truncated JPEG segment")
        seg_len = struct.unpack(">H", seg_len_bytes)[0]

        if m in (0xC0, 0xC1, 0xC2, 0xC3):  # SOF0..SOF3
            # Precision (1), Height(2), Width(2), Components(1)...
            sof = fh.read(5)
            if len(sof) != 5:
                raise ValueError("Truncated SOF segment")
            height, width = struct.unpack(">HH", sof[1:5])
            return width, height

        # Skip remainder of this segment.
        fh.seek(seg_len - 2, os.SEEK_CUR)


def _is_jpeg_progressive(fh) -> bool:
    """Return True if the open JPEG file object is progressive."""
    pos = fh.tell()
    try:
        fh.seek(0)
        if fh.read(2) != b"\xff\xd8":  # SOI
            return False

        while True:
            b = fh.read(1)
            if not b:
                return False
            if b != b"\xff":
                continue

            while True:
                marker = fh.read(1)
                if marker != b"\xff":
                    break
            if not marker:
                return False
            m = marker[0]

            if m == 0xC2:  # SOF2 progressive
                return True
            if m == 0xC0:  # SOF0 baseline
                return False
            if 0xD0 <= m <= 0xD7:  # Restart
                continue
            if m == 0xD9:  # EOI
                return False

            seg_len_bytes = fh.read(2)
            if len(seg_len_bytes) != 2:
                return False
            seg_len = struct.unpack(">H", seg_len_bytes)[0]
            fh.seek(seg_len - 2, os.SEEK_CUR)
    finally:
        fh.seek(pos)
