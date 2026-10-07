"""Procedural steampunk workstation art: brushed brass, riveted iron, aged paper, glass.
Everything static is rendered once at startup; per-frame helpers draw only the moving parts."""
import math
import random
from functools import lru_cache

import numpy as np
import pygame

BRASS = (172, 132, 64)
BRASS_LIGHT = (238, 206, 136)
BRASS_DARK = (92, 66, 28)
IRON = (60, 58, 55)
IRON_DARK = (24, 23, 22)
PAPER = (226, 212, 172)
INK = (36, 27, 20)
INK_RED = (160, 34, 22)
WOOD = (104, 60, 30)
WALL = (30, 32, 30)


@lru_cache(maxsize=None)
def serif(size, bold=False):
    return pygame.font.SysFont("georgia,timesnewroman,serif", size, bold=bold)


@lru_cache(maxsize=None)
def mono(size, bold=False):
    return pygame.font.SysFont("couriernew,consolas,monospace", size, bold=bold)


def polar(c, r, deg):
    """Point at radius r, angle deg (maths convention: 0 = east, CCW positive) from c on a y-down screen."""
    a = math.radians(deg)
    return c[0] + r * math.cos(a), c[1] - r * math.sin(a)


def value_angle(v, lo, hi, start=225.0, sweep=270.0):
    """Dial angle for value v: lo sits at `start`, hi at start - sweep (clockwise)."""
    return start - clamp01((v - lo) / (hi - lo)) * sweep


def angle_value(deg, lo, hi, start=225.0, sweep=270.0):
    """Inverse of value_angle, for clicking on a dial."""
    return lo + clamp01(((start - deg) % 360) / sweep) * (hi - lo)


def clamp01(f):
    return min(max(f, 0.0), 1.0)


# ---------- materials ----------
def texture(size, base, grain=8.0, streak=0.0, light=(1.12, 0.82)):
    """Flat noisy material, optional horizontal brushing, lit from the top."""
    w, h = size
    n = np.random.normal(0, grain, (w, h))
    if streak:
        n += np.random.normal(0, streak, (1, h))
    shade = np.linspace(light[0], light[1], h)[None, :, None]
    rgb = (np.array(base, float)[None, None, :] + n[..., None]) * shade
    surf = pygame.Surface(size)
    pygame.surfarray.blit_array(surf, np.clip(rgb, 0, 255).astype(np.uint8))
    return surf


def bevel(surf, rect, light=BRASS_LIGHT, dark=BRASS_DARK, width=2):
    r = pygame.Rect(rect)
    for i in range(width):
        pygame.draw.line(surf, light, (r.left + i, r.top + i), (r.right - 1 - i, r.top + i))
        pygame.draw.line(surf, light, (r.left + i, r.top + i), (r.left + i, r.bottom - 1 - i))
        pygame.draw.line(surf, dark, (r.left + i, r.bottom - 1 - i), (r.right - 1 - i, r.bottom - 1 - i))
        pygame.draw.line(surf, dark, (r.right - 1 - i, r.top + i), (r.right - 1 - i, r.bottom - 1 - i))


def rivet(surf, pos, r=4):
    x, y = int(pos[0]), int(pos[1])
    pygame.draw.circle(surf, (18, 14, 8), (x + 1, y + 1), r)
    pygame.draw.circle(surf, BRASS_DARK, (x, y), r)
    pygame.draw.circle(surf, BRASS, (x, y), r - 1)
    pygame.draw.circle(surf, BRASS_LIGHT, (x - r // 3, y - r // 3), max(1, r // 3))


def plate(surf, rect, base=BRASS, rivets=True, inset=9, spacing=80):
    """Riveted panel: brushed for brass, plain grain for iron."""
    r = pygame.Rect(rect)
    brushed = base == BRASS
    surf.blit(texture(r.size, base, grain=6 if brushed else 5, streak=7 if brushed else 0), r.topleft)
    if brushed:
        bevel(surf, r)
    else:
        bevel(surf, r, light=(98, 94, 88), dark=(12, 12, 12))
    if rivets:
        nx, ny = max(2, r.w // spacing + 1), max(2, r.h // spacing + 1)
        for x in np.linspace(r.left + inset, r.right - inset, nx):
            rivet(surf, (x, r.top + inset))
            rivet(surf, (x, r.bottom - inset))
        for y in np.linspace(r.top + inset, r.bottom - inset, ny)[1:-1]:
            rivet(surf, (r.left + inset, y))
            rivet(surf, (r.right - inset, y))


def plaque(surf, center, text, size=12, base=IRON_DARK, color=BRASS_LIGHT):
    """Small engraved name plate."""
    label = serif(size, True).render(text, True, color)
    r = label.get_rect(center=center).inflate(14, 6)
    pygame.draw.rect(surf, base, r, border_radius=3)
    pygame.draw.rect(surf, BRASS_DARK, r, 1, border_radius=3)
    surf.blit(label, label.get_rect(center=center))


def engrave(surf, text, pos, size=12, color=INK, center=False, bold=True):
    label = serif(size, bold).render(text, True, color)
    surf.blit(label, label.get_rect(center=pos) if center else pos)


# ---------- dials ----------
def _round_material(radius, rim=9):
    """Brass rim + aged paper disc as an alpha surface, shaded with numpy."""
    size = radius * 2 + 2
    c = size / 2
    x, y = np.ogrid[:size, :size]
    d = np.hypot(x - c, y - c)
    ang = np.arctan2(c - y, x - c)  # y-down -> maths angle
    lit = 0.78 + 0.32 * np.cos(ang - 2.36)  # light from upper left
    rgb = np.zeros((size, size, 3))
    rim_mask = (d <= radius) & (d > radius - rim)
    rgb[rim_mask] = np.array(BRASS)[None, :] * lit[rim_mask][:, None]
    face = d <= radius - rim
    grain = np.random.normal(0, 6, (size, size))
    age = 1 - 0.28 * np.clip(d / (radius - rim), 0, 1) ** 3  # yellowed, darker toward the rim
    for _ in range(3):  # tea stains
        sx, sy, sr = random.uniform(0.3, 1.7) * c, random.uniform(0.3, 1.7) * c, random.uniform(0.1, 0.3) * radius
        age = age - 0.06 * np.exp(-((x - sx) ** 2 + (y - sy) ** 2) / (2 * sr * sr))
    rgb[face] = (np.array(PAPER)[None, :] + grain[face][:, None]) * age[face][:, None]
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.surfarray.pixels3d(surf)[:] = np.clip(rgb, 0, 255).astype(np.uint8)
    alpha = pygame.surfarray.pixels_alpha(surf)
    alpha[:] = np.where(d <= radius, 255, 0).astype(np.uint8)
    del alpha
    pygame.draw.circle(surf, BRASS_DARK, (int(c), int(c)), radius - rim, 1)
    return surf


def gauge_face(radius, title, lo, hi, major, minor, red=None, units="", start=225.0, sweep=270.0, labels=None):
    """Steam-gauge face: ticks, numbers, red zone, title. Returns (surface, centre-in-surface)."""
    surf = _round_material(radius)
    c = (surf.get_width() / 2, surf.get_height() / 2)
    rr = radius - 12
    if red:
        a0, a1 = value_angle(red[0], lo, hi, start, sweep), value_angle(red[1], lo, hi, start, sweep)
        for k in range(41):
            a = a0 + (a1 - a0) * k / 40
            pygame.draw.line(surf, INK_RED, polar(c, rr - 1, a), polar(c, rr - 7, a), 3)
    for v in np.arange(lo, hi + minor / 2, minor):
        a = value_angle(v, lo, hi, start, sweep)
        is_major = abs((v - lo) / major - round((v - lo) / major)) < 1e-6
        pygame.draw.line(surf, INK, polar(c, rr, a), polar(c, rr - (10 if is_major else 5), a), 2 if is_major else 1)
        if is_major:
            text = labels.get(v, "") if labels else f"{v:g}"
            engrave(surf, text, polar(c, rr - 20, a), 11, INK, center=True)
    if title:
        engrave(surf, title, (c[0], c[1] + radius * 0.22), 12, INK, center=True)
    if units:
        engrave(surf, units, (c[0], c[1] + radius * 0.37), 10, INK_RED, center=True, bold=False)
    return surf, c


def glint(radius):
    """Glass reflection for a round gauge."""
    size = radius * 2 + 2
    x, y = np.ogrid[:size, :size]
    c = size / 2
    d = np.hypot(x - c, y - c)
    band = np.exp(-((x - c * 0.7) ** 2 / (radius * 0.45) ** 2 + (y - c * 0.55) ** 2 / (radius * 0.22) ** 2))
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    surf.fill((255, 255, 240, 0))
    alpha = pygame.surfarray.pixels_alpha(surf)
    alpha[:] = np.where(d < radius - 9, band * 70, 0).astype(np.uint8)
    del alpha
    return surf


def needle(surf, c, deg, length, color=INK, width=3, tail=14):
    tip, back = polar(c, length, deg), polar(c, -tail, deg)
    pygame.draw.polygon(surf, color, [tip, polar(c, width, deg + 90), back, polar(c, width, deg - 90)])
    pygame.draw.circle(surf, BRASS_DARK, (int(c[0]), int(c[1])), 6)
    pygame.draw.circle(surf, BRASS, (int(c[0]), int(c[1])), 4)


class Needle:
    """Spring-damped needle with a little mechanical flicker."""

    def __init__(self, value=0.0):
        self.v, self.vel = value, 0.0

    def update(self, target, dt, jitter=0.0):
        self.vel += ((target - self.v) * 60 - self.vel * 12) * dt
        self.v += self.vel * dt
        return self.v + (random.gauss(0, jitter) if jitter else 0.0)


def telegraph_face(radius, labels):
    """Engine-order telegraph: paper semicircle split into sectors, left to right."""
    surf = _round_material(radius, rim=10)
    c = (surf.get_width() / 2, surf.get_height() / 2)
    n = len(labels)
    for i in range(n + 1):
        a = 180 - i * 180 / n
        pygame.draw.line(surf, INK, polar(c, radius - 10, a), polar(c, radius * 0.86, a), 2)  # rim ticks only
    for i, text in enumerate(labels):
        a = 180 - (i + 0.5) * 180 / n
        engrave(surf, text, polar(c, radius * 0.7, a), 13, INK_RED if text in ("STOP", "FLANK") else INK, center=True)
    return surf.subsurface((0, 0, surf.get_width(), int(c[1]) + 4)).copy(), c


def telegraph_angle(index, count):
    return 180 - (index + 0.5) * 180 / count


def ship_wheel(radius):
    size = radius * 2 + 32
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    c = (size // 2, size // 2)
    for k in range(8):
        a = k * 45
        pygame.draw.line(surf, WOOD, c, polar(c, radius + 12, a), 6)
        pygame.draw.circle(surf, (80, 44, 20), [int(v) for v in polar(c, radius + 12, a)], 6)
        pygame.draw.circle(surf, (140, 90, 50), [int(v) for v in polar(c, radius + 11, a + 4)], 2)
    pygame.draw.circle(surf, WOOD, c, radius, 10)
    pygame.draw.circle(surf, BRASS, c, radius - 9, 2)
    pygame.draw.circle(surf, BRASS_DARK, c, 16)
    pygame.draw.circle(surf, BRASS, c, 13)
    pygame.draw.circle(surf, BRASS_LIGHT, (c[0] - 4, c[1] - 4), 4)
    pygame.draw.line(surf, BRASS_LIGHT, polar(c, radius + 12, 90), polar(c, radius - 2, 90), 3)  # king spoke
    return surf


# ---------- small controls ----------
@lru_cache(maxsize=32)
def _glow(color, r):
    surf = pygame.Surface((r * 6, r * 6), pygame.SRCALPHA)
    for k in range(r * 3, r, -2):
        pygame.draw.circle(surf, (*color, int(60 * (1 - k / (r * 3)))), (r * 3, r * 3), k)
    return surf


def lamp(surf, c, on, color, r=8):
    x, y = int(c[0]), int(c[1])
    if on:
        g = _glow(color, r)
        surf.blit(g, (x - r * 3, y - r * 3))
    pygame.draw.circle(surf, BRASS_DARK, (x, y), r + 3)
    pygame.draw.circle(surf, BRASS, (x, y), r + 2)
    pygame.draw.circle(surf, color if on else tuple(v // 5 for v in color), (x, y), r)
    pygame.draw.circle(surf, (255, 255, 255) if on else (90, 90, 90), (x - r // 3, y - r // 3), max(1, r // 4))


def toggle(surf, c, up):
    x, y = int(c[0]), int(c[1])
    pygame.draw.circle(surf, IRON_DARK, (x, y), 13)
    pygame.draw.circle(surf, BRASS, (x, y), 11)
    pygame.draw.circle(surf, BRASS_DARK, (x, y), 5)
    tip = (x, y - 22) if up else (x, y + 22)
    pygame.draw.line(surf, (200, 200, 196), (x, y), tip, 5)
    pygame.draw.circle(surf, (230, 230, 226), tip, 5)


def button(surf, rect, text, lit=False, color=(200, 60, 40)):
    r = pygame.Rect(rect)
    pygame.draw.rect(surf, IRON_DARK, r.inflate(4, 4), border_radius=5)
    pygame.draw.rect(surf, color if lit else BRASS, r, border_radius=4)
    pygame.draw.line(surf, BRASS_LIGHT, (r.left + 4, r.top + 1), (r.right - 4, r.top + 1))
    engrave(surf, text, r.center, 11, (255, 236, 210) if lit else INK, center=True)


@lru_cache(maxsize=256)
def _drum_glyph(ch, size):
    font = mono(size, True)
    w, h = font.size("0")
    cell = pygame.Surface((w + 4, h + 4))
    cell.fill((18, 16, 14))
    for k in range(h + 4):  # drum curvature: darker at top and bottom
        shade = int(40 * (1 - abs(k - (h + 4) / 2) / ((h + 4) / 2)))
        pygame.draw.line(cell, (18 + shade, 16 + shade, 14 + shade), (0, k), (w + 4, k))
    cell.blit(font.render(ch, True, (236, 226, 200)), (2, 2))
    return cell


def counter(surf, pos, text, size=15):
    """Mechanical drum counter readout. Returns the drawn width."""
    x, y = pos
    for ch in text:
        g = _drum_glyph(ch, size)
        surf.blit(g, (x, y))
        x += g.get_width() + 1
    pygame.draw.rect(surf, BRASS_DARK, (pos[0] - 2, y - 2, x - pos[0] + 3, g.get_height() + 4), 1)
    return x - pos[0]


# ---------- glass ----------
def bezel_overlay(size, frames):
    """Full-screen alpha overlay: iron bezels with transparent windows and glass glare.
    frames: [(outer_rect, hole_rect, corner_radius or None for round)]."""
    overlay = pygame.Surface(size, pygame.SRCALPHA)
    for outer, hole, radius in frames:
        outer, hole = pygame.Rect(outer), pygame.Rect(hole)
        tex = texture(outer.size, IRON, grain=5).convert_alpha()
        x, y = np.ogrid[:outer.w, :outer.h]
        hx, hy = hole.centerx - outer.x, hole.centery - outer.y
        if radius is None:
            rr = hole.w / 2
            dist = np.hypot(x - hx, y - hy) - rr
        else:
            qx = np.maximum(np.abs(x - hx) - (hole.w / 2 - radius), 0)
            qy = np.maximum(np.abs(y - hy) - (hole.h / 2 - radius), 0)
            dist = np.hypot(qx, qy) - radius
        u = (x - (hole.x - outer.x)) / hole.w
        v = (y - (hole.y - outer.y)) / hole.h
        glare = np.clip(1 - (u + v) * 1.3, 0, 1) ** 2 * 34 + np.exp(-((u - 0.75) ** 2 / 0.02 + (v - 0.12) ** 2 / 0.002)) * 40
        alpha = np.where(dist > 0, 255, glare).astype(np.uint8)
        rgb = pygame.surfarray.pixels3d(tex)
        inside = dist <= 0
        rgb[inside] = (255, 255, 245)
        ring = (dist > 0) & (dist < 7)  # brass lip around the glass, lit from the top
        lip = np.broadcast_to(1.15 - 0.4 * np.clip(v, 0, 1), ring.shape)[ring]
        rgb[ring] = np.clip(np.array(BRASS)[None, :] * lip[:, None], 0, 255).astype(np.uint8)
        del rgb
        pygame.surfarray.pixels_alpha(tex)[:] = alpha
        bevel(tex, tex.get_rect(), light=(100, 96, 90), dark=(10, 10, 10), width=3)
        overlay.blit(tex, outer.topleft)
        if radius is None:
            for k in range(8):  # rivets round the scope
                rivet(overlay, polar(hole.center, hole.w / 2 + 14, k * 45 + 22.5), 5)
        else:
            for px in np.linspace(outer.left + 14, outer.right - 14, 9):
                rivet(overlay, (px, outer.top + 12), 5)
                rivet(overlay, (px, outer.bottom - 12), 5)
            for py in np.linspace(outer.top + 14, outer.bottom - 14, 7)[1:-1]:
                rivet(overlay, (outer.left + 12, py), 5)
                rivet(overlay, (outer.right - 12, py), 5)
    return overlay
