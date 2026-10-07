"""1970s/80s submarine control-room art: painted steel consoles, black anodised faceplates with white engraved
legends, backlit push-buttons, annunciator tiles, 7-segment LED readouts and black-faced instruments.
Static pieces are built once at startup; per-frame helpers draw only the moving parts."""
import math
import random
from functools import lru_cache

import numpy as np
import pygame

WALL = (30, 34, 38)
STEEL = (92, 101, 98)            # console paint: Navy grey-green
STEEL_LIGHT = (132, 141, 137)
STEEL_DARK = (48, 53, 52)
FACE = (26, 28, 30)              # anodised black faceplate
FACE_EDGE = (62, 66, 70)
LEGEND = (228, 230, 224)         # white engraving
LEGEND_DIM = (146, 152, 148)
WARN = (255, 120, 40)            # orange: units, hints, needles
AMBER = (255, 176, 40)
RED = (255, 54, 36)
GREEN = (70, 226, 110)
BLUE = (90, 170, 255)
WHITE = (240, 240, 232)
INK = (24, 24, 26)               # print on paper
INK_RED = (176, 40, 30)
PAPER = (236, 238, 228)
PAPER_BAND = (206, 230, 208)     # green-bar printout
CHROME = (186, 190, 194)


@lru_cache(maxsize=None)
def sans(size, bold=True):
    return pygame.font.SysFont("arialnarrow,dejavusanscondensed,arial,helvetica", size, bold=bold)


@lru_cache(maxsize=None)
def mono(size, bold=False):
    return pygame.font.SysFont("consolas,couriernew,monospace", size, bold=bold)


def polar(c, r, deg):
    """Point at radius r, angle deg (maths convention: 0 = east, CCW positive) from c on a y-down screen."""
    a = math.radians(deg)
    return c[0] + r * math.cos(a), c[1] - r * math.sin(a)


def clamp01(f):
    return min(max(f, 0.0), 1.0)


def value_angle(v, lo, hi, start=225.0, sweep=270.0):
    return start - clamp01((v - lo) / (hi - lo)) * sweep


def angle_value(deg, lo, hi, start=225.0, sweep=270.0):
    return lo + clamp01(((start - deg) % 360) / sweep) * (hi - lo)


# ---------- surfaces ----------
def texture(size, base, grain=4.0, light=(1.06, 0.9)):
    """Matte paint: fine speckle, lit softly from above."""
    w, h = size
    n = np.random.normal(0, grain, (w, h))
    shade = np.linspace(light[0], light[1], h)[None, :, None]
    rgb = (np.array(base, float)[None, None, :] + n[..., None]) * shade
    surf = pygame.Surface(size)
    pygame.surfarray.blit_array(surf, np.clip(rgb, 0, 255).astype(np.uint8))
    return surf


def bevel(surf, rect, light=STEEL_LIGHT, dark=STEEL_DARK, width=2):
    r = pygame.Rect(rect)
    for i in range(width):
        pygame.draw.line(surf, light, (r.left + i, r.top + i), (r.right - 1 - i, r.top + i))
        pygame.draw.line(surf, light, (r.left + i, r.top + i), (r.left + i, r.bottom - 1 - i))
        pygame.draw.line(surf, dark, (r.left + i, r.bottom - 1 - i), (r.right - 1 - i, r.bottom - 1 - i))
        pygame.draw.line(surf, dark, (r.right - 1 - i, r.top + i), (r.right - 1 - i, r.bottom - 1 - i))


def screw(surf, pos, r=4):
    """Phillips pan-head screw, slots at a random twist."""
    x, y = int(pos[0]), int(pos[1])
    pygame.draw.circle(surf, (14, 15, 16), (x + 1, y + 1), r)
    pygame.draw.circle(surf, (120, 124, 126), (x, y), r)
    pygame.draw.circle(surf, (170, 174, 176), (x - 1, y - 1), max(1, r - 2))
    a = random.uniform(0, math.pi)
    for k in (0, math.pi / 2):
        dx, dy = math.cos(a + k) * (r - 1), math.sin(a + k) * (r - 1)
        pygame.draw.line(surf, (50, 52, 54), (x - dx, y - dy), (x + dx, y + dy), 1)


def panel(surf, rect, base=STEEL, screws=True):
    """Painted console section with screws in the corners."""
    r = pygame.Rect(rect)
    surf.blit(texture(r.size, base), r.topleft)
    bevel(surf, r)
    if screws:
        for x in (r.left + 8, r.right - 8):
            for y in (r.top + 8, r.bottom - 8):
                screw(surf, (x, y))


def faceplate(surf, rect, screws=True):
    """Black anodised instrument plate set into the console."""
    r = pygame.Rect(rect)
    pygame.draw.rect(surf, (12, 13, 14), r.inflate(4, 4), border_radius=4)
    surf.blit(texture(r.size, FACE, grain=2.5, light=(1.1, 0.92)), r.topleft)
    bevel(surf, r, light=FACE_EDGE, dark=(8, 8, 9), width=1)
    if screws:
        for x in (r.left + 7, r.right - 7):
            for y in (r.top + 7, r.bottom - 7):
                screw(surf, (x, y), 3)


def engrave(surf, text, pos, size=12, color=LEGEND, center=False, bold=True):
    label = sans(size, bold).render(text, True, color)
    surf.blit(label, label.get_rect(center=pos) if center else pos)


def label_plate(surf, center, text, size=12):
    """Engraved Lamacoid plate: black laminate, white letters, two screws."""
    label = sans(size, True).render(text, True, LEGEND)
    r = label.get_rect(center=center).inflate(26, 8)
    pygame.draw.rect(surf, (10, 10, 11), r.move(1, 1), border_radius=2)
    pygame.draw.rect(surf, (20, 21, 23), r, border_radius=2)
    pygame.draw.rect(surf, (70, 74, 78), r, 1, border_radius=2)
    surf.blit(label, label.get_rect(center=center))
    for x in (r.left + 6, r.right - 6):
        pygame.draw.circle(surf, (110, 114, 116), (x, r.centery), 2)


def dymo(surf, pos, text, size=11):
    """Embossed label-maker tape: the sailors' own additions."""
    label = sans(size, True).render(text, True, (236, 236, 230))
    r = label.get_rect(topleft=pos).inflate(10, 4)
    pygame.draw.rect(surf, (18, 20, 24), r, border_radius=2)
    surf.blit(label, label.get_rect(center=r.center))


# ---------- instruments ----------
def _dial(radius):
    """Black instrument face inside a chrome bezel, shaded with numpy."""
    size = radius * 2 + 2
    c = size / 2
    x, y = np.ogrid[:size, :size]
    d = np.hypot(x - c, y - c)
    ang = np.arctan2(c - y, x - c)
    rgb = np.zeros((size, size, 3))
    rim = (d <= radius) & (d > radius - 7)
    lit = 0.7 + 0.45 * np.cos(ang - 2.36)
    rgb[rim] = np.array(CHROME)[None, :] * lit[rim][:, None]
    face = d <= radius - 7
    rgb[face] = (np.array((20, 21, 23))[None, :] + np.random.normal(0, 2, (size, size))[face][:, None]) \
        * (1.15 - 0.3 * (d[face] / radius))[:, None]
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.surfarray.pixels3d(surf)[:] = np.clip(rgb, 0, 255).astype(np.uint8)
    alpha = pygame.surfarray.pixels_alpha(surf)
    alpha[:] = np.where(d <= radius, 255, 0).astype(np.uint8)
    del alpha
    return surf


def gauge_face(radius, title, lo, hi, major, minor, red=None, units="", start=225.0, sweep=270.0, labels=None):
    surf = _dial(radius)
    c = (surf.get_width() / 2, surf.get_height() / 2)
    rr = radius - 11
    if red:
        a0, a1 = value_angle(red[0], lo, hi, start, sweep), value_angle(red[1], lo, hi, start, sweep)
        for k in range(41):
            a = a0 + (a1 - a0) * k / 40
            pygame.draw.line(surf, RED, polar(c, rr - 1, a), polar(c, rr - 6, a), 3)
    for v in np.arange(lo, hi + minor / 2, minor):
        a = value_angle(v, lo, hi, start, sweep)
        is_major = abs((v - lo) / major - round((v - lo) / major)) < 1e-6
        pygame.draw.line(surf, LEGEND if is_major else LEGEND_DIM, polar(c, rr, a), polar(c, rr - (9 if is_major else 4), a),
                         2 if is_major else 1)
        if is_major:
            engrave(surf, labels.get(v, "") if labels else f"{v:g}", polar(c, rr - 19, a), 11, LEGEND, center=True)
    if title:
        engrave(surf, title, (c[0], c[1] + radius * 0.24), 12, LEGEND, center=True)
    if units:
        engrave(surf, units, (c[0], c[1] + radius * 0.4), 10, WARN, center=True, bold=False)
    return surf, c


def glint(radius):
    size = radius * 2 + 2
    x, y = np.ogrid[:size, :size]
    c = size / 2
    d = np.hypot(x - c, y - c)
    band = np.exp(-((x - c * 0.72) ** 2 / (radius * 0.5) ** 2 + (y - c * 0.5) ** 2 / (radius * 0.2) ** 2))
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    surf.fill((255, 255, 255, 0))
    alpha = pygame.surfarray.pixels_alpha(surf)
    alpha[:] = np.where(d < radius - 7, band * 45, 0).astype(np.uint8)
    del alpha
    return surf


def needle(surf, c, deg, length, color=WARN, width=3, tail=12):
    tip, back = polar(c, length, deg), polar(c, -tail, deg)
    pygame.draw.polygon(surf, color, [tip, polar(c, width, deg + 90), back, polar(c, width, deg - 90)])
    pygame.draw.circle(surf, (10, 10, 12), (int(c[0]), int(c[1])), 6)
    pygame.draw.circle(surf, (70, 74, 78), (int(c[0]), int(c[1])), 3)


class Needle:
    """Spring-damped needle with a little electrical flicker."""

    def __init__(self, value=0.0):
        self.v, self.vel = value, 0.0

    def update(self, target, dt, jitter=0.0):
        self.vel += ((target - self.v) * 60 - self.vel * 12) * dt
        self.v += self.vel * dt
        return self.v + (random.gauss(0, jitter) if jitter else 0.0)


# ---------- 7-segment LED readouts ----------
SEGMENTS = {  # a b c d e f g
    "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd", "6": "afgedc", "7": "abc",
    "8": "abcdefg", "9": "abcdfg", "-": "g", " ": "", "E": "afged", "F": "afge", "H": "fbgec", "L": "fed",
    "P": "abgfe", "A": "abcefg", "C": "afed", "O": "abcdef", "U": "bcdef", "r": "eg", "n": "egc", "o": "cdeg",
}


@lru_cache(maxsize=512)
def _seg_glyph(ch, size, color, dp=False):
    w, h = int(size * 0.62), size
    t = max(2, int(size * 0.13))
    s = pygame.Surface((w + 8, h + 4))
    s.fill((14, 6, 5))
    off = tuple(int(c * 0.14) + 8 for c in color)
    on = SEGMENTS.get(ch.upper() if ch.upper() in SEGMENTS else ch, None)
    m = h // 2 + 2
    segs = {"a": ((3, 2), (w, 2)), "g": ((3, m), (w, m)), "d": ((3, h + 1), (w, h + 1)),
            "f": ((2, 3), (2, m - 1)), "b": ((w + 1, 3), (w + 1, m - 1)),
            "e": ((2, m + 1), (2, h)), "c": ((w + 1, m + 1), (w + 1, h))}
    for name, (p0, p1) in segs.items():
        lit = on is not None and name in on
        pygame.draw.line(s, color if lit else off, (p0[0] + 1, p0[1]), (p1[0], p1[1]), t)
    if on is None:  # letters 7-seg can't do: dot-matrix fallback in the LED colour
        s.fill((14, 6, 5))
        s.blit(mono(size - 2, True).render(ch, True, color), (2, 0))
    pygame.draw.circle(s, color if dp else off, (w + 5, h + 1), max(1, t - 1))  # this digit's decimal point
    return s


def counter(surf, pos, text, size=15, color=AMBER):
    """7-segment LED readout in a dark window. A '.' lights the previous digit's decimal point; commas are
    dropped (no thousands separator on a 7-segment display)."""
    digits = []
    for ch in text:
        if ch == ".":
            if digits:
                digits[-1][1] = True
        elif ch != ",":
            digits.append([ch, False])
    x, y = pos
    for ch, dp in digits:
        g = _seg_glyph(ch, size, color, dp)
        surf.blit(g, (x, y))
        x += g.get_width()
    pygame.draw.rect(surf, (60, 64, 68), (pos[0] - 2, y - 2, x - pos[0] + 3, size + 8), 1)
    return x - pos[0]


# ---------- controls ----------
@lru_cache(maxsize=32)
def _glow(color, r):
    surf = pygame.Surface((r * 6, r * 6), pygame.SRCALPHA)
    for k in range(r * 3, r, -2):
        pygame.draw.circle(surf, (*color, int(55 * (1 - k / (r * 3)))), (r * 3, r * 3), k)
    return surf


def lamp(surf, c, on, color, r=6):
    """Small round LED indicator in a black bezel."""
    x, y = int(c[0]), int(c[1])
    if on:
        surf.blit(_glow(color, r), (x - r * 3, y - r * 3))
    pygame.draw.circle(surf, (8, 8, 9), (x, y), r + 2)
    pygame.draw.circle(surf, color if on else tuple(v // 6 for v in color), (x, y), r)
    pygame.draw.circle(surf, (255, 255, 255) if on else (70, 70, 70), (x - r // 3, y - r // 3), max(1, r // 4))


def annunciator(surf, rect, legend, on, color):
    """Warning annunciator tile: the legend is printed on the lens, so it reads lit or dark, in any colour."""
    r = pygame.Rect(rect)
    pygame.draw.rect(surf, (6, 6, 7), r.inflate(4, 4))
    lens = color if on else tuple(18 + v // 9 for v in color)
    pygame.draw.rect(surf, lens, r)
    if on:
        pygame.draw.rect(surf, tuple(min(255, v + 40) for v in color), r.inflate(-6, -6), 1)
    engrave(surf, legend, r.center, 10, (20, 18, 16) if on else tuple(60 + v // 4 for v in color), center=True)


def button(surf, rect, text, lit=False, color=AMBER):
    """Square backlit push-button: legend on the cap, glows when on."""
    r = pygame.Rect(rect)
    pygame.draw.rect(surf, (8, 8, 9), r.inflate(6, 6), border_radius=3)
    pygame.draw.rect(surf, (52, 56, 60), r.inflate(2, 2), border_radius=3)
    cap = color if lit else (58, 62, 64)
    pygame.draw.rect(surf, cap, r, border_radius=2)
    pygame.draw.line(surf, tuple(min(255, v + 50) for v in cap), (r.left + 3, r.top + 1), (r.right - 4, r.top + 1))
    size = 11
    while size > 7 and sans(size, True).size(text)[0] > r.w - 4:  # shrink the legend to fit the cap
        size -= 1
    engrave(surf, text, r.center, size, (16, 16, 16) if lit else LEGEND, center=True)


def toggle(surf, c, up, guard_color=None):
    """Bat-handle toggle on a nut; an optional flip guard (red for the FIRE switches)."""
    x, y = int(c[0]), int(c[1])
    if guard_color:
        pygame.draw.rect(surf, tuple(v // 2 for v in guard_color), (x - 15, y - 26, 30, 52), 2, border_radius=6)
    pygame.draw.circle(surf, (14, 14, 15), (x, y), 11)
    pygame.draw.circle(surf, CHROME, (x, y), 9)
    pygame.draw.circle(surf, (90, 94, 98), (x, y), 5)
    tip = (x, y - 20) if up else (x, y + 20)
    pygame.draw.line(surf, (210, 212, 214), (x, y), tip, 5)
    pygame.draw.circle(surf, (236, 236, 236), tip, 4)


def helm_yoke(radius):
    """Aircraft-style control yoke on the ship-control panel: rudder with the turn, planes with the push."""
    size = radius * 2 + 40
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    c = size // 2
    black, grip = (22, 22, 24), (40, 40, 44)
    pygame.draw.rect(surf, black, (c - radius - 6, c - 9, (radius + 6) * 2, 18), border_radius=8)       # cross bar
    for side in (-1, 1):                                                                               # grips
        gx = c + side * (radius + 2)
        pygame.draw.rect(surf, grip, (gx - 11, c - radius * 0.75, 22, radius * 1.5), border_radius=10)
        pygame.draw.line(surf, (90, 94, 98), (gx - 5, c - radius * 0.6), (gx - 5, c + radius * 0.6), 2)
        pygame.draw.circle(surf, RED if side < 0 else (200, 200, 60), (gx, int(c - radius * 0.6)), 4)  # thumb buttons
    pygame.draw.circle(surf, black, (c, c), 18)
    pygame.draw.circle(surf, CHROME, (c, c), 12)
    pygame.draw.circle(surf, (60, 64, 68), (c, c), 6)
    pygame.draw.line(surf, WHITE, (c, c - 18), (c, c - 30), 3)  # top-dead-centre mark
    return surf


# ---------- glass ----------
def bezel_overlay(size, frames):
    """Full-screen alpha overlay: moulded black bezels around the CRTs with screws and glass glare.
    frames: [(outer_rect, hole_rect, corner_radius or None for round)]."""
    overlay = pygame.Surface(size, pygame.SRCALPHA)
    for outer, hole, radius in frames:
        outer, hole = pygame.Rect(outer), pygame.Rect(hole)
        tex = texture(outer.size, (36, 38, 41), grain=2.0, light=(1.15, 0.85)).convert_alpha()
        x, y = np.ogrid[:outer.w, :outer.h]
        hx, hy = hole.centerx - outer.x, hole.centery - outer.y
        if radius is None:
            dist = np.hypot(x - hx, y - hy) - hole.w / 2
        else:
            qx = np.maximum(np.abs(x - hx) - (hole.w / 2 - radius), 0)
            qy = np.maximum(np.abs(y - hy) - (hole.h / 2 - radius), 0)
            dist = np.hypot(qx, qy) - radius
        u = (x - (hole.x - outer.x)) / hole.w
        v = (y - (hole.y - outer.y)) / hole.h
        glare = np.clip(1 - (u + v) * 1.3, 0, 1) ** 2 * 28 + np.exp(-((u - 0.75) ** 2 / 0.02 + (v - 0.12) ** 2 / 0.002)) * 34
        alpha = np.where(dist > 0, 255, glare).astype(np.uint8)
        rgb = pygame.surfarray.pixels3d(tex)
        rgb[dist <= 0] = (255, 255, 250)
        lip = (dist > 0) & (dist < 6)  # moulded lip shading into the glass
        rgb[lip] = (12, 13, 14)
        del rgb
        pygame.surfarray.pixels_alpha(tex)[:] = alpha
        bevel(tex, tex.get_rect(), light=(84, 88, 92), dark=(8, 8, 9), width=2)
        overlay.blit(tex, outer.topleft)
        if radius is None:
            for k in range(4):
                screw(overlay, polar(hole.center, hole.w / 2 + 13, k * 90 + 45), 4)
        else:
            for px in (outer.left + 12, outer.right - 12):
                for py in (outer.top + 12, outer.bottom - 12):
                    screw(overlay, (px, py), 5)
    return overlay
