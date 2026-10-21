"""Tests for the image type and size reading behind image hovers."""

import os
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from libs.utils.images import get_image_info, has_transparent_pixels


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


ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))


def _paeth(a, b, c):
    """Value the Paeth filter predicts a byte from its left, upper and upper-left neighbors."""
    guess = a + b - c
    near_a, near_b, near_c = abs(guess - a), abs(guess - b), abs(guess - c)
    return a if near_a <= near_b and near_a <= near_c else b if near_b <= near_c else c


def _scanlines(rows, pixel, filter_type):
    """Sample bytes encoded as PNG scanlines, all with one filter."""
    out, prior = b"", bytes(len(rows[0]))
    for row in rows:
        line = bytearray([filter_type])
        for i, value in enumerate(row):
            left = row[i - pixel] if i >= pixel else 0
            corner = prior[i - pixel] if i >= pixel else 0
            guess = (0, left, prior[i], (left + prior[i]) // 2, _paeth(left, prior[i], corner))[filter_type]
            line.append((value - guess) & 255)
        out += bytes(line)
        prior = row
    return out


def _pixels_png(pixels, color=6, depth=8, filter_type=0, interlace=False):
    """Full PNG of a grid of pixels, each a bytes of its samples."""
    width, pixel = len(pixels[0]), len(pixels[0][0])
    if interlace:
        data = b""
        for x0, y0, dx, dy in ADAM7:
            rows = [b"".join(row[x0::dx]) for row in pixels[y0::dy]]
            if rows and rows[0]:
                data += _scanlines(rows, pixel, filter_type)
    else:
        data = _scanlines([b"".join(row) for row in pixels], pixel, filter_type)

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    ihdr = struct.pack(">IIBBBBB", width, len(pixels), depth, color, 0, 0, int(interlace))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(data)) + chunk(b"IEND", b"")


def _rgba(alpha_at=None, alpha=0, size=9):
    """A square grid of varied colors, opaque but for one pixel when given."""
    return [[bytes(((x * 37 + y) & 255, (y * 53) & 255, (x * y) & 255, alpha if (x, y) == alpha_at else 255))
             for x in range(size)] for y in range(size)]


class TestTransparentPixels(unittest.TestCase):
    """Transparency read the way the add-on checker reads it: alpha of a PNG it opens as RGBA."""

    def setUp(self):
        """Set up a temp folder for the image files."""
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _read(self, data):
        """Write the bytes to a file and read its transparency."""
        path = os.path.join(self.tmp.name, "a.png")
        with open(path, "wb") as fh:
            fh.write(data)
        return has_transparent_pixels(path)

    def test_every_filter_type_reads_opaque_and_transparent(self):
        """Each filter type, plain and interlaced, finds a transparent pixel and no false one."""
        for filter_type in range(5):
            for interlace in (False, True):
                with self.subTest(filter_type=filter_type, interlace=interlace):
                    self.assertIs(self._read(_pixels_png(_rgba(), filter_type=filter_type, interlace=interlace)),
                                  False)
                    for spot in ((0, 0), (8, 0), (0, 8), (5, 7), (8, 8)):
                        grid = _rgba(spot, alpha=254)
                        self.assertIs(self._read(_pixels_png(grid, filter_type=filter_type, interlace=interlace)),
                                      True)

    def test_sixteen_bit_alpha_counts_by_its_high_byte(self):
        """16-bit gray with alpha reads as RGBA, transparent once the alpha's high byte drops."""
        def gray(alpha):
            return [[b"\x80\x00" + struct.pack(">H", alpha if (x, y) == (3, 2) else 65535) for x in range(5)]
                    for y in range(4)]
        self.assertIs(self._read(_pixels_png(gray(0xFF00), color=4, depth=16, filter_type=4)), False)
        self.assertIs(self._read(_pixels_png(gray(0xFEFF), color=4, depth=16, filter_type=4)), True)

    def test_images_not_read_as_rgba(self):
        """8-bit gray with alpha, RGB and other files are not read as RGBA."""
        self.assertIsNone(self._read(_pixels_png([[b"\x80\x00"] * 3] * 3, color=4)))
        self.assertIsNone(self._read(_pixels_png([[b"\x80\x80\x80"] * 3] * 3, color=2)))
        self.assertIsNone(self._read(_jpeg(10, 10, False)))
        self.assertIsNone(self._read(_png(10, 10)))


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
