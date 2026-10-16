"""Tests for the image type and size reading behind image hovers."""

import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from libs.utils.images import get_image_info


def _png(width, height):
    """PNG signature plus an IHDR chunk, nothing else."""
    ihdr = struct.pack(">II", width, height) + b"\x08\x06\x00\x00\x00"
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr + b"\x00" * 4


def _gif(width, height):
    """GIF89a header with a logical screen size."""
    return b"GIF89a" + struct.pack("<HH", width, height) + b"\x00" * 7


def _bmp(width, height, bpp):
    """54-byte BMP file header with no pixel data."""
    header = bytearray(54)
    header[:2] = b"BM"
    header[18:26] = struct.pack("<ii", width, height)
    header[28:30] = struct.pack("<H", bpp)
    return bytes(header)


def _jpeg(width, height, progressive):
    """SOI, one SOF frame header, EOI."""
    sof = b"\xff\xc2" if progressive else b"\xff\xc0"
    sof += struct.pack(">H", 11) + b"\x08" + struct.pack(">HH", height, width) + b"\x01\x01\x11\x00"
    return b"\xff\xd8" + sof + b"\xff\xd9"


class TestImageInfo(unittest.TestCase):
    """Image type and size come from the file bytes, never the extension."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _write(self, name, data):
        path = os.path.join(self.tmp.name, name)
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def _info(self, name, data):
        return dict(get_image_info(self._write(name, data)))

    def test_png(self):
        info = self._info("a.png", _png(800, 600))
        self.assertEqual(info["Type"], "png")
        self.assertEqual(info["Dimensions"], "800x600")

    def test_replaced_file_is_read_again(self):
        """An image overwritten at the same path reports its new dimensions."""
        path = self._write("icon.png", _png(800, 600))
        self.assertEqual(dict(get_image_info(path))["Dimensions"], "800x600")
        self._write("icon.png", _png(512, 512))
        stamp = os.stat(path).st_mtime_ns + 1_000_000_000
        os.utime(path, ns=(stamp, stamp))
        self.assertEqual(dict(get_image_info(path))["Dimensions"], "512x512")

    def test_gif(self):
        info = self._info("a.gif", _gif(64, 32))
        self.assertEqual(info["Type"], "gif")
        self.assertEqual(info["Dimensions"], "64x32")

    def test_bmp(self):
        info = self._info("a.bmp", _bmp(20, 10, 24))
        self.assertEqual(info["Type"], "bmp")
        self.assertEqual(info["Dimensions"], "20x10")
        self.assertEqual(info["Depth"], "24")

    def test_jpeg_baseline(self):
        info = self._info("a.jpg", _jpeg(1920, 1080, progressive=False))
        self.assertEqual(info["Type"], "jpeg")
        self.assertEqual(info["Dimensions"], "1920x1080")
        self.assertEqual(info["Progressive"], "False")

    def test_jpeg_progressive(self):
        info = self._info("p.jpg", _jpeg(4, 2, progressive=True))
        self.assertEqual(info["Progressive"], "True")

    def test_webp_reports_type_only(self):
        info = self._info("a.webp", b"RIFF\x00\x00\x00\x00WEBPVP8 ")
        self.assertEqual(info["Type"], "webp")
        self.assertNotIn("Dimensions", info)

    def test_extension_does_not_decide(self):
        info = self._info("lies.png", _gif(3, 3))
        self.assertEqual(info["Type"], "gif")

    def test_unknown_bytes_give_only_size(self):
        info = self._info("a.bin", b"not an image at all")
        self.assertEqual(list(info), ["FileSize"])

    def test_missing_file(self):
        self.assertEqual(get_image_info(os.path.join(self.tmp.name, "nope.png")), [])


if __name__ == "__main__":
    unittest.main()
