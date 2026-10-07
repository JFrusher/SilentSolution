"""Operator sensors: the only path from world truth to the console (sonar, active sonar, periscope optics)."""
import math
import random
from collections import namedtuple

import numpy as np

from sim import (R_EFF, SCOPE_TOP, SHIP_CLASSES, Decoy, angle_diff, bearing, horizon_distance, ping_delay,
                 range_from_delay, silhouette_class)
from tuning import DAMAGED_HYDROPHONES


MAX_ECHO_RANGE = 12000.0  # m; beyond this the return is lost in noise
DECOY_WIDTH = 14.0        # noisemaker cloud smears across ~30 deg of waterfall
HOSTILE_WIDTH = 0.8       # hostile fish: bright, narrow


def cone_gain(dial, bearings, cone=25.0):
    """0..1 hydrophone sensitivity per contact; 1 dead ahead of the dial, 0 past the cone."""
    delta = np.abs((bearings - dial + 180) % 360 - 180)
    return np.clip(1 - delta / cone, 0, 1) ** 2


# ---------- operator sensors: the only path from world truth to the console ----------
KIND_INDEX = {"MERCHANT": 0, "ESCORT": 1, "SUB": 2, "TORPEDO": 3, "DECOY": 4}


class PassiveSonar:
    """Relative bearings with noise, 0.5 deg resolution, 1/r spreading loss and thermocline loss."""

    def __init__(self, world, beam_width=1.5, noise_deg=0.8, resolution=0.5):
        self.world, self.beam_width, self.noise_deg, self.resolution = world, beam_width, noise_deg, resolution

    def listen(self):
        """Returns (rel_bearings, levels, waterfall widths, spectral family index, hostile-fish flags)."""
        p, ocean = self.world.player, self.world.ocean
        sources = [*self.world.targets, *self.world.torpedoes]
        if not sources:
            return np.empty(0), np.empty(0), np.empty(0), np.empty(0, int), np.empty(0, bool)
        src = np.array([(s.x, s.y, s.noise * ocean.transmission(p, s) * (1.5 if getattr(s, "hostile", False) else 1.0),
                         DECOY_WIDTH if isinstance(s, Decoy) else HOSTILE_WIDTH if getattr(s, "hostile", False)
                         else self.beam_width, KIND_INDEX.get(s.kind, 0), getattr(s, "hostile", False))
                        for s in sources])
        dx, dy = src[:, 0] - p.x, src[:, 1] - p.y
        rel = np.degrees(np.arctan2(dx, dy)) - p.heading + np.random.normal(0, self.noise_deg, len(src))
        rel = (np.round(rel / self.resolution) * self.resolution) % 360
        rng = np.maximum(np.hypot(dx, dy), 1.0)
        level = 160 * src[:, 2] * np.minimum(1.0, 3000 / rng) * np.random.uniform(0.75, 1.0, len(src))
        if "HYDROPHONES" in getattr(p, "damaged", ()):
            level *= DAMAGED_HYDROPHONES
        return rel, level, src[:, 3], src[:, 4].astype(int), src[:, 5].astype(bool)

    def bearing_of(self, source):
        """Noisy relative bearing of a transient (detonation, splash, ping)."""
        p = self.world.player
        return (bearing(p.x, p.y, source.x, source.y) - p.heading + random.gauss(0, self.noise_deg)) % 360

    def loudness(self, source, ref=3000.0):
        """0..1 how loud a transient at source sounds here."""
        p = self.world.player
        return min(1.0, ref / max(p.range_to(source), 1.0)) * self.world.ocean.transmission(p, source)


class ActiveSonar:
    """Ping now, echoes arrive after 2d/c. Operator only ever sees bearing + delay-derived range.
    Contacts across the layer sit in its shadow and return nothing; the layer itself returns reverb."""

    def __init__(self, world, noise_deg=1.5, timing_jitter=0.01):
        self.world, self.noise_deg, self.timing_jitter = world, noise_deg, timing_jitter
        self.clock = 0.0
        self.pending = []  # (arrival_time, rel_bearing or None for layer reverb, measured_delay)

    def ping(self):
        self.world.emit_ping()
        p, ocean = self.world.player, self.world.ocean
        for t in self.world.targets:
            r = p.range_to(t)
            if r <= MAX_ECHO_RANGE and not ocean.crosses_layer(p, t):
                rel = (bearing(p.x, p.y, t.x, t.y) - p.heading + random.gauss(0, self.noise_deg)) % 360
                delay = ping_delay(r)
                self.pending.append((self.clock + delay, rel, delay + random.gauss(0, self.timing_jitter)))
        layer = ping_delay(abs(ocean.layer_depth - p.z))
        self.pending.append((self.clock + layer, None, layer))

    def update(self, dt):
        """Returns [(rel_bearing or None, range_m)] for echoes arriving this frame."""
        self.clock += dt
        arrived = [(b, range_from_delay(d)) for at, b, d in self.pending if at <= self.clock]
        self.pending = [e for e in self.pending if e[0] > self.clock]
        return arrived


# ---------- periscope optics: the only path from the surface picture to the eyepiece ----------
SCOPE_FOV = {False: 32.0, True: 8.0}  # deg across the eyepiece: low power 1.5x, high power 6x
SCOPE_TRAIN_RATE = {False: 40.0, True: 12.0}  # deg/s on A/D
WAKE_SEEN = 2500.0                    # m, a torpedo's bubble track is visible this far
WRECK_TIME = 240.0                    # s a sinking ship stays on the surface picture

Sighting = namedtuple("Sighting", "uid cls brg rng aspect speed height drop sinking lamp")
Wake = namedtuple("Wake", "brg rng heading")
Burst = namedtuple("Burst", "kind brg rng age")



class PeriscopeOptics:
    """What an eye ~1.5 m above the waves can see: limited by weather, the horizon (hull-down) and the lens
    being under a wave. Bearings are far better than sonar's; range comes from the rangefinder."""

    def __init__(self, world):
        self.world = world

    def eye_height(self):
        p = self.world.player
        return max(0.3, SCOPE_TOP - p.z - p.wave)

    def look(self):
        """(sightings, wakes, bursts), or None when the scope is down or the lens is under a wave."""
        w, p = self.world, self.world.player
        if not (getattr(p, "scope_up", False) and p.scope_clear):
            return None
        vis, d_h = w.ocean.visibility, horizon_distance(self.eye_height())
        sightings = []
        wrecks = [t for t in w.sunk if w.time - t.sunk_at < WRECK_TIME]
        for t in [s for s in w.targets if s.kind in ("MERCHANT", "ESCORT")] + wrecks:
            r = p.range_to(t)
            cls = silhouette_class(t)
            height = SHIP_CLASSES[cls][2]
            drop = max(0.0, r - d_h) ** 2 / (2 * R_EFF)  # hull-down: this much of her is below our horizon
            if r > vis or drop >= height:
                continue
            brg = bearing(p.x, p.y, t.x, t.y)
            sightings.append(Sighting(id(t), cls, (brg + random.gauss(0, 0.1)) % 360, r,
                                      angle_diff(t.heading, (brg + 180) % 360), t.speed, height, drop,
                                      w.time - t.sunk_at if t.sunk_at >= 0 else -1.0, t.signal_until > w.time))
        wakes = [Wake(bearing(p.x, p.y, t.x, t.y), p.range_to(t), t.heading) for t in w.torpedoes
                 if t.z < 25 and p.range_to(t) < min(WAKE_SEEN, vis)]
        bursts = [Burst(k, bearing(p.x, p.y, x, y), math.hypot(x - p.x, y - p.y), w.time - t0)
                  for k, x, y, t0 in w.effects if math.hypot(x - p.x, y - p.y) < vis]
        return sightings, wakes, bursts

    @staticmethod
    def rangefinder(sighting, high_power):
        """Known mast height over its angular height: good at high power, rough at low."""
        return sighting.rng * (1 + random.gauss(0, 0.03 if high_power else 0.08))
