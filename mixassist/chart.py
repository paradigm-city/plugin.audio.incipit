"""Line charts as PNG images (the station drift chart). Kodi draws the text; this draws the panel, grid and lines.

Uses Pillow when Kodi's Python has it (Kodi for Windows ships Pillow 6.2), with smooth lines; otherwise a small
built-in drawing (zlib), with plain lines.
"""

from __future__ import annotations

import struct
import zlib
from typing import List, Optional, Sequence, Tuple

BACKGROUND = (24, 27, 34)
BORDER = (70, 76, 90)
GRID = (52, 57, 68)
SUPERSAMPLE = 2


class Series:
    def __init__(self, name: str, color: Tuple[int, int, int], values: Sequence[float], axis: str = "left"):
        self.name, self.color, self.values, self.axis = name, color, list(values), axis


def hex_color(text: str) -> Tuple[int, int, int]:
    text = text.lstrip("#")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def plot_points(xs: Sequence[float], values: Sequence[float], plot: Tuple[int, int, int, int],
                value_range: Tuple[float, float]) -> List[Tuple[float, float]]:
    """Pixel positions of a series inside plot = (left, top, right, bottom)."""
    left, top, right, bottom = plot
    x_low, x_high = min(xs), max(xs)
    v_low, v_high = value_range
    points = []
    for x, value in zip(xs, values):
        px = left + (right - left) * ((x - x_low) / (x_high - x_low) if x_high > x_low else 1.0)
        share = (value - v_low) / (v_high - v_low) if v_high > v_low else 0.5
        points.append((px, bottom - (bottom - top) * max(0.0, min(1.0, share))))
    return points


def render_chart(path: str, xs: Sequence[float], series: Sequence[Series], size: Tuple[int, int],
                 plot: Tuple[int, int, int, int], left_range: Tuple[float, float],
                 right_range: Optional[Tuple[float, float]] = None, grid_lines: int = 4) -> str:
    """Draw the panel, a horizontal grid and one line per series; returns which renderer was used."""
    xs = list(xs)
    if len(xs) == 1:  # a single measurement: a flat line across the plot
        xs = [xs[0], xs[0] + 1]
        series = [Series(s.name, s.color, s.values * 2, s.axis) for s in series]
    lines = []
    for item in series:
        value_range = right_range if item.axis == "right" and right_range else left_range
        lines.append((item.color, plot_points(xs, item.values, plot, value_range)))
    left, top, right, bottom = plot
    grid = [top + (bottom - top) * step / grid_lines for step in range(grid_lines + 1)]
    try:
        from PIL import Image, ImageDraw  # noqa: F401
    except Exception:
        _render_plain(path, size, plot, grid, lines)
        return "plain"
    _render_pillow(path, size, plot, grid, lines)
    return "pillow"


def _render_pillow(path, size, plot, grid, lines) -> None:
    from PIL import Image, ImageDraw

    k = SUPERSAMPLE
    image = Image.new("RGB", (size[0] * k, size[1] * k), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, size[0] * k - 1, size[1] * k - 1], outline=BORDER, width=2 * k)
    left, top, right, bottom = plot
    for y in grid:
        draw.line([(left * k, y * k), (right * k, y * k)], fill=GRID, width=k)
    for color, points in lines:
        scaled = [(x * k, y * k) for x, y in points]
        draw.line(scaled, fill=color, width=3 * k)
        for x, y in scaled:
            r = 4 * k
            draw.ellipse([x - r, y - r, x + r, y + r], fill=color)
    resample = getattr(Image, "LANCZOS", getattr(Image, "ANTIALIAS", 1))
    image.resize(size, resample).save(path, "PNG")


def _render_plain(path, size, plot, grid, lines) -> None:
    width, height = size
    pixels = bytearray(bytes(BACKGROUND) * (width * height))

    def dot(x: int, y: int, color, radius: int) -> None:
        for yy in range(max(0, y - radius), min(height, y + radius + 1)):
            for xx in range(max(0, x - radius), min(width, x + radius + 1)):
                offset = (yy * width + xx) * 3
                pixels[offset:offset + 3] = bytes(color)

    def line(a, b, color, radius: int) -> None:
        (x0, y0), (x1, y1) = (int(round(a[0])), int(round(a[1]))), (int(round(b[0])), int(round(b[1])))
        steps = max(abs(x1 - x0), abs(y1 - y0), 1)
        for step in range(steps + 1):
            dot(x0 + (x1 - x0) * step // steps, y0 + (y1 - y0) * step // steps, color, radius)

    for x in range(width):
        for y in (0, 1, height - 2, height - 1):
            dot(x, y, BORDER, 0)
    for y in range(height):
        for x in (0, 1, width - 2, width - 1):
            dot(x, y, BORDER, 0)
    left, top, right, bottom = plot
    for y in grid:
        line((left, y), (right, y), GRID, 0)
    for color, points in lines:
        for a, b in zip(points, points[1:]):
            line(a, b, color, 1)
        for x, y in points:
            dot(int(round(x)), int(round(y)), color, 3)
    write_png(path, width, height, bytes(pixels))


def write_png(path: str, width: int, height: int, rgb: bytes) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    rows = b"".join(b"\x00" + rgb[y * width * 3:(y + 1) * width * 3] for y in range(height))
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) \
        + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b"")
    with open(path, "wb") as handle:
        handle.write(data)
