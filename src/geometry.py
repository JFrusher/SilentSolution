"""The positional backbone: every bearing, range and angle between two bodies is measured here, so sonar, the
periscope, the plots and fire control can never disagree about where something is.

Conventions: x east, y north, z depth (metres, positive down). Bearings are degrees clockwise from north;
relative bearings are degrees clockwise from the observer's head."""
import math
from dataclasses import dataclass

import numpy as np


def bearing(ax, ay, bx, by):
    """True bearing from a to b, 0..360."""
    return math.degrees(math.atan2(bx - ax, by - ay)) % 360


def angle_diff(a, b):
    """Signed a - b in degrees, wrapped to [-180, 180)."""
    return (a - b + 180) % 360 - 180


def true_bearings(ax, ay, bx, by):
    """Vectorised bearing(): numpy arrays in, true bearings 0..360 out."""
    return np.degrees(np.arctan2(np.asarray(bx, float) - ax, np.asarray(by, float) - ay)) % 360


def horizontal(a, b):
    return math.hypot(b.x - a.x, b.y - a.y)


def slant(a, b):
    """Straight-line 3D distance: what sound and seekers actually travel."""
    return math.sqrt((b.x - a.x) ** 2 + (b.y - a.y) ** 2 + (b.z - a.z) ** 2)


def offset(x, y, brg, rng):
    """The point `rng` metres from (x, y) on true bearing `brg`."""
    b = math.radians(brg)
    return x + rng * math.sin(b), y + rng * math.cos(b)


def velocity(v):
    h = math.radians(v.heading)
    return v.speed * math.sin(h), v.speed * math.cos(h)


@dataclass(frozen=True)
class Fix:
    """Everything an observer could measure of a target, computed from true positions and motion."""
    true_brg: float   # deg
    rel_brg: float    # deg from the observer's head
    rng: float        # m, horizontal
    slant: float      # m, 3D
    de: float         # deg below the observer's horizontal plane (negative: above)
    brg_rate: float   # deg/s, true bearing drift (+ draws right / clockwise)
    rng_rate: float   # m/s horizontal (+ opening)
    aspect: float     # deg, target angle: where the observer sits off the target's bow (+ starboard)


def fix(obs, tgt):
    dx, dy, dz = tgt.x - obs.x, tgt.y - obs.y, tgt.z - obs.z
    r2 = max(dx * dx + dy * dy, 1e-9)
    r = math.sqrt(r2)
    (ox, oy), (tx, ty) = velocity(obs), velocity(tgt)
    vx, vy = tx - ox, ty - oy
    true_brg = math.degrees(math.atan2(dx, dy)) % 360
    return Fix(true_brg=true_brg, rel_brg=(true_brg - obs.heading) % 360, rng=r,
               slant=math.sqrt(r2 + dz * dz), de=math.degrees(math.atan2(dz, r)),
               brg_rate=math.degrees((dy * vx - dx * vy) / r2), rng_rate=(dx * vx + dy * vy) / r,
               aspect=angle_diff(bearing(tgt.x, tgt.y, obs.x, obs.y), tgt.heading))


def relate(obs, xs, ys, zs=None):
    """Vectorised fix for many targets: (true bearing deg, horizontal m, slant m) arrays."""
    rng = np.hypot(np.asarray(xs, float) - obs.x, np.asarray(ys, float) - obs.y)
    dz = 0.0 if zs is None else np.asarray(zs, float) - obs.z
    return true_bearings(obs.x, obs.y, xs, ys), rng, np.sqrt(rng * rng + dz * dz)


if __name__ == "__main__":  # self-check of the conventions every other module relies on
    from types import SimpleNamespace as P
    me = P(x=0.0, y=0.0, z=60.0, heading=90.0, speed=0.0)
    north = P(x=0.0, y=1000.0, z=60.0, heading=180.0, speed=5.0)  # dead ahead of nothing: due north, coming at us
    f = fix(me, north)
    assert f.true_brg == 0.0 and f.rel_brg == 270.0 and abs(f.rng - 1000) < 1e-9 and f.de == 0.0
    assert abs(f.rng_rate + 5.0) < 1e-9 and abs(f.brg_rate) < 1e-9 and abs(f.aspect) < 1e-9  # closing, bow-on
    deep = P(x=1000.0, y=0.0, z=1060.0, heading=0.0, speed=10.0)  # due east, 1000 m deeper, steaming north
    f = fix(me, deep)
    assert f.true_brg == 90.0 and f.rel_brg == 0.0 and abs(f.de - 45.0) < 1e-9 and abs(f.slant - 1000 * 2 ** 0.5) < 1e-6
    assert abs(f.brg_rate + math.degrees(10 / 1000)) < 1e-9  # moving north from due east: bearing draws left
    assert abs(f.aspect - -90.0) < 1e-9  # we are on her port beam
    b, r, s = relate(me, [0, 1000], [1000, 0], [60, 1060])
    assert np.allclose(b, [0, 90]) and np.allclose(r, [1000, 1000]) and np.allclose(s, [1000, 1000 * 2 ** 0.5])
    x, y = offset(0, 0, 45, math.sqrt(2))
    assert abs(x - 1) < 1e-9 and abs(y - 1) < 1e-9 and abs(angle_diff(350, 10) + 20) < 1e-9
    print("geometry ok")
