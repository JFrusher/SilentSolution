"""The control room's detailed models, built in code and saved as .glb under assets/ (graphics/gltf.py reads them back).
Oberon-class, 1960s Royal Navy: grey hammertone consoles round worn black faceplates, bakelite tumbler switches,
traffolyte labels, chrome and brass, sound-powered telephones, and the watch's own clutter.
They aren't kept in git: the game builds any that are missing when the room first opens (and build.py before
packaging). Regenerate them all: PYTHONPATH=src uv run src/graphics/models.py

Model space for a station: the floor under its panel's centre is the origin, y up, z out of the panel into the room,
x to the right as you face it. A crewman: the floor under his seat, y up, facing +z, his neck the "head" pivot."""
import io
import math
import sys
from pathlib import Path

import numpy as np
import pygame

import control_room as cr
from graphics import console_art as art
from graphics import gltf

ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "assets"
MODELS = "Silent Solution graphics/models.py v2"  # bump when the models change, so old copies are rebuilt
TILT = math.radians(18.0)  # the console faces lean back this far (control_room._tilted)
I3 = np.identity(3)


def unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def frame(forward, up=(0.0, 1.0, 0.0)):
    """Columns (x, y, z) of a frame whose z is `forward` and y as near `up` as it can be."""
    z = unit(forward)
    x = unit(np.cross(up, z))
    return np.column_stack((x, np.cross(z, x), z))


def png(surf):
    out = io.BytesIO()
    pygame.image.save(surf, out, "texture.png")
    return out.getvalue()


# ---------- the builder ----------
class Builder:
    """Indexed triangles by part and material, with smooth or crisp normals, uv and vertex colour."""
    MATERIALS = dict(paint=dict(rough=0.75, wear=1.0), bakelite=dict(rough=0.35), metal=dict(rough=0.3, metal=1.0),
                     rubber=dict(rough=0.95), cloth=dict(rough=1.0), skin=dict(rough=0.65),
                     glow=dict(rough=1.0, emissive=(1.0, 1.0, 1.0)), lino=dict(rough=0.6))

    def __init__(self):
        self.parts = {}
        self.pivots = {}
        self.part = "body"
        self.materials = {k: dict(v) for k, v in self.MATERIALS.items()}

    def texture(self, name, surf, rough=0.7):
        self.materials[name] = dict(rough=rough, png=png(surf))
        return name

    def put(self, mat, pos, nrm, uv, col, idx):
        assert mat in self.materials, mat
        n = len(pos)
        col = np.broadcast_to(np.asarray(col, float)[..., :3], (n, 3)) if np.ndim(col) == 1 else col
        verts = np.column_stack([pos, nrm, uv, col]).astype("f4")
        bucket = self.parts.setdefault(self.part, {}).setdefault(mat, [[], [], 0])
        bucket[0].append(verts)
        bucket[1].append(np.asarray(idx, "u4") + bucket[2])
        bucket[2] += n

    def grid(self, mat, P, col, uv=None, wrap=False, normals=None, centre=None):
        """A surface from a (rows, cols, 3) grid of points; normals from the grid unless given. wrap: the columns
        close round (a tube). Normals face away from `centre` (default: the grid's middle)."""
        r, c = P.shape[:2]
        if normals is None:
            Q = np.concatenate([P[:, -1:], P, P[:, :1]], 1) if wrap else P
            du = np.gradient(Q, axis=1)[:, 1:-1] if wrap else np.gradient(P, axis=1)
            dv = np.gradient(P, axis=0) if r > 1 else np.zeros_like(P)
            N = np.cross(du, dv)
            ref = P - (np.asarray(centre) if centre is not None else P.reshape(-1, 3).mean(0))
            weak = np.linalg.norm(N, axis=2) < 1e-12
            N[weak] = ref[weak]
            if np.sum(N * ref) < 0:
                N = -N
            normals = N / np.maximum(np.linalg.norm(N, axis=2, keepdims=True), 1e-12)
        if uv is None:
            uu, vv = np.meshgrid(np.linspace(0, 1, c), np.linspace(0, 1, r))
            uv = np.stack([uu, vv], -1)
        cols = c if not wrap else c
        ii, jj = np.meshgrid(np.arange(r - 1), np.arange(cols if wrap else c - 1), indexing="ij")
        a = ii * c + jj
        b = ii * c + (jj + 1) % c
        d, e = a + c, b + c
        idx = np.stack([a, d, e, a, e, b], -1).reshape(-1)
        colours = np.asarray(col, float)
        colours = colours.reshape(-1, 3) if colours.ndim == 3 else colours
        self.put(mat, P.reshape(-1, 3), normals.reshape(-1, 3), uv.reshape(-1, 2), colours, idx)

    def quad(self, a, b, c, d, col, mat="paint", uv=((0, 1), (1, 1), (1, 0), (0, 0))):
        """a, b, c, d round the face, bottom-left first as you look at it (uv (0,0) is the texture's top-left)."""
        pts = np.array([a, b, c, d], float)
        n = unit(np.cross(pts[1] - pts[0], pts[3] - pts[0]))
        self.put(mat, pts, np.tile(n, (4, 1)), np.array(uv, float), col, [0, 1, 2, 0, 2, 3])

    def box(self, centre, size, col, mat="paint", axes=I3, r=0.0, steps=2):
        """A box, its edges rounded to radius r. axes: columns are the box's x, y, z."""
        h = np.asarray(size, float) / 2
        r = min(r, float(h.min()) * 0.999)
        c, axes = np.asarray(centre, float), np.asarray(axes, float)

        def coords(hh):
            if r <= 0:
                return np.array([-hh, hh])
            left = -(hh - r) - r * np.cos(np.linspace(0, math.pi / 2, steps + 1))
            return np.concatenate([left, -left[::-1]])
        for axis in range(3):
            u, v = [k for k in range(3) if k != axis]
            for sign in (-1, 1):
                U, V = np.meshgrid(coords(h[u]), coords(h[v]), indexing="ij")
                P = np.zeros(U.shape + (3,))
                P[..., axis], P[..., u], P[..., v] = sign * h[axis], U, V
                if r > 0:
                    inner = np.clip(P, -(h - r), h - r)
                    d = P - inner
                    N = d / np.linalg.norm(d, axis=2, keepdims=True)
                    P = inner + N * r
                else:
                    N = np.zeros_like(P)
                    N[..., axis] = sign
                self.grid(mat, c + P @ axes.T, col, uv=np.stack([U, V], -1), normals=N @ axes.T)

    def lathe(self, base, axis, profile, col, mat="paint", seg=16, crisp=True):
        """Revolve [(radius, height)] about `axis` from `base`. crisp: each profile step is flat-shaded across."""
        base, ax = np.asarray(base, float), unit(axis)
        u = unit(np.cross(ax, (0.0, 1.0, 0.0) if abs(ax[1]) < 0.9 else (1.0, 0.0, 0.0)))
        v = np.cross(ax, u)
        t = np.linspace(0, 2 * math.pi, seg + 1)
        ring = np.cos(t)[:, None] * u + np.sin(t)[:, None] * v
        prof = np.asarray(profile, float)
        steps = [prof[k:k + 2] for k in range(len(prof) - 1)] if crisp else [prof]
        for p in steps:
            P = base + p[:, 1, None, None] * ax + p[:, 0, None, None] * ring[None]
            d = np.gradient(p, axis=0) if len(p) > 1 else np.zeros_like(p)
            nr, nh = d[:, 1], -d[:, 0]
            ln = np.maximum(np.hypot(nr, nh), 1e-12)
            N = (nr / ln)[:, None, None] * ring[None] + (nh / ln)[:, None, None] * ax
            self.grid(mat, P, col, normals=N)

    def cylinder(self, a, b, r, col, mat="paint", seg=12, caps=True):
        a, b = np.asarray(a, float), np.asarray(b, float)
        L = np.linalg.norm(b - a)
        self.lathe(a, b - a, ([(0, 0)] if caps else []) + [(r, 0), (r, L)] + ([(0, L)] if caps else []), col, mat, seg)

    def tube(self, points, radius, col, mat="paint", seg=8, closed=False, ellipse=None, side=None):
        """Sweep a circle (or an ellipse (rx, ry) per point, rx along `side` as it's carried along) down a polyline."""
        P = np.asarray(points, float)
        n = len(P)
        R = np.broadcast_to(np.asarray(radius, float), (n,)) if np.ndim(radius) == 0 else np.asarray(radius, float)
        T = np.gradient(P, axis=0)
        if closed:
            T = np.roll(P, -1, 0) - np.roll(P, 1, 0)
        T = T / np.linalg.norm(T, axis=1, keepdims=True)
        if side is None:
            side = np.cross(T[0], (0.0, 1.0, 0.0) if abs(T[0][1]) < 0.9 else (1.0, 0.0, 0.0))
        side = unit(side)
        sides = []
        for k in range(n):  # parallel transport, so the tube doesn't twist
            side = side - T[k] * np.dot(side, T[k])
            side = unit(side)
            sides.append(side)
        S = np.array(sides)
        U = np.cross(T, S)
        t = np.linspace(0, 2 * math.pi, seg, endpoint=False)
        rx = R[:, None] if ellipse is None else np.asarray(ellipse, float)[:, 0:1]
        ry = R[:, None] if ellipse is None else np.asarray(ellipse, float)[:, 1:2]
        G = P[:, None] + np.cos(t)[None, :, None] * (S * rx)[:, None] + np.sin(t)[None, :, None] * (U * ry)[:, None]
        if closed:
            G = np.concatenate([G, G[:1]], 0)
            P = np.concatenate([P, P[:1]], 0)
        N = G - P[:, None]
        N /= np.maximum(np.linalg.norm(N, axis=2, keepdims=True), 1e-12)
        self.grid(mat, G, col, wrap=True, normals=N)

    def blob(self, centre, axes, radii, col, mat="skin", nu=28, nv=18, shape=None):
        """A sphere scaled to `radii` and turned to `axes`; shape(d) -> (scale, colour or None) per unit direction d
        sculpts and paints it (a face, a hair line)."""
        c, axes = np.asarray(centre, float), np.asarray(axes, float)
        th, ph = np.meshgrid(np.linspace(0, math.pi, nv), np.linspace(0, 2 * math.pi, nu, endpoint=False),
                             indexing="ij")
        D = np.stack([np.sin(th) * np.sin(ph), np.cos(th), np.sin(th) * np.cos(ph)], -1)
        S = np.ones(th.shape)
        C = np.broadcast_to(np.asarray(col, float), th.shape + (3,)).copy()
        if shape:
            for i in range(nv):
                for j in range(nu):
                    s, colour = shape(D[i, j])
                    S[i, j] = s
                    if colour is not None:
                        C[i, j] = colour
        P = c + (D * S[..., None] * np.asarray(radii, float)) @ axes.T
        self.grid(mat, P, C, wrap=True, centre=c)

    def mesh(self):
        """{part: (pivot, [(material, verts, idx)])} for gltf.write."""
        return {part: (self.pivots.get(part), [(m, np.concatenate(v), np.concatenate(i)) for m, (v, i, _) in
                                               mats.items()]) for part, mats in self.parts.items()}

    def save(self, path):
        gltf.write(path, self.mesh(), self.materials, MODELS)


# ---------- colours (linear, as the shader lights them) ----------
HAMMERTONE = (0.29, 0.31, 0.29)   # console steel, a shade of the 2D panels' battleship grey
PLINTH = (0.08, 0.08, 0.08)
LINO = (0.13, 0.11, 0.09)
BAKELITE = (0.025, 0.024, 0.022)
CHROME = (0.62, 0.62, 0.6)
BRASS = (0.6, 0.42, 0.16)
RED = (0.55, 0.04, 0.02)
CREAM = (0.78, 0.72, 0.58)
LEATHER = (0.18, 0.07, 0.04)
CABLE = (0.07, 0.07, 0.065)
ARMOUR = (0.32, 0.31, 0.28)


# ---------- painted faces ----------
def plate_art(text, size=(512, 96)):
    """A traffolyte name plate: cream engraving on black, rubbed edges, two screws."""
    s = pygame.Surface(size)
    s.fill((22, 22, 21))
    w, h = size
    pygame.draw.rect(s, (70, 68, 62), s.get_rect(), 4, border_radius=6)
    label = art.sans(int(h * 0.55), True).render(text, True, art.LEGEND)
    if label.get_width() > w - 90:
        label = pygame.transform.smoothscale(label, (w - 90, label.get_height()))
    s.blit(label, label.get_rect(center=(w // 2, h // 2)))
    for x in (20, w - 20):
        pygame.draw.circle(s, (150, 146, 136), (x, h // 2), 8)
        pygame.draw.line(s, (60, 58, 54), (x - 6, h // 2), (x + 6, h // 2), 2)
    return s


def rail_art(labels, size=(1024, 128)):
    """The engraved strip under the desk's switches, a legend centred under each."""
    s = art.texture(size, art.FACE, grain=3)
    w, h = size
    for i, text in enumerate(labels):
        x = (i + 0.5) * w / len(labels)
        art.engrave(s, text, (x, h * 0.78), 22, center=True)
    return s


def paper_art(title, lines, size=(384, 512), seed=0):
    """A log sheet on a clipboard: printed rules and a hand's pencil entries."""
    s = pygame.Surface(size)
    s.fill(art.PAPER)
    w, h = size
    art.engrave(s, title, (w // 2, 26), 22, art.INK, center=True)
    for y in range(64, h - 20, 30):
        pygame.draw.line(s, (170, 186, 196), (14, y), (w - 14, y), 1)
    pygame.draw.line(s, (196, 120, 120), (70, 50), (70, h - 10), 1)
    font = art.hand(18)
    for k, line in enumerate(lines):
        s.blit(font.render(line, True, (70, 70, 84)), (20, 40 + 30 * (k + 1)))
    return s


def maker_art(size=(256, 128)):
    """A brass maker's plate."""
    s = pygame.Surface(size)
    s.fill((160, 124, 60))
    w, h = size
    pygame.draw.rect(s, (110, 82, 36), s.get_rect(), 6, border_radius=10)
    for k, (text, sz) in enumerate((("ADMIRALTY PATTERN", 20), ("No. 4471  1963", 26), ("H.M. DOCKYARD", 18))):
        art.engrave(s, text, (w // 2, 30 + k * 34), sz, (60, 40, 14), center=True)
    for x, y in ((14, 14), (w - 14, 14), (14, h - 14), (w - 14, h - 14)):
        pygame.draw.circle(s, (90, 66, 28), (x, y), 5)
    return s


def placard_art(lines, size=(384, 160), ground=(196, 44, 32)):
    s = pygame.Surface(size)
    s.fill(ground)
    w, h = size
    pygame.draw.rect(s, (240, 236, 220), s.get_rect().inflate(-12, -12), 3)
    for k, text in enumerate(lines):
        art.engrave(s, text, (w // 2, h // 2 + (k - (len(lines) - 1) / 2) * 40), 28, (244, 240, 226), center=True)
    return s


def dial_art(title, lo, hi, major, minor, units="", size=256):
    face, _ = art.gauge_face(size // 2, title, lo, hi, major, minor, units=units)
    return pygame.transform.smoothscale(face, (size, size))


def clock_art(size=256):
    face, c = art.gauge_face(size // 2, "", 0, 12, 1, 0.2, start=0.0, sweep=360.0,
                             labels={float(k): str(k or 12) for k in range(12)})
    art.needle(face, c, 300, size * 0.25, art.LEGEND, 5)
    art.needle(face, c, 60, size * 0.36, art.LEGEND, 3)
    return pygame.transform.smoothscale(face, (size, size))


# ---------- station kit ----------
class Station:
    """One station's console, built round its panel: the panel face itself is the live 2D station (the renderer
    draws it), so nothing here may stand in front of the panel's rectangle."""

    def __init__(self, b, s):
        self.b, self.s = b, s
        self.w, self.h = s.w, s.h
        self.cy = s.centre[1]
        self.N = np.array((0.0, math.sin(TILT), math.cos(TILT)))   # the panel's normal
        self.U = np.array((0.0, math.cos(TILT), -math.sin(TILT)))  # up the panel
        self.X = np.array((1.0, 0.0, 0.0))
        self.tilted = np.column_stack((self.X, self.U, self.N))
        self.centre = np.array((0.0, self.cy, 0.0))
        bottom = self.at_panel(0, -self.h / 2)
        self.desk_y = bottom[1] - 0.06
        self.desk_z0, self.desk_z1 = bottom[2] - 0.02, 0.5
        self.top = self.at_panel(0, self.h / 2 + 0.26)

    def at_panel(self, x, y, out=0.0):
        """A point on the panel's plane: x right, y up it from the centre, `out` in front of it."""
        return self.centre + self.X * x + self.U * y + self.N * out

    def housing(self):
        b, w, h = self.b, self.w, self.h
        b.box(self.at_panel(0, 0.06, -0.13), (w + 0.16, h + 0.28, 0.26), HAMMERTONE, axes=self.tilted, r=0.025)
        t = 0.034  # the bezel: a moulded black frame proud of the face, a screw at each corner
        for y in (-1, 1):
            b.box(self.at_panel(0, y * (h / 2 + t / 2 + 0.002), 0.012), (w + 2 * t + 0.004, t, 0.024), BAKELITE,
                  "bakelite", self.tilted, r=0.008)
        for x in (-1, 1):
            b.box(self.at_panel(x * (w / 2 + t / 2 + 0.002), 0, 0.012), (t, h + 0.004, 0.024), BAKELITE, "bakelite",
                  self.tilted, r=0.008)
        for x in (-1, 1):
            for y in (-1, 1):
                p = self.at_panel(x * (w / 2 + t / 2), y * (h / 2 + t / 2), 0.024)
                b.lathe(p, self.N, [(0, 0), (0.008, 0), (0.007, 0.003), (0, 0.004)], CHROME, "metal", seg=8)
        hood = self.at_panel(0, h / 2 + 0.23, -0.02)  # the hood, with a dim instrument light along its lip
        b.box(hood, (w + 0.2, 0.06, 0.32), HAMMERTONE, axes=self.tilted, r=0.02)
        b.box(self.at_panel(0, h / 2 + 0.198, 0.11), (w * 0.8, 0.008, 0.02), (0.9, 0.62, 0.32), "glow", self.tilted)
        plate = self.b.texture(f"plate {self.s.name}", plate_art(self.s.name))
        pw, ph = min(0.62, w * 0.45), 0.09
        a = self.at_panel(-pw / 2, h / 2 + 0.07, 0.003)
        b.quad(a, a + self.X * pw, a + self.X * pw + self.U * ph, a + self.U * ph, (1, 1, 1), plate)

    def cabinet(self, knees):
        """The desk's carcass: a full-width band under the top, pedestals with doors and louvres, and a knee hole
        (with a footrest) wherever a man sits at it."""
        b, w = self.b, self.w
        top, z0, z1, knee_y = self.desk_y - 0.035, -0.3, self.desk_z1 - 0.06, 0.66
        W = w + 0.14
        b.box((0, (top + knee_y) / 2, (z0 + z1) / 2), (W, top - knee_y, z1 - z0), HAMMERTONE, r=0.02)
        edges = sorted([-W / 2, W / 2] + [x + d for x in knees for d in (-0.28, 0.28)])
        for x0, x1 in zip(edges[::2], edges[1::2]):  # pedestals between the knee holes
            x, dw = (x0 + x1) / 2, x1 - x0
            b.box((x, (knee_y + 0.09) / 2, (z0 + z1) / 2), (dw, knee_y - 0.09, z1 - z0), HAMMERTONE, r=0.015)
            b.box((x, 0.045, (z0 + z1) / 2 - 0.03), (max(dw - 0.04, 0.01), 0.09, z1 - z0 - 0.06), PLINTH)
            if dw > 0.25:  # room for a door: its latch, and a louvred vent low down
                b.box((x, (top + 0.14) / 2, z1 + 0.004), (dw - 0.05, top - 0.2, 0.01), HAMMERTONE, r=0.004)
                b.box((x + (dw / 2 - 0.07) * (1 if x < 0 else -1), top - 0.12, z1 + 0.02), (0.018, 0.1, 0.02), CHROME,
                      "metal", r=0.006)
                for j in range(6):
                    b.box((x, 0.18 + j * 0.022, z1 + 0.012), (dw * 0.5, 0.008, 0.012), PLINTH,
                          axes=frame((0, -0.5, 1)))
        for x in knees:  # knee holes: a back panel set in, a chrome footrest
            b.box((x, (knee_y + 0.02) / 2, (z0 + 0.05) / 2), (0.56, knee_y - 0.02, 0.05 - z0), HAMMERTONE)
            b.cylinder((x - 0.25, 0.12, 0.16), (x + 0.25, 0.12, 0.16), 0.014, CHROME, "metal", seg=8)
        for x in (-1, 1):  # rivets down the cabinet's front corners
            for y in np.arange(0.16, top - 0.04, 0.09):
                b.lathe((x * (W / 2 - 0.015), y, z1 + 0.004), (0, 0, 1), [(0, 0), (0.006, 0), (0.004, 0.004),
                                                                          (0, 0.005)], HAMMERTONE, seg=6)
        maker = b.texture("maker", maker_art(), rough=0.4)
        a = np.array((W / 2 - 0.2, top - 0.1, z1 + 0.011))
        b.quad(a, a + (0.12, 0, 0), a + (0.12, 0.06, 0), a + (0, 0.06, 0), (1, 1, 1), maker)

    def desk(self):
        b, w = self.b, self.w
        z0, z1 = self.desk_z0, self.desk_z1
        b.box((0, self.desk_y - 0.018, (z0 + z1) / 2), (w + 0.18, 0.036, z1 - z0), LINO, "lino", r=0.01)
        b.cylinder((-w / 2 - 0.09, self.desk_y - 0.018, z1), (w / 2 + 0.09, self.desk_y - 0.018, z1), 0.02, CHROME,
                   "metal", seg=10)

    def rail(self, controls):
        """A sloped switch rail across the back of the desk: controls [(kind, legend)] spaced along it."""
        b, w = self.b, self.w
        depth, slope = 0.14, frame((0, math.sin(math.radians(35)), math.cos(math.radians(35))))
        c = np.array((0, self.desk_y + 0.045, self.desk_z0 + depth / 2 + 0.01))
        b.box(c - slope[:, 2] * 0.03, (w * 0.92, depth, 0.06), HAMMERTONE, axes=slope, r=0.01)
        face = c + slope[:, 2] * 0.0005
        strip = b.texture(f"rail {self.s.name}", rail_art([lbl for _, lbl in controls]))
        rw, rh = w * 0.9, depth * 0.94
        a = face - slope[:, 0] * rw / 2 - slope[:, 1] * rh / 2
        b.quad(a, a + slope[:, 0] * rw, a + slope[:, 0] * rw + slope[:, 1] * rh, a + slope[:, 1] * rh, (1, 1, 1),
               strip)
        for k, (kind, _) in enumerate(controls):
            p = face + slope[:, 0] * ((k + 0.5) / len(controls) - 0.5) * rw + slope[:, 1] * 0.015
            control(b, kind, p, slope)

    def phone(self, side):
        """A sound-powered telephone on the housing's flank: its box, the handset on its hook, a coiled cord."""
        b = self.b
        x = side * (self.w / 2 + 0.09)
        p = np.array((x + side * 0.04, self.desk_y + 0.32, -0.05))
        fr = frame((side, 0, 0))
        b.box(p, (0.16, 0.24, 0.08), (0.08, 0.08, 0.075), "bakelite", fr, r=0.012)
        handset(b, p + fr[:, 2] * 0.06, fr)
        coil = [p + fr[:, 2] * 0.05 + np.array((0, -0.12 - 0.11 * t, 0.0))
                + (math.cos(t * 40) * fr[:, 0] + math.sin(t * 40) * fr[:, 2]) * 0.012 for t in np.linspace(0, 1, 160)]
        b.tube(coil, 0.0035, BAKELITE, "rubber", seg=5)

    def cables(self, xs):
        """Armoured cable looms out of the housing's back, up into a tray under the deckhead."""
        b = self.b
        top = self.top[1]
        for x in xs:
            for k in range(3):
                dx = x + (k - 1) * 0.022
                path = [(dx, top - 0.05, -0.2), (dx, top + 0.08, -0.26), (dx, top + 0.3, -0.36), (dx, 2.42, -0.44)]
                path = bezier(path, 14)
                b.tube(path, 0.009, ARMOUR if k == 1 else CABLE, "rubber", seg=6)
        tray_y, tray_z = 2.45, -0.46
        L = self.w + 0.5
        b.box((0, tray_y - 0.02, tray_z), (L, 0.006, 0.16), HAMMERTONE)
        for z in (-0.08, 0.08):
            b.box((0, tray_y + 0.005, tray_z + z), (L, 0.05, 0.006), HAMMERTONE)
        for k in range(5):
            b.cylinder((-L / 2, tray_y + 0.002, tray_z - 0.05 + k * 0.025), (L / 2, tray_y + 0.002,
                                                                              tray_z - 0.05 + k * 0.025),
                       0.01, ARMOUR if k % 2 else CABLE, "rubber", seg=6, caps=False)
        jb = np.array((xs[0], top + 0.18, -0.34))  # a junction box where the first loom passes, its glands brass
        b.box(jb, (0.16, 0.14, 0.08), HAMMERTONE, r=0.01)
        for dx in (-0.04, 0.0, 0.04):
            b.cylinder(jb + (dx, -0.07, 0), jb + (dx, -0.09, 0), 0.012, BRASS, "metal", seg=8)


def bezier(pts, n):
    """Points along a Bezier curve through control points `pts`."""
    P = np.asarray(pts, float)
    out = []
    for t in np.linspace(0, 1, n):
        Q = P.copy()
        while len(Q) > 1:
            Q = Q[:-1] * (1 - t) + Q[1:] * t
        out.append(Q[0])
    return np.array(out)


def control(b, kind, p, fr):
    """One control on a sloped rail at p: fr's z is out of the rail, y up it."""
    y, z = fr[:, 1], fr[:, 2]
    if kind == "toggle":  # bakelite tumbler: a boss and a chrome bat, thrown up
        b.lathe(p, z, [(0, 0), (0.014, 0), (0.012, 0.008), (0.006, 0.012), (0, 0.012)], BAKELITE, "bakelite", seg=10)
        b.cylinder(p + z * 0.01, p + z * 0.04 + y * 0.012, 0.0035, CHROME, "metal", seg=6)
    elif kind == "guard":  # a firing key under a hinged red guard, propped open
        b.lathe(p, z, [(0, 0), (0.016, 0), (0.014, 0.01), (0, 0.012)], BAKELITE, "bakelite", seg=10)
        b.cylinder(p + z * 0.01, p + z * 0.036, 0.004, CHROME, "metal", seg=6)
        b.box(p + z * 0.03 - y * 0.03, (0.04, 0.006, 0.05), RED, "bakelite", frame(y + z * 0.4, z), r=0.002)
    elif kind == "knob":  # a fluted rotary knob with a skirt and a white pointer line
        b.lathe(p, z, [(0, 0), (0.02, 0), (0.02, 0.004), (0.013, 0.006), (0.012, 0.022), (0.009, 0.026),
                       (0, 0.026)], BAKELITE, "bakelite", seg=14)
        b.box(p + z * 0.0265 + y * 0.006, (0.002, 0.009, 0.001), CREAM, "glow", fr)
    elif kind == "button":  # a lit push-button: amber cap in a chrome ring
        b.lathe(p, z, [(0, 0), (0.014, 0), (0.014, 0.006), (0, 0.006)], CHROME, "metal", seg=12)
        b.lathe(p + z * 0.006, z, [(0, 0), (0.01, 0), (0.009, 0.008), (0, 0.009)], (0.9, 0.55, 0.15), "glow", seg=10)
    elif kind == "lamp":  # a jewelled indicator lamp
        b.lathe(p, z, [(0, 0), (0.012, 0), (0.012, 0.005), (0, 0.005)], CHROME, "metal", seg=10)
        b.lathe(p + z * 0.005, z, [(0, 0), (0.008, 0), (0.006, 0.008), (0, 0.009)], (0.3, 0.75, 0.25), "glow", seg=8)
    elif kind == "lever":  # a blow lever: a red ball on a chrome bar, in a slotted quadrant
        b.box(p + z * 0.006, (0.03, 0.07, 0.012), BAKELITE, "bakelite", fr, r=0.004)
        top = p + z * 0.09 + y * 0.02
        b.cylinder(p + z * 0.01, top, 0.005, CHROME, "metal", seg=6)
        b.blob(top, fr, (0.016, 0.016, 0.016), RED, "bakelite", nu=10, nv=8)
    else:
        raise ValueError(kind)


def handset(b, p, fr):
    """A telephone handset lying along fr's y: grip, earpiece and mouthpiece cups."""
    y, z = fr[:, 1], fr[:, 2]
    ear, mouth = p + y * 0.085, p - y * 0.085
    b.tube(bezier([ear, p + z * 0.02, mouth], 10), 0.013, BAKELITE, "bakelite", seg=8)
    for end in (ear, mouth):
        b.lathe(end - z * 0.005, z, [(0, 0), (0.026, 0.0), (0.028, 0.02), (0.02, 0.026), (0, 0.026)], BAKELITE,
                "bakelite", seg=12, crisp=False)


def mug(b, p, colour=(0.75, 0.72, 0.66)):
    b.lathe(p, (0, 1, 0), [(0, 0), (0.035, 0), (0.04, 0.09), (0.036, 0.09), (0.031, 0.006), (0, 0.006)], colour,
            "bakelite", seg=16, crisp=False)
    b.cylinder(p + (0, 0.075, 0), p + (0, 0.076, 0), 0.034, (0.18, 0.1, 0.05), "lino", seg=14)  # tea
    arc = [p + (0.04 + 0.022 * math.sin(t), 0.045 + 0.028 * math.cos(t), 0) for t in np.linspace(0, math.pi, 9)]
    b.tube(arc, 0.006, colour, "bakelite", seg=6)


def clipboard(b, p, yaw, title, lines, name):
    fr = frame((math.sin(yaw), 0, math.cos(yaw)))
    b.box(p + (0, 0.004, 0), (0.24, 0.008, 0.32), (0.35, 0.22, 0.1), "lino", fr, r=0.003)
    sheet = b.texture(name, paper_art(title, lines), rough=0.9)
    x, z = fr[:, 0], fr[:, 2]
    a = p + (0, 0.0085, 0) - x * 0.105 + z * 0.15
    b.quad(a, a + x * 0.21, a + x * 0.21 - z * 0.28, a - z * 0.28, (1, 1, 1), sheet)
    b.box(p + (0, 0.012, 0) - z * 0.15, (0.1, 0.01, 0.03), CHROME, "metal", fr, r=0.003)


def pencil(b, p, q, colour=(0.85, 0.66, 0.1)):
    p, q = np.asarray(p, float), np.asarray(q, float)
    b.cylinder(p, q, 0.0045, colour, seg=6)
    b.lathe(q, q - p, [(0.0045, 0), (0, 0.016)], (0.85, 0.72, 0.55), seg=6)


def headphones(b, p, yaw):
    fr = frame((math.sin(yaw), 0, math.cos(yaw)))
    x = fr[:, 0]
    for side in (-1, 1):
        c = p + x * side * 0.08
        b.lathe(c, (0, 1, 0), [(0, 0), (0.04, 0), (0.042, 0.03), (0.03, 0.04), (0, 0.04)], BAKELITE, "bakelite",
                seg=14, crisp=False)
    band = [p + x * 0.08 * math.cos(t) + np.array((0, 0.04 + 0.025 * math.sin(t), 0)) for t in
            np.linspace(0, math.pi, 12)]
    b.tube(band, 0.006, (0.3, 0.3, 0.3), "metal", seg=6)


def logbook(b, p, yaw, colour=(0.12, 0.2, 0.12)):
    fr = frame((math.sin(yaw), 0, math.cos(yaw)))
    b.box(p + (0, 0.012, 0), (0.2, 0.024, 0.27), colour, "lino", fr, r=0.004)
    b.box(p + (0.004, 0.012, 0) + fr[:, 0] * 0.004, (0.196, 0.018, 0.262), CREAM, "cloth", fr)


def ashtray(b, p):
    b.lathe(p, (0, 1, 0), [(0, 0), (0.05, 0), (0.055, 0.02), (0.045, 0.02), (0.04, 0.008), (0, 0.008)],
            (0.5, 0.5, 0.48), "metal", seg=16)


def handwheel(b, centre, axis, r, colour=RED):
    """A training or valve hand wheel: a rim, four spokes and a hub."""
    fr = frame(axis)
    rim = [centre + r * (math.cos(t) * fr[:, 0] + math.sin(t) * fr[:, 1]) for t in np.linspace(0, 2 * math.pi, 28,
                                                                                             endpoint=False)]
    b.tube(rim, r * 0.1, colour, "bakelite", seg=8, closed=True)
    for t in (0.4, 0.4 + math.pi / 2, 0.4 + math.pi, 0.4 + 3 * math.pi / 2):
        b.cylinder(centre, centre + r * (math.cos(t) * fr[:, 0] + math.sin(t) * fr[:, 1]), r * 0.06, colour,
                   "bakelite", seg=6, caps=False)
    b.lathe(centre - fr[:, 2] * 0.02, fr[:, 2], [(0, 0), (r * 0.22, 0), (r * 0.2, 0.05), (0, 0.05)], CHROME,
            "metal", seg=10)


def dial(b, centre, normal, r, name, surf):
    """A round instrument: a black case, chrome bezel, and its painted face, round, behind the glass."""
    fr = frame(normal)
    x, y, z = fr[:, 0], fr[:, 1], fr[:, 2]
    b.lathe(centre - z * 0.09, z, [(0, 0), (r * 0.9, 0), (r + 0.006, 0.02), (r + 0.006, 0.06)], BAKELITE, "bakelite",
            seg=20)
    b.lathe(centre - z * 0.03, z, [(r + 0.006, 0), (r + 0.014, 0.004), (r + 0.014, 0.03), (r, 0.034), (r, 0.03)],
            CHROME, "metal", seg=24)
    face = b.texture(name, surf, rough=0.3)
    t = np.linspace(0, 2 * math.pi, 33)
    rad = np.array([0.0, 1.0])[:, None]
    c = centre + z * 0.029
    P = c + (rad * np.cos(t))[..., None] * x * r + (rad * np.sin(t))[..., None] * y * r
    uv = np.stack([0.5 + 0.5 * rad * np.cos(t), 0.5 - 0.5 * rad * np.sin(t)], -1)
    b.grid(face, P, (1, 1, 1), uv=uv, normals=np.broadcast_to(z, P.shape))


def stool(b, p):
    """A watchkeeper's swivel stool: a steel column on a foot ring, a padded round seat."""
    b.lathe(p, (0, 1, 0), [(0, 0), (0.2, 0), (0.19, 0.02), (0, 0.03)], PLINTH, "metal", seg=16)
    b.cylinder(p, p + (0, 0.44, 0), 0.03, CHROME, "metal", seg=10)
    rim = [p + (0.16 * math.cos(t), 0.2, 0.16 * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 20, endpoint=False)]
    b.tube(rim, 0.008, CHROME, "metal", seg=6, closed=True)
    b.lathe(p + (0, 0.44, 0), (0, 1, 0), [(0, 0), (0.18, 0), (0.19, 0.03), (0.17, 0.065), (0, 0.07)], LEATHER,
            "cloth", seg=20, crisp=False)


def seat(b, p, facing):
    """A helmsman's seat: pedestal, padded leather seat and back, a footrest."""
    fr = frame(facing)
    x, z = fr[:, 0], fr[:, 2]
    b.cylinder(p, p + (0, 0.42, 0), 0.04, CHROME, "metal", seg=12)
    b.lathe(p, (0, 1, 0), [(0, 0), (0.22, 0), (0.2, 0.025), (0, 0.025)], PLINTH, "metal", seg=16)
    b.box(p + (0, 0.47, 0), (0.46, 0.09, 0.44), LEATHER, "cloth", fr, r=0.035)
    b.box(p + (0, 0.82, 0) - z * 0.22, (0.44, 0.52, 0.08), LEATHER, "cloth", fr, r=0.03)
    for side in (-1, 1):
        b.cylinder(p + (0, 0.45, 0) + x * side * 0.18 - z * 0.12, p + (0, 0.62, 0) + x * side * 0.18 - z * 0.24,
                   0.012, CHROME, "metal", seg=6)
    b.box(p + (0, 0.16, 0) + z * 0.3, (0.36, 0.02, 0.1), CHROME, "metal", fr, r=0.006)


def yoke(b, p, facing, part):
    """An aircraft-style control column: column from the deck, and (as `part`, turning on its hub) a wheel with two
    grips."""
    fr = frame(facing)
    x, z = fr[:, 0], fr[:, 2]
    b.box(p + (0, 0.05, 0), (0.16, 0.1, 0.16), BAKELITE, "bakelite", fr, r=0.02)
    hub = p + (0, 0.93, 0) + z * 0.08
    b.cylinder(p + (0, 0.1, 0), p + (0, 0.88, 0), 0.035, HAMMERTONE, seg=12)
    b.cylinder(p + (0, 0.88, 0), hub, 0.03, CHROME, "metal", seg=10)
    b.part = part
    b.pivots[part] = hub
    arc = [hub + z * 0.02 + x * 0.17 * math.cos(t) + np.array((0, 0.09 * math.sin(t), 0))
           for t in np.linspace(-0.3, math.pi + 0.3, 16)]
    b.tube(arc, 0.014, BAKELITE, "bakelite", seg=8)
    for side in (-1, 1):
        g = hub + z * 0.02 + x * side * 0.17
        b.cylinder(g - (0, 0.06, 0), g + (0, 0.03, 0), 0.02, BAKELITE, "rubber", seg=10)
    b.part = "body"


RAIL = {  # each station's switch rail, left to right
    "SONAR": [("knob", "GAIN"), ("knob", "FILTER"), ("toggle", "BEAM"), ("toggle", "TRAIN"), ("button", "MARK"),
              ("lamp", "ON TGT"), ("knob", "VOLUME")],
    "FIRE CONTROL": [("guard", "FIRE 1"), ("guard", "FIRE 2"), ("toggle", "TUBE 1"), ("toggle", "TUBE 2"),
                     ("knob", "SPREAD"), ("button", "SOLVE"), ("lamp", "READY")],
    "RADIO": [("knob", "TUNE"), ("knob", "BAND"), ("toggle", "AERIAL"), ("lamp", "CARRIER"), ("knob", "GAIN")],
    "HELM AND PLANES": [("toggle", "STEER"), ("lamp", "GYRO"), ("knob", "TELEGRAPH"), ("button", "HOLD"),
                        ("toggle", "FWD PLN"), ("toggle", "AFT PLN"), ("lamp", "PLANES"), ("knob", "DEPTH")],
    "BALLAST CONTROL": [("lever", "BLOW 1"), ("lever", "BLOW 2"), ("lever", "BLOW 3"), ("toggle", "VENTS"),
                        ("toggle", "SNORT"), ("button", "PUMP"), ("lamp", "AIR")],
    "DAMAGE CONTROL": [("toggle", "FLOOD"), ("toggle", "PUMPS"), ("lamp", "WATERTIGHT"), ("button", "ALARM"),
                       ("knob", "SECTION"), ("toggle", "VENT")],
    "NAVIGATION": [("toggle", "LOG"), ("knob", "SOUNDER"), ("lamp", "GYRO"), ("toggle", "LIGHTS"), ("knob", "DIM")],
}
PHONE_SIDE = {"BALLAST CONTROL": -1, "HELM AND PLANES": 0}
KNEES = {"HELM AND PLANES": (-0.6, 0.6)}  # where men sit at a desk (default: its middle)
SEAT_OUT = 0.74  # how far out from a station's panel its watchkeeper's stool stands
HELM_SEATS = ((-0.6, 0.75), (0.6, 0.75))  # the helmsman's and planesman's seats, x and out, in the helm's model space


def station(s):
    """The whole console for control_room station s."""
    b = Builder()
    st = Station(b, s)
    st.housing()
    knees = KNEES.get(s.name, (0.0,)) if s.working else ()
    st.cabinet(knees)
    if s.working and s.name != "HELM AND PLANES":  # the watchkeeper's stool
        stool(b, np.array((0.0, 0.0, SEAT_OUT)))
    st.desk()
    st.rail(RAIL[s.name])
    if PHONE_SIDE.get(s.name, 1):
        st.phone(PHONE_SIDE.get(s.name, 1))
    st.cables((-s.w / 2 + 0.18, s.w / 2 - 0.18))
    w, y, z = s.w, st.desk_y, (st.desk_z0 + st.desk_z1) / 2 + 0.07
    if s.name == "SONAR":
        logbook(b, np.array((w / 2 - 0.22, y, z)), -0.15)
        pencil(b, (w / 2 - 0.38, y + 0.005, z + 0.06), (w / 2 - 0.3, y + 0.005, z - 0.08))
        mug(b, np.array((w / 2 + 0.02, y, z + 0.04)))
        handwheel(b, np.array((w / 2 + 0.03, y + 0.2, 0.3)), (1, 0.0, 0.25), 0.11, (0.1, 0.1, 0.1))
    elif s.name == "FIRE CONTROL":
        clipboard(b, np.array((-w / 2 + 0.25, y, z)), 0.2, "ATTACK LOG",
                  ["0412  CONTACT 045", "0414  MARK 047", "0416  SPD 10 CRS 090", "0419  SOLUTION SET"], "attack log")
        pencil(b, (-w / 2 + 0.42, y + 0.005, z + 0.1), (-w / 2 + 0.5, y + 0.005, z - 0.04), (0.6, 0.1, 0.06))
        ashtray(b, np.array((w / 2 - 0.12, y, z + 0.02)))
        placard = b.texture("placard fire", placard_art(["TUBES MUST BE", "REPORTED READY"]))
        a = np.array((-w / 2 - 0.075, y + 0.15, 0.1))
        b.quad(a, a + (0, 0, -0.16), a + (0, 0.065, -0.16), a + (0, 0.065, 0), (1, 1, 1), placard)
    elif s.name == "RADIO":
        clipboard(b, np.array((w / 2 - 0.22, y, z)), -0.1, "SIGNAL PAD",
                  ["FOSM 041200Z", "CONVOY 6M 2E", "RV 040 9NM", "ACK"], "signal pad")
        k = np.array((0.05, y, z + 0.05))  # morse key
        b.box(k + (0, 0.008, 0), (0.06, 0.016, 0.12), BAKELITE, "bakelite", r=0.004)
        b.cylinder(k + (0, 0.025, -0.04), k + (0, 0.03, 0.05), 0.005, BRASS, "metal", seg=6)
        b.lathe(k + (0, 0.03, 0.05), (0, 1, 0), [(0, 0), (0.014, 0), (0.014, 0.012), (0, 0.016)], BAKELITE,
                "bakelite", seg=10)
        b.box(st.at_panel(w / 2 + 0.12, 0.25, -0.12), (0.12, 0.04, 0.03), HAMMERTONE, axes=st.tilted, r=0.008)
        dial(b, st.at_panel(w / 2 + 0.2, 0.25, -0.06), st.N, 0.075, "clock", clock_art())
    elif s.name == "HELM AND PLANES":
        for k, (x, out) in enumerate(HELM_SEATS):  # the helmsman's and planesman's seats and their columns
            seat(b, np.array((x, 0.0, out)), (0, 0, -1))
            yoke(b, np.array((x, 0.0, out - 0.33)), (0, 0, 1), f"wheel_{k}")
        for side, title in ((-1, "FWD PLANES"), (1, "AFT PLANES")):
            c = st.at_panel(side * (w / 2 + 0.2), 0.2, -0.04)
            b.box(st.at_panel(side * (w / 2 + 0.1), 0.2, -0.09), (0.16, 0.05, 0.03), HAMMERTONE, axes=st.tilted,
                  r=0.008)
            dial(b, c, st.N, 0.09, title.lower(), dial_art(title, -30, 30, 10, 5, "DEG"))
    elif s.name == "BALLAST CONTROL":
        for k, x in enumerate((-0.5, -0.2, 0.1)):  # the H.P. air group's gauges along the cabinet top
            dial(b, np.array((x, y - 0.15, st.desk_z1 - 0.06 + 0.005)), (0, 0, 1), 0.05, f"hp air {k}",
                 dial_art(f"H.P. AIR {k + 1}", 0, 4000, 1000, 250, "PSI"))
        placard = b.texture("placard blow", placard_art(["EMERGENCY BLOW", "CAPTAIN'S ORDER ONLY"]))
        a = np.array((0.28, y - 0.2, st.desk_z1 - 0.06 + 0.012))
        b.quad(a, a + (0.24, 0, 0), a + (0.24, 0.1, 0), a + (0, 0.1, 0), (1, 1, 1), placard)
        mug(b, np.array((-w / 2 + 0.18, y, z + 0.05)), (0.2, 0.25, 0.4))
    elif s.name == "DAMAGE CONTROL":
        clipboard(b, np.array((-w / 2 + 0.26, y, z)), 0.15, "STATE BOARD",
                  ["FWD ESC HATCH  SHUT", "BATTERY VENT  OPEN", "AFT PLANES  OK", "PUMP 2  RUNNING"], "state board")
        p = np.array((w / 2 + 0.2, 0.0, 0.25))  # a fire extinguisher on its bracket by the console
        b.lathe(p + (0, 0.06, 0), (0, 1, 0), [(0, 0), (0.07, 0), (0.075, 0.04), (0.075, 0.46), (0.05, 0.53),
                                              (0.02, 0.56), (0, 0.56)], (0.6, 0.06, 0.03), "bakelite", seg=16,
                crisp=False)
        b.box(p + (0, 0.66, 0), (0.06, 0.06, 0.04), BAKELITE, "bakelite", r=0.01)
        box = np.array((-w / 2 - 0.2, 1.35, -0.05))  # a first-aid box on the hull side
        b.box(box, (0.26, 0.2, 0.12), (0.12, 0.3, 0.12), r=0.01)
        b.box(box + (0, 0, 0.061), (0.1, 0.03, 0.002), (0.9, 0.9, 0.86), "cloth")
        b.box(box + (0, 0, 0.061), (0.03, 0.1, 0.002), (0.9, 0.9, 0.86), "cloth")
    elif s.name == "NAVIGATION":
        logbook(b, np.array((-w / 2 + 0.2, y, z)), 0.1, (0.3, 0.06, 0.05))
        b.box(st.at_panel(w / 2 + 0.12, 0.15, -0.11), (0.12, 0.04, 0.03), HAMMERTONE, axes=st.tilted, r=0.008)
        dial(b, st.at_panel(w / 2 + 0.2, 0.15, -0.05), st.N, 0.075, "gyro rep",
             dial_art("GYRO", 0, 360, 90, 10, "DEG"))
    return b


# ---------- the crew ----------
SKINS = ((0.62, 0.43, 0.33), (0.55, 0.37, 0.27), (0.29, 0.18, 0.11), (0.66, 0.5, 0.41), (0.5, 0.33, 0.22))
HAIRS = ((0.05, 0.035, 0.02), (0.16, 0.09, 0.04), (0.36, 0.14, 0.05), (0.42, 0.34, 0.2), (0.3, 0.3, 0.29))
OUTFITS = {  # 1960s RN at sea: the submariner's white sweater, the navy jumper, working dress, a boiler suit
    "white sweater": dict(top=(0.7, 0.68, 0.6), sleeve=(0.7, 0.68, 0.6), legs=(0.03, 0.035, 0.06), collar="roll"),
    "navy jumper": dict(top=(0.04, 0.05, 0.1), sleeve=(0.04, 0.05, 0.1), legs=(0.03, 0.035, 0.06), collar="shirt"),
    "working dress": dict(top=(0.32, 0.42, 0.58), sleeve=None, legs=(0.03, 0.035, 0.07), collar="open"),
    "overalls": dict(top=(0.06, 0.08, 0.16), sleeve=(0.06, 0.08, 0.16), legs=(0.06, 0.08, 0.16), collar="open"),
}
CREW = {  # who keeps each watch: outfit, skin, hair, face hair, headphones
    "SONAR": ("white sweater", 0, 1, None, True),
    "FIRE CONTROL": ("navy jumper", 1, 0, "beard", False),
    "RADIO": ("working dress", 3, 2, None, True),
    "BALLAST CONTROL": ("overalls", 4, 4, "moustache", False),
    "DAMAGE CONTROL": ("white sweater", 2, 0, "beard", False),
    "HELM": ("navy jumper", 0, 3, None, False),
    "PLANES": ("working dress", 1, 1, "beard", False),
}
UPPER_ARM, FOREARM, THIGH, SHIN = 0.3, 0.27, 0.44, 0.46


def ik(root, target, l1, l2, pole):
    """Where the middle joint of a two-bone limb goes so its end reaches `target`, bending toward `pole`."""
    d = np.asarray(target, float) - root
    L = min(max(np.linalg.norm(d), 1e-3), (l1 + l2) * 0.999)
    n = d / np.linalg.norm(d)
    x = (l1 * l1 - l2 * l2 + L * L) / (2 * L)
    p = unit(np.asarray(pole, float) - n * np.dot(pole, n))
    return root + n * x + p * math.sqrt(max(l1 * l1 - x * x, 0.0)), root + n * L


def growth(d, beard):
    """How far past the hairline (or beard line) direction d on the head is: > 0 where it grows."""
    x, y, z = d
    if beard is None:
        grow = max(y - (0.3 + 0.3 * max(z, 0.0) - 0.25 * max(-z, 0.0)), min(-0.12 - z, y + 0.42))
        return min(grow, 0.9 - abs(x) + 0.6 * max(abs(y) - 0.3, 0.0))  # clear of the ears
    if beard == "beard":
        return min(-0.1 - y, z + 0.3, max(abs(x) - 0.26, -0.3 - y, y + 0.5) * 0.6)  # jaw and chin, the mouth clear
    return min(z - 0.83, 0.3 - abs(x), y + 0.37, -0.25 - y)  # a moustache


def ease(v, width):
    k = min(max(v / width + 0.5, 0.0), 1.0)
    return k * k * (3 - 2 * k)


def face(skin, hair, beard):
    """shape(d) for the head: jaw, brow, nose, cheeks and ears pushed out, the lips and brows painted on.
    d is a unit direction in the head's frame: +z the face, +y up, +x his left."""
    skin, hair = np.array(skin), np.array(hair)
    lips = skin * np.array((1.15, 0.72, 0.7))

    def g(v, w):
        return math.exp(-(v / w) ** 2)

    def shape(d):
        x, y, z = d
        ax, front = abs(x), max(z, 0.0)
        s = 1.0
        s -= 0.16 * max(-y - 0.15, 0.0) * (0.6 + 0.4 * ax)        # jaw narrows to the chin
        s += 0.06 * max(-z, 0.0) * max(y + 0.2, 0.0)               # the back of the skull
        s += 0.2 * g(x, 0.11) * g(y + 0.1, 0.16) * front ** 6      # nose
        s += 0.05 * g(y - 0.22, 0.07) * front ** 3 * (ax < 0.6)    # brow ridge
        s -= 0.045 * g(ax - 0.32, 0.11) * g(y - 0.1, 0.08) * front ** 2  # eye sockets
        s += 0.035 * g(ax - 0.55, 0.15) * g(y + 0.05, 0.12)        # cheekbones
        s += 0.04 * g(x, 0.3) * g(y + 0.62, 0.12) * front           # chin
        s += 0.16 * g(ax - 0.97, 0.05) * g(y - 0.02, 0.2) * g(z + 0.05, 0.15)  # ears
        colour = skin
        if front > 0.85 and ax < 0.22 and -0.47 < y < -0.36:
            colour = lips
        elif front > 0.5 and 0.18 < ax < 0.48 and 0.2 < y < 0.27:
            colour = hair * 0.8 + skin * 0.2  # eyebrows
        k = max(ease(growth(d, None), 0.1), ease(growth(d, beard), 0.1) if beard else 0.0)
        return s, colour + (hair - colour) * k  # the hair line painted on, soft; the shell gives it body
    return shape


def hair_shape(beard):
    """shape(d) for the hair shell (or the beard): out past the skin well inside where it grows, tucked into the head
    elsewhere, so its edge hides under hair already painted on the skin."""
    top = 1.065 if beard is None else 1.045

    def shape(d):
        return 0.94 + (top - 0.94) * ease(growth(d, beard) - 0.1, 0.12), None
    return shape


def hand(b, wrist, forward, side, skin, grip=False):
    """A hand at the wrist, palm down along `forward`: a palm, four fingers curled over, a thumb."""
    f = unit(forward)
    up = np.array((0.0, 1.0, 0.0))
    x = unit(np.cross(up, f))
    up = np.cross(f, x)
    palm = wrist + f * 0.045
    b.blob(palm, np.column_stack((x, up, f)), (0.042, 0.016, 0.05), skin, "skin", nu=12, nv=8)
    curl = 0.03 if grip else 0.016
    for k in range(4):
        base = wrist + f * 0.085 + x * (k - 1.5) * 0.018
        L = (0.042, 0.048, 0.045, 0.036)[k]
        pts = [base, base + f * L * 0.45 - up * curl * 0.3, base + f * L * 0.8 - up * curl,
               base + f * L - up * curl * 2]
        b.tube(pts, 0.0075, skin, "skin", seg=6)
    t0 = wrist + f * 0.03 - x * side * 0.035
    b.tube([t0, t0 + f * 0.03 - x * side * 0.012, t0 + f * 0.05 - x * side * 0.004 - up * 0.01], 0.009, skin, "skin",
           seg=6)


def crewman(key, pose, poses=None):
    """A rating, seated or standing; his head a part turning on his neck, his arms a part per pose in `poses` (each a
    pair of hand points, model space; none: hanging at his sides). Model space: the floor under his seat, facing +z."""
    outfit, skin_i, hair_i, beard, phones = CREW[key]
    o, skin, hair = OUTFITS[outfit], SKINS[skin_i], HAIRS[hair_i]
    b = Builder()
    b.materials["cloth"] = dict(rough=1.0, wear=0.6)
    seated = pose == "seated"
    hip_y = 0.56 if seated else 0.94
    lean = 0.07 if seated else 0.0
    spine = [np.array((0.0, hip_y - 0.02, -0.04)), np.array((0.0, hip_y + 0.18, -0.02 + lean * 0.3)),
             np.array((0.0, hip_y + 0.38, 0.0 + lean * 0.7)), np.array((0.0, hip_y + 0.52, 0.02 + lean)),
             np.array((0.0, hip_y + 0.6, 0.03 + lean))]
    spine = bezier(spine, 9)
    widths = np.interp(np.linspace(0, 1, 9), (0, 0.25, 0.55, 0.85, 1), (0.165, 0.15, 0.185, 0.2, 0.07))
    depths = np.interp(np.linspace(0, 1, 9), (0, 0.25, 0.55, 0.85, 1), (0.11, 0.1, 0.12, 0.1, 0.06))
    b.tube(spine, 0, o["top"], "cloth", seg=18, ellipse=np.column_stack((widths, depths)), side=(1.0, 0.0, 0.0))
    b.blob(spine[0], I3, (0.165, 0.07, 0.11), o["legs"], "cloth", nu=16, nv=8)  # seat of his trousers
    neck0, head_pivot = spine[-1], spine[-1] + np.array((0.0, 0.035, 0.01))
    b.cylinder(neck0 - (0, 0.03, 0), head_pivot + (0, 0.05, 0.005), 0.05, skin, "skin", seg=12)
    if o["collar"] == "roll":  # the submariner's sweater: a thick roll neck
        b.tube([neck0 + (0, k * 0.02, 0.004 * k) for k in range(4)], 0.072, o["top"], "cloth", seg=14)
    elif o["collar"] == "shirt":
        b.tube([neck0 + (0, 0.005 + k * 0.012, 0.003 * k) for k in range(3)], 0.062, (0.55, 0.62, 0.72), "cloth",
               seg=12)
    else:  # an open neck: a vee of shirt, skin showing
        b.blob(neck0 + (0, -0.04, 0.085 + lean * 0.2), I3, (0.05, 0.06, 0.02), skin, "skin", nu=10, nv=6)
    for side in (-1, 1):  # legs
        hip = spine[0] + np.array((side * 0.095, 0.0, 0.0))
        if seated:
            knee = np.array((side * 0.11, hip_y - 0.02, THIGH - 0.04))
            ankle = np.array((side * 0.12, 0.09, THIGH + 0.02))
        else:
            knee, ankle = hip + (0.005 * side, -0.44, 0.02), np.array((side * 0.1, 0.09, -0.01))
        b.tube(bezier([hip, (hip + knee) / 2, knee], 5), np.linspace(0.085, 0.062, 5), o["legs"], "cloth", seg=12)
        b.tube(bezier([knee, (knee + ankle) / 2, ankle], 5), np.linspace(0.062, 0.045, 5), o["legs"], "cloth", seg=12)
        b.blob(knee, I3, (0.062, 0.062, 0.062), o["legs"], "cloth", nu=10, nv=8)
        b.box(ankle + (0, -0.055, 0.05), (0.1, 0.07, 0.27), (0.02, 0.02, 0.02), "bakelite", r=0.03)  # boots
    for k, hands in enumerate(poses or [None]):  # the arms, a part per pose: the renderer shows one at a time
        b.part = f"arms_{k}"
        for side in (-1, 1):
            shoulder = spine[-2] + np.array((side * 0.18, -0.035, 0.0))
            if hands is not None:
                target = np.asarray(hands[(side + 1) // 2], float)
                elbow, wrist = ik(shoulder, target - np.array((0, 0.012, 0.0)), UPPER_ARM, FOREARM,
                                  (side * 0.8, -1.0, -0.3))
                forward = target - elbow
                forward[1] = 0.0
            else:
                elbow, wrist = shoulder + (side * 0.04, -0.29, 0.02), shoulder + (side * 0.06, -0.55, 0.06)
                forward = np.array((side * 0.15, -1.0, 0.2))
            sleeve = o["sleeve"] or o["top"]
            b.tube(bezier([shoulder - (side * 0.03, -0.01, 0), shoulder, (shoulder + elbow) / 2, elbow], 6),
                   np.interp(np.linspace(0, 1, 6), (0, 0.2, 1), (0.05, 0.058, 0.046)), sleeve, "cloth", seg=12)
            fore = bezier([elbow, (elbow + wrist) / 2, wrist], 5)
            if o["sleeve"]:
                b.tube(fore, np.linspace(0.046, 0.036, 5), sleeve, "cloth", seg=12)
            else:  # sleeves rolled to the elbow
                b.tube(fore[:2], 0.052, o["top"], "cloth", seg=12)
                b.tube(fore[1:], np.linspace(0.04, 0.032, 4), skin, "skin", seg=10)
            if hands is not None:
                hand(b, wrist, forward, side, skin, grip=key in ("HELM", "PLANES"))
            else:
                b.blob(wrist + (0, -0.05, 0.01), I3, (0.03, 0.055, 0.04), skin, "skin", nu=10, nv=8)
    b.part = "body"
    if o["collar"] != "roll" and outfit == "overalls":
        b.tube([spine[1] + (np.cos(t) * 0.152, 0, np.sin(t) * 0.103) for t in np.linspace(0, 2 * math.pi, 24,
                                                                                         endpoint=False)],
               0.012, (0.03, 0.03, 0.03), "rubber", seg=6, closed=True)  # belt

    b.part = "head"
    b.pivots["head"] = head_pivot
    hc = head_pivot + np.array((0.0, 0.09, 0.02))
    b.blob(hc, I3, (0.082, 0.112, 0.098), skin, "skin", nu=48, nv=34, shape=face(skin, hair, beard))
    b.blob(hc + (0, 0.004, -0.004), I3, (0.082, 0.112, 0.098), hair, "cloth", nu=48, nv=34, shape=hair_shape(None))
    if beard:
        b.blob(hc, I3, (0.082, 0.112, 0.098), hair, "cloth", nu=48, nv=34, shape=hair_shape(beard))
    for side in (-1, 1):  # eyes: white, an iris and pupil looking ahead
        e = hc + np.array((side * 0.029, 0.012, 0.079))
        b.blob(e, I3, (0.0125, 0.0125, 0.0125), (0.75, 0.73, 0.68), "bakelite", nu=12, nv=10,
               shape=lambda d: (1.0, (0.02, 0.015, 0.01) if d[2] > 0.88 else (0.16, 0.1, 0.06) if d[2] > 0.7
                                else None))
    if phones:  # a sonarman's or radioman's headset
        for side in (-1, 1):
            b.lathe(hc + (side * 0.082, 0.0, -0.005), (side, 0, 0), [(0, 0), (0.038, 0), (0.04, 0.02), (0.03, 0.03),
                                                                    (0, 0.03)], BAKELITE, "bakelite", seg=14,
                    crisp=False)
        band = [hc + (0.1 * math.cos(t), 0.118 * math.sin(t) + 0.0, -0.005) for t in np.linspace(0, math.pi, 14)]
        b.tube(band, 0.007, (0.3, 0.3, 0.3), "metal", seg=6)
    return b


def crew_hands(s):
    """The poses of the man on the stool at station s, in his own model space: hands resting on the desk, his right
    hand halfway to the switch rail, and on it."""
    st = Station(Builder(), s)
    z = SEAT_OUT - (st.desk_z0 + st.desk_z1) / 2 - 0.06  # the desk's middle, seen from his seat
    rest = [np.array((side * 0.17, st.desk_y + 0.02, z)) for side in (-1, 1)]
    rail = np.array((-0.1, st.desk_y + 0.09, SEAT_OUT - st.desk_z0 - 0.07))  # +x is his left: his right is -x
    half = (rest[0] + rail) / 2 + (0, 0.04, 0)
    return [rest, [half, rest[1]], [rail, rest[1]]]


WHEEL_ANGLES = np.linspace(-45, 45, 13)  # the helm wheels' turns his arms are posed at, deg (+: top to his right)
HUB = np.array((0.0, 0.93, 0.25))        # the wheel's hub, in the seated man's space (the column 0.33 ahead of him)


def grips(angle):
    """The helmsman's or planesman's hands on the wheel's grips with it turned `angle` deg."""
    a = math.radians(angle)
    return [HUB + (side * 0.17 * math.cos(a), side * 0.17 * math.sin(a), -0.02) for side in (-1, 1)]


def crew_models():
    """{file: build()} for every crewman: seated at his station, and stood aside (helm crew stay seated)."""
    out = {}
    for s in cr.STATIONS:
        if s.working and s.name != "HELM AND PLANES":
            key = s.name
            out[CREW_FILES[key]] = lambda key=key, s=s: crewman(key, "seated", crew_hands(s))  # rest, half, reach
            out[CREW_FILES[key].replace("seated", "standing")] = lambda key=key: crewman(key, "standing")
    for key in ("HELM", "PLANES"):  # hands on the yoke's grips, at each of the wheel's turns
        out[CREW_FILES[key]] = lambda key=key: crewman(key, "seated", [grips(a) for a in WHEEL_ANGLES])
    return out


CREW_FILES = {key: f"crew/{key.lower().replace(' ', '_')}_seated.glb" for key in CREW}


# ---------- writing them all ----------
STATION_FILES = {s.name: f"stations/{s.name.lower().replace(' ', '_')}.glb" for s in cr.STATIONS}


def build_all(root=ASSETS, force=False):
    """Write every model that's missing or was built by an older version of this file (all of them with force).
    A model dropped in by hand (made by anything else) is kept."""
    todo = {STATION_FILES[s.name]: (lambda s=s: station(s)) for s in cr.STATIONS} | crew_models()
    for path, build in todo.items():
        f = root / path
        stale = f.exists() and gltf.generator(f).startswith("Silent Solution") and gltf.generator(f) != MODELS
        if force or stale or not f.exists():
            build().save(f)


if __name__ == "__main__":
    import os
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    build_all(force=True)
    for p in sorted(ASSETS.rglob("*.glb")):
        print(f"{p.relative_to(ASSETS)}  {p.stat().st_size // 1024} KB")
