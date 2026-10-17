"""Charts as PNG images (the drift chart, the sound bars, the course strips), with Pillow and with the
built-in drawing; text only with Pillow and a font."""

import builtins
import os
import struct
import sys
import tempfile
import unittest
from unittest import mock

from fake_kodi import ADDON_DIR

if ADDON_DIR not in sys.path:
    sys.path.insert(0, ADDON_DIR)

from mixassist import chart  # noqa: E402

SIZE, PLOT = (400, 200), (40, 30, 300, 170)


def png_size(path):
    with open(path, "rb") as handle:
        data = handle.read(24)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


class ChartTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.series = [chart.Series("Energy", (228, 87, 86), [5.0, 5.5, 6.1]),
                       chart.Series("Sounding year", (218, 218, 218), [1977, 1980, 1983], axis="right")]

    def render(self, name="chart.png"):
        path = os.path.join(self.folder, name)
        used = chart.render_chart(path, [0, 600, 1200], self.series, SIZE, PLOT, (0, 10), (1970, 1990))
        return path, used

    def test_points_fill_the_plot_from_left_to_right(self):
        points = chart.plot_points([0, 50, 100], [0, 5, 10], PLOT, (0, 10))
        self.assertEqual(points, [(40, 170), (170, 100), (300, 30)])
        self.assertEqual(chart.plot_points([0, 1], [20, -5], PLOT, (0, 10)), [(40, 30), (300, 170)])  # clipped

    def test_with_pillow(self):
        path, used = self.render()
        self.assertEqual(used, "pillow")
        self.assertEqual(png_size(path), SIZE)

    def test_without_pillow(self):
        with without_pillow():
            path, used = self.render("plain.png")
        self.assertEqual(used, "plain")
        self.assertEqual(png_size(path), SIZE)

    def test_a_single_measurement_draws_a_flat_line(self):
        path = os.path.join(self.folder, "one.png")
        chart.render_chart(path, [0], [chart.Series("Energy", (228, 87, 86), [5.0])], SIZE, PLOT, (0, 10))
        self.assertEqual(png_size(path), SIZE)


def find_font():
    for path in (r"C:\Program Files\Kodi\media\Fonts\arial.ttf",
                 r"C:\Windows\Fonts\arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.isfile(path):
            return path
    return ""


def without_pillow():
    real_import = builtins.__import__

    def no_pil(name, *args, **kwargs):
        if name == "PIL" or name.startswith("PIL."):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    return mock.patch.object(builtins, "__import__", no_pil)


class BarsAndStripsTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.bars = [chart.Bar("Energy", 2, 5, 8, (228, 87, 86), "5.0 steady (2-8)"),
                     chart.Bar("Sounding year", 1978, 1983, 1990, (218, 218, 218), "1983 (1978-1990)", (1975, 1995))]
        self.strips = [chart.Strip("Energy", [2, 4, None, 6, 8], (228, 87, 86), text="2-8"),
                       chart.Strip("Sounding year", [1980, None], (218, 218, 218), (1975, 1995), "1980-1980")]

    def test_bars_and_strips_with_and_without_pillow(self):
        for name, draw, items in (("bars", chart.render_bars, self.bars), ("strips", chart.render_strips, self.strips)):
            with self.subTest(chart=name):
                path = os.path.join(self.folder, f"{name}.png")
                self.assertEqual(draw(path, items, SIZE), "pillow")
                self.assertEqual(png_size(path), SIZE)
                with without_pillow():
                    self.assertEqual(draw(path, items, SIZE), "plain")
                self.assertEqual(png_size(path), SIZE)

    def test_text_needs_pillow_and_a_font(self):
        font = find_font()
        if not font:
            self.skipTest("no TrueType font here")
        self.assertFalse(chart.can_draw_text(""))
        self.assertFalse(chart.can_draw_text(os.path.join(self.folder, "missing.ttf")))
        self.assertTrue(chart.can_draw_text(font))
        with without_pillow():
            self.assertFalse(chart.can_draw_text(font))
        plain_path, text_path = os.path.join(self.folder, "plain.png"), os.path.join(self.folder, "text.png")
        chart.render_bars(plain_path, self.bars, SIZE)
        chart.render_bars(text_path, self.bars, SIZE, font)
        with open(plain_path, "rb") as plain, open(text_path, "rb") as text:
            self.assertNotEqual(plain.read(), text.read())

    def test_line_chart_text_aligns_right(self):
        font = find_font()
        if not font:
            self.skipTest("no TrueType font here")
        path = os.path.join(self.folder, "texts.png")
        texts = [chart.Text(290, 10, "10", align="right"), chart.Text(310, 10, "1990")]
        series = [chart.Series("Energy", (228, 87, 86), [5.0, 6.0])]
        self.assertEqual(chart.render_chart(path, [0, 1], series, SIZE, PLOT, (0, 10), texts=texts, font_path=font,
                                            points=False), "pillow")
        self.assertEqual(png_size(path), SIZE)


if __name__ == "__main__":
    unittest.main()
