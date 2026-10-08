"""Target motion analysis: the operator's bearing history set against the TDC's estimate, and a least-squares
helper that searches course, speed and range for the estimate that best explains the bearings.
Operator side: it only knows own-ship navigation and what the sensors reported."""
import math
from collections import deque

import numpy as np

from geometry import true_bearings
from sim import KNOT, YARD

HISTORY = 480.0     # s of bearings kept
PLOT_WINDOW = 360.0  # s shown on the plot
PLOT_SPAN = 40.0     # deg of true bearing across the plot, centred on the TDC bearing
AUTO_LOG = 4.0      # s between automatic bearings while the hydrophone holds a lock
TRACK_STEP = 2.0    # s between own-ship track points
FIT_WINDOW = 300.0  # s of bearings the fit figure uses


def wrap(d):
    return (d + 180) % 360 - 180


class TMALog:
    def __init__(self):
        self.track = deque()     # (t, x, y): own ship, from own navigation
        self.bearings = deque()  # (t, true bearing, kind, range m or None); kind HYD / MARK / SCOPE / ECHO
        self.last_track = self.last_auto = -1e9

    def update(self, t, own, locked, dial_true):
        if t - self.last_track >= TRACK_STEP:
            self.track.append((t, own.x, own.y))
            self.last_track = t
        if locked and t - self.last_auto >= AUTO_LOG:
            self.add(t, dial_true, "HYD")
            self.last_auto = t
        while self.track and t - self.track[0][0] > HISTORY + 60:
            self.track.popleft()
        while self.bearings and t - self.bearings[0][0] > HISTORY:
            self.bearings.popleft()

    def add(self, t, brg, kind, rng=None):
        self.bearings.append((t, brg % 360, kind, rng))

    def own_at(self, times):
        tr = np.array(self.track)
        return np.interp(times, tr[:, 0], tr[:, 1]), np.interp(times, tr[:, 0], tr[:, 2])

    def predicted(self, times, now, own, tdc):
        """Bearing and range the TDC's current estimate implies at past `times`, or None without a track."""
        if len(self.track) < 2:
            return None
        times = np.asarray(times, float)
        vx, vy = tdc.target_velocity()
        tx = own.x + tdc.x - vx * (now - times)
        ty = own.y + tdc.y - vy * (now - times)
        ox, oy = self.own_at(times)
        return true_bearings(ox, oy, tx, ty), np.hypot(tx - ox, ty - oy)

    def recent(self, now, window):
        return [b for b in self.bearings if now - b[0] <= window]

    def fit(self, now, own, tdc):
        """Mean bearing error (deg) of the estimate against the last FIT_WINDOW of bearings, or None."""
        pts = self.recent(now, FIT_WINDOW)
        pred = self.predicted([b[0] for b in pts], now, own, tdc) if len(pts) >= 3 else None
        if pred is None:
            return None
        return float(np.abs(wrap(np.array([b[1] for b in pts]) - pred[0])).mean())

    def auto_solve(self, now, own, tdc):
        """Grid-search course, speed and present range; set the TDC to the best.
        Returns (fit deg, ambiguous) or a reason string."""
        pts = self.recent(now, HISTORY)
        if len(pts) < 4 or pts[-1][0] - pts[0][0] < 60 or len(self.track) < 2:
            return "NEED MORE BEARINGS (60 S+)"
        times = np.array([b[0] for b in pts])
        meas = np.array([b[1] for b in pts])
        ox, oy = self.own_at(times)
        anchor = math.radians(pts[-1][1])
        ranged = [(i, b[3]) for i, b in enumerate(pts) if b[3]]
        base = ranged[-1][1] if ranged else max(math.hypot(tdc.x, tdc.y), 1000.0)
        course = np.radians(np.arange(0, 360, 5.0))
        speed = np.arange(0, 21, 1.0) * KNOT
        rng = base * np.linspace(0.5, 1.6, 23)
        px = own.x + rng * math.sin(anchor)  # candidate present position, on the latest bearing
        py = own.y + rng * math.cos(anchor)
        vx = np.sin(course)[:, None] * speed[None, :]
        vy = np.cos(course)[:, None] * speed[None, :]
        back = now - times
        tx = px[None, None, :, None] - vx[:, :, None, None] * back
        ty = py[None, None, :, None] - vy[:, :, None, None] * back
        dx, dy = tx - ox, ty - oy
        err = np.abs(wrap(meas - true_bearings(0.0, 0.0, dx, dy))).mean(axis=-1)
        if ranged:  # measured ranges pin down what bearings alone can't
            idx = np.array([i for i, _ in ranged])
            r_meas = np.array([r for _, r in ranged])
            err = err + 20 * (np.abs(np.hypot(dx[..., idx], dy[..., idx]) - r_meas) / r_meas).mean(axis=-1)
        c, s, r = np.unravel_index(np.argmin(err), err.shape)
        # bearings-only TMA is often ill-conditioned: many courses fit almost as well without an own-ship leg change
        near = np.argwhere(err <= err[c, s, r] * 1.15 + 0.03)  # "as good", relative to the bearing noise
        moving = near[speed[near[:, 1]] >= 2 * KNOT]  # a stopped target fits every course: that's not ambiguity
        spread = np.abs(wrap(np.degrees(course[moving[:, 0]]) - math.degrees(course[c]))).max() if len(moving) else 0.0
        tdc.set("BRG", (math.degrees(anchor) - own.heading) % 360)
        tdc.set("RNG", rng[r] / YARD)
        tdc.set("SPD", speed[s] / KNOT)
        tdc.set("CRS", math.degrees(course[c]) % 360)
        return float(err[c, s, r]), bool(spread > 40)
