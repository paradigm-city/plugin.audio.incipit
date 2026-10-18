"""Charts as PNG images (the drift and course line charts, the sound bars), with Pillow and with the built-in
drawing; text only with Pillow and a font."""

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


class SmoothLinesTest(unittest.TestCase):
    def test_the_curve_goes_through_the_points_and_not_beyond_them(self):
        points = [(0, 10), (10, 30), (20, 30), (30, 0), (40, 20), (50, 21), (60, 60)]  # the last: a steep rise
        curve = chart.smooth_curve(points, steps=10)
        self.assertEqual(len(curve), 61)
        for point in points:
            self.assertIn(point, [(round(x, 6), round(y, 6)) for x, y in curve])
        for (x0, y0), (x1, y1) in zip(points, points[1:]):  # monotone: each piece stays between its two values
            piece = [y for x, y in curve if x0 <= x <= x1]
            self.assertGreaterEqual(min(piece), min(y0, y1) - 1e-9)
            self.assertLessEqual(max(piece), max(y0, y1) + 1e-9)
        self.assertEqual(chart.smooth_curve(points[:2]), points[:2])

    def test_a_missing_value_breaks_the_line(self):
        runs = chart.plot_runs([0, 1, 2, 3, 4], [5, 6, None, 7, None], PLOT, (0, 10))
        self.assertEqual([len(run) for run in runs], [2, 1])
        self.assertEqual(runs[1][0][0], 40 + 260 * 3 / 4)  # the x scale is the whole series'

    def test_see_through_lines(self):
        folder = tempfile.mkdtemp()
        series = [chart.Series("Energy", (255, 0, 0), [4, 4])]  # away from the grid
        for opacity in (1.0, 0.7):
            chart.render_chart(os.path.join(folder, f"{opacity}.png"), [0, 1], series, SIZE, PLOT, (0, 10),
                               points=False, line_width=12, opacity=opacity)  # wide: no edge in the middle
        from PIL import Image
        middle = (170, 114)  # on the line
        solid = Image.open(os.path.join(folder, "1.0.png")).getpixel(middle)
        faint = Image.open(os.path.join(folder, "0.7.png")).getpixel(middle)
        self.assertEqual(solid[:3], (255, 0, 0))
        expected = tuple(int(c * 178 / 255 + b * 77 / 255) for c, b in zip((255, 0, 0), chart.BACKGROUND))
        self.assertTrue(all(abs(f - e) <= 1 for f, e in zip(faint, expected)), (faint, expected))

    def test_a_smooth_chart_with_gaps_and_a_second_scale(self):
        folder = tempfile.mkdtemp()
        series = [chart.Series("Energy", (228, 87, 86), [5, 6, None, 4, 7, 7]),
                  chart.Series("Sounding year", (218, 218, 218), [1980, 1985, 1983, None, 1990, 1981], axis="right")]
        for renderer in ("pillow", "plain"):
            with self.subTest(renderer=renderer):
                path = os.path.join(folder, f"{renderer}.png")
                if renderer == "plain":
                    with without_pillow():
                        used = chart.render_chart(path, range(6), series, SIZE, PLOT, (0, 10), (1975, 1995), smooth=True)
                else:
                    used = chart.render_chart(path, range(6), series, SIZE, PLOT, (0, 10), (1975, 1995), smooth=True,
                                              points=False, line_width=2, opacity=0.7)
                self.assertEqual((used, png_size(path)), (renderer, SIZE))


class BarsTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.bars = [chart.Bar("Energy", 2, 5, 8, (228, 87, 86), "5.0 steady (2-8)"),
                     chart.Bar("Sounding year", 1978, 1983, 1990, (218, 218, 218), "1983 (1978-1990)", (1975, 1995))]

    def test_bars_with_and_without_pillow(self):
        path = os.path.join(self.folder, "bars.png")
        self.assertEqual(chart.render_bars(path, self.bars, SIZE), "pillow")
        self.assertEqual(png_size(path), SIZE)
        with without_pillow():
            self.assertEqual(chart.render_bars(path, self.bars, SIZE), "plain")
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
