"""World simulation: hidden true state. Units: metres, seconds, m/s.
Bearings/headings are degrees clockwise from north; x = east, y = north."""
import math
import random
from dataclasses import dataclass, field

SOUND_SPEED = 1500.0  # m/s
KNOT = 0.514444       # m/s
YARD = 0.9144         # m


def bearing(ax, ay, bx, by):
    return math.degrees(math.atan2(bx - ax, by - ay)) % 360


def ping_delay(distance):
    return 2 * distance / SOUND_SPEED


def range_from_delay(delay):
    return delay * SOUND_SPEED / 2


@dataclass
class Vessel:
    x: float
    y: float
    heading: float  # deg
    speed: float    # m/s

    def velocity(self):
        h = math.radians(self.heading)
        return self.speed * math.sin(h), self.speed * math.cos(h)

    def step(self, dt):
        vx, vy = self.velocity()
        self.x += vx * dt
        self.y += vy * dt

    def range_to(self, other):
        return math.hypot(other.x - self.x, other.y - self.y)


@dataclass
class Torpedo(Vessel):
    max_run: float = 10000.0  # m before fuel out
    run: float = 0.0

    def step(self, dt):
        super().step(dt)
        self.run += self.speed * dt

    @property
    def spent(self):
        return self.run >= self.max_run


def intercept_heading(sx, sy, tx, ty, t_course, t_speed, torp_speed):
    """Gyro heading for a straight-run torpedo from (sx,sy) to hit a target at
    (tx,ty) on t_course/t_speed. Returns (heading, time) or None if no solution."""
    rx, ry = tx - sx, ty - sy
    h = math.radians(t_course)
    vx, vy = t_speed * math.sin(h), t_speed * math.cos(h)
    # |r + v t| = s t  ->  a t^2 + b t + c = 0
    a = vx * vx + vy * vy - torp_speed ** 2
    b = 2 * (rx * vx + ry * vy)
    c = rx * rx + ry * ry
    if abs(a) < 1e-9:
        ts = [-c / b] if b < 0 else []
    else:
        disc = b * b - 4 * a * c
        if disc < 0:
            return None
        sq = math.sqrt(disc)
        ts = [(-b - sq) / (2 * a), (-b + sq) / (2 * a)]
    ts = [t for t in ts if t > 0]
    if not ts:
        return None
    t = min(ts)
    return bearing(0, 0, rx + vx * t, ry + vy * t), t


@dataclass
class World:
    player: Vessel
    targets: list
    torpedoes: list = field(default_factory=list)
    hit_radius: float = 20.0
    time: float = 0.0
    sunk: list = field(default_factory=list)

    def step(self, dt):
        self.time += dt
        for v in [self.player, *self.targets, *self.torpedoes]:
            v.step(dt)
        for torp in self.torpedoes[:]:
            hit = next((t for t in self.targets if torp.range_to(t) <= self.hit_radius), None)
            if hit:
                self.targets.remove(hit)
                self.sunk.append(hit)
                self.torpedoes.remove(torp)
            elif torp.spent:
                self.torpedoes.remove(torp)

    def fire(self, heading, speed, max_run=10000.0):
        p = self.player
        self.torpedoes.append(Torpedo(p.x, p.y, heading, speed, max_run))

    # --- operator-facing (imperfect) information ---
    def passive_bearings(self, noise_deg=1.0):
        p = self.player
        return [(bearing(p.x, p.y, t.x, t.y) + random.gauss(0, noise_deg)) % 360
                for t in self.targets]

    def ping(self):
        """Echo delays (s) for each target. Caller decides what pinging reveals."""
        return [ping_delay(self.player.range_to(t)) for t in self.targets]
