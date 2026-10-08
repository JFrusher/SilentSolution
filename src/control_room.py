"""The control room you can walk: where everything stands, how you move between it, and what you can reach.
Operator side and drawing-free (graphics/room3d.py renders it). Metres; x starboard, y up, z aft, bow at -z.
Yaw 0 looks at the bow; positive yaw turns to starboard. Pitch is up positive."""
import math
from dataclasses import dataclass

import numpy as np

HULL_R, HULL_Y = 2.9, 1.15         # pressure hull radius and its axis height above the deck
LENGTH = 11.0                      # bulkhead to bulkhead
EYE_H = 1.65                       # standing eye height
BODY_R = 0.28                      # how close you can stand to anything
WALK, RUN = 1.6, 2.8               # m/s
REACH = 1.4                        # m from a station's front you can use it
MOVE_TIME = 0.9                    # s for the camera to carry you between standing and seated / at the eyepiece
FOVY = 62.0                        # vertical field of view, deg
PANEL_LIFT = 0.004                 # panel faces sit this far proud of their housings


def deck_half_width(y=0.0):
    """Half the width of the room at height y: the hull curves in above and below the axis."""
    return math.sqrt(HULL_R ** 2 - (y - HULL_Y) ** 2)


@dataclass(frozen=True)
class Station:
    """A console against the hull or a bulkhead. Its panel faces `normal` (pointing into the room, tilted back) and
    is w x h metres. `working` stations open the live console when you sit; the rest are set dressing for now."""
    name: str
    centre: tuple   # panel centre
    normal: tuple   # unit, into the room
    w: float
    h: float
    working: bool = False
    stand: float = 0.85  # how far out from the panel you stand to use it

    def front(self):
        """Where you stand to use it: a pace out from the panel, at the deck."""
        c, n = np.array(self.centre), np.array(self.normal)
        flat = np.array([n[0], 0.0, n[2]]) / math.hypot(n[0], n[2])
        p = c + flat * self.stand
        return np.array([p[0], 0.0, p[2]])


def _tilted(dx, dz, tilt=18.0):
    """Unit normal facing (dx, 0, dz) on the deck, leaned back `tilt` degrees like a console face."""
    t = math.radians(tilt)
    return (dx * math.cos(t), math.sin(t), dz * math.cos(t))


STATIONS = (  # 16:9 panels, so each crewed station can be taken and its 2D close-up fills the screen
    Station("SONAR", (-2.05, 1.30, 1.70), _tilted(1, 0), 1.60, 0.90, working=True),
    Station("FIRE CONTROL", (-2.05, 1.30, -0.55), _tilted(1, 0), 1.60, 0.90, working=True),
    Station("RADIO", (-2.05, 1.30, -2.70), _tilted(1, 0), 1.20, 0.675, working=True),
    Station("HELM AND PLANES", (0.0, 1.35, -4.75), _tilted(0, 1), 1.92, 1.08, working=True, stand=1.40),
    Station("BALLAST CONTROL", (2.05, 1.30, -2.30), _tilted(-1, 0), 1.60, 0.90, working=True),
    Station("DAMAGE CONTROL", (2.05, 1.30, 0.10), _tilted(-1, 0), 1.60, 0.90, working=True),
    Station("NAVIGATION", (2.05, 1.30, 2.40), _tilted(-1, 0), 1.20, 0.675),
)
PERISCOPE = (0.0, 0.55)            # x, z of the search periscope in its well
PERISCOPE_R = 0.55                 # the rail round it
EYEPIECE_Y = 1.62
TABLE = (0.0, -2.05, 1.30, 0.90)   # x, z, size along x, size along z of the dead-reckoning plot table
TABLE_TOP = 0.95


def obstacles():
    """Footprints you can't walk through, as (x0, z0, x1, z1)."""
    rects = []
    for s in STATIONS:  # the console body below each panel, out to its front edge
        c, n = s.centre, s.normal
        if abs(n[0]) > abs(n[2]):  # against the hull side
            x_out, x_hull = c[0] + math.copysign(0.45, n[0]), c[0] - math.copysign(1.0, n[0])
            rects.append((min(x_out, x_hull), c[2] - s.w / 2, max(x_out, x_hull), c[2] + s.w / 2))
        else:  # forward bulkhead: the helm, and the seats in front of it
            rects.append((c[0] - s.w / 2, c[2] - 0.6, c[0] + s.w / 2, c[2] + 0.95))
    x, z = PERISCOPE
    rects.append((x - PERISCOPE_R, z - PERISCOPE_R, x + PERISCOPE_R, z + PERISCOPE_R))
    tx, tz, sx, sz = TABLE
    rects.append((tx - sx / 2, tz - sz / 2, tx + sx / 2, tz + sz / 2))
    return tuple(rects)


OBSTACLES = obstacles()


@dataclass
class Pose:
    pos: np.ndarray  # eye position
    yaw: float       # deg
    pitch: float     # deg

    def forward(self):
        y, p = math.radians(self.yaw), math.radians(self.pitch)
        return np.array([math.sin(y) * math.cos(p), math.sin(p), -math.cos(y) * math.cos(p)])


def facing(direction):
    """(yaw, pitch) that look along `direction`."""
    d = np.asarray(direction, float)
    return math.degrees(math.atan2(d[0], -d[2])), math.degrees(math.asin(d[1] / np.linalg.norm(d)))


def seated(station, aspect=16 / 9):
    """The eye square to the panel at the distance where it exactly fills the view: the 3D panel and the 2D console
    are then the same picture, so cutting between them can't be seen."""
    n = np.array(station.normal)
    d = (station.h / 2) / math.tan(math.radians(FOVY) / 2)
    assert abs(station.w / station.h - aspect) < 0.02, "a sit-down panel must have the screen's shape"
    return Pose(np.array(station.centre) + n * (d + PANEL_LIFT), *facing(-n))


def at_eyepiece():
    """Face pressed to the periscope's eyepiece, looking forward along the boat."""
    x, z = PERISCOPE
    return Pose(np.array([x, EYEPIECE_Y, z + 0.40]), 0.0, 0.0)  # just off the eyepiece face (z + 0.32)


def by_periscope():
    """Stepped back from the eyepiece, still facing the scope."""
    x, z = PERISCOPE
    return Pose(np.array([x, EYE_H, z + PERISCOPE_R + 0.45]), 0.0, -12.0)


def standing(station):
    """Stood back from a station, looking at it."""
    p = station.front() + np.array([0.0, EYE_H, 0.0])
    return Pose(p, *facing(np.array(station.centre) - p))


def blocked(x, z):
    w = deck_half_width(0.3) - BODY_R
    if abs(x) > w or abs(z) > LENGTH / 2 - BODY_R:
        return True
    return any(x0 - BODY_R < x < x1 + BODY_R and z0 - BODY_R < z < z1 + BODY_R for x0, z0, x1, z1 in OBSTACLES)


def ease(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def blend(a, b, t):
    """Pose between a and b, turning the short way round."""
    k = ease(t)
    dyaw = (b.yaw - a.yaw + 180) % 360 - 180
    return Pose(a.pos + (b.pos - a.pos) * k, a.yaw + dyaw * k, a.pitch + (b.pitch - a.pitch) * k)


class ControlRoom:
    """You, in the room: walking, looking, and being carried to and from a station or the eyepiece."""

    def __init__(self, station=STATIONS[0]):
        self.pose = seated(station)
        self.move = None  # (from, to, elapsed, then): a camera move under way and what happens at its end
        self.bob = 0.0

    @property
    def moving(self):
        return self.move is not None

    def carry(self, to, then):
        """Glide the eye to `to`; `then` names what the patrol does on arrival."""
        self.move = (self.pose, to, 0.0, then)

    def update(self, dt, forward=0.0, side=0.0, run=False):
        """Advance a camera move, or walk. Returns the finished move's `then`, if one finished."""
        if self.move:
            a, b, t, then = self.move
            t += dt / MOVE_TIME
            self.pose = blend(a, b, t)
            self.move = None if t >= 1 else (a, b, t, then)
            return then if t >= 1 else None
        if forward or side:
            y = math.radians(self.pose.yaw)
            fx, fz = math.sin(y), -math.cos(y)
            step = (RUN if run else WALK) * dt / math.hypot(forward, side)
            dx, dz = (fx * forward - fz * side) * step, (fz * forward + fx * side) * step
            p = self.pose.pos
            if not blocked(p[0] + dx, p[2]):  # slide along whatever stops you
                p[0] += dx
            if not blocked(p[0], p[2] + dz):
                p[2] += dz
            self.bob += dt * (9.0 if run else 6.5)
            p[1] = EYE_H + 0.025 * math.sin(self.bob)
        return None

    def look(self, dx, dy, sensitivity=0.12):
        self.pose.yaw = (self.pose.yaw + dx * sensitivity) % 360
        self.pose.pitch = max(-75.0, min(75.0, self.pose.pitch - dy * sensitivity))

    def target(self):
        """What you'd use with E: the station or periscope in reach that you're facing most squarely, or None."""
        p, f = self.pose.pos, self.pose.forward()
        best, score = None, 0.5  # must be roughly in front of you
        spots = [(s, s.front(), np.array(s.centre)) for s in STATIONS]
        x, z = PERISCOPE
        spots.append(("PERISCOPE", np.array([x, 0.0, z + PERISCOPE_R]), np.array([x, EYEPIECE_Y, z])))
        for thing, stand, aim in spots:
            if math.hypot(p[0] - stand[0], p[2] - stand[2]) > REACH:
                continue
            d = aim - p
            s = float(np.dot(d / np.linalg.norm(d), f))
            if s > score:
                best, score = thing, s
        return best


if __name__ == "__main__":  # self-check: the room's geometry holds together
    for s in STATIONS:
        assert abs(np.linalg.norm(s.normal) - 1) < 1e-9, s.name
        f = s.front()
        assert not blocked(f[0], f[2]), f"{s.name}: you can't stand at it"
        if s.working:
            assert seated(s)  # its shape fits the screen
    assert not blocked(0.0, PERISCOPE[1] + PERISCOPE_R + 0.4), "you can't stand at the periscope"
    print("control room ok")
