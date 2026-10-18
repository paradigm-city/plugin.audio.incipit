"""Charts as PNG images: line charts (a station's drift, a mix's course; straight or smooth) and range bars (a
mix's sound). A series on the right-hand scale (the sounding year) is drawn dashed, so it doesn't read as one of the
0-10 scales.

Uses Pillow when Kodi's Python has it (Kodi for Windows ships Pillow 6.2), with smooth lines and, given a TrueType
font, text in the image; otherwise a small built-in drawing (zlib), with plain lines and no text.
"""

from __future__ import annotations

import math
import struct
import zlib
from typing import List, Optional, Sequence, Tuple

BACKGROUND = (24, 27, 34)
GRID = (52, 57, 68)
TEXT = (154, 160, 170)
TRACK = (52, 57, 68)
SUPERSAMPLE = 2


class Text:
    """A text in the image: x, y (top), the text, its colour; align "left" or "right" (x is then the right edge)."""

    def __init__(self, x: float, y: float, text: str, color: Tuple[int, int, int] = TEXT, align: str = "left",
                 size: int = 22):
        self.x, self.y, self.text, self.color, self.align, self.size = x, y, text, color, align, size


def load_font(font_path: str, size: int):
    """A Pillow TrueType font, or None (no Pillow, no font file)."""
    if not font_path:
        return None
    try:
        from PIL import ImageFont
        return ImageFont.truetype(font_path, size)
    except Exception:
        return None


def can_draw_text(font_path: str) -> bool:
    """Whether charts get their text (Pillow and the font are there); otherwise the caller shows it as text."""
    try:
        from PIL import Image, ImageDraw  # noqa: F401
    except Exception:
        return False
    return load_font(font_path, 10) is not None


def text_width(draw, text: str, font) -> float:
    if hasattr(font, "getbbox"):  # Pillow 8 and later
        box = font.getbbox(text)
        return box[2] - box[0]
    return draw.textsize(text, font=font)[0]  # Pillow 6 (Kodi for Windows)


def draw_texts(draw, texts: Sequence["Text"], font_path: str, scale: int) -> None:
    fonts = {}
    for item in texts:
        font = fonts.setdefault(item.size, load_font(font_path, item.size * scale))
        if font is None:
            return
        x = item.x * scale
        if item.align == "right":
            x -= text_width(draw, item.text, font)
        draw.text((x, item.y * scale), item.text, fill=item.color, font=font)


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


def plot_runs(xs: Sequence[float], values: Sequence[Optional[float]], plot: Tuple[int, int, int, int],
              value_range: Tuple[float, float]) -> List[List[Tuple[float, float]]]:
    """Like plot_points, but a value may be None (not measured): the line breaks there."""
    points = plot_points(xs, [value_range[0] if value is None else value for value in values], plot, value_range)
    runs, run = [], []
    for point, value in zip(points, values):
        if value is None:
            if run:
                runs.append(run)
            run = []
        else:
            run.append(point)
    return runs + ([run] if run else [])


def smooth_curve(points: Sequence[Tuple[float, float]], steps: int = 10) -> List[Tuple[float, float]]:
    """A smooth curve through the points, left to right: a monotone cubic spline (Fritsch-Carlson), which doesn't
    swing above or below its neighbours, so a curve stays within the values it was drawn from."""
    if len(points) < 3:
        return list(points)
    xs, ys = [x for x, _ in points], [y for _, y in points]
    count = len(points)
    slopes = [(ys[i + 1] - ys[i]) / ((xs[i + 1] - xs[i]) or 1e-9) for i in range(count - 1)]
    tangents = [slopes[0]] + [0.0 if slopes[i - 1] * slopes[i] <= 0 else (slopes[i - 1] + slopes[i]) / 2
                              for i in range(1, count - 1)] + [slopes[-1]]
    for i, slope in enumerate(slopes):
        if slope == 0:
            tangents[i] = tangents[i + 1] = 0.0
            continue
        a, b = tangents[i] / slope, tangents[i + 1] / slope
        if a * a + b * b > 9:
            factor = 3 / math.sqrt(a * a + b * b)
            tangents[i], tangents[i + 1] = factor * a * slope, factor * b * slope
    curve = [points[0]]
    for i in range(count - 1):
        width = xs[i + 1] - xs[i]
        for step in range(1, steps + 1):
            t = step / steps
            curve.append((xs[i] + t * width,
                          (2 * t ** 3 - 3 * t ** 2 + 1) * ys[i] + (t ** 3 - 2 * t ** 2 + t) * width * tangents[i]
                          + (-2 * t ** 3 + 3 * t ** 2) * ys[i + 1] + (t ** 3 - t ** 2) * width * tangents[i + 1]))
    return curve


def dashes(points: Sequence[Tuple[float, float]], dash: float, gap: float) -> List[List[Tuple[float, float]]]:
    """The pieces of a dashed line along the points."""
    pieces, piece, drawing, left = [], [points[0]], True, dash
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        length = math.hypot(x1 - x0, y1 - y0)
        done = 0.0
        while length - done > left:
            done += left
            point = (x0 + (x1 - x0) * done / length, y0 + (y1 - y0) * done / length)
            if drawing:
                pieces.append(piece + [point])
            piece, drawing, left = [point], not drawing, gap if drawing else dash
        left -= length - done
        if drawing:
            piece.append((x1, y1))
    if drawing and len(piece) > 1:
        pieces.append(piece)
    return pieces


def render_chart(path: str, xs: Sequence[float], series: Sequence[Series], size: Tuple[int, int],
                 plot: Tuple[int, int, int, int], left_range: Tuple[float, float],
                 right_range: Optional[Tuple[float, float]] = None, grid_lines: int = 4,
                 texts: Sequence[Text] = (), font_path: str = "", points: bool = True, smooth: bool = False,
                 line_width: int = 3) -> str:
    """Draw a horizontal grid and one line per series (None values break it); returns which renderer was used."""
    xs = list(xs)
    if len(xs) == 1:  # a single measurement: a flat line across the plot
        xs = [xs[0], xs[0] + 1]
        series = [Series(s.name, s.color, s.values * 2, s.axis) for s in series]
    lines = []  # (colour, points, dashed); the right-hand scale first, behind the others
    for item in sorted(series, key=lambda item: item.axis != "right"):
        value_range = right_range if item.axis == "right" and right_range else left_range
        dashed = item.axis == "right" and right_range is not None
        lines += [(item.color, run, dashed) for run in plot_runs(xs, item.values, plot, value_range)]
    left, top, right, bottom = plot
    grid = [top + (bottom - top) * step / grid_lines for step in range(grid_lines + 1)]
    try:
        from PIL import Image, ImageDraw  # noqa: F401
    except Exception:
        _render_plain(path, size, plot, grid, [(color, run) for color, run, _dashed in lines])
        return "plain"
    _render_pillow(path, size, plot, grid, lines, texts, font_path, points, smooth, line_width)
    return "pillow"


def _render_pillow(path, size, plot, grid, lines, texts=(), font_path="", points=True, smooth=False,
                   line_width=3) -> None:
    from PIL import Image, ImageDraw

    k = SUPERSAMPLE
    image = Image.new("RGB", (size[0] * k, size[1] * k), BACKGROUND)
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = plot
    for y in grid:
        draw.line([(left * k, y * k), (right * k, y * k)], fill=GRID, width=k)
    for color, run, dashed in lines:
        scaled = [(x * k, y * k) for x, y in run]
        curve = smooth_curve(scaled) if smooth else scaled
        for piece in (dashes(curve, 10 * k, 7 * k) if dashed else [curve]):
            draw.line(piece, fill=color, width=line_width * k, joint="curve")
        if points or len(run) == 1:  # a lone value would vanish without its dot
            for x, y in scaled:
                r = (line_width + 1) * k
                draw.ellipse([x - r, y - r, x + r, y + r], fill=color)
    draw_texts(draw, texts, font_path, k)
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


class Bar:
    """One row of a range chart: a name, the range (low to high) and the average, on a 0..scale track."""

    def __init__(self, name: str, low: float, average: float, high: float, color: Tuple[int, int, int], text: str = "",
                 scale: Tuple[float, float] = (0.0, 10.0)):
        self.name, self.low, self.average, self.high, self.color, self.text = name, low, average, high, color, text
        self.scale = scale


def render_bars(path: str, bars: Sequence[Bar], size: Tuple[int, int], font_path: str = "") -> str:
    """A range chart: per row its name (left), a track for the scale, the range as a thick bar and the average as a
    dot, and a text (right). Returns the renderer used."""
    width, height = size
    left, right = int(width * 0.2), int(width * 0.72)
    row_height = height / max(1, len(bars))
    texts, shapes = [], []
    for index, bar in enumerate(bars):
        y = row_height * (index + 0.5)
        low_scale, high_scale = bar.scale
        span = (high_scale - low_scale) or 1.0
        position = lambda value: left + (right - left) * max(0.0, min(1.0, (value - low_scale) / span))  # noqa: E731
        shapes.append(((left, y), (right, y), TRACK, 4, False))
        shapes.append(((position(bar.low), y), (position(bar.high), y), bar.color, 14, False))
        shapes.append(((position(bar.average), y), None, bar.color, 11, True))
        texts.append(Text(20, y - 15, bar.name, bar.color))
        texts.append(Text(right + 30, y - 15, bar.text))
    try:
        from PIL import Image, ImageDraw  # noqa: F401
    except Exception:
        lines = [(color, [a, b]) for a, b, color, _w, dot in shapes if not dot]
        _render_plain(path, size, (left, 0, right, height), [], lines)
        return "plain"
    k = SUPERSAMPLE
    image = Image.new("RGB", (width * k, height * k), BACKGROUND)
    draw = ImageDraw.Draw(image)
    for a, b, color, thickness, dot in shapes:
        if dot:
            r = thickness * k
            draw.ellipse([a[0] * k - r, a[1] * k - r, a[0] * k + r, a[1] * k + r], fill=(240, 240, 240), outline=color,
                         width=3 * k)
        else:
            draw.line([(a[0] * k, a[1] * k), (b[0] * k, b[1] * k)], fill=color, width=thickness * k)
    draw_texts(draw, texts, font_path, k)
    resample = getattr(Image, "LANCZOS", getattr(Image, "ANTIALIAS", 1))
    image.resize(size, resample).save(path, "PNG")
    return "pillow"
