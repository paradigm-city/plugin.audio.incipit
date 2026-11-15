"""A small diagram kit on Pillow: boxes, stores, decisions, groups, orthogonal arrows, sequence diagrams, charts."""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFont

FONTS = "C:/Windows/Fonts/"
REG, BOLD, SEMI, MONO = "segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "consola.ttf"

INK = (31, 41, 55)
MUTED = (107, 114, 128)
LINE = (55, 65, 81)
WHITE = (255, 255, 255)

KINDS = {  # fill, stroke
    "kodi": ((224, 236, 255), (59, 111, 216)),
    "core": ((221, 244, 238), (19, 138, 114)),
    "ai": ((255, 241, 214), (199, 124, 2)),
    "sound": ((232, 245, 217), (78, 138, 30)),
    "ext": ((241, 241, 244), (107, 114, 128)),
    "store": ((238, 231, 251), (109, 75, 194)),
    "warn": ((253, 226, 226), (192, 57, 43)),
    "plain": ((255, 255, 255), (55, 65, 81)),
    "note": ((255, 251, 230), (180, 150, 40)),
    "user": ((252, 231, 243), (190, 24, 93)),
}

_cache = {}
FS = 1.3  # all text this much larger than its nominal size (readable in the document)


def font(size, face=REG):
    key = (size, face)
    if key not in _cache:
        _cache[key] = ImageFont.truetype(FONTS + face, size)
    return _cache[key]


class Box:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h

    @property
    def n(self): return (self.x + self.w / 2, self.y)
    @property
    def s(self): return (self.x + self.w / 2, self.y + self.h)
    @property
    def e(self): return (self.x + self.w, self.y + self.h / 2)
    @property
    def w_(self): return (self.x, self.y + self.h / 2)
    @property
    def c(self): return (self.x + self.w / 2, self.y + self.h / 2)

    def side(self, name, frac=0.5):
        if name == "n": return (self.x + self.w * frac, self.y)
        if name == "s": return (self.x + self.w * frac, self.y + self.h)
        if name == "e": return (self.x + self.w, self.y + self.h * frac)
        if name == "w": return (self.x, self.y + self.h * frac)
        return self.c


class Canvas:
    def __init__(self, w, h, scale=2, bg=WHITE):
        self.W, self.H, self.k = w, h, scale
        self.img = Image.new("RGB", (int(w * scale), int(h * scale)), bg)
        self.d = ImageDraw.Draw(self.img)

    # --- low level, logical coordinates ---
    def _p(self, pts):
        return [(x * self.k, y * self.k) for x, y in pts]

    def f(self, size, face=REG):
        return font(int(size * FS * self.k), face)

    def textlen(self, s, size, face=REG):
        return self.f(size, face).getlength(s) / self.k

    def wrap(self, text, width, size, face=REG):
        out = []
        for para in str(text).split("\n"):
            words, line = para.split(" "), ""
            pieces = []
            for word in words:  # a long identifier is broken after its underscores
                if self.textlen(word, size, face) > width and "_" in word:
                    part = ""
                    for bit in word.split("_"):
                        bit_ = bit + "_"
                        if part and self.textlen(part + bit_, size, face) > width:
                            pieces.append(part)
                            part = ""
                        part += bit_
                    pieces.append(part[:-1])
                else:
                    pieces.append(word)
            words = pieces
            for word in words:
                trial = (line + " " + word).strip()
                if self.textlen(trial, size, face) <= width or not line:
                    line = trial
                else:
                    out.append(line)
                    line = word
            out.append(line)
        return out

    def text(self, x, y, s, size=16, face=REG, color=INK, anchor="la"):
        self.d.text((x * self.k, y * self.k), s, font=self.f(size, face), fill=color, anchor=anchor)

    def textblock(self, x, y, w, s, size=16, face=REG, color=INK, align="left", leading=1.3):
        lines = self.wrap(s, w, size, face)
        for i, line in enumerate(lines):
            yy = y + i * size * FS * leading
            if align == "center":
                self.text(x + w / 2, yy, line, size, face, color, "ma")
            else:
                self.text(x, yy, line, size, face, color, "la")
        return len(lines) * size * FS * leading

    def rect(self, x, y, w, h, fill=None, outline=None, width=2, radius=0, dash=False):
        if dash:
            self.dashed_rect(x, y, w, h, outline, width, radius)
            return
        box = [x * self.k, y * self.k, (x + w) * self.k, (y + h) * self.k]
        if radius:
            self.d.rounded_rectangle(box, radius * self.k, fill=fill, outline=outline, width=int(width * self.k))
        else:
            self.d.rectangle(box, fill=fill, outline=outline, width=int(width * self.k))

    def dashed_rect(self, x, y, w, h, color, width=2, radius=0):
        r = radius
        self.dline([(x + r, y), (x + w - r, y)], color, width)
        self.dline([(x + r, y + h), (x + w - r, y + h)], color, width)
        self.dline([(x, y + r), (x, y + h - r)], color, width)
        self.dline([(x + w, y + r), (x + w, y + h - r)], color, width)
        if r:
            k = self.k
            for cx, cy, a0 in ((x + r, y + r, 180), (x + w - r, y + r, 270), (x + w - r, y + h - r, 0), (x + r, y + h - r, 90)):
                self.d.arc([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k], a0, a0 + 90, fill=color,
                           width=int(width * k))

    def line(self, pts, color=LINE, width=2):
        self.d.line(self._p(pts), fill=color, width=int(width * self.k), joint="curve")

    def dline(self, pts, color=LINE, width=2, dash=8, gap=6):
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            length = math.hypot(x2 - x1, y2 - y1)
            if not length:
                continue
            ux, uy = (x2 - x1) / length, (y2 - y1) / length
            t = 0.0
            while t < length:
                e = min(t + dash, length)
                self.line([(x1 + ux * t, y1 + uy * t), (x1 + ux * e, y1 + uy * e)], color, width)
                t = e + gap

    def head(self, tip, frm, color=LINE, size=11):
        x, y = tip
        a = math.atan2(y - frm[1], x - frm[0])
        p1 = (x - size * math.cos(a - 0.4), y - size * math.sin(a - 0.4))
        p2 = (x - size * math.cos(a + 0.4), y - size * math.sin(a + 0.4))
        self.d.polygon(self._p([tip, p1, p2]), fill=color)

    def label(self, x, y, s, size=14, color=MUTED, bg=WHITE, face=REG):
        lines = s.split("\n")
        w = max(self.textlen(l, size, face) for l in lines) + 8
        h = len(lines) * size * FS * 1.25 + 4
        self.rect(x - w / 2, y - h / 2, w, h, fill=bg)
        for i, l in enumerate(lines):
            self.text(x, y - h / 2 + 2 + i * size * FS * 1.25, l, size, face, color, "ma")

    # --- shapes ---
    def box(self, x, y, w, h, title=None, text=None, kind="core", shape="round", tsize=18, size=15, align="center",
            title_face=SEMI, dash=False):
        fill, stroke = KINDS[kind]
        if shape == "round":
            self.rect(x, y, w, h, fill, None, radius=10)
            self.rect(x, y, w, h, None if dash else None, stroke, 2, radius=10, dash=dash)
        elif shape == "rect":
            self.rect(x, y, w, h, fill, stroke, 2)
        elif shape == "store":
            self.cylinder(x, y, w, h, fill, stroke)
        elif shape == "diamond":
            pts = [(x + w / 2, y), (x + w, y + h / 2), (x + w / 2, y + h), (x, y + h / 2)]
            self.d.polygon(self._p(pts), fill=fill, outline=stroke, width=int(2 * self.k))
        elif shape == "doc":
            fold = 14
            pts = [(x, y), (x + w - fold, y), (x + w, y + fold), (x + w, y + h), (x, y + h)]
            self.d.polygon(self._p(pts), fill=fill, outline=stroke, width=int(2 * self.k))
            self.line([(x + w - fold, y), (x + w - fold, y + fold), (x + w, y + fold)], stroke, 2)
        elif shape == "actor":
            self.actor(x + w / 2, y, h, stroke)
            if title:
                self.text(x + w / 2, y + h + 4, title, tsize, title_face, INK, "ma")
            return Box(x, y, w, h)
        top = y + (14 if shape == "store" else 0)
        inner_w = w - 20 if shape != "diamond" else w * 0.62
        lines_t = self.wrap(title, inner_w, tsize, title_face) if title else []
        lines_b = self.wrap(text, inner_w, size) if text else []
        th = len(lines_t) * tsize * FS * 1.25 + (6 if lines_b and lines_t else 0) + len(lines_b) * size * FS * 1.3
        yy = top + (h - (top - y) - th) / 2
        for l in lines_t:
            if align == "center":
                self.text(x + w / 2, yy, l, tsize, title_face, INK, "ma")
            else:
                self.text(x + 12, yy, l, tsize, title_face, INK)
            yy += tsize * FS * 1.25
        if lines_b and lines_t:
            yy += 6
        for l in lines_b:
            if align == "center":
                self.text(x + w / 2, yy, l, size, REG, INK, "ma")
            else:
                self.text(x + 12, yy, l, size, REG, INK)
            yy += size * FS * 1.3
        return Box(x, y, w, h)

    def cylinder(self, x, y, w, h, fill, stroke, e=14):
        k = self.k
        self.d.rectangle([x * k, (y + e / 2) * k, (x + w) * k, (y + h - e / 2) * k], fill=fill)
        self.d.ellipse([x * k, (y + h - e) * k, (x + w) * k, (y + h) * k], fill=fill, outline=stroke, width=int(2 * k))
        self.d.rectangle([x * k + 2 * k, (y + e / 2) * k, (x + w) * k - 2 * k, (y + h - e / 2) * k], fill=fill)
        self.line([(x, y + e / 2), (x, y + h - e / 2)], stroke)
        self.line([(x + w, y + e / 2), (x + w, y + h - e / 2)], stroke)
        self.d.ellipse([x * k, y * k, (x + w) * k, (y + e) * k], fill=fill, outline=stroke, width=int(2 * k))

    def actor(self, cx, y, h, color):
        r = h * 0.14
        k = self.k
        self.d.ellipse([(cx - r) * k, y * k, (cx + r) * k, (y + 2 * r) * k], outline=color, width=int(2.5 * k))
        body = y + 2 * r
        self.line([(cx, body), (cx, y + h * 0.66)], color, 2.5)
        self.line([(cx - h * 0.25, body + h * 0.12), (cx + h * 0.25, body + h * 0.12)], color, 2.5)
        self.line([(cx, y + h * 0.66), (cx - h * 0.2, y + h)], color, 2.5)
        self.line([(cx, y + h * 0.66), (cx + h * 0.2, y + h)], color, 2.5)

    def group(self, x, y, w, h, label, kind="ext", size=16):
        fill, stroke = KINDS[kind]
        light = tuple(int(c + (255 - c) * 0.55) for c in fill)
        self.rect(x, y, w, h, light, None, radius=14)
        self.dashed_rect(x, y, w, h, stroke, 2, 14)
        self.text(x + 14, y + 8, label, size, BOLD, stroke)

    # --- arrows ---
    def arrow(self, pts, label=None, dashed=False, color=LINE, both=False, lpos=None, lsize=13, width=2, loff=(0, 0)):
        if dashed:
            self.dline(pts, color, width)
        else:
            self.line(pts, color, width)
        self.head(pts[-1], pts[-2], color)
        if both:
            self.head(pts[0], pts[1], color)
        if label:
            if lpos is None:
                # middle of the longest segment
                seg = max(range(len(pts) - 1), key=lambda i: math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]))
                mx = (pts[seg][0] + pts[seg + 1][0]) / 2
                my = (pts[seg][1] + pts[seg + 1][1]) / 2
            else:
                mx, my = lpos
            self.label(mx + loff[0], my + loff[1], label, lsize)

    def connect(self, a, sa, b, sb, label=None, dashed=False, via=None, fa=0.5, fb=0.5, **kw):
        p, q = a.side(sa, fa), b.side(sb, fb)
        if via is not None:
            pts = [p] + via + [q]
        elif sa in "ew" and sb in "ew":
            mx = (p[0] + q[0]) / 2
            pts = [p, (mx, p[1]), (mx, q[1]), q] if abs(p[1] - q[1]) > 1 else [p, q]
        elif sa in "ns" and sb in "ns":
            my = (p[1] + q[1]) / 2
            pts = [p, (p[0], my), (q[0], my), q] if abs(p[0] - q[0]) > 1 else [p, q]
        elif sa in "ew":
            pts = [p, (q[0], p[1]), q]
        else:
            pts = [p, (p[0], q[1]), q]
        self.arrow(pts, label, dashed, **kw)

    def title(self, s, sub=None):
        self.text(24, 18, s, 24, BOLD, INK)
        if sub:
            self.text(24, 58, sub, 15, REG, MUTED)

    def legend(self, x, y, items, size=14):
        for i, (kind, name) in enumerate(items):
            fill, stroke = KINDS[kind]
            xx = x + i * 0
            self.rect(x, y + i * 24, 22, 16, fill, stroke, 1.5, radius=3)
            self.text(x + 30, y + i * 24 - 2, name, size, REG, INK)

    def legend_row(self, x, y, items, size=14, gap=26):
        xx = x
        for kind, name in items:
            fill, stroke = KINDS[kind]
            self.rect(xx, y, 22, 16, fill, stroke, 1.5, radius=3)
            self.text(xx + 30, y - 2, name, size, REG, INK)
            xx += 30 + self.textlen(name, size) + gap

    def save(self, path):
        self.img.save(path, dpi=(300, 300))


# --- sequence diagrams ---------------------------------------------------------------------------------------------
def sequence(path, title, parts, steps, width=1600, col=None, sub=None):
    """parts: [(name, kind)]; steps: (from, to, text) | ("note", idx_from, idx_to, text) | ("divider", text) |
    (from, to, text, "dashed") | ("self", idx, text)."""
    n = len(parts)
    margin = 40
    col = col or (width - 2 * margin) / n
    top = 100 if sub else 80
    row = 52
    # height estimate
    h = top + 70 + 20
    for st in steps:
        h += row + (12 if st[0] == "note" else 0)
    h += 60
    c = Canvas(width, h)
    c.title(title, sub)
    xs = [margin + col * (i + 0.5) for i in range(n)]
    for i, (name, kind) in enumerate(parts):
        c.box(xs[i] - col * 0.44, top, col * 0.88, 52, name, kind=kind, tsize=15)
    y0 = top + 52
    y_end = h - 40
    for x in xs:
        c.dline([(x, y0), (x, y_end)], MUTED, 1.5, 6, 6)
    y = y0 + 30
    for st in steps:
        if st[0] == "divider":
            c.line([(margin, y + 6), (width - margin, y + 6)], (200, 200, 210), 1.5)
            c.label(width / 2, y + 6, st[1], 13, INK, (243, 244, 246), SEMI)
            y += row
            continue
        if st[0] == "note":
            _, a, b, text = st
            x1, x2 = min(xs[a], xs[b]) - col * 0.4, max(xs[a], xs[b]) + col * 0.4
            lines = c.wrap(text, x2 - x1 - 16, 13)
            hh = len(lines) * 17 * FS + 10
            c.rect(x1, y - 8, x2 - x1, hh, KINDS["note"][0], KINDS["note"][1], 1.5, radius=4)
            for i, l in enumerate(lines):
                c.text((x1 + x2) / 2, y - 3 + i * 17 * FS, l, 13, REG, INK, "ma")
            y += max(row, hh + 14)
            continue
        if st[0] == "self":
            _, a, text = st
            x = xs[a]
            c.arrow([(x, y), (x + 40, y), (x + 40, y + 20), (x + 3, y + 20)])
            tw = c.textlen(text, 13) + 8
            if x + 48 + tw > width - 10:  # no room on the right: write it on the left
                c.rect(x - 8 - tw, y, tw, 20, WHITE)
                c.text(x - 4, y + 1, text, 13, REG, INK, "ra")
            else:
                c.rect(x + 46, y, tw, 20, WHITE)
                c.text(x + 50, y + 1, text, 13, REG, INK)
            y += row + 6
            continue
        a, b, text = st[0], st[1], st[2]
        dashed = len(st) > 3 and st[3] == "dashed"
        x1, x2 = xs[a], xs[b]
        x2a = x2 - 4 if x2 > x1 else x2 + 4
        c.arrow([(x1, y + 14), (x2a, y + 14)], dashed=dashed, color=MUTED if dashed else LINE)
        c.label((x1 + x2) / 2, y + 1, text, 13, INK)
        y += row + (len(text.split("\n")) - 1) * 16
    # crop to used height
    used = int((y + 30) * c.k)
    for i, (name, kind) in enumerate(parts):
        pass
    c.img = c.img.crop((0, 0, c.img.width, min(c.img.height, used)))
    c.save(path)


# --- charts --------------------------------------------------------------------------------------------------------
class Chart:
    def __init__(self, canvas, x, y, w, h, xr, yr, logx=False):
        self.c, self.x, self.y, self.w, self.h = canvas, x, y, w, h
        self.xr, self.yr, self.logx = xr, yr, logx

    def px(self, v):
        lo, hi = self.xr
        if self.logx:
            v, lo, hi = math.log10(max(v, 1e-9)), math.log10(lo), math.log10(hi)
        return self.x + (v - lo) / (hi - lo) * self.w

    def py(self, v):
        lo, hi = self.yr
        return self.y + self.h - (v - lo) / (hi - lo) * self.h

    def axes(self, xticks, yticks, xlabel="", ylabel="", grid=True, fmt_x=str, fmt_y=str):
        c = self.c
        for t in yticks:
            yy = self.py(t)
            if grid:
                c.line([(self.x, yy), (self.x + self.w, yy)], (229, 231, 235), 1)
            c.text(self.x - 8, yy, fmt_y(t), 14, REG, MUTED, "rm")
        for t in xticks:
            xx = self.px(t)
            if grid:
                c.line([(xx, self.y), (xx, self.y + self.h)], (229, 231, 235), 1)
            c.text(xx, self.y + self.h + 8, fmt_x(t), 14, REG, MUTED, "ma")
        c.line([(self.x, self.y + self.h), (self.x + self.w, self.y + self.h)], LINE, 1.5)
        c.line([(self.x, self.y), (self.x, self.y + self.h)], LINE, 1.5)
        if xlabel:
            c.text(self.x + self.w / 2, self.y + self.h + 36, xlabel, 14, SEMI, INK, "ma")
        if ylabel:
            c.text(self.x - 60, self.y - 26, ylabel, 14, SEMI, INK, "la")

    def series(self, xs, ys, color, width=2.5):
        pts = [(self.px(a), self.py(b)) for a, b in zip(xs, ys)]
        self.c.line(pts, color, width)
