"""The after-action plotting table: a patrol's recorded truth in 3D, seen across a wardroom chart table.
The chart is the sea surface (frosted glass); submarines and fish hang beneath it on depth stalks; the
thermocline is a smoked-glass sheet. Depth is exaggerated (and labelled) so 300 m reads against 10 km."""
import math
from collections import namedtuple

import numpy as np
import pygame

from graphics import console_art as art
from sim import KNOT

NM = 1852.0
WOOD, RAIL, FELT = (58, 38, 24), (36, 24, 16), (24, 28, 26)
PAPER, GRID, INKC = (226, 220, 198), (160, 150, 126), (60, 54, 46)
SEA = (70, 96, 104)  # deep models fade toward this, so depth reads even from above
GLASS = (110, 130, 140)
COLORS = {  # (hull, upperworks)
    "merchant": ((118, 116, 108), (198, 182, 140)), "tanker": ((104, 100, 92), (190, 170, 128)),
    "escort": ((86, 92, 98), (128, 134, 140)), "own": ((92, 116, 140), (150, 170, 190)),
    "sub": ((136, 72, 52), (170, 104, 80)), "torpedo": ((206, 166, 64), (230, 200, 110)),
    "charge": ((26, 26, 26), (60, 60, 60)), "decoy": ((236, 236, 230), (250, 250, 250)),
}
TRACK = {"own": (52, 84, 128), "sub": (150, 60, 40), "escort": (70, 74, 80), "torpedo": (190, 140, 30),
         "merchant": (110, 100, 80), "tanker": (110, 100, 80), "charge": (30, 30, 30), "decoy": (160, 160, 160)}
Item = namedtuple("Item", "uid x y z heading speed cls settle dead")
LIGHT = np.array([-0.4, 0.5, 0.75]) / np.linalg.norm([-0.4, 0.5, 0.75])


class Camera:
    """Perspective camera orbiting a look-at point on the table. yaw: bearing from the target to the camera;
    pitch: degrees above the table."""

    def __init__(self, target, dist, yaw=200.0, pitch=35.0, fov=40.0, size=(1280, 720)):
        self.target, self.dist, self.yaw, self.pitch, self.fov, self.size = list(target), dist, yaw, pitch, fov, size
        self._cache = (None, None)

    def basis(self):
        key = (*self.target, self.dist, self.yaw, self.pitch, self.fov, self.size)
        if self._cache[0] == key:
            return self._cache[1]
        p, y = math.radians(max(2.0, min(89.0, self.pitch))), math.radians(self.yaw)
        tx, ty = self.target
        cam = np.array([tx + self.dist * math.cos(p) * math.sin(y), ty + self.dist * math.cos(p) * math.cos(y),
                        self.dist * math.sin(p)])
        f = np.array([tx, ty, 0.0]) - cam
        f /= np.linalg.norm(f)
        r = np.array([f[1], -f[0], 0.0])  # f x up, with up = +z
        r /= np.linalg.norm(r)
        u = np.array([r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]])
        self._cache = (key, (cam, r, u, f))
        return self._cache[1]

    def project(self, x, y, h):
        """Table coordinates (h = height, negative below the chart) -> screen x, y and camera depth."""
        cam, r, u, f = self.basis()
        vx, vy, vh = np.asarray(x, float) - cam[0], np.asarray(y, float) - cam[1], np.asarray(h, float) - cam[2]
        d = vx * f[0] + vy * f[1] + vh * f[2]
        focal = self.size[0] / 2 / math.tan(math.radians(self.fov) / 2)
        safe = np.maximum(d, 1e-6)
        return (self.size[0] / 2 + focal * (vx * r[0] + vy * r[1] + vh * r[2]) / safe,
                self.size[1] / 2 - focal * (vx * u[0] + vy * u[1] + vh * u[2]) / safe, d)

    def preset(self, name, table):
        cx, cy, size = table
        self.target = [cx, cy]
        self.dist = size * 1.7
        self.yaw, self.pitch = {"plan": (180.0, 89.0), "side": (90.0, 4.0), "oblique": (200.0, 35.0)}[name]


class TabletopRenderer:
    def __init__(self, replay, size=(1280, 720)):
        self.r, self.size = replay, size
        pts = np.concatenate([tr[:, 1:3] for tr in replay.tracks.values()])
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        self.span = max(hi[0] - lo[0], hi[1] - lo[1], 2 * NM) * 1.25 + 2 * NM
        self.table = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, self.span)
        self.model = self.span * 0.045  # a merchant's model length on the table: models are not to scale
        self.layer = replay.meta.get("layer") or 100.0
        self.ex = 10.0  # depth exaggeration
        self.font = art.sans(13, True)
        self.small = art.sans(11, False)
        self.labels = []  # (screen x, y, text) of every model drawn, for hover

    # ---------- helpers ----------
    def h(self, z):
        return -np.asarray(z, float) * self.ex

    def scale(self, kind_cls):
        length = {"merchant": 1.0, "tanker": 1.15, "escort": 0.75, "own": 0.7, "sub": 0.65, "torpedo": 0.28,
                  "charge": 0.1, "decoy": 0.1}.get(kind_cls, 0.5)
        return self.model * length

    def _poly(self, surf, cam, xs, ys, hs, color, width=0, alpha=None):
        sx, sy, d = cam.project(xs, ys, hs)
        if (d <= 1).any():
            return
        pts = list(zip(sx, sy))
        if alpha is None:
            pygame.draw.polygon(surf, color, pts, width)
        else:  # translucent sheet: one reusable overlay, cleared each time
            if getattr(self, "_overlay", None) is None:
                self._overlay = pygame.Surface(self.size, pygame.SRCALPHA)
            self._overlay.fill((0, 0, 0, 0))
            pygame.draw.polygon(self._overlay, (*color, alpha), pts, width)
            surf.blit(self._overlay, (0, 0))

    def _line(self, surf, cam, xyz, color, width=1):
        if len(xyz) < 2:
            return
        sx, sy, d = cam.project(xyz[:, 0], xyz[:, 1], xyz[:, 2])
        ok = d > 1
        if ok.sum() >= 2:
            pygame.draw.lines(surf, color, False, list(zip(sx[ok], sy[ok])), width)

    # ---------- the table ----------
    def _table(self, surf, cam, below):
        cx, cy, s = self.table
        half = s / 2
        corners = np.array([[cx - half, cy - half], [cx + half, cy - half], [cx + half, cy + half],
                            [cx - half, cy + half]])
        if below:  # the felt floor under the glass, then the smoked thermocline sheet
            self._poly(surf, cam, corners[:, 0], corners[:, 1], np.full(4, self.h(320)), FELT)
            self._poly(surf, cam, corners[:, 0], corners[:, 1], np.full(4, self.h(self.layer)), GLASS, alpha=70)
            self._poly(surf, cam, corners[:, 0], corners[:, 1], np.full(4, self.h(self.layer)), (70, 90, 100), 1)
            return
        rim = corners + np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]]) * s * 0.04
        self._poly(surf, cam, rim[:, 0], rim[:, 1], np.zeros(4), RAIL)
        self._poly(surf, cam, corners[:, 0], corners[:, 1], np.zeros(4), PAPER, alpha=205)  # frosted chart glass
        start = math.floor((cx - half) / NM) * NM
        for k in range(int(s / NM) + 2):  # a 1 nm grid
            g = start + k * NM
            if cx - half <= g <= cx + half:
                self._line(surf, cam, np.array([[g, cy - half, 0], [g, cy + half, 0]]), GRID)
            g2 = math.floor((cy - half) / NM) * NM + k * NM
            if cy - half <= g2 <= cy + half:
                self._line(surf, cam, np.array([[cx - half, g2, 0], [cx + half, g2, 0]]), GRID)
        # compass rose and the depth ruler at the south-west corner
        ox, oy = cx - half + s * 0.07, cy - half + s * 0.07
        arm = s * 0.04
        self._line(surf, cam, np.array([[ox, oy - arm, 0], [ox, oy + arm * 1.4, 0]]), INKC, 2)
        self._line(surf, cam, np.array([[ox - arm, oy, 0], [ox + arm, oy, 0]]), INKC, 1)
        nx, ny, _ = cam.project(ox, oy + arm * 1.8, 0)
        surf.blit(self.font.render("N", True, INKC), (nx - 4, ny - 8))

    def _ruler(self, surf, cam):
        cx, cy, s = self.table
        x, y = cx - s / 2, cy - s / 2
        self._line(surf, cam, np.array([[x, y, 0], [x, y, float(self.h(300))]]), (200, 190, 160), 2)
        for depth in (0, 100, 200, 300):
            sx, sy, d = cam.project(x, y, self.h(depth))
            if d > 1:
                pygame.draw.line(surf, (200, 190, 160), (sx - 6, sy), (sx + 6, sy), 2)
                surf.blit(self.small.render(f"{depth} M", True, (220, 210, 180)), (sx + 9, sy - 7))
        sx, sy, _ = cam.project(x, y, self.h(320))
        surf.blit(self.small.render(f"DEPTH x{self.ex:g}", True, (220, 210, 180)), (sx + 9, sy - 2))

    # ---------- models ----------
    def _footprint(self, cls, length):
        b = length * (0.16 if cls in ("merchant", "tanker", "escort") else 0.12)
        if cls in ("own", "sub"):
            return np.array([[0.5, 0], [0.38, b / 2], [-0.42, b / 2], [-0.5, 0], [-0.42, -b / 2], [0.38, -b / 2]]) \
                * [length, 1]
        return np.array([[0.5, 0], [0.32, b / 2], [-0.5, b / 2], [-0.5, -b / 2], [0.32, -b / 2]]) * [length, 1]

    def _prism(self, x, y, heading, local, h0, h1):
        """World vertices of a footprint (local x forward, y starboard) extruded from h0 to h1."""
        hr = math.radians(heading)
        wx = x + local[:, 0] * math.sin(hr) + local[:, 1] * math.cos(hr)
        wy = y + local[:, 0] * math.cos(hr) - local[:, 1] * math.sin(hr)
        return wx, wy, h0, h1

    def _faces(self, x, y, h, heading, cls, sinking=0.0):
        """Shaded faces (screen-depth, points xyz, colour) of one model."""
        length = self.scale(cls)
        hull, upper = COLORS.get(cls, COLORS["merchant"])
        out = []
        if cls in ("merchant", "tanker", "escort"):
            parts = [(self._footprint(cls, length), 0.0, length * 0.10, hull)]
            box = np.array([[0.05, 0.05], [0.05, -0.05], [-0.18, -0.05], [-0.18, 0.05]]) * [length, length]
            if cls == "tanker":
                box = box + [-length * 0.22, 0]
            parts.append((box, length * 0.10, length * 0.22, upper))
        elif cls in ("own", "sub"):
            r = length * 0.06
            parts = [(self._footprint(cls, length), -r, r, hull),
                     (np.array([[0.14, 0.03], [0.14, -0.03], [0.0, -0.03], [0.0, 0.03]]) * [length, length], r, r * 2.6,
                      upper)]
        else:  # fish, charges, decoys: a small dart or block
            r = length * 0.2
            parts = [(np.array([[0.5, 0], [-0.5, r / length], [-0.5, -r / length]]) * [length, length], -r, r, hull)]
        for local, h0, h1, color in parts:
            wx, wy, a, b = self._prism(x, y, heading, local, h + h0 - sinking, h + h1 - sinking)
            n = len(wx)
            for i in range(n):  # sides
                j = (i + 1) % n
                xs, ys, hs = [wx[i], wx[j], wx[j], wx[i]], [wy[i], wy[j], wy[j], wy[i]], [a, a, b, b]
                normal = np.array([wy[j] - wy[i], -(wx[j] - wx[i]), 0.0])
                normal /= max(np.linalg.norm(normal), 1e-9)
                out.append((xs, ys, hs, _shade(color, 0.55 + 0.45 * max(0.0, normal @ LIGHT))))
            out.append((list(wx), list(wy), [b] * n, _shade(color, 1.0)))  # top
        return out

    # ---------- frame ----------
    def render(self, t, cam, surf=None):
        surf = surf or pygame.Surface(self.size)
        surf.fill(WOOD)
        state, self.labels = self.r.at(t), []
        below, above = [], []
        for uid, (x, y, z, heading, speed) in state.items():
            body = self.r.bodies[uid]
            cls = "own" if body["kind"] == "OWN" else body["cls"]
            sunk = body.get("sunk")
            settle = 0.0 if sunk is None or t < sunk else min(1.0, (t - sunk) / 150) * self.model * 0.5
            item = Item(uid, x, y, z, heading, speed, cls, settle, sunk is not None and t >= sunk)
            (below if z > 2 or settle > 0 else above).append(item)
        # a cutaway table: the floor and the layer sheet, the chart glass, then everything on top of it, with
        # submerged hulls hanging on stalks below their shadows and fading toward the sea colour with depth
        self._table(surf, cam, below=True)
        self._table(surf, cam, below=False)
        self._tracks(surf, cam, t, deep=False)
        self._tracks(surf, cam, t, deep=True)
        for it in below:
            sx, sy, d = cam.project(it.x, it.y, 0.0)
            if d > 1:
                pygame.draw.circle(surf, (90, 90, 84), (sx, sy), 4)
            self._line(surf, cam, np.array([[it.x, it.y, 0.0], [it.x, it.y, float(self.h(it.z))]]), (40, 44, 42), 1)
        self._bursts(surf, cam, t, deep=True)
        self._models(surf, cam, below + above)
        self._bursts(surf, cam, t, deep=False)
        self._ruler(surf, cam)
        for it in below + above:
            sx, sy, d = cam.project(it.x, it.y, self.h(it.z))
            if d > 1:
                name = {"own": "OWN BOAT", "sub": "SUBMARINE"}.get(it.cls, it.cls.upper())
                self.labels.append((sx, sy, f"{name}  {it.z:.0f} M  {it.speed / KNOT:.0f} KT  {it.heading:03.0f}"
                                    + ("  SUNK" if it.dead else "")))
        return surf

    def _models(self, surf, cam, items):
        faces = []
        for it in items:
            fog = min(0.6, max(0.0, it.z) / 300)
            for xs, ys, hs, color in self._faces(it.x, it.y, float(self.h(it.z)), it.heading, it.cls, it.settle):
                color = _mix(color, SEA, fog)
                faces.append((xs, ys, hs, _shade(color, 0.6) if it.dead else color))
        if not faces:
            return
        sizes = [len(f[0]) for f in faces]  # one projection for every vertex of every face
        sx, sy, d = cam.project(np.concatenate([f[0] for f in faces]), np.concatenate([f[1] for f in faces]),
                                np.concatenate([f[2] for f in faces]))
        cuts = np.cumsum([0, *sizes])
        drawn = []
        for k, (_, _, _, color) in enumerate(faces):
            a, b = cuts[k], cuts[k + 1]
            if (d[a:b] > 1).all():
                drawn.append((float(d[a:b].mean()), list(zip(sx[a:b], sy[a:b])), color))
        for _, pts, color in sorted(drawn, key=lambda f: -f[0]):  # painter's algorithm: far to near
            pygame.draw.polygon(surf, color, pts)
            pygame.draw.polygon(surf, _shade(color, 0.5), pts, 1)

    def _tracks(self, surf, cam, t, deep):
        for uid, tr in self.r.tracks.items():
            body = self.r.bodies[uid]
            cls = "own" if body["kind"] == "OWN" else body["cls"]
            past = tr[tr[:, 0] <= t]
            if len(past) < 2:
                continue
            sub = past[:, 3].max() > 2
            if deep and sub:
                pts = np.column_stack([past[:, 1], past[:, 2], self.h(past[:, 3])])
                self._line(surf, cam, pts, TRACK.get(cls, INKC), 2)
            if not deep:
                color = TRACK.get(cls, INKC) if not sub else (150, 144, 128)  # submerged: its shadow on the chart
                pts = np.column_stack([past[:, 1], past[:, 2], np.zeros(len(past))])
                self._line(surf, cam, pts, color, 1 if sub else 2)

    def _bursts(self, surf, cam, t, deep):
        for e in self.r.events:
            age = t - e["t"]
            if not 0 <= age < 6 or "x" not in e or e["kind"] not in ("CHARGE", "HIT", "PLAYER_HIT", "DECOYED"):
                continue
            z = e.get("z", 0.0) if e["kind"] == "CHARGE" else 0.0
            if (z > 2) != deep:
                continue
            radius = self.model * (0.3 + age * 0.5)
            ring = np.linspace(0, 2 * math.pi, 28)
            pts = np.column_stack([e["x"] + radius * np.sin(ring), e["y"] + radius * np.cos(ring),
                                   np.full(28, float(self.h(z)))])
            color = (230, 120, 40) if e["kind"] != "CHARGE" else (240, 240, 230)
            self._line(surf, cam, pts, _shade(color, 1 - age / 6), 2)


TICKS = {"HIT": (220, 60, 40), "PLAYER_HIT": (240, 140, 40), "CHARGES": (240, 240, 230), "DAMAGE": (240, 140, 40),
         "HOSTILE_LAUNCH": (200, 50, 40), "LAUNCH": (220, 180, 70), "WAVE": (120, 170, 200)}
SPEEDS = (1.0, 4.0, 16.0, 60.0)
BAR = pygame.Rect(90, 676, 1100, 14)  # the timeline


class ReplayView:
    """The REPLAY page. Drag orbits, wheel zooms, right-drag pans; 1 plan, 2 side, 3 oblique, 4 follow own boat,
    0 reset, [ ] depth exaggeration; Space play/pause, LEFT/RIGHT 10 s (with Shift: event to event), +/- speed,
    click the timeline to scrub; Esc back."""

    def __init__(self, replay, back):
        self.r, self.back = replay, back
        self.tab = TabletopRenderer(replay)
        self.cam = Camera(self.tab.table[:2], self.tab.span * 1.7)
        self.cam.preset("oblique", self.tab.table)
        self.t, self.speed, self.playing, self.follow = replay.start, SPEEDS[1], True, False
        self.drag, self.mouse = None, (0, 0)
        own = next((u for u, b in replay.bodies.items() if b["kind"] == "OWN"), None)
        self.own = own
        self.ticks = [(e["t"], TICKS[e["kind"]]) for e in replay.events if e["kind"] in TICKS]
        self.ticks += [(b["born"], TICKS["LAUNCH"]) for b in replay.bodies.values()
                       if b["kind"] == "TORPEDO" and not b["hostile"]]
        self.ticks.sort()

    def key(self, k, mods=0):
        """Returns "BACK" to leave."""
        shift = mods & pygame.KMOD_SHIFT
        if k == pygame.K_ESCAPE:
            return "BACK"
        if k == pygame.K_SPACE:
            self.playing = not self.playing
            if self.t >= self.r.end:
                self.t = self.r.start
        elif k in (pygame.K_LEFT, pygame.K_RIGHT):
            d = 1 if k == pygame.K_RIGHT else -1
            if shift:  # event to event
                times = [t for t, _ in self.ticks if (t > self.t + 0.5 if d > 0 else t < self.t - 0.5)]
                if times:
                    self.t = min(times) if d > 0 else max(times)
            else:
                self.t += 10 * d
        elif k in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_MINUS, pygame.K_KP_MINUS):
            i = SPEEDS.index(self.speed) + (1 if k in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS) else -1)
            self.speed = SPEEDS[max(0, min(len(SPEEDS) - 1, i))]
        elif k in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_0):
            self.follow = False
            self.cam.preset({pygame.K_1: "plan", pygame.K_2: "side"}.get(k, "oblique"), self.tab.table)
        elif k == pygame.K_4:
            self.follow = not self.follow
        elif k in (pygame.K_LEFTBRACKET, pygame.K_RIGHTBRACKET):
            steps = (1.0, 3.0, 5.0, 10.0, 15.0, 25.0)
            i = min(range(len(steps)), key=lambda j: abs(steps[j] - self.tab.ex))
            self.tab.ex = steps[max(0, min(len(steps) - 1, i + (1 if k == pygame.K_RIGHTBRACKET else -1)))]
        elif k == pygame.K_HOME:
            self.t = self.r.start
        self.t = max(self.r.start, min(self.r.end, self.t))
        return None

    def mouse_down(self, pos, button):
        if button == 1 and BAR.inflate(0, 16).collidepoint(pos):
            self.t = self.r.start + (pos[0] - BAR.x) / BAR.w * (self.r.end - self.r.start)
            self.drag = ("scrub", pos)
        elif button in (1, 3):
            self.drag = ("orbit" if button == 1 else "pan", pos)

    def mouse_up(self):
        self.drag = None

    def motion(self, pos):
        self.mouse = pos
        if not self.drag:
            return
        kind, (x0, y0) = self.drag
        dx, dy = pos[0] - x0, pos[1] - y0
        if kind == "scrub":
            self.t = self.r.start + max(0.0, min(1.0, (pos[0] - BAR.x) / BAR.w)) * (self.r.end - self.r.start)
        elif kind == "orbit":
            self.cam.yaw = (self.cam.yaw - dx * 0.4) % 360
            self.cam.pitch = max(3.0, min(89.0, self.cam.pitch + dy * 0.3))
        else:  # pan in the table plane, along the camera's own right and forward
            yaw = math.radians(self.cam.yaw)
            k = self.cam.dist / 900
            self.cam.target[0] += (-dx * math.cos(yaw) + dy * math.sin(yaw)) * k
            self.cam.target[1] += (dx * math.sin(yaw) + dy * math.cos(yaw)) * k
            self.follow = False
        self.drag = (kind, pos)

    def wheel(self, dy):
        self.cam.dist = max(self.tab.span * 0.15, min(self.tab.span * 4, self.cam.dist * 0.88 ** dy))

    def update(self, dt):
        if self.playing:
            self.t += dt * self.speed
            if self.t >= self.r.end:
                self.t, self.playing = self.r.end, False
        if self.follow and self.own is not None:
            own = self.r.at(self.t).get(self.own)
            if own:
                self.cam.target = [own[0], own[1]]

    def draw(self, screen):
        self.tab.render(self.t, self.cam, screen)
        meta = self.r.meta
        art.label_plate(screen, (640, 26), f"AFTER-ACTION PLOT  -  {meta.get('title', meta.get('mode', 'PATROL'))}  -  "
                                           f"{meta.get('result', '')}", 13)
        elapsed = self.t - self.r.start
        state = "PLAYING" if self.playing else "PAUSED"
        clock = f"T+{int(elapsed // 60):02d}:{int(elapsed % 60):02d}"
        art.dymo(screen, (14, 640), f"{clock}   x{self.speed:g}   {state}", 13)
        art.dymo(screen, (900, 640), "DRAG ORBIT  WHEEL ZOOM  1-4 VIEWS  [ ] DEPTH  SPACE  ESC", 11)
        pygame.draw.rect(screen, (30, 22, 14), BAR.inflate(6, 6))
        pygame.draw.rect(screen, (90, 70, 46), BAR)
        span = max(self.r.end - self.r.start, 1e-6)
        for t, color in self.ticks:
            x = BAR.x + (t - self.r.start) / span * BAR.w
            pygame.draw.line(screen, color, (x, BAR.y - 4), (x, BAR.bottom + 4), 2)
        x = BAR.x + elapsed / span * BAR.w
        pygame.draw.polygon(screen, (240, 230, 200), [(x, BAR.y - 2), (x - 6, BAR.y - 12), (x + 6, BAR.y - 12)])
        near = min(self.tab.labels, key=lambda lb: math.dist(lb[:2], self.mouse), default=None)
        if near and math.dist(near[:2], self.mouse) < 24:  # hover: what it is, how deep, how fast
            art.dymo(screen, (int(near[0]) + 12, int(near[1]) - 26), near[2], 12)


def _mix(a, b, k):
    return tuple(int(x + (y - x) * k) for x, y in zip(a, b))


def _shade(color, k):
    return tuple(int(max(0, min(255, c * k))) for c in color)


if __name__ == "__main__":  # self-check: projection conventions, presets, a smoke render and its frame time
    import os
    import time
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((1280, 720))
    cam = Camera((0, 0), 10000)
    cam.preset("plan", (0, 0, 8000))
    x, y, _ = cam.project([0, 0, 1000], [0, 1000, 0], [0, 0, 0])
    assert abs(x[0] - 640) < 1 and abs(y[0] - 360) < 1, "the look-at point is the screen centre"
    assert y[1] < y[0] and abs(x[1] - x[0]) < 2, "plan: north is up"
    assert x[2] > x[0] and abs(y[2] - y[0]) < 2, "plan: east is right"
    cam.preset("side", (0, 0, 8000))
    _, y, _ = cam.project([0, 0], [0, 0], [0, -1000])
    assert y[1] > y[0], "side: deeper is lower"
    cam.yaw, cam.pitch = 123.0, 47.0
    x, y, _ = cam.project([0], [0], [0])
    assert abs(x[0] - 640) < 1 and abs(y[0] - 360) < 1, "orbiting keeps the target centred"

    from replay import Recorder, Replay
    from sim import Submarine, Torpedo, Vessel, WorldSimulation
    w = WorldSimulation(Submarine(0, 0, 45, 5 * KNOT, z=60), [Vessel(3000, 1000, 270, 8 * KNOT),
                                                              Vessel(-2000, 2500, 120, 12 * KNOT, z=120, kind="SUB")])
    w.torpedoes.append(Torpedo(0, 0, 60, 35 * KNOT, z=60))
    rec = Recorder()
    for _ in range(1200):
        rec.sample(w, w.step(0.1))
    rp = Replay(rec.data(dict(mode="TEST")))
    tab = TabletopRenderer(rp)
    cam = Camera(tab.table[:2], tab.span * 1.25)
    surf = pygame.Surface((1280, 720))
    t0 = time.perf_counter()
    for name in ("plan", "side", "oblique", "oblique"):
        cam.preset(name, tab.table)
        tab.render(60.0, cam, surf)
    ms = (time.perf_counter() - t0) / 4 * 1000
    assert len(tab.labels) == 4, tab.labels
    print(f"tabletop ok ({ms:.1f} ms a frame)")
