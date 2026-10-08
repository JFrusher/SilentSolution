"""World simulation: hidden true state. Units: metres, seconds, m/s.
Bearings/headings are degrees clockwise from north; x = east, y = north; z = depth, positive down."""
import itertools
import math
import random
from dataclasses import dataclass, field
from typing import Any

import numpy as np

import geometry
from geometry import angle_diff, bearing  # re-exported: the rest of the code imports them from here
from tuning import (
    CHARGE_LETHAL,
    CHARGE_REACH,
    DAMAGED_BATTERY,
    DAMAGED_MOTOR_KT,
    DAMAGED_PLANES,
    DAMAGED_RUDDER,
    REPAIR_TIME,
    SPOT_BASE,
    SPOT_REACH,
    WIRE_LENGTH,
)

SOUND_SPEED = 1500.0  # m/s
KNOT = 0.514444       # m/s
YARD = 0.9144         # m
TORP_SPEED = 35 * KNOT
TORP_MAX_RUN = 6000 * YARD
HIT_RADIUS = 25 * YARD
HIT_DEPTH = 25.0         # m of vertical miss that still detonates
TORP_DIVE_RATE = 4.0     # m/s

LAYER_DEPTH = 100.0      # m, thermocline
LAYER_LOSS = 0.3         # fraction of sound energy that crosses the layer
SNORKEL_DEPTH = 15.0     # m, diesels can breathe here
CRUSH_DEPTH = 250.0      # m, hull starts to fail below this
MAX_DEPTH = 300.0        # m, deepest order the planesman accepts
DIVE_RATE = 1.5          # m/s on the planes
BLOW_RATE = 5.0          # m/s emergency blow
ACCEL = 0.15             # m/s^2, own boat
MAX_RUDDER = 30.0        # deg
TURN_RATE = 3.5          # deg/s at full rudder with steerage way
CHARGE_SINK_RATE = 4.0   # m/s
LEAK_SINK = 0.2          # m/s of extra weight per leak
LEAK_HULL = 0.02         # % hull per second per leak
LEAK_REPAIR = 60.0       # s for damage control to plug one

# masts: depths are own keel depth z
PERISCOPE_DEPTH = 15.0   # m, what the "periscope depth" order means
MAST_DEPTH = 18.0        # m, deepest a mast can be raised
SCOPE_TOP = 17.0         # m above the keel: the scope head clears the water by SCOPE_TOP - z - wave
SNORKEL_TOP = 16.5       # m above the keel: snorkel head valve
BROACH_DEPTH = 13.0      # m, shallower and the tower is awash
MIN_ORDER_DEPTH = 10.0   # m, shallowest depth the planesman will take her
AUTO_LOWER_DEPTH = 20.0  # m, ordering deeper than this strikes the masts
FEATHER_KT = 6.0         # kt, scope up faster than this throws a feather
SCOPE_DAMAGE_KT = 10.0   # kt, scope up faster than this can bend it (if the difficulty says so)
SNORKEL_FLOOD_KT = 8.0   # kt, snorkel head floods faster than this
DIESEL_TRIP = 10.0       # s the diesels stay stalled after the snorkel floods
WIRE_MAX_KT = 12.0       # kt; faster than this and the wire parts
R_EFF = 7.6e6            # m, effective earth radius with refraction (hull-down maths)

# being seen: per-second chance at zero range for an alertness-1 observer, and how far it can reach in clear air

UIDS = itertools.count(1)
TELEGRAPH = (("STOP", 0.0), ("SLOW", 4.0), ("HALF", 8.0), ("FULL", 14.0), ("FLANK", 20.0))  # order, knots


# ship families as a lookout or recognition manual knows them: (length, beam, mast top, freeboard) m
SHIP_CLASSES = {
    "merchant": (130.0, 17.0, 30.0, 8.0),
    "tanker": (150.0, 20.0, 26.0, 6.0),
    "escort": (95.0, 11.0, 24.0, 5.0),
}
def silhouette_class(ship):
    if ship.kind == "ESCORT":
        return "escort"
    return "tanker" if ship.uid % 3 == 0 else "merchant"  # uid, not id(): same ship, same class, every run


# torpedo lifecycle
RUNNING, ACQUIRING, HOMING, EXHAUSTED = "RUNNING", "ACQUIRING", "HOMING", "EXHAUSTED"


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def ping_delay(distance):
    return 2 * distance / SOUND_SPEED


def range_from_delay(delay):
    return delay * SOUND_SPEED / 2


def intercept(los, rng, course, speed, torp_speed):
    """Straight-run collision course: sin(lead) = v_target / v_torp * sin(target angle off the line of sight).
    Returns (gyro, lead, time) or None when the torpedo can't catch it."""
    angle = math.radians(course - los)
    k = speed / torp_speed * math.sin(angle)
    if abs(k) > 1:
        return None
    lead = math.asin(k)
    closing = torp_speed * math.cos(lead) - speed * math.cos(angle)
    if closing <= 0:
        return None
    return (los + math.degrees(lead)) % 360, math.degrees(lead), rng / closing


def horizon_distance(eye_height):
    """m to the sea horizon for an eye `eye_height` m above the water."""
    return math.sqrt(2 * R_EFF * max(eye_height, 0.05))


def spot_probability(exposed, speed_kt, rng, visibility, sea_state, alertness=1.0):
    """Chance per second that one lookout sees what we are showing above the water.
    exposed: None / 'scope' / 'snorkel' / 'both' / 'broach'. Shared by the AI (truth) and the
    exposure meter (own estimate), so the warning and the danger are the same maths."""
    if not exposed:
        return 0.0
    reach = SPOT_REACH[exposed] * visibility / 12000.0
    near = clamp(1 - rng / reach, 0.0, 1.0) ** 2
    feather = 1 + (speed_kt / 4) ** 2 if exposed in ("scope", "both") else 1 + (speed_kt / 8) ** 2
    return min(1.0, SPOT_BASE[exposed] * feather * alertness * near / (1 + 0.5 * sea_state))


@dataclass(eq=False)
class Vessel:
    x: float
    y: float
    heading: float  # deg
    speed: float    # m/s
    noise: float = 1.0  # radiated acoustic signature, 1.0 = typical merchant
    decoys: int = 0     # noisemakers carried
    z: float = 0.0      # depth, m
    kind: str = "MERCHANT"  # acoustic signature family: MERCHANT ESCORT SUB TORPEDO DECOY OWN
    sunk_at: float = -1.0       # world time it was sunk (wrecks settle visibly for a while)
    signal_until: float = -1.0  # an escort that has spotted us flashes its signal lamp until then
    uid: int = field(default_factory=lambda: next(UIDS))  # stable identity for the after-action replay

    def velocity(self):
        return geometry.velocity(self)

    def step(self, dt):
        vx, vy = self.velocity()
        self.x += vx * dt
        self.y += vy * dt

    def range_to(self, other):
        """Horizontal range: navigation, lookouts, plotting."""
        return geometry.horizontal(self, other)

    def slant_to(self, other):
        """3D range: what sound and seekers travel."""
        return geometry.slant(self, other)


@dataclass(eq=False)
class Submarine(Vessel):
    """Own boat. Helm orders depth, speed and rudder; the boat answers at finite rates.
    Self-noise comes from speed, cavitation, the snorkel diesel and blowing ballast."""
    kind: str = "OWN"
    uses_battery: bool = True
    uses_oxygen: bool = False
    torpedoes: int = 8    # reloads in the racks
    noisemakers: int = 4
    ordered_depth: float = field(init=False)
    ordered_speed: float = field(init=False)
    rudder: float = 0.0
    battery: float = 100.0
    o2: float = 100.0
    blowing: bool = False
    cavitating: bool = False
    snorkeling: bool = False   # diesels running on the snorkel
    leaks: list = field(default_factory=list)  # seconds until each is plugged
    # masts
    mast_damage: bool = False  # difficulty: speed can bend a raised scope
    lower_delay: float = 0.0   # difficulty: seconds to strike masts once ordered deep
    scope_up: bool = False
    snorkel_up: bool = False
    diesel_trip: float = 0.0   # s the diesels stay stalled
    head_valve: bool = False   # snorkel head shut by a wave
    scope_clear: bool = False  # scope head out of the water right now
    snorkel_clear: bool = False
    wave: float = 0.0          # sea surface elevation over the boat, m
    lowering: float = -1.0     # countdown while the masts are being struck
    alerts: list = field(default_factory=list)  # own-ship events for the world to report: kind or (kind, detail)
    damaged: dict = field(default_factory=dict)  # system -> s of repair left, in the party's work order
    quiet: float = 1.0  # refit: self-noise multiplier

    def __post_init__(self):
        self.ordered_depth, self.ordered_speed = self.z, self.speed
        self.noise = 0.25 + 0.035 * self.speed / KNOT  # real self-noise from the first tick, not the generic 1.0

    @property
    def broached(self):
        return self.z < BROACH_DEPTH

    @property
    def exposed(self):
        """What a lookout could see above the water: None, 'scope', 'snorkel', 'both' or 'broach'."""
        if self.broached:
            return "broach"
        scope = self.scope_up and self.scope_clear
        snort = self.snorkel_up and (self.snorkel_clear or self.snorkeling)  # exhaust smoke too
        return "both" if scope and snort else "scope" if scope else "snorkel" if snort else None

    def raise_mast(self, mast):
        """Returns why not, or None when the mast goes up."""
        if self.z > MAST_DEPTH:
            return "TOO DEEP FOR MASTS"
        if mast == "scope":
            if "PERISCOPE" in self.damaged:
                return "PERISCOPE JAMMED"
            self.scope_up = True
        else:
            if "SNORKEL" in self.damaged:
                return "SNORKEL DAMAGED"
            self.snorkel_up = True
        return None

    def break_systems(self, names):
        for name in names:
            self.damaged.setdefault(name, REPAIR_TIME[name])
        self.scope_up = self.scope_up and "PERISCOPE" not in self.damaged
        self.snorkel_up = self.snorkel_up and "SNORKEL" not in self.damaged

    def repair_first(self, name):
        """Send the damage-control party to `name` next."""
        if name in self.damaged:
            self.damaged = {name: self.damaged.pop(name), **self.damaged}

    def _repair(self, dt):
        if self.damaged:
            first = next(iter(self.damaged))
            self.damaged[first] -= dt
            if self.damaged[first] <= 0:
                del self.damaged[first]
                self.alerts.append(("REPAIRED", first))

    def lower_masts(self):
        self.scope_up = self.snorkel_up = False
        self.lowering = -1.0

    def sense_surface(self, ocean, t):
        """Where the waves are against the mast heads this instant."""
        self.wave = float(ocean.surface(self.x, self.y, t))
        self.scope_clear = SCOPE_TOP - self.z - self.wave > 0.2
        self.snorkel_clear = SNORKEL_TOP - self.z - self.wave > 0.3

    def _masts(self, dt, kt):
        if self.scope_up or self.snorkel_up:
            if self.ordered_depth > AUTO_LOWER_DEPTH or self.z > MAST_DEPTH + 1:
                if self.lowering < 0:
                    self.lowering = self.lower_delay
            if self.lowering >= 0:
                self.lowering -= dt
                if self.lowering <= 0:
                    self.lower_masts()
                    self.alerts.append("MASTS_LOWERED")
        if self.scope_up and self.mast_damage and kt > SCOPE_DAMAGE_KT:
            self.break_systems(["PERISCOPE"])
            self.alerts.append("SCOPE_DAMAGED")
        if self.snorkel_up and kt > SNORKEL_FLOOD_KT and self.diesel_trip <= 0:
            self.diesel_trip = DIESEL_TRIP
            self.alerts.append("SNORKEL_FLOODED")
        self.diesel_trip = max(0.0, self.diesel_trip - dt)
        shut = self.snorkel_up and not self.snorkel_clear
        if shut and not self.head_valve:
            self.alerts.append("HEAD_VALVE")
        self.head_valve = shut
        self.snorkeling = self.snorkel_up and self.snorkel_clear and self.diesel_trip <= 0

    def step(self, dt):
        kt = self.speed / KNOT
        self.cavitating = kt > 8 + self.z / 15  # pressure suppresses cavitation: deeper boats can run faster quietly
        self._masts(dt, kt)
        self._repair(dt)
        hurt = self.damaged
        if self.uses_battery:
            drain = (0.005 + 0.0006 * kt * kt) * (DAMAGED_BATTERY if "BATTERY" in hurt else 1.0)
            self.battery = max(0.0, self.battery - drain * dt)
            if self.snorkeling:
                self.battery = min(100.0, self.battery + 0.35 * dt)
        if self.uses_oxygen:
            fresh = self.snorkeling or self.broached
            self.o2 = min(100.0, self.o2 + dt) if fresh else max(0.0, self.o2 - 100 / 1200 * dt)

        dv = ACCEL * dt
        top = DAMAGED_MOTOR_KT * KNOT if "MOTORS" in hurt else math.inf
        self.speed += clamp((min(self.ordered_speed, top) if self.battery > 0 else 0.0) - self.speed, -dv, dv)
        if self.blowing:
            self.z = max(PERISCOPE_DEPTH, self.z - BLOW_RATE * dt)
            if self.z <= PERISCOPE_DEPTH:
                self.blowing, self.ordered_depth = False, PERISCOPE_DEPTH
        else:
            rate = DIVE_RATE * (DAMAGED_PLANES if "PLANES" in hurt else 1.0) * dt
            self.z += clamp(self.ordered_depth - self.z, -rate, rate)
        self.z = clamp(self.z + len(self.leaks) * LEAK_SINK * dt, 0.0, 400.0)  # flooding makes her heavy
        steerage = min(1.0, self.speed / (4 * KNOT)) * (DAMAGED_RUDDER if "RUDDER" in hurt else 1.0)
        self.heading = (self.heading + self.rudder / MAX_RUDDER * TURN_RATE * steerage * dt) % 360
        self.leaks = [t - dt for t in self.leaks if t > dt]  # damage control works through them
        self.noise = self.quiet * (0.25 + 0.035 * kt + 0.9 * self.cavitating + 0.8 * self.snorkeling
                                   + 1.5 * self.blowing)
        super().step(dt)


@dataclass(eq=False)
class Decoy(Vessel):
    kind: str = "DECOY"
    ttl: float = 60.0      # s of noisemaking before it goes quiet
    owner: str = "ENEMY"   # PLAYER decoys bait hostile torpedoes, ENEMY decoys bait ours

    def step(self, dt):
        super().step(dt)
        self.ttl -= dt


@dataclass(eq=False)
class DepthCharge(Vessel):
    kind: str = "CHARGE"
    set_depth: float = 100.0

    def step(self, dt):
        self.z += CHARGE_SINK_RATE * dt


@dataclass(eq=False)
class Torpedo(Vessel):
    noise: float = 1.2
    kind: str = "TORPEDO"
    hostile: bool = False
    max_run: float = TORP_MAX_RUN
    arm_distance: float = 1000 * YARD  # run before the seeker switches on
    seeker_range: float = 1000 * YARD  # 0 = straight runner
    seeker_half_arc: float = 45.0      # deg either side of the nose; must exceed the lead angle to see the target
    turn_rate: float = 25.0            # deg/s
    run_depth: float = 10.0            # m; homing overrides with the target's depth
    tube: int = 0
    run: float = 0.0
    state: str = RUNNING
    lock: Vessel | None = None
    wired: bool = False                # still on the guidance wire: we can steer it
    wire_aim: tuple | None = None      # (x, y) the wire is steering it toward
    ox: float = field(init=False)  # launch point: escorts back-plot the track to it
    oy: float = field(init=False)

    def __post_init__(self):
        self.ox, self.oy = self.x, self.y

    def step(self, dt):
        super().step(dt)
        self.z += clamp(self.run_depth - self.z, -TORP_DIVE_RATE * dt, TORP_DIVE_RATE * dt)
        self.run += self.speed * dt

    def steer_to(self, x, y, dt):
        turn = angle_diff(bearing(self.x, self.y, x, y), self.heading)
        limit = self.turn_rate * dt
        self.heading = (self.heading + clamp(turn, -limit, limit)) % 360

    def hits(self, other):
        return self.range_to(other) <= HIT_RADIUS and abs(self.z - other.z) <= HIT_DEPTH

    def seek(self, contacts, ocean, dt):
        """Advance the seeker state machine. Returns an event name on a transition."""
        if self.state == RUNNING:
            if self.run < self.arm_distance:
                return None
            self.state = ACQUIRING
            return "ARMED"

        def heard(c):  # the layer bends the seeker's sound away too
            return ocean.transmission(self, c)

        in_cone = [c for c in contacts if self.slant_to(c) <= self.seeker_range * heard(c) and
                   abs(angle_diff(bearing(self.x, self.y, c.x, c.y), self.heading)) <= self.seeker_half_arc]

        def signal(c):
            return c.noise * heard(c) / max(self.slant_to(c), 1.0)
        best = max(in_cone, key=signal, default=None)
        if self.lock in in_cone and signal(best) < 1.5 * signal(self.lock):
            best = self.lock  # seeker holds its lock unless something clearly louder appears
        self.lock = best
        if self.lock is None:
            if self.state == HOMING:
                self.state = ACQUIRING
                return "LOST"
            return None
        self.run_depth = self.lock.z
        self.steer_to(self.lock.x, self.lock.y, dt)
        if self.state != HOMING:
            self.state = HOMING
            return "HOMING"
        return None


@dataclass(eq=False)
class Ocean:
    layer_depth: float = LAYER_DEPTH
    layer_loss: float = LAYER_LOSS
    rain: float = 0.0   # surface rain noise, 0 calm .. 1 storm
    front: float = 0.0  # rain level the current weather front is heading for
    timer: float = 0.0
    wind: float = 4.0        # m/s; sea follows the weather
    wind_dir: float = 240.0  # deg the swell runs toward
    swells: list = field(default_factory=list)  # (amplitude share, wavenumber, direction offset deg, phase)

    def __post_init__(self):
        if not self.swells:
            self.swells = [(a, 2 * math.pi / lam, off, random.uniform(0, 2 * math.pi))
                           for a, lam, off in ((0.55, 90.0, 0.0), (0.3, 45.0, 25.0), (0.15, 22.0, -35.0),
                                               (0.1, 11.0, 60.0))]

    def step(self, dt):
        self.timer -= dt
        if self.timer <= 0:
            self.timer = random.uniform(60, 180)
            self.front = random.choice((0.0, 0.0, 0.3, 0.6, 1.0))
        self.rain += (self.front - self.rain) * min(1.0, dt / 20)  # fronts roll in over ~20 s
        self.wind += (3.0 + 11.0 * self.rain - self.wind) * min(1.0, dt / 60)  # the sea builds slower than the rain

    @property
    def wave_height(self):
        """Significant wave height, m (fully developed sea for the wind)."""
        return 0.05 + 0.022 * self.wind ** 2

    @property
    def sea_state(self):
        return int(np.searchsorted((0.1, 0.5, 1.25, 2.5, 4.0, 6.0), self.wave_height))

    @property
    def visibility(self):
        """m; rain and spray close it right down."""
        return 12000.0 * (1 - 0.88 * self.rain)

    def surface(self, x, y, t):
        """Sea surface elevation, m (works on numpy arrays: the periscope renders the same sea the boat rides)."""
        h = self.wave_height / 2
        eta = 0.0
        for a, k, off, phase in self.swells:
            d = math.radians(self.wind_dir + off)
            eta = eta + a * h * np.sin(k * (x * math.sin(d) + y * math.cos(d)) - math.sqrt(9.81 * k) * t + phase)
        return eta

    def crosses_layer(self, a, b):
        return (a.z < self.layer_depth) != (b.z < self.layer_depth)

    def transmission(self, a, b):
        """Fraction of sound energy getting from a to b; the thermocline bends most of it away."""
        return self.layer_loss if self.crosses_layer(a, b) else 1.0


@dataclass(eq=False)
class WorldSimulation:
    player: Vessel
    targets: list  # ships and decoys: anything sonar can hear or a seeker can lock
    torpedoes: list = field(default_factory=list)
    charges: list = field(default_factory=list)
    ais: list = field(default_factory=list)  # ship behaviours: .update(world, dt) -> events, .hear_ping/.hear_launch
    director: Any = None                    # spawns waves: .update(world, dt) -> events
    ocean: Ocean = field(default_factory=Ocean)
    time: float = 0.0
    hull: float = 100.0  # own boat integrity, %
    min_hull: float = 0.0  # training floor: shaken, never sunk
    leaks_enabled: bool = False
    systems_damage: bool = False  # hits knock out own-boat systems for damage control to repair
    armour: float = 1.0  # refit: share of hit damage the hull takes
    torp_damage: float = 75.0
    spot_mult: float = 1.0  # difficulty: how sharp enemy lookouts are
    sunk: list = field(default_factory=list)
    effects: list = field(default_factory=list)  # (kind, x, y, time): what an eye on the surface would see go up

    def step(self, dt):
        """Advance dt seconds. Returns [(event, a, b)]."""
        self.time += dt
        self.ocean.step(dt)
        p = self.player
        if isinstance(p, Submarine):
            p.sense_surface(self.ocean, self.time)
        events = self.director.update(self, dt) if self.director else []
        events += [e for ai in self.ais for e in ai.update(self, dt)]
        for v in [self.player, *self.targets, *self.torpedoes, *self.charges]:
            v.step(dt)
        if isinstance(p, Submarine) and p.alerts:
            events += [(a, p, None) if isinstance(a, str) else (a[0], p, a[1]) for a in p.alerts]
            p.alerts.clear()
        self.effects = [e for e in self.effects if self.time - e[3] < 20]
        self.targets = [t for t in self.targets if not (isinstance(t, Decoy) and t.ttl <= 0)]

        ours = [t for t in self.targets if getattr(t, "owner", "") != "PLAYER"]
        theirs = [self.player] + [t for t in self.targets if getattr(t, "owner", "") == "PLAYER"]
        for torp in self.torpedoes[:]:
            contacts = theirs if torp.hostile else ours
            if torp.wired:  # wire guidance: steer toward the aim point until the seeker has something
                why = "LENGTH" if torp.run > WIRE_LENGTH else "SPEED" if p.speed > WIRE_MAX_KT * KNOT else None
                if why:
                    torp.wired, torp.wire_aim = False, None
                    events.append(("WIRE_CUT", torp, why))
                elif torp.wire_aim and torp.state != HOMING:
                    if math.hypot(torp.wire_aim[0] - torp.x, torp.wire_aim[1] - torp.y) < 60:
                        torp.wire_aim = None  # arrived: run on straight
                    else:
                        torp.steer_to(*torp.wire_aim, dt)
            ev = torp.seek(contacts, self.ocean, dt)
            if ev:
                events.append((ev, torp, torp.lock))
            hit = next((c for c in contacts if torp.hits(c)), None)
            if hit:
                self.torpedoes.remove(torp)
                if hit is self.player:
                    events.append(("PLAYER_HIT", torp, self.torp_damage))
                    self.damage(self.torp_damage, events)
                    self.explosion(hit.x, hit.y, False, None)
                    continue
                self.targets.remove(hit)
                if isinstance(hit, Decoy):
                    events.append(("DECOYED", torp, hit))
                else:
                    hit.sunk_at = self.time  # the wreck settles for a few minutes in the periscope
                    self.sunk.append(hit)
                    events.append(("HIT", torp, hit))
                self.explosion(hit.x, hit.y, not isinstance(hit, Decoy), torp)
            elif torp.run >= torp.max_run:
                torp.state = EXHAUSTED
                self.torpedoes.remove(torp)
                events.append((EXHAUSTED, torp, torp.lock))  # lock is a Decoy -> it was seduced, not a clean miss
        self.ais = [ai for ai in self.ais if ai.ship in self.targets]

        p = self.player
        for c in [c for c in self.charges if c.z >= c.set_depth]:
            self.charges.remove(c)
            d = c.slant_to(p)
            dmg = 100.0 if d < CHARGE_LETHAL else 60.0 * max(0.0, 1 - d / CHARGE_REACH) ** 2
            events.append(("CHARGE", c, dmg))
            self.damage(dmg, events)
            self.explosion(c.x, c.y, False, None)
        if p.z > CRUSH_DEPTH:
            self.hull = max(self.min_hull, self.hull - (p.z - CRUSH_DEPTH) / 50 * 1.5 * dt)
        self.hull = max(self.min_hull, self.hull - len(getattr(p, "leaks", ())) * LEAK_HULL * dt)
        return events

    def damage(self, dmg, events):
        dmg *= self.armour
        self.hull = max(self.min_hull, self.hull - dmg)
        p = self.player
        if self.systems_damage and dmg >= 8 and isinstance(p, Submarine):
            pool = [s for s in REPAIR_TIME if s not in p.damaged]
            hit = random.sample(pool, min(len(pool), 1 + int(dmg // 30)))
            p.break_systems(hit)
            if hit:
                events.append(("DAMAGE", p, hit))
        if self.leaks_enabled and dmg >= 8 and isinstance(self.player, Submarine):
            self.player.leaks.append(LEAK_REPAIR)
            events.append(("LEAK", self.player, len(self.player.leaks)))

    def fire(self, heading, speed=TORP_SPEED, **kw):
        p = self.player
        torp = Torpedo(p.x, p.y, heading, speed, z=p.z, **kw)
        self.torpedoes.append(torp)
        for ai in self.ais:
            ai.hear_launch(self)
        return torp

    def launch_hostile(self, shooter, heading, speed, **kw):
        torp = Torpedo(shooter.x, shooter.y, heading, speed, z=shooter.z, hostile=True, noise=1.4, **kw)
        self.torpedoes.append(torp)
        return torp

    def drop_noisemaker(self):
        """Own countermeasure: a bubble decoy left astern at our depth."""
        p = self.player
        h = math.radians(p.heading)
        self.targets.append(Decoy(p.x - 30 * math.sin(h), p.y - 30 * math.cos(h), 0, 0, noise=2.5, z=p.z, ttl=45.0,
                                  owner="PLAYER"))

    def explosion(self, x, y, sunk, torp):
        """Everyone in earshot hears it; a sinking (sunk=True) is what scatters convoys and starts searches."""
        self.effects.append(("BLAST" if torp else "COLUMN", x, y, self.time))
        for ai in self.ais:
            ai.hear_explosion(self, x, y, sunk, torp)

    def emit_ping(self):
        """Own active sonar transmission: loud, anyone in earshot hears where it came from."""
        for ai in self.ais:
            ai.hear_ping(self)
