"""Line charts as PNG images (the station drift chart), with Pillow and with the built-in drawing."""

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
        real_import = builtins.__import__

        def no_pil(name, *args, **kwargs):
            if name == "PIL" or name.startswith("PIL."):
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        with mock.patch.object(builtins, "__import__", no_pil):
            path, used = self.render("plain.png")
        self.assertEqual(used, "plain")
        self.assertEqual(png_size(path), SIZE)

    def test_a_single_measurement_draws_a_flat_line(self):
        path = os.path.join(self.folder, "one.png")
        chart.render_chart(path, [0], [chart.Series("Energy", (228, 87, 86), [5.0])], SIZE, PLOT, (0, 10))
        self.assertEqual(png_size(path), SIZE)


if __name__ == "__main__":
    unittest.main()
