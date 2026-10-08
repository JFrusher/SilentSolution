"""Vintage control-room art, 1960s-80s and well used: battleship-grey hammertone consoles with chipped edges and
grime, worn black faceplates with yellowed engraving, mechanical drum counters, incandescent lamps behind dirty
lenses, aged black-faced instruments, and the crew's masking-tape notes.
Static pieces are built once at startup; per-frame helpers draw only the moving parts."""
import math
import random
import zlib
from functools import cache, lru_cache

import numpy as np
import pygame

from layout import value_angle
from settings import SETTINGS

_FX = random.Random()  # presentation-only randomness, so drawing never moves the simulation's dice
_NP = np.random.default_rng()

WALL = (36, 37, 36)
STEEL = (106, 108, 104)          # battleship-grey hammertone
STEEL_LIGHT = (146, 147, 142)
STEEL_DARK = (60, 61, 59)
BARE = (70, 68, 64)              # metal showing through chipped paint
FACE = (38, 38, 37)              # worn black faceplate, faded toward grey
FACE_EDGE = (78, 78, 74)
LEGEND = (222, 214, 188)         # engraving gone ivory with age
LEGEND_DIM = (156, 150, 130)
WARN = (226, 132, 60)            # faded orange: units, hints, needles
AMBER = (255, 190, 86)           # incandescent behind amber glass
RED = (232, 74, 52)
GREEN = (132, 214, 112)
BLUE = (128, 172, 222)
SAFE = {GREEN: (86, 180, 233), RED: (213, 94, 0), AMBER: (240, 228, 66)}
WHITE = (238, 232, 214)
INK = (32, 30, 28)               # print on paper
INK_RED = (164, 44, 32)
PAPER = (232, 230, 214)
PAPER_BAND = (204, 222, 196)     # green-bar printout
CHROME = (162, 162, 156)         # dulled, scuffed bright-work
TAPE = (214, 200, 160)           # masking tape


def _seed(*parts):
    """Deterministic randomness: the same scratch, fade and drum skew every frame."""
    return zlib.crc32(repr(parts).encode())


@cache
def sans(size, bold=True):
    return pygame.font.SysFont("arialnarrow,dejavusanscondensed,arial,helvetica", size, bold=bold)


@cache
def mono(size, bold=False):
    return pygame.font.SysFont("consolas,couriernew,monospace", size, bold=bold)


@cache
def hand(size):
    return pygame.font.SysFont("inkfree,segoeprint,comicsansms,bradleyhanditc", size, bold=True)


def polar(c, r, deg):
    """Point at radius r, angle deg (maths convention: 0 = east, CCW positive) from c on a y-down screen."""
    a = math.radians(deg)
    return c[0] + r * math.cos(a), c[1] - r * math.sin(a)


# ---------- surfaces ----------
def _mottle(w, h, scale):
    """Low-frequency blotches: hammertone paint, uneven fading."""
    small = _NP.random((max(2, w // scale), max(2, h // scale)))
    src = pygame.Surface(small.shape)
    pygame.surfarray.blit_array(src, np.repeat((small * 255).astype(np.uint8)[..., None], 3, axis=2))
    return pygame.surfarray.array_red(pygame.transform.smoothscale(src, (w, h))) / 255.0 - 0.5


def texture(size, base, grain=4.0, light=(1.06, 0.88), mottle=10.0):
    """Hammertone: speckle over blotches, lit from above, grime settling toward the bottom."""
    w, h = size
    n = _NP.normal(0, grain, (w, h)) + _mottle(w, h, 6) * mottle + _mottle(w, h, 40) * mottle * 0.8
    shade = np.linspace(light[0], light[1], h)[None, :]
    grime = 1 - 0.18 * np.clip(np.linspace(-0.6, 1, h), 0, 1)[None, :] ** 2
    rgb = (np.array(base, float)[None, None, :] + n[..., None]) * (shade * grime)[..., None]
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


def wear(surf, rect, amount=1.0, paint=STEEL):
    """Years of hands and boots: chipped edges, scratches, grime in the corners."""
    r = pygame.Rect(rect)
    rng = random.Random(_seed(r.topleft, r.size))
    layer = pygame.Surface(r.size, pygame.SRCALPHA)
    for _ in range(int(r.w * r.h / 2500 * amount)):  # scratches
        x, y = rng.uniform(0, r.w), rng.uniform(0, r.h)
        a, ln = rng.uniform(-0.5, 0.5) + (math.pi / 2 if rng.random() < 0.3 else 0), rng.uniform(4, 26)
        light = rng.random() < 0.6
        pygame.draw.line(layer, (220, 220, 210, 45) if light else (0, 0, 0, 55), (x, y),
                         (x + math.cos(a) * ln, y + math.sin(a) * ln), 1)
    for _ in range(int((r.w + r.h) / 22 * amount)):  # chips along the edges
        edge = rng.random()
        if edge < 0.5:
            x, y = rng.uniform(0, r.w), rng.choice((rng.uniform(0, 5), r.h - rng.uniform(0, 5)))
        else:
            x, y = rng.choice((rng.uniform(0, 5), r.w - rng.uniform(0, 5))), rng.uniform(0, r.h)
        rad = rng.uniform(1.5, 4.5)
        pygame.draw.circle(layer, (*BARE, 210), (x, y), rad)
        pygame.draw.circle(layer, (*[min(255, v + 30) for v in paint], 120), (x - 1, y - 1), rad, 1)
    for corner in ((0, r.h), (r.w, r.h), (0, 0), (r.w, 0)):  # grime gathers in corners, most at the bottom
        for k in range(8, 0, -1):
            weight = 1.0 if corner[1] else 0.5
            pygame.draw.circle(layer, (20, 18, 14, int(10 * weight * amount)), corner, k * 7)
    for _ in range(int(3 * amount)):  # thumb smudges
        x, y = rng.uniform(10, r.w - 10), rng.uniform(r.h * 0.4, r.h - 6)
        pygame.draw.ellipse(layer, (24, 22, 18, 24), (x, y, rng.uniform(10, 22), rng.uniform(6, 12)))
    surf.blit(layer, r.topleft)


def screw(surf, pos, r=4):
    """Phillips pan-head screw, slots at a random twist, a little rust bleeding out."""
    x, y = int(pos[0]), int(pos[1])
    rng = random.Random(_seed(x, y))
    if rng.random() < 0.5:
        pygame.draw.ellipse(surf, (96, 70, 44), (x - 2, y, 4 + rng.randint(0, 3), r + rng.randint(2, 6)))
    pygame.draw.circle(surf, (18, 18, 17), (x + 1, y + 1), r)
    pygame.draw.circle(surf, (112, 112, 106), (x, y), r)
    pygame.draw.circle(surf, (150, 150, 142), (x - 1, y - 1), max(1, r - 2))
    a = rng.uniform(0, math.pi)
    for k in (0, math.pi / 2):
        dx, dy = math.cos(a + k) * (r - 1), math.sin(a + k) * (r - 1)
        pygame.draw.line(surf, (48, 48, 46), (x - dx, y - dy), (x + dx, y + dy), 1)


def panel(surf, rect, base=STEEL, screws=True):
    """Painted console section, worn, with screws in the corners."""
    r = pygame.Rect(rect)
    surf.blit(texture(r.size, base), r.topleft)
    bevel(surf, r)
    wear(surf, r, 1.0, base)
    if screws:
        for x in (r.left + 8, r.right - 8):
            for y in (r.top + 8, r.bottom - 8):
                screw(surf, (x, y))


def faceplate(surf, rect, screws=True):
    """Black instrument plate, faded and rubbed bare where hands go."""
    r = pygame.Rect(rect)
    pygame.draw.rect(surf, (16, 16, 15), r.inflate(4, 4), border_radius=3)
    surf.blit(texture(r.size, FACE, grain=3, light=(1.12, 0.9), mottle=7), r.topleft)
    bevel(surf, r, light=FACE_EDGE, dark=(12, 12, 11), width=1)
    wear(surf, r, 0.7, FACE)
    if screws:
        for x in (r.left + 7, r.right - 7):
            for y in (r.top + 7, r.bottom - 7):
                screw(surf, (x, y), 3)


def _faded(color, key):
    """Engraving fill wears unevenly: a stable per-label fade."""
    f = 0.72 + 0.28 * (_seed(key) % 100) / 100
    return tuple(int(c * f) for c in color)


def engrave(surf, text, pos, size=12, color=LEGEND, center=False, bold=True):
    label = sans(size, bold).render(text, True, _faded(color, text) if color in (LEGEND, LEGEND_DIM) else color)
    surf.blit(label, label.get_rect(center=pos) if center else pos)


def label_plate(surf, center, text, size=12):
    """Engraved laminate plate, edges rubbed, held on by two screws."""
    label = sans(size, True).render(text, True, _faded(LEGEND, text))
    r = label.get_rect(center=center).inflate(26, 8)
    pygame.draw.rect(surf, (14, 14, 13), r.move(1, 1), border_radius=2)
    pygame.draw.rect(surf, (32, 32, 31), r, border_radius=2)
    pygame.draw.rect(surf, (90, 88, 82), r, 1, border_radius=2)
    surf.blit(label, label.get_rect(center=center))
    for x in (r.left + 6, r.right - 6):
        pygame.draw.circle(surf, (120, 118, 110), (x, r.centery), 2)


def dymo(surf, pos, text, size=11):
    """Embossed label-maker tape, curling at one end."""
    label = sans(size, True).render(text, True, (226, 222, 208))
    r = label.get_rect(topleft=pos).inflate(10, 4)
    pygame.draw.rect(surf, (24, 26, 30), r, border_radius=2)
    pygame.draw.line(surf, (60, 62, 66), (r.right - 3, r.top + 1), (r.right - 1, r.bottom - 2), 2)
    surf.blit(label, label.get_rect(center=r.center))


def tape(surf, center, text, angle=0.0, size=13):
    """A strip of masking tape with a grease-pencil note: the crew's own amendments to the manual."""
    label = hand(size).render(text, True, (40, 34, 30))
    w, h = label.get_width() + 18, label.get_height() + 6
    strip = pygame.Surface((w, h), pygame.SRCALPHA)
    strip.fill((*TAPE, 228))
    rng = random.Random(_seed(text))
    for x in range(0, w, 3):  # torn ends
        for end in (0, w - 3):
            if rng.random() < 0.5:
                pygame.draw.rect(strip, (0, 0, 0, 0), (end + rng.randint(0, 2), x % h, 2, 3))
    pygame.draw.rect(strip, (180, 164, 120, 160), strip.get_rect(), 1)
    strip.blit(label, (9, 3))
    rot = pygame.transform.rotate(strip, angle)
    surf.blit(rot, rot.get_rect(center=center))


# ---------- instruments ----------
def _dial(radius):
    """Aged black instrument face in a dull, scuffed bezel, shaded with numpy."""
    size = radius * 2 + 2
    c = size / 2
    x, y = np.ogrid[:size, :size]
    d = np.hypot(x - c, y - c)
    ang = np.arctan2(c - y, x - c)
    rgb = np.zeros((size, size, 3))
    rim = (d <= radius) & (d > radius - 7)
    lit = 0.65 + 0.4 * np.cos(ang - 2.36) + _NP.normal(0, 0.06, (size, size))
    rgb[rim] = np.array(CHROME)[None, :] * lit[rim][:, None]
    face = d <= radius - 7
    tint = np.array((30, 29, 26))  # black gone slightly brown and dusty
    rgb[face] = (tint[None, :] + (_NP.normal(0, 3, (size, size)) + _mottle(size, size, 10) * 10)[face][:, None]) \
        * (1.2 - 0.35 * (d[face] / radius))[:, None]
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
            pygame.draw.line(surf, (184, 64, 46), polar(c, rr - 1, a), polar(c, rr - 6, a), 3)
    for v in np.arange(lo, hi + minor / 2, minor):
        a = value_angle(v, lo, hi, start, sweep)
        is_major = abs((v - lo) / major - round((v - lo) / major)) < 1e-6
        inner = polar(c, rr - (9 if is_major else 4), a)
        pygame.draw.line(surf, LEGEND if is_major else LEGEND_DIM, polar(c, rr, a), inner,
                         2 if is_major else 1)
        if is_major:
            engrave(surf, labels.get(v, "") if labels else f"{v:g}", polar(c, rr - 19, a), 11, LEGEND, center=True)
    if title:
        engrave(surf, title, (c[0], c[1] + radius * 0.24), 12, LEGEND, center=True)
    if units:
        engrave(surf, units, (c[0], c[1] + radius * 0.4), 10, WARN, center=True, bold=False)
    return surf, c


def glint(radius):
    """Old glass: a soft reflection and a hairline crack or two."""
    size = radius * 2 + 2
    x, y = np.ogrid[:size, :size]
    c = size / 2
    d = np.hypot(x - c, y - c)
    band = np.exp(-((x - c * 0.72) ** 2 / (radius * 0.5) ** 2 + (y - c * 0.5) ** 2 / (radius * 0.2) ** 2))
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    surf.fill((255, 250, 235, 0))
    alpha = pygame.surfarray.pixels_alpha(surf)
    alpha[:] = np.where(d < radius - 7, band * 38 + 8, 0).astype(np.uint8)  # +8: a film of grime on the glass
    del alpha
    rng = random.Random(_seed(radius, "crack"))
    if rng.random() < 0.6:
        p = (c + rng.uniform(-0.6, 0.6) * radius, c + rng.uniform(-0.6, 0.6) * radius)
        for _ in range(3):
            q = (p[0] + rng.uniform(-18, 18), p[1] + rng.uniform(-18, 18))
            pygame.draw.line(surf, (235, 235, 225, 70), p, q, 1)
            p = q
    return surf


def needle(surf, c, deg, length, color=WARN, width=3, tail=12):
    tip, back = polar(c, length, deg), polar(c, -tail, deg)
    pygame.draw.polygon(surf, color, [tip, polar(c, width, deg + 90), back, polar(c, width, deg - 90)])
    pygame.draw.circle(surf, (14, 14, 13), (int(c[0]), int(c[1])), 6)
    pygame.draw.circle(surf, (86, 84, 78), (int(c[0]), int(c[1])), 3)


class Needle:
    """Spring-damped needle with a little mechanical flicker."""

    def __init__(self, value=0.0):
        self.v, self.vel = value, 0.0

    def update(self, target, dt, jitter=0.0):
        self.vel += ((target - self.v) * 60 - self.vel * 12) * dt
        self.v += self.vel * dt
        return self.v + (_FX.gauss(0, jitter) if jitter else 0.0)


# ---------- mechanical drum counters ----------
DRUM_INK = {AMBER: (236, 228, 204), GREEN: (196, 226, 180), RED: (236, 132, 108)}


@lru_cache(maxsize=1024)
def _drum(ch, size, ink, skew, dp):
    """One drum of an odometer-style counter: off-white digit on a black wheel, shaded round, sometimes caught
    a little between numbers."""
    font = mono(size, True)
    w, h = font.size("0")
    cell = pygame.Surface((w + 4, h + 4))
    for k in range(h + 4):  # the drum's curvature
        shade = int(34 * (1 - abs(k - (h + 4) / 2) / ((h + 4) / 2)) ** 0.8)
        pygame.draw.line(cell, (14 + shade, 14 + shade, 13 + shade), (0, k), (w + 4, k))
    cell.blit(font.render(ch, True, ink), (2, 2 + skew))
    if skew:  # the next number peeking in from the edge
        nxt = str((int(ch) + (1 if skew < 0 else -1)) % 10) if ch.isdigit() else " "
        cell.blit(font.render(nxt, True, ink), (2, 2 + skew + (h + 2) * (1 if skew < 0 else -1)))
    for k in (0, 1, h + 2, h + 3):  # shadow where the wheel turns away
        pygame.draw.line(cell, (6, 6, 6), (0, k), (w + 4, k))
    if dp:
        pygame.draw.circle(cell, ink, (w + 2, h + 1), max(1, size // 9))
    return cell


def counter(surf, pos, text, size=15, color=AMBER):
    """Mechanical drum counter in a grimy window. '.' marks the previous drum; commas are dropped."""
    ink = DRUM_INK.get(color, (236, 228, 204))
    drums = []
    for ch in text:
        if ch == ".":
            if drums:
                drums[-1][1] = True
        elif ch != ",":
            drums.append([ch, False])
    x, y = pos
    pygame.draw.rect(surf, (10, 10, 10), (x - 3, y - 3, sum(mono(size, True).size("0")[0] + 5 for _ in drums) + 5,
                                          size + 10))
    for i, (ch, dp) in enumerate(drums):
        skew = (_seed(pos, i, ch) % 5) - 2 if ch.isdigit() else 0  # a drum or two never quite seats
        g = _drum(ch, size, ink, skew if abs(skew) == 2 else 0, dp)
        surf.blit(g, (x, y))
        x += g.get_width() + 1
    pygame.draw.rect(surf, (88, 86, 80), (pos[0] - 3, y - 3, x - pos[0] + 5, size + 10), 1)
    return x - pos[0]


# ---------- controls ----------
@lru_cache(maxsize=32)
def _glow(color, r):
    surf = pygame.Surface((r * 6, r * 6), pygame.SRCALPHA)
    for k in range(r * 3, r, -2):
        pygame.draw.circle(surf, (*color, int(50 * (1 - k / (r * 3)))), (r * 3, r * 3), k)
    return surf


def _warm(color, on):
    """Incandescent behind coloured glass: warm and a touch uneven when lit, a dark dirty lens when not."""
    if on:
        return tuple(min(255, int(v * 0.92 + 18)) for v in color)
    return tuple(int(18 + v * 0.13) for v in color)


def lamp(surf, c, on, color, r=6):
    """Pilot lamp: a domed lens in a knurled bezel."""
    color = SAFE.get(color, color) if SETTINGS["colorblind"] else color
    x, y = int(c[0]), int(c[1])
    if on:
        surf.blit(_glow(color, r), (x - r * 3, y - r * 3))
    pygame.draw.circle(surf, (12, 12, 11), (x, y), r + 3)
    pygame.draw.circle(surf, (96, 94, 88), (x, y), r + 2, 1)
    pygame.draw.circle(surf, _warm(color, on), (x, y), r)
    if on:
        pygame.draw.circle(surf, (255, 248, 220), (x - r // 3, y - r // 3), max(1, r // 3))
    pygame.draw.circle(surf, (40, 36, 30), (x + r // 3, y + r // 3), max(1, r // 4))  # grime on the lens


def annunciator(surf, rect, legend, on, color):
    """Warning annunciator tile: legend engraved on the lens, so it reads lit or dark, in any colour."""
    color = SAFE.get(color, color) if SETTINGS["colorblind"] else color
    r = pygame.Rect(rect)
    pygame.draw.rect(surf, (10, 10, 9), r.inflate(4, 4))
    lens = _warm(color, on)
    pygame.draw.rect(surf, lens, r)
    if on:  # the bulb's hot spot
        hot = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.ellipse(hot, (255, 250, 220, 60), (r.w * 0.2, 1, r.w * 0.6, r.h - 2))
        surf.blit(hot, r.topleft)
    pygame.draw.line(surf, (0, 0, 0), (r.left, r.bottom - 1), (r.right - 1, r.bottom - 1))
    engrave(surf, legend, r.center, 10, (28, 24, 20) if on else tuple(70 + v // 5 for v in color), center=True)


def button(surf, rect, text, lit=False, color=AMBER):
    """Square backlit push-button: worn cap, legend rubbed by thumbs, glows when on."""
    r = pygame.Rect(rect)
    pygame.draw.rect(surf, (12, 12, 11), r.inflate(6, 6), border_radius=3)
    pygame.draw.rect(surf, (74, 74, 70), r.inflate(2, 2), border_radius=3)
    cap = _warm(color, True) if lit else (78, 78, 74)
    pygame.draw.rect(surf, cap, r, border_radius=2)
    pygame.draw.line(surf, tuple(min(255, v + 40) for v in cap), (r.left + 3, r.top + 1), (r.right - 4, r.top + 1))
    thumb = (r.centerx - r.w // 4, r.centery - 3, r.w // 2, 8)  # worn where the thumb lands
    pygame.draw.ellipse(surf, tuple(max(0, v - 18) for v in cap), thumb)
    size = 11
    while size > 7 and sans(size, True).size(text)[0] > r.w - 4:  # shrink the legend to fit the cap
        size -= 1
    engrave(surf, text, r.center, size, (24, 22, 18) if lit else LEGEND, center=True)


def toggle(surf, c, up, guard_color=None):
    """Bat-handle toggle on a nut; an optional flip guard (red for the FIRE switches), paint worn off its edge."""
    x, y = int(c[0]), int(c[1])
    if guard_color:
        g = tuple(int(v * 0.6) for v in guard_color)
        pygame.draw.rect(surf, g, (x - 15, y - 26, 30, 52), 2, border_radius=6)
        pygame.draw.line(surf, BARE, (x - 13, y - 26), (x - 4, y - 26), 2)
    pygame.draw.circle(surf, (16, 16, 15), (x, y), 11)
    pygame.draw.circle(surf, CHROME, (x, y), 9)
    pygame.draw.circle(surf, (92, 90, 86), (x, y), 5)
    tip = (x, y - 20) if up else (x, y + 20)
    pygame.draw.line(surf, (196, 194, 186), (x, y), tip, 5)
    pygame.draw.circle(surf, (224, 220, 210), tip, 4)


def helm_yoke(radius):
    """Control yoke on the ship-control panel, grips worn shiny, tape on one horn."""
    size = radius * 2 + 40
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    c = size // 2
    black, grip = (30, 30, 29), (46, 45, 42)
    pygame.draw.rect(surf, black, (c - radius - 6, c - 9, (radius + 6) * 2, 18), border_radius=8)
    for side in (-1, 1):
        gx = c + side * (radius + 2)
        pygame.draw.rect(surf, grip, (gx - 11, c - radius * 0.75, 22, radius * 1.5), border_radius=10)
        pygame.draw.line(surf, (110, 108, 100), (gx - 5, c - radius * 0.6), (gx - 5, c + radius * 0.6), 2)  # shiny wear
        pygame.draw.circle(surf, RED if side < 0 else (200, 196, 80), (gx, int(c - radius * 0.6)), 4)
    pygame.draw.rect(surf, (*TAPE, 230), (c + radius - 9, c + radius * 0.25, 22, 10))  # tape repair
    pygame.draw.circle(surf, black, (c, c), 18)
    pygame.draw.circle(surf, CHROME, (c, c), 12)
    pygame.draw.circle(surf, (70, 68, 64), (c, c), 6)
    pygame.draw.line(surf, WHITE, (c, c - 18), (c, c - 30), 3)
    return surf


# ---------- glass ----------
def bezel_overlay(size, frames):
    """Full-screen alpha overlay: painted steel bezels around the CRTs, worn, with screws and glass glare.
    frames: [(outer_rect, hole_rect, corner_radius or None for round)]."""
    overlay = pygame.Surface(size, pygame.SRCALPHA)
    for outer, hole, radius in frames:
        outer, hole = pygame.Rect(outer), pygame.Rect(hole)
        tex = texture(outer.size, (78, 79, 76), grain=3, light=(1.12, 0.84)).convert_alpha()
        wear(tex, tex.get_rect(), 1.2, (78, 79, 76))
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
        sheen = np.exp(-((u - 0.75) ** 2 / 0.02 + (v - 0.12) ** 2 / 0.002))  # a window reflected top right
        glare = np.clip(1 - (u + v) * 1.3, 0, 1) ** 2 * 26 + sheen * 30
        alpha = np.where(dist > 0, 255, glare + 6).astype(np.uint8)  # +6: smoke film on the glass
        rgb = pygame.surfarray.pixels3d(tex)
        rgb[dist <= 0] = (255, 248, 230)
        lip = (dist > 0) & (dist < 6)  # rubber gasket between bezel and tube
        rgb[lip] = (18, 18, 17)
        del rgb
        pygame.surfarray.pixels_alpha(tex)[:] = alpha
        bevel(tex, tex.get_rect(), light=(118, 118, 112), dark=(14, 14, 13), width=2)
        overlay.blit(tex, outer.topleft)
        if radius is None:
            for k in range(4):
                screw(overlay, polar(hole.center, hole.w / 2 + 13, k * 90 + 45), 4)
        else:
            for px in (outer.left + 12, outer.right - 12):
                for py in (outer.top + 12, outer.bottom - 12):
                    screw(overlay, (px, py), 5)
    return overlay
