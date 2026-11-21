#!/usr/bin/env python3
"""VELMARA -- a travel poster for a place that isn't there.

Writes one image to /output/entry.png: a 1024x1024 travel poster for the
invented floating-island archipelago of Velmara, at sunset above a golden sea.

Pure Python 3 standard library only (no Pillow, no fonts, no network):
the sandbox runs python:3.13-slim, so the picture is painted scanline by
scanline into a bytearray and encoded as PNG with zlib + struct. The
lettering is a hand-drawn vector stroke font (no external font files).

Deterministic: fixed seed, fixed geometry, no clock, no I/O besides the
single output file. Runs in well under 60 seconds.
"""

import math
import os
import random
import struct
import zlib

W = 1024
H = 1024
OUT = "/output/entry.png"
MAX_BYTES = 1_048_576

# ---------------------------------------------------------------- palette
CREAM = (255, 243, 218)
CREAM_DIM = (238, 214, 178)
SHADOW = (26, 14, 48)
GOLD = (255, 196, 110)
SUN_CORE = (255, 222, 148)

SKY_STOPS = [  # (y, rgb) -- dusk gradient, deep indigo down to amber
    (0, (22, 14, 52)),
    (170, (52, 30, 92)),
    (330, (112, 48, 108)),
    (480, (196, 88, 110)),
    (600, (240, 148, 84)),
    (680, (250, 190, 110)),
]
SEA_STOPS = [  # (y, rgb) -- horizon glow down to deep dusk water
    (680, (238, 168, 96)),
    (740, (150, 92, 116)),
    (860, (62, 48, 100)),
    (1024, (20, 16, 50)),
]
ROCK = (44, 26, 64)
ROCK_DARK = (30, 18, 48)
FOLIAGE = (26, 64, 56)
RIM = (240, 158, 92)


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def gradient(stops, y):
    """Colour of a vertical gradient at row y."""
    if y <= stops[0][0]:
        return stops[0][1]
    for (y0, c0), (y1, c1) in zip(stops, stops[1:]):
        if y <= y1:
            return lerp(c0, c1, (y - y0) / max(1, y1 - y0))
    return stops[-1][1]


def blend(fg, bg, a):
    """fg over bg, a in 0..1."""
    return tuple(int(round(fg[i] * a + bg[i] * (1.0 - a))) for i in range(3))


# ---------------------------------------------------------------- canvas
class Canvas:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.px = bytearray(w * h * 3)

    def _off(self, x, y):
        return (y * self.w + x) * 3

    def hspan(self, y, x0, x1, color):
        """Fill a horizontal span of row y with a solid colour."""
        if y < 0 or y >= self.h:
            return
        x0 = max(0, int(x0))
        x1 = min(self.w, int(x1))
        if x1 <= x0:
            return
        o = self._off(x0, y)
        self.px[o:o + (x1 - x0) * 3] = bytes(color) * (x1 - x0)

    def vgradient(self, stops, y0, y1):
        for y in range(y0, y1):
            self.hspan(y, 0, self.w, gradient(stops, y))

    def fill_polygon(self, pts, color, alpha=1.0):
        """Even-odd scanline fill. pts: list of (x, y)."""
        if not pts:
            return
        ys = [p[1] for p in pts]
        y0, y1 = max(0, int(math.ceil(min(ys)))), min(self.h, int(math.floor(max(ys))) + 1)
        n = len(pts)
        for y in range(y0, y1):
            xs = []
            for i in range(n):
                x0, yy0 = pts[i]
                x1, yy1 = pts[(i + 1) % n]
                if (yy0 <= y < yy1) or (yy1 <= y < yy0):
                    t = (y - yy0) / (yy1 - yy0)
                    xs.append(x0 + t * (x1 - x0))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                self.hspan(y, xs[i], xs[i + 1], color)

    def disc(self, cx, cy, r, color, alpha=1.0):
        """Filled disc; alpha blends against the vertical sky/sea gradient,
        which is exact while the background is still the plain gradient."""
        if r <= 0:
            return
        r = int(r)
        for dy in range(-r, r + 1):
            y = int(cy) + dy
            if y < 0 or y >= self.h:
                continue
            half = int(math.sqrt(max(0, r * r - dy * dy)))
            c = color
            if alpha < 1.0:
                bg = gradient(SKY_STOPS, y) if y < 680 else gradient(SEA_STOPS, y)
                c = blend(color, bg, alpha)
            self.hspan(y, cx - half, cx + half + 1, c)

    def glow(self, cx, cy, r_max, color, a_max=0.55, steps=14):
        """Soft radial glow: concentric discs, fading outwards."""
        for i in range(steps, 0, -1):
            t = i / steps
            self.disc(cx, cy, r_max * t, color, a_max * (1.0 - t) * 0.55)

    def ellipse(self, cx, cy, rx, ry, color, alpha=1.0):
        for dy in range(-int(ry), int(ry) + 1):
            y = int(cy) + dy
            if y < 0 or y >= self.h:
                continue
            t = dy / ry
            half = int(rx * math.sqrt(max(0.0, 1.0 - t * t)))
            c = color
            if alpha < 1.0:
                bg = gradient(SKY_STOPS, y) if y < 680 else gradient(SEA_STOPS, y)
                c = blend(color, bg, alpha)
            self.hspan(y, cx - half, cx + half + 1, c)

    def thick_line(self, x0, y0, x1, y1, width, color):
        """Round-capped thick segment, drawn as a chain of discs."""
        dx, dy = x1 - x0, y1 - y0
        dist = math.hypot(dx, dy)
        steps = max(1, int(dist / max(1.0, width * 0.45)) + 1)
        r = width / 2.0
        for i in range(steps + 1):
            t = i / steps
            self.disc(x0 + dx * t, y0 + dy * t, r, color)

    def vspan_alpha(self, x, y0, y1, color, a0, a1):
        """Vertical streak whose alpha fades from a0 (top) to a1 (bottom)."""
        for y in range(int(y0), int(y1)):
            if y < 0 or y >= self.h:
                continue
            t = (y - y0) / max(1, y1 - y0)
            bg = gradient(SKY_STOPS, y) if y < 680 else gradient(SEA_STOPS, y)
            self.hspan(y, x, x + 1, blend(color, bg, a0 + (a1 - a0) * t))

# ------------------------------------------------------- vector stroke font
# Each glyph: list of polylines in a 5-wide x 7-tall box (y down).
FONT = {
    "A": [[(0, 7), (2.5, 0), (5, 7)], [(1.3, 4.3), (3.7, 4.3)]],
    "B": [[(0, 0), (0, 7)], [(0, 0), (3, 0), (4.8, 1.2), (4.8, 2.6), (3.2, 3.5), (0, 3.5)],
          [(0, 3.5), (3.2, 3.5), (4.8, 4.8), (4.8, 5.8), (3, 7), (0, 7)]],
    "C": [[(4.8, 1.2), (3, 0), (1.5, 0), (0, 1.5), (0, 5.5), (1.5, 7), (3, 7), (4.8, 5.8)]],
    "D": [[(0, 0), (0, 7)], [(0, 0), (3, 0), (4.8, 1.6), (4.8, 5.4), (3, 7), (0, 7)]],
    "E": [[(4.5, 0), (0, 0), (0, 7), (4.5, 7)], [(0, 3.5), (3.4, 3.5)]],
    "F": [[(0, 0), (0, 7)], [(0, 0), (4.5, 0)], [(0, 3.5), (3.4, 3.5)]],
    "G": [[(4.8, 1.2), (3, 0), (1.5, 0), (0, 1.5), (0, 5.5), (1.5, 7), (3, 7),
           (4.8, 5.8), (4.8, 3.8), (2.6, 3.8)]],
    "H": [[(0, 0), (0, 7)], [(5, 0), (5, 7)], [(0, 3.5), (5, 3.5)]],
    "I": [[(2.5, 0), (2.5, 7)], [(1, 0), (4, 0)], [(1, 7), (4, 7)]],
    "J": [[(4.2, 0), (4.2, 5.5), (3, 7), (1.4, 7), (0.2, 5.6)]],
    "K": [[(0, 0), (0, 7)], [(4.8, 0), (0.9, 3.4)], [(2.2, 3.8), (4.8, 7)]],
    "L": [[(0, 0), (0, 7), (4.8, 7)]],
    "M": [[(0, 7), (0, 0), (2.5, 3.2), (5, 0), (5, 7)]],
    "N": [[(0, 7), (0, 0), (5, 7), (5, 0)]],
    "O": [[(1.4, 0), (3.6, 0), (5, 1.6), (5, 5.4), (3.6, 7), (1.4, 7),
           (0, 5.4), (0, 1.6), (1.4, 0)]],
    "P": [[(0, 7), (0, 0), (3.2, 0), (4.8, 1.4), (4.8, 2.6), (3.2, 3.6), (0, 3.6)]],
    "Q": [[(1.4, 0), (3.6, 0), (5, 1.6), (5, 5.4), (3.6, 7), (1.4, 7),
           (0, 5.4), (0, 1.6), (1.4, 0)], [(3.4, 5.2), (5.2, 7)]],
    "R": [[(0, 7), (0, 0), (3.2, 0), (4.8, 1.4), (4.8, 2.6), (3.2, 3.6), (0, 3.6)],
          [(2.4, 3.6), (5, 7)]],
    "S": [[(4.8, 1.2), (3, 0), (1.6, 0), (0, 1.4), (0, 2.6), (1.2, 3.5),
           (3.4, 3.5), (4.8, 4.6), (4.8, 5.8), (3, 7), (1.6, 7), (0, 5.8)]],
    "T": [[(0, 0), (5, 0)], [(2.5, 0), (2.5, 7)]],
    "U": [[(0, 0), (0, 5.4), (1.4, 7), (3.6, 7), (5, 5.4), (5, 0)]],
    "V": [[(0, 0), (2.5, 7), (5, 0)]],
    "W": [[(0, 0), (1.3, 7), (2.5, 3.4), (3.7, 7), (5, 0)]],
    "X": [[(0, 0), (5, 7)], [(5, 0), (0, 7)]],
    "Y": [[(0, 0), (2.5, 3.4), (5, 0)], [(2.5, 3.4), (2.5, 7)]],
    "Z": [[(0, 0), (5, 0), (0, 7), (5, 7)]],
    "-": [[(0.6, 3.5), (4.4, 3.5)]],
    ".": [[(2.5, 6.4), (2.5, 6.9)]],
    "'": [[(2.5, 0), (2.5, 1.8)]],
    " ": [],
}


def text_width(text, height, tracking):
    unit = height / 7.0
    return sum((5.0 * unit + tracking) for _ in text) - tracking


def draw_text(cv, text, cx, y_top, height, color, stroke, tracking):
    """Draw centred text with the stroke font. Returns the drawn width."""
    unit = height / 7.0
    adv = 5.0 * unit + tracking
    total = adv * len(text) - tracking
    x = cx - total / 2.0
    for ch in text:
        for poly in FONT.get(ch, []):
            for (ax, ay), (bx, by) in zip(poly, poly[1:]):
                cv.thick_line(x + ax * unit, y_top + ay * unit,
                              x + bx * unit, y_top + by * unit, stroke, color)
        x += adv
    return total


# ------------------------------------------------------------------ scene
def pine(cv, x, y, s, color):
    """Small pine silhouette, base at (x, y), height s."""
    cv.fill_polygon([(x, y - s), (x - s * 0.42, y - s * 0.35), (x + s * 0.42, y - s * 0.35)], color)
    cv.fill_polygon([(x, y - s * 0.72), (x - s * 0.32, y - s * 0.12), (x + s * 0.32, y - s * 0.12)], color)
    cv.fill_polygon([(x, y - s * 0.48), (x - s * 0.24, y + s * 0.12), (x + s * 0.24, y + s * 0.12)], color)


def island(cv, x0, x1, y_top, y_tip, haze=False):
    """A floating island: flat grassy top, rock underside tapering to a point."""
    cx = (x0 + x1) / 2.0
    rock = (74, 52, 96) if haze else ROCK
    dark = (52, 36, 76) if haze else ROCK_DARK
    # underside
    cv.fill_polygon([(x0 + 8, y_top + 26), (x1 - 8, y_top + 26), (cx, y_tip)], dark)
    cv.fill_polygon([(x0, y_top), (x1, y_top), (x1 - 8, y_top + 26), (x0 + 8, y_top + 26)], rock)
    # grassy cap
    cap = (52, 92, 82) if haze else FOLIAGE
    cv.fill_polygon([(x0, y_top), (x1, y_top), (x1 - 4, y_top + 12), (x0 + 4, y_top + 12)], cap)
    # warm rim light along the top edge
    cv.thick_line(x0 + 2, y_top + 2, x1 - 2, y_top + 2, 3, RIM if not haze else (200, 140, 110))
    # layered rock strata: thin darker bands following the taper
    if not haze:
        for sy in (y_top + 62, y_top + 104, y_top + 142):
            frac = (y_tip - sy) / max(1, y_tip - (y_top + 26))
            half = (x1 - x0) / 2.0 * max(0.0, frac) * 0.82
            cv.hspan(sy, cx - half, cx + half, (36, 22, 56))
    return cx


def cloud(cv, cx, cy, s, color, alpha=0.16):
    """A soft, flat, wide dusk cloud: overlapping squashed ellipses."""
    for dx, dy, f in ((0, 0, 1.0), (-0.85, 0.10, 0.62), (0.85, 0.10, 0.58),
                      (-0.42, -0.16, 0.52), (0.45, -0.14, 0.55), (0.05, 0.14, 0.66)):
        cv.ellipse(cx + dx * s, cy + dy * s, s * f * 0.42, s * f * 0.16, color, alpha)


def waterfall(cv, x, y0, y1, width=9):
    """A pale cascade falling off an island's edge, fading as it falls."""
    rng = random.Random(7)
    for i in range(width):
        xx = x + i - width // 2
        wob = rng.uniform(-2, 2)
        for yy in range(int(y0), int(y1), 2):
            t = (yy - y0) / max(1, y1 - y0)
            a = 0.9 * (1.0 - t * 0.75)
            bg = gradient(SKY_STOPS, yy) if yy < 680 else gradient(SEA_STOPS, yy)
            col = blend((220, 236, 242), bg, a)
            px = int(xx + wob * math.sin(yy / 26.0))
            cv.hspan(yy, px, px + 2, col)


def bird(cv, x, y, s, color):
    cv.thick_line(x - s, y, x, y - s * 0.45, 3, color)
    cv.thick_line(x, y - s * 0.45, x + s, y, 3, color)


def sailboat(cv, x, y, s, color):
    cv.fill_polygon([(x, y - s), (x, y), (x + s * 0.62, y)], color)          # sail
    cv.fill_polygon([(x - s * 0.28, y - s * 0.72), (x - s * 0.28, y), (x, y)], color)  # jib
    cv.thick_line(x - s * 0.55, y, x + s * 0.62, y + s * 0.16, 3, color)      # hull

def render():
    cv = Canvas(W, H)
    rng = random.Random(20261121)

    # --- sky & sea
    cv.vgradient(SKY_STOPS, 0, 680)
    cv.vgradient(SEA_STOPS, 680, H)

    # --- stars, fading out toward the horizon
    for _ in range(150):
        x = rng.randint(30, W - 30)
        y = int(rng.random() ** 1.6 * 330)
        a = 0.25 + 0.65 * (1 - y / 340.0)
        r = 1 if rng.random() < 0.8 else 2
        bg = gradient(SKY_STOPS, y)
        cv.hspan(y, x - r, x + r + 1, blend((255, 240, 210), bg, a))

    # --- low sun, right of centre and clear of the islands, with warm glow
    cv.glow(778, 592, 260, (255, 150, 70), a_max=0.5)
    cv.glow(778, 592, 150, (255, 190, 100), a_max=0.55)
    cv.disc(778, 592, 72, SUN_CORE)
    cv.disc(778, 592, 58, (255, 232, 170))

    # --- soft dusk clouds (warm-lit, flat wide clusters)
    for cx, cy, s, col, al in (
        (210, 250, 150, (226, 130, 130), 0.20),
        (300, 300, 100, (240, 170, 130), 0.18),
        (880, 330, 150, (220, 120, 130), 0.20),
        (480, 180, 110, (180, 110, 150), 0.16),
        (120, 420, 120, (214, 120, 120), 0.18),
    ):
        cloud(cv, cx, cy, s, col, al)

    # --- birds
    for bx, by, bs in ((300, 300, 13), (345, 322, 10), (268, 338, 9), (760, 250, 12), (812, 272, 9)):
        bird(cv, bx, by, bs, (40, 22, 58))

    # --- far hazy island, left
    island(cv, 28, 232, 428, 566, haze=True)
    pine(cv, 90, 428, 34, (70, 90, 88))
    pine(cv, 150, 428, 26, (70, 90, 88))

    # --- main island with its crystal tower
    island(cv, 120, 640, 498, 652)
    # pines along the plateau
    for px, ps in ((175, 44), (225, 34), (270, 48), (540, 40), (588, 30)):
        pine(cv, px, 498, ps, (16, 44, 40))
    # crystal tower: a faceted cut-gem spire rising from the plateau
    cv.glow(415, 400, 90, (170, 210, 235), a_max=0.25)
    cv.fill_polygon([(360, 498), (470, 498), (452, 332), (430, 300), (408, 332)], (168, 214, 232))
    cv.fill_polygon([(360, 498), (408, 332), (430, 300), (415, 498)], (138, 148, 216))
    cv.fill_polygon([(470, 498), (452, 332), (430, 300), (445, 498)], (250, 200, 122))
    cv.thick_line(408, 332, 452, 332, 3, (220, 235, 245))
    cv.thick_line(415, 498, 430, 300, 2, (200, 225, 240))
    cv.thick_line(445, 498, 430, 300, 2, (255, 220, 150))
    cv.disc(430, 296, 6, (255, 246, 220))  # beacon light on the spire
    cv.glow(430, 296, 22, (255, 230, 170), a_max=0.4)
    # small round hut beside the tower
    cv.fill_polygon([(500, 498), (500, 468), (532, 448), (564, 468), (564, 498)], (200, 120, 96))
    cv.fill_polygon([(500, 468), (532, 448), (564, 468), (556, 476), (508, 476)], (150, 84, 72))
    cv.disc(532, 484, 5, GOLD)

    # --- right island, smaller, with a beacon pine
    island(cv, 856, 988, 566, 694)
    pine(cv, 892, 566, 34, (16, 44, 40))
    pine(cv, 932, 566, 26, (16, 44, 40))
    cv.disc(964, 558, 6, GOLD)
    cv.glow(964, 558, 24, (255, 210, 130), a_max=0.5)

    # --- waterfalls spilling off the islands into the sea
    waterfall(cv, 300, 600, 684, 9)
    waterfall(cv, 500, 606, 684, 8)
    waterfall(cv, 922, 668, 700, 5)

    # --- sun's reflection: a glittering column on the water
    for _ in range(90):
        y = rng.randint(686, 990)
        wdt = int(10 + (y - 686) / 304.0 * 150 + rng.uniform(-8, 8))
        xx = int(778 + rng.gauss(0, 34 + (y - 686) * 0.10))
        a = 0.55 * (1 - (y - 686) / 330.0) + 0.08
        bg = gradient(SEA_STOPS, y)
        cv.hspan(y, xx - wdt // 2, xx + wdt // 2, blend(GOLD, bg, max(0.05, min(0.7, a))))

    # --- a couple of tiny sailboats, for scale and longing
    sailboat(cv, 300, 812, 26, (24, 16, 46))
    sailboat(cv, 836, 884, 20, (24, 16, 46))

    # --- dark headlands framing the bottom corners
    cv.fill_polygon([(0, 1024), (0, 936), (120, 962), (268, 1002), (300, 1024)], (18, 14, 44))
    cv.fill_polygon([(1024, 1024), (1024, 952), (920, 976), (800, 1010), (780, 1024)], (18, 14, 44))
    pine(cv, 96, 962, 52, (14, 12, 36))
    pine(cv, 150, 972, 38, (14, 12, 36))
    pine(cv, 930, 976, 44, (14, 12, 36))

    # --- title: the invented place's name, big and legible, top of poster
    draw_text(cv, "VELMARA", 512, 66, 116, (58, 26, 66), 15, 30)   # soft shadow
    draw_text(cv, "VELMARA", 512, 60, 116, CREAM, 15, 30)
    # tagline + flanking rules (rules kept clear of the text)
    draw_text(cv, "ISLANDS IN THE SKY", 512, 202, 34, CREAM_DIM, 5, 8)
    cv.thick_line(88, 219, 196, 219, 3, CREAM_DIM)
    cv.thick_line(828, 219, 936, 219, 3, CREAM_DIM)

    # --- thin double frame, poster style
    for inset, wd in ((26, 4), (36, 2)):
        cv.thick_line(inset, inset, W - inset, inset, wd, CREAM_DIM)
        cv.thick_line(inset, H - inset, W - inset, H - inset, wd, CREAM_DIM)
        cv.thick_line(inset, inset, inset, H - inset, wd, CREAM_DIM)
        cv.thick_line(W - inset, inset, W - inset, H - inset, wd, CREAM_DIM)

    return cv


# ------------------------------------------------------------------- PNG out
def write_png(cv, path):
    raw = bytearray()
    prev = bytes(W * 3)
    for y in range(H):
        row = bytes(cv.px[y * W * 3:(y + 1) * W * 3])
        # Filter 2 (Up): residuals against the row above compress gradients hard.
        filt = bytes((b - p) & 0xFF for b, p in zip(row, prev))
        raw.append(2)
        raw.extend(filt)
        prev = row
    data = zlib.compress(bytes(raw), 9)

    def chunk(kind, payload):
        c = struct.pack(">I", len(payload)) + kind + payload
        return c + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", data)
    png += chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


def main():
    cv = render()
    size = write_png(cv, OUT)
    print(f"wrote {OUT}: {W}x{H}, {size} bytes")
    if size > MAX_BYTES:
        raise SystemExit(f"entry.png too large: {size} > {MAX_BYTES}")


if __name__ == "__main__":
    main()
