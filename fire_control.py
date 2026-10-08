"""Torpedo Data Computer: the operator's target estimate, position keeper and gyro solution."""
import math
from collections import namedtuple

from sim import KNOT, TORP_SPEED, YARD, bearing, clamp, intercept

# ---------- fire control ----------
Solution = namedtuple("Solution", "gyro lead time run intercept")

# name: (label, units, format, tap step, hold rate per s, min, max, wraps)
FIELDS = {
    "BRG": ("TGT BRG", "REL", "{:05.1f}", 1.0, 20.0, 0, 360, True),
    "RNG": ("TGT RNG", "YD", "{:6,.0f}", 100.0, 1500.0, 200, 20000, False),
    "SPD": ("TGT SPD", "KT", "{:4.1f}", 0.5, 4.0, 0, 35, False),
    "CRS": ("TGT CRS", "TRUE", "{:05.1f}", 1.0, 20.0, 0, 360, True),
    "ARM": ("SKR ARM", "YD", "{:5,.0f}", 100.0, 1500.0, 0, 6000, False),
    "DEP": ("RUN DEP", "M", "{:03.0f}", 5.0, 40.0, 5, 250, False),
    "SPR": ("SPREAD", "DEG", "{:04.1f}", 1.0, 4.0, 0, 10, False),
}


class TargetDataComputer:
    """Holds only the operator's estimates, as a north-up position relative to own ship.
    Acts as a position keeper: dead-reckons the estimate along estimated course/speed, so
    BRG/RNG drift the way the real contact would if the estimates are right."""

    def __init__(self, own):
        self.own = own
        self.x, self.y = 0.0, 3000 * YARD
        self.values = {"SPD": 10.0, "CRS": 90.0, "ARM": 1000.0, "DEP": 10.0, "SPR": 0.0}
        self.selected = 0

    @property
    def field(self):
        return list(FIELDS)[self.selected]

    def get(self, name):
        if name == "BRG":
            return (bearing(0, 0, self.x, self.y) - self.own.heading) % 360
        if name == "RNG":
            return math.hypot(self.x, self.y) / YARD
        return self.values[name]

    def set(self, name, v):
        *_, lo, hi, wraps = FIELDS[name]
        v = v % hi if wraps else clamp(v, lo, hi)
        if name in ("BRG", "RNG"):
            brg = v if name == "BRG" else self.get("BRG")
            rng = (v if name == "RNG" else self.get("RNG")) * YARD
            b = math.radians(brg + self.own.heading)
            self.x, self.y = rng * math.sin(b), rng * math.cos(b)
        else:
            self.values[name] = v

    def cycle(self, d):
        self.selected = (self.selected + d) % len(FIELDS)

    def nudge(self, d):
        self.set(self.field, self.get(self.field) + d * FIELDS[self.field][3])

    def hold(self, d, dt):
        self.set(self.field, self.get(self.field) + d * FIELDS[self.field][4] * dt)

    def target_velocity(self):
        c, s = math.radians(self.values["CRS"]), self.values["SPD"] * KNOT
        return s * math.sin(c), s * math.cos(c)

    def update(self, dt):
        (vx, vy), (ox, oy) = self.target_velocity(), self.own.velocity()
        self.x += (vx - ox) * dt
        self.y += (vy - oy) * dt

    def solve(self):
        sol = intercept(bearing(0, 0, self.x, self.y), math.hypot(self.x, self.y), self.values["CRS"],
                        self.values["SPD"] * KNOT, TORP_SPEED)
        if sol is None:
            return None
        gyro, lead, t = sol
        run, g = TORP_SPEED * t, math.radians(gyro)
        return Solution(gyro, lead, t, run, (run * math.sin(g), run * math.cos(g)))
