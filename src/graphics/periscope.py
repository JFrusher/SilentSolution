"""Periscope eyepiece: sky, sea and ships from a lens ~1.5 m above the waves, then the optics on top.
Draws what PeriscopeOptics reported plus the sea itself (environment); it never reads ships from the world."""
import math
import random
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
import pygame

from layout import EYE
from sim import R_EFF, SHIP_CLASSES, angle_diff, horizon_distance

_FX = random.Random()  # presentation-only randomness, so drawing never moves the simulation's dice
_NP = np.random.default_rng()

SEA_DIV = 3                # sky and sea are shaded at 1/SEA_DIV resolution, then smooth-scaled
SUN_BRG, SUN_ELEV = 205.0, 28.0
CLOUD_W, CLOUD_H = 1440, 160  # cloud strip: 0.25 deg per texel in azimuth and elevation (0-40 deg)
RIPPLE_N, RIPPLE_TILE, RIPPLE_SLOPE = 128, 24.0, 0.22  # short chop texture: texels, metres per tile, peak slope

# side profiles in recognition-manual style: (fraction of length from the stern, height above waterline m);
# length and beam come from sim.SHIP_CLASSES
SHAPES = {
    "merchant": dict(
        hull=[(0.02, 0.0), (0.0, 7.5), (0.02, 8.5), (0.11, 8.5), (0.12, 7.0), (0.80, 7.0), (0.82, 10.0),
              (1.0, 10.8), (0.96, 0.0)],
        blocks=[(0.42, 0.58, 7.0, 14.0), (0.45, 0.56, 14.0, 17.5)],
        funnel=(0.34, 0.40, 14.0, 22.0),
        masts=[(0.22, 30.0), (0.72, 29.0)],
        booms=[(0.22, 9.0, 0.12, 7.5), (0.72, 9.0, 0.83, 10.0)]),
    "tanker": dict(
        hull=[(0.01, 0.0), (0.0, 7.0), (0.25, 7.0), (0.26, 6.0), (0.93, 6.5), (1.0, 8.0), (0.97, 0.0)],
        blocks=[(0.05, 0.22, 6.0, 13.0), (0.07, 0.18, 13.0, 16.0), (0.55, 0.62, 6.0, 10.0)],
        funnel=(0.08, 0.14, 16.0, 23.0),
        masts=[(0.58, 26.0), (0.90, 20.0)],
        booms=[]),
    "escort": dict(
        hull=[(0.01, 0.0), (0.0, 4.5), (0.55, 5.0), (0.60, 6.5), (0.92, 7.5), (1.0, 8.2), (0.94, 0.0)],
        blocks=[(0.56, 0.72, 6.5, 12.0), (0.60, 0.68, 12.0, 14.0), (0.80, 0.86, 7.5, 9.0), (0.12, 0.18, 5.0, 6.5)],
        funnel=(0.40, 0.48, 6.0, 12.5),
        masts=[(0.63, 24.0)],
        booms=[]),
}
BURSTS = {"BLAST": (8.0, 70.0), "COLUMN": (5.0, 45.0), "SPLASH": (1.5, 4.0)}  # life s, peak height m


@dataclass
class View:
    brg: float              # true bearing at the centre of the eyepiece
    fov: float              # deg across the eyepiece
    eye: float              # lens height above the water, m
    x: float                # own position: which patch of sea we look over
    y: float
    time: float
    ocean: object           # environment only: swell, wind, rain, visibility
    sightings: list = field(default_factory=list)
    wakes: list = field(default_factory=list)
    bursts: list = field(default_factory=list)
    under: bool = False     # a wave is over the lens
    shake: float = 0.0      # px of vibration (feather, speed)
    scale_ref: float = 0.0  # subtracted from bearings on the tape: 0 = true, own heading = relative
    marks: list = field(default_factory=list)  # (true bearing, letter, colour) set into the bearing tape


def _mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


@lru_cache(maxsize=64)
def _puff(radius, shade, alpha):
    s = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
    for k in range(radius, 0, -1):
        a = int(alpha * (1 - k / (radius + 1)) ** 0.7)
        pygame.draw.circle(s, (shade, shade, shade, a), (radius + 1, radius + 1), k)
    return s


class PeriscopeRenderer:
    def __init__(self):
        n = EYE // SEA_DIV
        g = (np.arange(n) + 0.5) / n - 0.5
        self.gu, self.gv = g[:, None], g[None, :]  # surfarray layout: [x, y]
        self.small = pygame.Surface((n, n))
        self.frame = pygame.Surface((EYE, EYE))
        self.clouds = self._cloud_strip().astype(np.float32)
        self.sky, self.sky_rain = None, None
        self.ripple = self._ripples()
        self.lens = self._lens()
        self.reticles = {}
        self.font = pygame.font.SysFont("consolas,couriernew,monospace", 13, bold=True)
        self.labels = {}
        self.drops = []   # [x, y, r, life] droplets running down the glass
        self.wash = 0.0
        self.last_t = None

    # ---------- static assets ----------
    @staticmethod
    def _cloud_strip():
        """Fractal cloud cover over 360 deg of azimuth: octaves of random noise, smooth-scaled and summed."""
        total = np.zeros((CLOUD_W, CLOUD_H))
        for i, (w, h) in enumerate(((12, 3), (24, 6), (48, 12), (96, 24), (192, 40))):
            noise = _NP.random((w + 1, h))
            noise[-1] = noise[0]  # wrap the seam at 000/360
            src = pygame.Surface((w + 1, h))
            pygame.surfarray.blit_array(src, np.repeat((noise * 255).astype(np.uint8)[..., None], 3, axis=2))
            big = pygame.transform.smoothscale(src, (CLOUD_W, CLOUD_H))
            total += pygame.surfarray.array_red(big) / 255.0 * 0.5 ** i
        total = (total - total.min()) / (total.max() - total.min())
        total *= np.clip(1.4 - np.arange(CLOUD_H) / CLOUD_H, 0.3, 1)[None, :]  # thicker toward the horizon
        return total

    @staticmethod
    def _ripples():
        """Tileable chop: slope maps (x, y) of short wind-waves over a RIPPLE_TILE m square, RIPPLE_N texels."""
        k = 2 * np.pi * np.arange(RIPPLE_N) / RIPPLE_N
        gx = np.zeros((RIPPLE_N, RIPPLE_N), np.float32)
        gy = np.zeros_like(gx)
        for _ in range(14):  # integer wave numbers keep the tile seamless
            mx, my = _FX.randint(-6, 6), _FX.randint(1, 7)
            amp, phase = _FX.uniform(0.4, 1.0) / math.hypot(mx, my), _FX.uniform(0, 2 * np.pi)
            c = np.cos(mx * k[:, None] + my * k[None, :] + phase) * amp
            gx += c * mx
            gy += c * my
        scale = RIPPLE_SLOPE / max(np.abs(gx).max(), np.abs(gy).max())
        return gx * scale, gy * scale

    @staticmethod
    def _lens():
        """Black mask outside the eyepiece circle, vignette and a faint chromatic fringe inside."""
        x, y = np.ogrid[:EYE, :EYE]
        r = np.hypot(x - EYE / 2, y - EYE / 2) / (EYE / 2)
        alpha = np.clip((r - 0.985) / 0.015, 0, 1) * 255 + np.clip((r - 0.55) / 0.45, 0, 1) ** 2.2 * 110 * (r < 0.985)
        s = pygame.Surface((EYE, EYE), pygame.SRCALPHA)
        rgb = pygame.surfarray.pixels3d(s)
        rgb[:] = 0
        fringe = (r > 0.968) & (r < 0.985)
        rgb[fringe] = (40, 70, 90)
        del rgb
        pygame.surfarray.pixels_alpha(s)[:] = np.clip(alpha + fringe * 25, 0, 255).astype(np.uint8)
        return s

    def _reticle(self, fov):
        if fov in self.reticles:
            return self.reticles[fov]
        s = pygame.Surface((EYE, EYE), pygame.SRCALPHA)
        c, ppd = EYE // 2, EYE / fov
        ink = (18, 22, 24, 220)
        pygame.draw.line(s, ink, (40, c), (c - 18, c), 2)
        pygame.draw.line(s, ink, (c + 18, c), (EYE - 40, c), 2)
        pygame.draw.line(s, ink, (c, c + 18), (c, EYE - 60), 2)
        pygame.draw.line(s, ink, (c, 60), (c, c - 60), 1)
        step = 1.0 if fov <= 10 else 4.0
        for k in range(1, int(fov / 2 / step) + 1):  # horizontal mil ticks
            for side in (-1, 1):
                x = c + side * k * step * ppd
                tall = 10 if k % 5 == 0 else 5
                pygame.draw.line(s, ink, (x, c - tall), (x, c + tall), 1)
        for k in range(1, 8):  # rangefinder ladder: 0.1 deg steps at high power, 0.4 at low
            y = c + 18 + k * (0.1 if fov <= 10 else 0.4) * ppd
            if y < EYE - 60:
                pygame.draw.line(s, ink, (c - 6, y), (c + 6, y), 1)
        self.reticles[fov] = s
        return s

    def _label(self, text, color=(20, 24, 26)):
        key = (text, color)
        if key not in self.labels:
            self.labels[key] = self.font.render(text, True, color)
        return self.labels[key]

    # ---------- motion ----------
    @staticmethod
    def _swell_gradient(o, X, Y, t):
        h = o.wave_height / 2
        gx = gy = 0.0
        for a, k, off, phase in o.swells:
            d = math.radians(o.wind_dir + off)
            sd, cd = math.sin(d), math.cos(d)
            c = np.cos(k * (X * sd + Y * cd) - math.sqrt(9.81 * k) * t + phase) * a * h * k
            gx, gy = gx + c * sd, gy + c * cd
        return gx, gy

    def _motion(self, v):
        """Roll and pitch of the boat in the swell (deg), as seen down the line of sight."""
        gx, gy = self._swell_gradient(v.ocean, v.x, v.y, v.time)
        b = math.radians(v.brg)
        along, across = gx * math.sin(b) + gy * math.cos(b), gx * math.cos(b) - gy * math.sin(b)
        return math.degrees(math.atan(across)) * 0.5, math.degrees(math.atan(along)) * 0.35

    # ---------- sky and sea (vectorised, reduced resolution) ----------
    @staticmethod
    def _palette(rain):
        overcast = min(1.0, 0.2 + rain)
        return (overcast, np.array(_mix((66, 110, 168), (104, 109, 117), overcast), np.float32),
                np.array(_mix((182, 196, 208), (132, 137, 143), overcast), np.float32))

    def _sky_panorama(self, rain):
        """360 x 40 deg sky for this weather: gradient, sun glow, clouds. Rebuilt only when the weather moves."""
        overcast, zen, hor = self._palette(rain)
        el = ((np.arange(CLOUD_H) + 0.5) * (40.0 / CLOUD_H)).astype(np.float32)
        az = ((np.arange(CLOUD_W) + 0.5) * (360.0 / CLOUD_W)).astype(np.float32)
        e = (np.clip(el / 25, 0, 1) ** 0.6)[None, :, None]
        sky = hor + (zen - hor) * e
        sun = np.hypot(((az - SUN_BRG + 180) % 360 - 180)[:, None], el[None, :] - SUN_ELEV)
        glow = (np.exp(-(sun / 5) ** 2) * 110 + np.exp(-(sun / 22) ** 2) * 30) * (1 - overcast)
        sky = sky + glow[..., None] * np.array((1.0, 0.95, 0.78), np.float32)
        cover = np.clip((self.clouds - (0.62 - 0.45 * overcast)) * 3.0, 0, 1)[..., None]
        cloud = np.array(_mix((238, 238, 234), (112, 114, 118), rain), np.float32) * (0.85 + 0.15 * e)
        sky = (sky * (1 - cover) + cloud * cover) * (1 - 0.25 * rain)
        return np.clip(sky, 0, 255).astype(np.uint8)

    def _scene(self, v, roll, pitch):
        o, fov = v.ocean, v.fov
        overcast, _, hor = self._palette(o.rain)
        if self.sky_rain is None or abs(o.rain - self.sky_rain) > 0.03:
            self.sky, self.sky_rain = self._sky_panorama(o.rain), o.rain
        n = self.gu.shape[0]
        az = (v.brg + self.gu * fov).astype(np.float32)                                    # (n, 1)
        elev = (-self.gv * fov + pitch - math.tan(math.radians(roll)) * self.gu * fov).astype(np.float32)  # (n, n)
        img = np.empty((n, n, 3), np.uint8)
        ai = ((az % 360) * (CLOUD_W / 360)).astype(np.int32) % CLOUD_W
        sky_rows = int(np.searchsorted(-elev.max(axis=0), 0.0)) + 1  # rows that can show any sky
        ei = np.clip(elev[:, :sky_rows] * (CLOUD_H / 40), 0, CLOUD_H - 1).astype(np.int32)
        img[:, :sky_rows] = self.sky[ai, ei]

        r0 = int(np.searchsorted(-elev.min(axis=0), 0.0))  # first row with any sea
        if r0 < n:
            el = elev[:, r0:]
            d_h = horizon_distance(v.eye)
            dep = np.radians(np.maximum(-el, 0.01))
            d = np.minimum(v.eye / np.tan(dep), d_h)
            azr = np.radians(az)
            X, Y = v.x + d * np.sin(azr), v.y + d * np.cos(azr)
            gx, gy = self._swell_gradient(o, X, Y, v.time)
            # wind chop: two drifting layers of the ripple tile, stronger as the wind gets up
            drift = v.time * 1.2
            wd = math.radians(o.wind_dir)
            ix = ((X + drift * math.sin(wd)) * (RIPPLE_N / RIPPLE_TILE)).astype(np.int32) % RIPPLE_N
            iy = ((Y + drift * math.cos(wd)) * (RIPPLE_N / RIPPLE_TILE)).astype(np.int32) % RIPPLE_N
            jx = ((X * 0.61 - drift * 0.5) * (RIPPLE_N / RIPPLE_TILE)).astype(np.int32) % RIPPLE_N
            jy = ((Y * 0.61 + drift * 0.3) * (RIPPLE_N / RIPPLE_TILE)).astype(np.int32) % RIPPLE_N
            chop = 0.6 + 0.12 * o.wind
            rx, ry = self.ripple
            gx = gx + (rx[ix, iy] + 0.6 * rx[jx, jy]) * chop
            gy = gy + (ry[ix, iy] + 0.6 * ry[jx, jy]) * chop
            fade = 1.0 / (1.0 + d / 250.0)  # far ripples average out into a flat sheen
            nx, ny = gx * fade, gy * fade
            sb, se = math.radians(SUN_BRG), math.radians(SUN_ELEV)
            sx, sy, sz = math.cos(se) * math.sin(sb), math.cos(se) * math.cos(sb), math.sin(se)
            lum = (sz - nx * sx - ny * sy) / np.sqrt(nx * nx + ny * ny + 1)
            haze = np.clip(np.clip(d / o.visibility, 0, 1) ** 0.7 + (d / d_h) ** 6 * 0.4, 0, 1)
            grazing = np.clip(1 - np.degrees(dep) / 6, 0, 1) ** 3  # low angles mirror the sky
            sun = np.exp(-((az - SUN_BRG + 180) % 360 - 180) ** 2 / 144)  # glitter path under the sun
            glint = np.clip(lum - 0.985, 0, 1) * 15000 * (1 - overcast) * sun
            sky_glance = np.clip((lum - 0.85) * 4, 0, 1) * 0.35  # facets tilted toward the sky catch it
            k_base = (0.45 + 0.9 * lum) * (1 - haze) * (1 - 0.25 * o.rain)
            k_hor = ((grazing * 0.6 + sky_glance) * (1 - haze) + haze) * (1 - 0.25 * o.rain)
            base = np.array(_mix((26, 60, 76), (48, 60, 66), overcast), np.float32)
            sea = k_base[..., None] * base + k_hor[..., None] * hor + glint[..., None]
            if o.sea_state >= 3:  # whitecaps on the crests, stable in world space as the scope turns
                eta = o.surface(X, Y, v.time)
                patches = np.clip((rx[ix, iy] - ry[jx, jy]) / RIPPLE_SLOPE, 0, 1)  # coherent foam streaks
                crest = np.clip((eta - 0.2 * o.wave_height) / (0.2 * o.wave_height), 0, 1)
                foam = crest * patches * np.clip(1.5 - d / 900, 0, 1) * (1 - haze) * 0.8
                sea += (np.array((230, 236, 236), np.float32) - sea) * foam[..., None]
            sea = np.clip(sea, 0, 255).astype(np.uint8)
            under = (el < 0)[..., None]
            img[:, r0:] = np.where(under, sea, img[:, r0:]) if r0 < sky_rows else sea
        return img, hor

    # ---------- projection ----------
    def _project(self, v, roll, pitch, brg, elev):
        """Screen point for a true bearing and an elevation angle (deg)."""
        ppd = EYE / v.fov
        u = angle_diff(brg, v.brg)
        x = EYE / 2 + u * ppd
        y = EYE / 2 + (pitch - math.tan(math.radians(roll)) * u - elev) * ppd
        return x, y

    def _ship(self, f, v, roll, pitch, s, hor):
        shape = SHAPES[s.cls]
        L, B = SHIP_CLASSES[s.cls][:2]
        asp = math.radians(s.aspect)
        proj = L * abs(math.sin(asp)) + B * abs(math.cos(asp))
        bow = -1 if math.sin(asp) > 0 else 1  # +1: bow toward screen right
        ppd = EYE / v.fov
        half = math.degrees(proj / s.rng) / 2
        if abs(angle_diff(s.brg, v.brg)) - half > v.fov / 2 + 1:
            return
        b = math.radians(s.brg)
        sx, sy = v.x + s.rng * math.sin(b), v.y + s.rng * math.cos(b)
        bob = float(v.ocean.surface(sx, sy, v.time)) * 0.6
        sinking = s.sinking >= 0
        settle = min(1.0, s.sinking / 150.0) if sinking else 0.0
        tilt = math.sin(math.radians(settle * 18))

        def pt(fr, h):
            h = h - settle * 16.0 + (fr - 0.5) * L * tilt  # going down by the stern, bow rising
            brg = s.brg + bow * (fr - 0.5) * 2 * half
            return self._project(v, roll, pitch, brg, math.degrees(math.atan2(h + bob - v.eye - s.drop, s.rng)))

        haze = min(1.0, (s.rng / v.ocean.visibility) ** 0.8)
        hull = _mix((46, 50, 56), hor, haze)
        upper = _mix((92, 96, 102), hor, haze * 0.95)
        dark = _mix((22, 22, 24), hor, haze)
        # clip at the waterline (near) or our horizon (hull-down)
        cx, wy = pt(0.5, -bob + settle * 16.0)
        if s.drop > 0:
            wy = self._project(v, roll, pitch, s.brg, -math.degrees(math.sqrt(2 * v.eye / R_EFF)))[1]
        f.set_clip(pygame.Rect(0, 0, EYE, max(0, int(wy) + 1)))
        width = max(1, int(ppd * math.degrees(0.8 / s.rng) + 0.5))
        for fr, h, fr2, h2 in shape["booms"]:
            pygame.draw.line(f, dark, pt(fr, h), pt(fr2, h2), 1)
        for fr, top in shape["masts"]:
            pygame.draw.line(f, dark, pt(fr, 0), pt(fr, top), width)
        pygame.draw.polygon(f, hull, [pt(fr, h) for fr, h in shape["hull"]])
        for f0, f1, h0, h1 in shape["blocks"]:
            pygame.draw.polygon(f, upper, [pt(f0, h0), pt(f0, h1), pt(f1, h1), pt(f1, h0)])
        f0, f1, h0, h1 = shape["funnel"]
        pygame.draw.polygon(f, hull, [pt(f0, h0), pt(f0 + 0.01, h1), pt(f1 + 0.01, h1), pt(f1, h0)])
        pygame.draw.polygon(f, dark, [pt(f0 + 0.008, h1 - 1.5), pt(f0 + 0.01, h1), pt(f1 + 0.01, h1),
                                      pt(f1 + 0.008, h1 - 1.5)])
        if s.speed > 1.0 and not sinking:  # bow wave and wake
            kt = s.speed / 0.514444
            foam = _mix((236, 240, 240), hor, haze)
            pygame.draw.polygon(f, foam, [pt(0.99, -0.3), pt(0.94, 0.25 * kt), pt(0.86, -0.3)])
            pygame.draw.polygon(f, foam, [pt(0.0, -0.3), pt(0.06, 0.08 * kt), pt(0.14, -0.3)])
        f.set_clip(None)
        if s.lamp and int(v.time * 3) % 2 == 0:  # bridge signal lamp: they have seen us
            bx, by = pt((shape["blocks"][0][0] + shape["blocks"][0][1]) / 2, shape["blocks"][0][3] + 0.5)
            pygame.draw.circle(f, (255, 250, 210), (int(bx), int(by)), max(2, width + 1))
        # smoke: puffs drift downwind from the funnel
        fx, fy = pt((f0 + f1) / 2 + 0.01, h1)
        size = max(2, int(ppd * math.degrees(5.0 / s.rng)))
        drift = math.sin(math.radians(angle_diff(v.ocean.wind_dir, v.brg)))
        heavy = sinking and s.sinking < 200
        for k in range(8 if not heavy else 12):
            jitter = math.sin(v.time * 0.7 + k * 1.7 + s.uid % 97) * size * 0.3
            px = fx + drift * k * size * 1.3 + jitter
            py = fy - k * size * (0.45 if not heavy else 0.9)
            rad = min(80, int(size * (0.7 + 0.3 * k)))
            shade = 40 if heavy else int(_mix((70, 70, 70), hor, haze * 0.7)[0])
            density = int((110 if heavy else 70) * (1 - k / 13) * (1 - haze * 0.6))
            f.blit(_puff(rad, shade, density), (px - rad, py - rad))
        if heavy and s.sinking < 140:  # fire
            for k in range(3):
                gx, gy = pt(0.45 + 0.08 * k, 6 + 3 * math.sin(v.time * 9 + k))
                pygame.draw.circle(f, (255, 140 + 40 * k, 40), (int(gx), int(gy)), max(2, size // 2))

    def _wake(self, f, v, roll, pitch, w):
        b, h = math.radians(w.brg), math.radians(w.heading)
        px, py = w.rng * math.sin(b), w.rng * math.cos(b)
        pts = []
        for k in range(14):
            qx, qy = px - k * 25 * math.sin(h), py - k * 25 * math.cos(h)
            r = math.hypot(qx, qy)
            if r < 20:
                continue
            brg = math.degrees(math.atan2(qx, qy)) % 360
            pts.append(self._project(v, roll, pitch, brg, math.degrees(math.atan2(-v.eye, r))))
        if len(pts) > 1:
            pygame.draw.lines(f, (225, 235, 232), False, pts, 2)

    def _burst(self, f, v, roll, pitch, bu, hor):
        life, peak = BURSTS.get(bu.kind, (3.0, 20.0))
        if bu.age > life or bu.rng < 30:
            return
        grow = math.sin(math.pi * min(bu.age / life, 1.0)) ** 0.6
        height = peak * grow
        haze = min(1.0, bu.rng / v.ocean.visibility)
        base = self._project(v, roll, pitch, bu.brg, math.degrees(math.atan2(-v.eye, bu.rng)))
        top = self._project(v, roll, pitch, bu.brg, math.degrees(math.atan2(height - v.eye, bu.rng)))
        ppm = EYE / v.fov * math.degrees(1.0 / bu.rng)  # px per metre at that range
        shade = int(_mix((236, 236, 236), (150, 150, 150), haze)[0])
        steps = 9
        for k in range(steps):  # a column of spray: soft puffs, widening and thinning toward the top
            t = k / (steps - 1)
            rad = max(2, int(ppm * peak * (0.12 + 0.12 * t) * (0.6 + 0.4 * grow)))
            x = base[0] + math.sin(k * 2.1 + bu.age) * rad * 0.3
            y = base[1] + (top[1] - base[1]) * t
            f.blit(_puff(min(rad, 90), shade, int(200 * (1 - 0.6 * t) * (1 - haze * 0.5))), (x - rad, y - rad))
        if bu.kind == "BLAST" and bu.age < 0.5:
            pygame.draw.circle(f, (255, 220, 140), (int(base[0]), int(base[1] - 4)), max(4, int(ppm * 15)))

    # ---------- lens ----------
    def _lens_effects(self, f, v, dt):
        rain = v.ocean.rain
        if v.under:
            self.wash = 1.0
            f.fill((16, 54, 52))
            for _ in range(24):
                spot = (_FX.randrange(EYE), _FX.randrange(EYE))
                pygame.draw.circle(f, (110, 170, 160), spot, _FX.randint(2, 7), 1)
            if len(self.drops) < 40:
                self.drops += [[_FX.uniform(60, EYE - 60), _FX.uniform(60, EYE - 60), _FX.uniform(3, 8), 3.0]
                               for _ in range(4)]
        elif self.wash > 0:  # water sheeting off the glass
            self.wash = max(0.0, self.wash - dt * 2.0)
            sheet = pygame.Surface((EYE, EYE), pygame.SRCALPHA)
            sheet.fill((30, 70, 70, int(160 * self.wash)))
            f.blit(sheet, (0, 0))
        if rain > 0.15:
            for _ in range(int(30 * rain)):
                x, y = _FX.randrange(EYE), _FX.randrange(EYE)
                pygame.draw.line(f, (200, 210, 215), (x, y), (x - 2, y + 9), 1)
            if _FX.random() < rain * dt * 6 and len(self.drops) < 40:
                self.drops.append([_FX.uniform(60, EYE - 60), _FX.uniform(40, EYE - 80), _FX.uniform(2, 6),
                                   4.0])
        for d in self.drops:
            d[1] += dt * 18 * d[2] / 4
            d[3] -= dt
            r = int(d[2])
            pygame.draw.circle(f, (30, 36, 40), (int(d[0]), int(d[1])), r, 1)
            pygame.draw.circle(f, (220, 230, 235), (int(d[0] - r / 3), int(d[1] - r / 3)), max(1, r // 3))
        self.drops = [d for d in self.drops if d[3] > 0 and d[1] < EYE]

    def _bearing_tape(self, f, v, roll, pitch):
        ppd = EYE / v.fov
        step = 1 if v.fov <= 10 else 5
        label = 2 if v.fov <= 10 else 10
        y = 74
        start = math.floor((v.brg - v.fov / 2) / step) * step
        for k in range(int(v.fov / step) + 2):
            b = start + k * step
            x = EYE / 2 + angle_diff(b % 360, v.brg) * ppd
            if 60 < x < EYE - 60:
                major = round(b) % label == 0
                pygame.draw.line(f, (16, 18, 20), (x, y), (x, y + (10 if major else 5)), 1)
                if major:
                    img = self._label(f"{round(b - v.scale_ref) % 360:03d}")
                    f.blit(img, (x - img.get_width() / 2, y - 16))
        pygame.draw.polygon(f, (180, 30, 20), [(EYE / 2, y + 12), (EYE / 2 - 5, y + 20), (EYE / 2 + 5, y + 20)])
        edge = EYE / 2 - 80
        for k, (brg, letter, color) in enumerate(v.marks):  # where sonar and the TDC say to look
            off = angle_diff(brg, v.brg) * ppd
            inside = abs(off) <= edge
            x = EYE / 2 + max(-edge, min(edge, off))
            ty = y + 26 + (0 if inside else 22 * k)  # off the tape they stack at the edge instead of overlapping
            if inside:  # a pointer under the tape at the bearing
                pts = [(x, y + 14), (x - 7, y + 26), (x + 7, y + 26)]
            else:  # an arrow at the edge pointing the way to train
                d = 1 if off > 0 else -1
                pts = [(x + 12 * d, ty + 8), (x, ty + 1), (x, ty + 15)]
            pygame.draw.polygon(f, color, pts)
            pygame.draw.polygon(f, (12, 14, 16), pts, 1)
            tag = self._label(letter, (240, 240, 230))
            side = 0 if inside else 16 * (1 if off > 0 else -1)
            box = tag.get_rect(center=(x - side, ty + 8 + (12 if inside else 0)))
            pygame.draw.rect(f, color, box.inflate(6, 2))
            f.blit(tag, box)

    # ---------- frame ----------
    def render(self, v):
        dt = 0.0 if self.last_t is None else max(0.0, min(0.1, v.time - self.last_t))
        self.last_t = v.time
        roll, pitch = self._motion(v)
        img, hor = self._scene(v, roll, pitch)
        pygame.surfarray.blit_array(self.small, img)
        pygame.transform.smoothscale(self.small, (EYE, EYE), self.frame)
        f = self.frame
        for b in sorted(v.bursts, key=lambda b: -b.rng):
            self._burst(f, v, roll, pitch, b, hor)
        for w in v.wakes:
            self._wake(f, v, roll, pitch, w)
        for s in sorted(v.sightings, key=lambda s: -s.rng):
            self._ship(f, v, roll, pitch, s, hor)
        self._lens_effects(f, v, dt)
        if not v.under:
            f.blit(self._reticle(v.fov), (0, 0))
            self._bearing_tape(f, v, roll, pitch)
        f.blit(self.lens, (0, 0))
        if v.shake:
            f.scroll(int(_FX.uniform(-v.shake, v.shake)), int(_FX.uniform(-v.shake, v.shake)))
        return f
