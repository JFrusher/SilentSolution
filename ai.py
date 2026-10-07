"""Ship behaviour - civilian, escort and enemy submarine - plus convoys and the wave director.
World side: reads ground truth; the console only hears the results."""
import math
import random

from tuning import (ALARM_HEARING, BLIND_RANGE, CALM_TIME, DESPAWN_RANGE, EXPLOSION_HEARING, GIVE_UP,
                    LATE_DESPAWN_RANGE, LAUNCH_HEARING, LOOKOUT_ALERT, LOOKOUT_IDLE, LOOKOUT_MERCHANT, PING_HEARING,
                    PING_INTERVAL, RUN_OUT, SCATTER_RANGE, SCATTER_TIME, SEARCH_TIME, SONAR_RANGE, TONNAGE,
                    TORPEDO_HEARING, WAKE_SIGHTING, WAVE_GAP, WAVE_TIME_LIMIT)
from sim import (KNOT, LAYER_DEPTH, YARD, Decoy, DepthCharge, Vessel, angle_diff, bearing, clamp, intercept,
                 spot_probability)

# military states: unaware -> searching -> aware (hunting / attacking) / evading
PATROL, SEARCH, ALERT, ATTACK, EVADE = "PATROL", "SEARCH", "ALERT", "ATTACK", "EVADE"
# civilian states: unaware -> alarmed -> scattering
CRUISE, ALARMED, SCATTER = "CRUISE", "ALARMED", "SCATTER"

SHIP_ACCEL = 0.4          # m/s^2
ZIG_LEG, ZIG_ANGLE = 60.0, 30.0

# escorts
ESCORT_PATROL, ESCORT_FULL, SEARCH_SPEED = 8 * KNOT, 24 * KNOT, 15 * KNOT
DROP_RANGE = 100.0        # m from datum: roll charges
PATTERN = ((0, 0), (60, 0), (-60, 0), (0, 60), (0, -60))  # (along, across) charge offsets, m
SEARCH_LEG = 500.0        # m, first leg of the expanding square; grows each pair of legs

# merchants
CONVOY_ZIG, CONVOY_LEG = (0, 30, 0, -30), 90.0  # alarmed convoy zig-zag plan

# waves


def frame_point(x, y, course, along, across):
    """World point at (along, across) metres in a frame heading `course` from (x, y); across is to starboard."""
    h = math.radians(course)
    return x + along * math.sin(h) + across * math.cos(h), y + along * math.cos(h) - across * math.sin(h)


def steer_to_station(ship, sx, sy, course, speed, max_speed):
    """Aim a little ahead of a moving station point and trim revs on how far behind it we are."""
    ax, ay = frame_point(sx, sy, course, 400, 0)
    h = math.radians(course)
    behind = (sx - ship.x) * math.sin(h) + (sy - ship.y) * math.cos(h)
    return bearing(ship.x, ship.y, ax, ay), clamp(speed + 0.004 * behind, 0.3 * speed, max_speed)


class Convoy:
    """A merchant column and its escort screen: one course, one zig-zag plan, one alarm."""

    def __init__(self, course, speed):
        self.course, self.speed = course, speed
        self.merchants, self.escorts = [], []
        self.alarmed = self.scattered = False
        self.alarm_time = 0.0

    def formation(self, world):
        return [m for m in self.merchants if m.state != SCATTER and m.convoy is self and m.ship in world.targets]

    def guide(self, world):
        f = self.formation(world)
        return f[0] if f else None

    def heading(self, t):
        return (self.course + (CONVOY_ZIG[int(t // CONVOY_LEG) % len(CONVOY_ZIG)] if self.alarmed else 0)) % 360

    def top_speed(self, world):
        return min((m.max_speed for m in self.formation(world)), default=self.speed)

    def alarm(self, world, events, datum=None):
        """Ring up full revs and start the zig-zag plan; pass any sighting to the escorts."""
        self.alarm_time = world.time
        guide = self.guide(world)
        if not self.alarmed and guide:
            events.append(("CONVOY_ALARM", guide.ship, None))
        self.alarmed = True
        for m in self.formation(world):
            m.state = ALARMED
        if datum:
            for e in self.escorts:
                e.report_contact(datum)

    def calm(self, world, events):
        self.alarmed = False
        guide = self.guide(world)
        if guide:
            events.append(("CONVOY_CALM", guide.ship, None))
        for m in self.formation(world):
            m.state = CRUISE

    def scatter(self, world, events, x, y):
        """Every ship for herself: fan out away from the sinking."""
        members = self.formation(world)
        if self.scattered or not members:
            return
        self.scattered = self.alarmed = True
        events.append(("CONVOY_SCATTER", members[0].ship, None))
        for i, m in enumerate(members):
            m.scatter_from(x, y, i, len(members))


class ShipAI:
    """Senses and helm shared by every hull."""
    lookouts = True

    def __init__(self, ship, base_course, detect_radius=3000.0, layer_sensitivity=1.0, aggression=0.5,
                 turn_rate=3.0, zigzag=True, decoys=0, cavitation_instant=False):
        self.ship, self.base_course = ship, base_course
        self.detect_radius, self.layer_sensitivity, self.aggression = detect_radius, layer_sensitivity, aggression
        self.turn_rate, self.zigzag, self.decoys, self.cavitation_instant = turn_rate, zigzag, decoys, cavitation_instant
        self.state = PATROL
        self.datum = None             # (x, y, depth guess): where it thinks we are
        self.datum_vel = (0.0, 0.0)   # our motion, from successive fixes
        self.search_request = None    # indirect evidence (a sinking) worth investigating
        self.threat = None            # torpedo it is running from
        self.alarm = False
        self.pending = []             # events raised outside update() (hearing callbacks)
        self.clock = self.since_contact = self.listen_timer = self.mark_time = 0.0

    # --- senses ---
    def _trans(self, world, other):
        """Layer loss as this hull hears it: sensitivity 1 = full loss, 0 = its sonar ignores the layer."""
        return 1 - self.layer_sensitivity * (1 - world.ocean.transmission(self.ship, other))

    def _in_earshot(self, world, max_range):
        return self.ship.range_to(world.player) <= max_range * self._trans(world, world.player)

    def _mark(self, world, error):
        p = world.player
        new = (p.x + random.gauss(0, error), p.y + random.gauss(0, error), p.z + random.gauss(0, 25))
        gap = self.clock - self.mark_time
        if self.datum and 10 < gap < 120:
            self.datum_vel = ((new[0] - self.datum[0]) / gap, (new[1] - self.datum[1]) / gap)
        self.datum, self.mark_time, self.since_contact = new, self.clock, 0.0

    def _alertness(self):
        """How hard the lookouts are looking: unaware ships scan lazily, hunting ones sweep the sea."""
        return LOOKOUT_ALERT if self.state in (SEARCH, ALERT, ATTACK) else LOOKOUT_IDLE

    def _sighted(self, world):
        """Lookouts, checked once a second: a chance to see whatever we are showing above the water."""
        p, o = world.player, world.ocean
        exposed = getattr(p, "exposed", None)
        if not self.lookouts or not exposed:
            return False
        chance = spot_probability(exposed, p.speed / KNOT, self.ship.range_to(p), o.visibility, o.sea_state,
                                  self._alertness()) * world.spot_mult
        if random.random() >= chance:
            return False
        self.ship.signal_until = world.time + 25.0  # the bridge lamp starts flashing: visible through our scope
        self.pending.append(("SPOTTED", self.ship, exposed))
        return True

    def hear_ping(self, world):
        if self._in_earshot(world, PING_HEARING):
            self._mark(world, 0.1 * self.ship.range_to(world.player))
            self.alarm = True

    def hear_launch(self, world):
        if self._in_earshot(world, LAUNCH_HEARING):
            self._mark(world, 0.15 * self.ship.range_to(world.player))
            self.alarm = True

    def hear_explosion(self, world, x, y, sunk, torp):
        """A ship going up: back-plot the torpedo track to roughly where it was fired from."""
        if not sunk or math.hypot(x - self.ship.x, y - self.ship.y) > EXPLOSION_HEARING:
            return
        if torp is not None:
            err = 0.3 * torp.run
            self.search_request = (torp.ox + random.gauss(0, err), torp.oy + random.gauss(0, err), 60.0)
        else:
            self.search_request = (x, y, 60.0)

    def _listen(self, world, dt):
        """Once a second: passive (our self-noise against its detection radius) and lookouts."""
        self.listen_timer -= dt
        if self.listen_timer > 0:
            return
        self.listen_timer = 1.0
        p = world.player
        r = self.ship.range_to(p)
        heard = (self.cavitation_instant and getattr(p, "cavitating", False) and r < PING_HEARING) or \
            r <= self.detect_radius * p.noise * self._trans(world, p)
        if heard or self._sighted(world):
            self._mark(world, 80.0 if not heard else 0.1 * r)
            self.alarm = True

    def _incoming(self, world):
        s = self.ship
        return next((t for t in world.torpedoes if not t.hostile and
                     (t.lock is s or s.range_to(t) <= TORPEDO_HEARING * self._trans(world, t))), None)

    # --- actions ---
    def _set(self, state, events):
        if state != self.state:
            events.append(("AI_" + state, self.ship, self.state))
            self.state = state

    def _drop_decoy(self, world, events):
        s = self.ship
        if self.decoys:
            self.decoys -= 1
            world.targets.append(Decoy(s.x, s.y, 0, 0, noise=s.noise * random.uniform(1.5, 3.0), z=s.z))
            events.append(("DECOY_DROP", s, None))

    def _patrol_course(self):
        if not self.zigzag:
            return self.base_course
        return self.base_course + (ZIG_ANGLE if int(self.clock // ZIG_LEG) % 2 else -ZIG_ANGLE)

    def _helm(self, desired, speed, dt):
        s, limit = self.ship, self.turn_rate * dt
        s.heading = (s.heading + clamp(angle_diff(desired, s.heading), -limit, limit)) % 360
        s.speed += clamp(speed - s.speed, -SHIP_ACCEL * dt, SHIP_ACCEL * dt)


class MerchantAI(ShipAI):
    """Civilian: CRUISE (unaware: steady course, keeping station) -> ALARMED (full revs, zig-zag plan)
    -> SCATTER (a ship has gone: fan out at full speed, then sail on alone)."""

    def __init__(self, ship, convoy=None, offset=(0.0, 0.0), max_speed=13 * KNOT):
        super().__init__(ship, ship.heading, detect_radius=0.0, turn_rate=2.0, zigzag=False)
        self.convoy, self.offset, self.max_speed = convoy, offset, max_speed
        self.cruise, self.base_noise = ship.speed, ship.noise
        self.state = CRUISE
        self.timer = self.calm_at = 0.0
        self.wake = None
        ship.kind = "MERCHANT"
        if convoy:
            convoy.merchants.append(self)

    def _alertness(self):
        return LOOKOUT_MERCHANT * (1.5 if self.state != CRUISE else 1.0)

    def scatter_from(self, x, y, index, count):
        fan = (index - (count - 1) / 2) * 35 + random.uniform(-20, 20)
        self.base_course = (bearing(x, y, self.ship.x, self.ship.y) + fan) % 360
        self.timer = random.uniform(*SCATTER_TIME)
        self.state = SCATTER

    def _raise(self, world, datum=None):
        self.calm_at = world.time + CALM_TIME
        if self.convoy and self.state != SCATTER:
            self.convoy.alarm(world, self.pending, datum)
        elif self.state == CRUISE:
            self._set(ALARMED, self.pending)

    def hear_ping(self, world):
        if self.ship.range_to(world.player) <= ALARM_HEARING * world.ocean.transmission(self.ship, world.player):
            self._raise(world)

    def hear_launch(self, world):
        if self.ship.range_to(world.player) <= LAUNCH_HEARING / 2:
            self._raise(world)

    def hear_explosion(self, world, x, y, sunk, torp):
        if self.ship not in world.targets or math.hypot(x - self.ship.x, y - self.ship.y) > SCATTER_RANGE:
            return  # (the ship going down doesn't get a say)
        if not sunk:
            self._raise(world)
        elif self.convoy and self.state != SCATTER:
            self.convoy.scatter(world, self.pending, x, y)
        elif self.state != SCATTER:
            self.scatter_from(x, y, 0, 1)
            self.pending.append(("AI_SCATTER", self.ship, ALARMED))

    def update(self, world, dt):
        s, events, self.pending = self.ship, self.pending, []
        self.clock += dt
        self.listen_timer -= dt
        if self.listen_timer <= 0:
            self.listen_timer = 1.0
            if self._sighted(world):
                self._mark(world, 50.0)
                self._raise(world, self.datum)
            wake = next((t for t in world.torpedoes if not t.hostile and
                         s.range_to(t) <= WAKE_SIGHTING * (1 - 0.6 * world.ocean.rain)), None)
            if wake:
                self.wake = wake
                self._raise(world)
        events += self.pending
        self.pending = []

        conv = self.convoy
        guide = conv.guide(world) if conv else None
        if self.state == SCATTER:
            self.timer -= dt
            desired = self.base_course + (40 if int(self.clock // 45) % 2 else -40)
            speed = self.max_speed
            if self.timer <= 0:  # far enough: settle on an independent zig-zag
                self.convoy, self.calm_at = None, world.time + CALM_TIME
                self._set(ALARMED, events)
        elif guide is self:
            desired = conv.heading(world.time)
            speed = conv.top_speed(world) if conv.alarmed else conv.speed
            if conv.alarmed and not conv.scattered and world.time > conv.alarm_time + CALM_TIME:
                conv.calm(world, events)
        elif guide:
            g = guide.ship
            sx, sy = frame_point(g.x, g.y, g.heading, self.offset[0] - guide.offset[0], self.offset[1] - guide.offset[1])
            desired, speed = steer_to_station(s, sx, sy, g.heading, g.speed, self.max_speed)
        else:  # independent
            alarmed = self.state == ALARMED
            desired = self.base_course + ((ZIG_ANGLE if int(self.clock // ZIG_LEG) % 2 else -ZIG_ANGLE) if alarmed else 0)
            speed = self.max_speed if alarmed else self.cruise
            if alarmed and world.time > self.calm_at:
                self._set(CRUISE, events)
        if self.wake in world.torpedoes and s.range_to(self.wake) < 600:  # wake close aboard: comb the track
            desired, speed = self.wake.heading, self.max_speed

        self._helm(desired, speed, dt)
        s.noise = self.base_noise * (0.6 + 0.6 * s.speed / self.max_speed)  # revs up = louder on the waterfall
        return events


class EscortAI(ShipAI):
    """Surface escort. Unaware: PATROL its screening station. Suspicious: SEARCH an expanding square round a
    datum, pinging. Aware: ALERT run in on a held contact -> ATTACK depth-charge run. EVADE torpedoes."""

    def __init__(self, ship, base_course, charges=15, convoy=None, station=(1000.0, 0.0), **kw):
        kw.setdefault("decoys", ship.decoys)
        super().__init__(ship, base_course, **kw)
        self.charges, self.convoy, self.station = charges, convoy, station
        self.attack_start = 1000 + 1000 * self.aggression  # m from datum: commit to the run
        self.ping_timer = self.run_out = 0.0
        self.waypoints, self.search_until = [], math.inf
        ship.kind, ship.speed = "ESCORT", ESCORT_PATROL
        if convoy:
            convoy.escorts.append(self)

    def report_contact(self, datum):
        """A merchant's lookouts saw something."""
        if self.state in (PATROL, SEARCH):
            self.datum, self.since_contact, self.alarm = datum, 0.0, True

    def update(self, world, dt):
        s, events, self.pending = self.ship, self.pending, []
        self.clock += dt
        self.run_out = max(0.0, self.run_out - dt)
        self._listen(world, dt)

        threat = self._incoming(world)
        if threat and threat is not self.threat:  # new fish in the water: noisemaker over the side and run
            self.threat = threat
            if self.datum is None or self.since_contact > 30:  # no fresh contact: back-plot the fish's track
                err = 0.3 * threat.run
                self.datum = (threat.ox + random.gauss(0, err), threat.oy + random.gauss(0, err), threat.z)
            self._set(EVADE, events)
            self._drop_decoy(world, events)
        if self.state == EVADE and self.threat not in world.torpedoes:
            if self.mark_time and self.clock - self.mark_time <= 30:  # held us by sonar/sight just before: resume
                self._set(ALERT, events)
            else:
                self._begin_search(self.datum, events)
        if self.alarm and self.state in (PATROL, SEARCH):
            self._set(ALERT, events)
            if self.convoy:  # warn the convoy and the rest of the screen
                self.convoy.alarm(world, events, self.datum)
        elif self.search_request and self.state == PATROL:
            self._begin_search(self.search_request, events)
        self.alarm, self.search_request = False, None

        if self.state == PATROL:
            desired, speed = self._screen(world)
        elif self.state == SEARCH:
            desired, speed = self._search(world, dt, events)
        elif self.state == EVADE:
            desired, speed = bearing(self.threat.x, self.threat.y, s.x, s.y), ESCORT_FULL
        else:  # ALERT / ATTACK: run in on the datum
            dx, dy, dz = self.datum
            dist = math.hypot(dx - s.x, dy - s.y)
            desired = s.heading if self.run_out else bearing(s.x, s.y, dx, dy)
            speed = ESCORT_FULL
            if self.state == ALERT or dist > BLIND_RANGE:
                self._ping(world, dt, events)
            if self.state == ALERT:
                if dist < SONAR_RANGE:  # only counts once it is out there, not while transiting
                    self.since_contact += dt
                if self.since_contact > GIVE_UP:
                    self._begin_search(self.datum, events)  # lost it: search round the last datum
                elif dist < self.attack_start and self.charges >= len(PATTERN) and not self.run_out:
                    self._set(ATTACK, events)
            elif dist < DROP_RANGE:
                self._drop_pattern(world, dz)
                events.append(("CHARGES", s, None))
                self.run_out = RUN_OUT
                self._set(ALERT, events)

        self._helm(desired, speed, dt)
        s.noise = 0.4 + 1.4 * s.speed / ESCORT_FULL  # 8 kt ~0.9, flank 1.8
        return events

    def _ping(self, world, dt, events):
        self.ping_timer -= dt
        if self.ping_timer > 0:
            return
        self.ping_timer = PING_INTERVAL
        held = self._in_earshot(world, SONAR_RANGE)
        if held:
            self._mark(world, 30.0)
            self.alarm = True
        events.append(("ESCORT_PING", self.ship, held))

    def _screen(self, world):
        """Hold a screening station on the convoy guide, weaving across it; alone, zig-zag the base course."""
        guide = self.convoy.guide(world) if self.convoy else None
        if guide is None:
            return self._patrol_course(), ESCORT_PATROL
        g = guide.ship
        weave = 300 * math.sin(self.clock / 40)
        sx, sy = frame_point(g.x, g.y, g.heading, self.station[0] - guide.offset[0],
                             self.station[1] - guide.offset[1] + weave)
        return steer_to_station(self.ship, sx, sy, g.heading, max(g.speed, ESCORT_PATROL * 0.8), 18 * KNOT)

    def _begin_search(self, datum, events):
        """Expanding square round the datum: legs of 1, 1, 2, 2, 3, 3 ... x SEARCH_LEG."""
        self.datum = datum
        x, y = datum[0], datum[1]
        self.waypoints = [(x, y)]
        for k, (ux, uy) in enumerate(((0, 1), (1, 0), (0, -1), (-1, 0)) * 3):
            leg = SEARCH_LEG * (k // 2 + 1)
            x, y = x + ux * leg, y + uy * leg
            self.waypoints.append((x, y))
        self.search_until, self.since_contact = math.inf, 0.0
        self._set(SEARCH, events)

    def _search(self, world, dt, events):
        s = self.ship
        if self.waypoints and math.hypot(self.waypoints[0][0] - s.x, self.waypoints[0][1] - s.y) < 150:
            self.waypoints.pop(0)
            if self.search_until == math.inf:  # on the datum: the clock starts now
                self.search_until = self.clock + SEARCH_TIME
        if not self.waypoints or self.clock > self.search_until:
            self._set(PATROL, events)
            return self._screen(world)
        self._ping(world, dt, events)
        wx, wy = self.waypoints[0]
        return bearing(s.x, s.y, wx, wy), SEARCH_SPEED

    def _drop_pattern(self, world, depth_guess):
        s = self.ship
        for along, across in PATTERN:
            x, y = frame_point(s.x, s.y, s.heading, along, across)
            world.effects.append(("SPLASH", x, y, world.time))
            world.charges.append(DepthCharge(x, y, 0, 0, noise=0.0, set_depth=max(10.0, depth_guess + random.gauss(0, 15))))
        self.charges -= len(PATTERN)


class SubmarineAI(ShipAI):
    """Enemy boat: quiet PATROL -> ALERT stalk to firing range (also to investigate a nearby sinking)
    -> ATTACK (return fire, reload) -> EVADE (noisemaker, sprint, duck across the layer)."""
    lookouts = False  # deep boats see nothing

    def __init__(self, ship, base_course, stealth=0.4, top_speed=16 * KNOT, torpedo_speed=40 * KNOT,
                 seeker_range=600 * YARD, torpedoes=4, **kw):
        super().__init__(ship, base_course, **kw)
        self.stealth, self.top_speed, self.cruise = stealth, top_speed, 4 * KNOT
        self.torpedo_speed, self.seeker_range, self.torpedoes = torpedo_speed, seeker_range, torpedoes
        self.fire_range = 2500 + 3000 * self.aggression
        self.reload = 0.0
        self.depth_order = ship.z
        ship.kind, ship.speed, ship.noise = "SUB", self.cruise, stealth

    def update(self, world, dt):
        s, events, self.pending = self.ship, self.pending, []
        self.clock += dt
        self.since_contact += dt
        self.reload = max(0.0, self.reload - dt)
        self._listen(world, dt)

        threat = self._incoming(world)
        if threat and threat is not self.threat:
            self.threat = threat
            self._set(EVADE, events)
            self._drop_decoy(world, events)
            if random.random() < self.layer_sensitivity:  # it knows the layer hides it
                self.depth_order = 60.0 if s.z >= LAYER_DEPTH else 160.0
        if self.state == EVADE and self.threat not in world.torpedoes:
            self._set(ALERT if self.datum else PATROL, events)
        if self.search_request and self.state == PATROL:  # something blew up: go and look
            self.datum, self.since_contact, self.alarm = self.search_request, 0.0, True
        if self.alarm and self.state == PATROL:
            self._set(ALERT, events)
        self.alarm, self.search_request = False, None
        if self.state == ATTACK and not self.reload:
            self._set(ALERT, events)

        if self.state == PATROL:
            desired, speed = self._patrol_course(), self.cruise
        elif self.state == EVADE:
            desired, speed = bearing(self.threat.x, self.threat.y, s.x, s.y), self.top_speed
        else:
            dx, dy, dz = self.datum
            dist = math.hypot(dx - s.x, dy - s.y)
            desired = bearing(s.x, s.y, dx, dy)
            speed = self.cruise + 3 * KNOT if dist > self.fire_range else self.cruise
            if self.state == ALERT and self.since_contact > GIVE_UP:
                self._set(PATROL, events)
            elif self.state == ALERT and dist <= self.fire_range and self.torpedoes and not self.reload \
                    and self.since_contact < GIVE_UP / 2:  # only shoot at a fresh fix, not a back-plotted guess
                self._fire(world, events)

        self._helm(desired, speed, dt)
        s.z += clamp(self.depth_order - s.z, -dt, dt)
        s.noise = self.stealth * (1 + 1.5 * s.speed / self.top_speed)
        return events

    def _fire(self, world, events):
        """Return fire: lead the datum by our estimated motion, let the seeker do the rest."""
        s = self.ship
        dx, dy, dz = self.datum
        vx, vy = self.datum_vel
        los = bearing(s.x, s.y, dx, dy)
        sol = intercept(los, math.hypot(dx - s.x, dy - s.y), bearing(0, 0, vx, vy), math.hypot(vx, vy), self.torpedo_speed)
        world.launch_hostile(s, sol[0] if sol else los, self.torpedo_speed, seeker_range=self.seeker_range,
                             arm_distance=600 * YARD, max_run=9000 * YARD, run_depth=dz)
        self.torpedoes -= 1
        self.reload = 60.0
        self._set(ATTACK, events)
        events.append(("HOSTILE_LAUNCH", s, None))


class ThreatDirector:
    """Endless patrol: each wave rolls a convoy (merchant column + escort screen), sometimes a lone independent
    merchant, and submarines - harder every time. A wave ends when every hull is sunk or beyond DESPAWN_RANGE."""

    def __init__(self, difficulty, boost=0, waves=None):
        self.diff = difficulty
        self.boost = boost  # campaign: waves' worth of escalation to start with
        self.waves = waves  # campaign: the patrol ends when this wave clears; None = endless
        self.done = False
        self.wave = 0
        self.timer = 8.0
        self.wave_started = 0.0

    def update(self, world, dt):
        events, p = [], world.player
        late = self.wave and world.time - self.wave_started > WAVE_TIME_LIMIT  # don't let stragglers stall the patrol
        reach = LATE_DESPAWN_RANGE if late else DESPAWN_RANGE
        for t in [t for t in world.targets if not isinstance(t, Decoy) and p.range_to(t) > reach]:
            world.targets.remove(t)
            events.append(("ESCAPED", t, None))
        if self.done or any(not isinstance(t, Decoy) for t in world.targets):
            return events
        if self.timer == WAVE_GAP and self.wave:  # first quiet tick after a wave: resupply
            p.torpedoes = min(p.torpedoes + 4, 12)
            p.noisemakers = min(p.noisemakers + 2, 6)
            events.append(("WAVE_CLEAR", self.wave, None))
            self.done = self.wave == self.waves
        self.timer -= dt
        if self.timer <= 0:
            self._spawn(world, events)
            self.timer = WAVE_GAP
        return events

    def _spawn(self, world, events):
        self.wave += 1
        self.wave_started = world.time
        n, d, p = self.wave + self.boost, self.diff, world.player
        brg = random.uniform(0, 360)
        dist = random.uniform(7000, 9500)
        cx, cy = p.x + dist * math.sin(math.radians(brg)), p.y + dist * math.cos(math.radians(brg))
        course = (brg + 180 + random.choice((-1, 1)) * random.uniform(50, 100)) % 360  # crossing, not at us
        speed = random.uniform(6, 10) * KNOT
        merchants, escorts, subs = min(2 + n // 3, 4), min(1 + (n - 1) // 2, 3), min(n // 2, 3)
        convoy = Convoy(course, speed)
        for i in range(merchants):  # column astern of the guide
            offset = (-500.0 * i, 0.0)
            ship = Vessel(*frame_point(cx, cy, course, *offset), course, speed, noise=random.uniform(0.8, 1.2))
            world.targets.append(ship)
            world.ais.append(MerchantAI(ship, convoy, offset, max_speed=random.uniform(11, 15) * KNOT))
        for i in range(escorts):  # screen ahead, then the flanks
            station = (1200.0, 0.0) if i == 0 else (-200.0, (1 if i % 2 else -1) * 1500.0)
            ship = Vessel(*frame_point(cx, cy, course, *station), course, 0, decoys=3)
            world.targets.append(ship)
            world.ais.append(EscortAI(ship, course, convoy=convoy, station=station,
                                      aggression=clamp(random.uniform(0.3, 0.7) + 0.05 * n, 0, 1),
                                      detect_radius=random.uniform(2500, 3500), zigzag=d["zigzag"],
                                      cavitation_instant=d["cavitation_instant"]))
        lone = random.random() < 0.35  # an unescorted independent, minding its own business
        if lone:
            b = math.radians(random.uniform(0, 360))
            ship = Vessel(p.x + 6000 * math.sin(b), p.y + 6000 * math.cos(b), random.uniform(0, 360),
                          random.uniform(9, 12) * KNOT, noise=random.uniform(0.9, 1.3))
            world.targets.append(ship)
            world.ais.append(MerchantAI(ship, max_speed=15 * KNOT))
        for _ in range(subs):
            b = math.radians(random.uniform(0, 360))
            r = random.uniform(4000, 8000)
            ship = Vessel(p.x + r * math.sin(b), p.y + r * math.cos(b), random.uniform(0, 360), 0,
                          z=random.choice((60.0, 160.0)))
            world.targets.append(ship)
            world.ais.append(SubmarineAI(
                ship, ship.heading,
                stealth=random.uniform(0.2, 0.6),                                        # stealth rating
                top_speed=random.uniform(12, 22) * KNOT, turn_rate=random.uniform(2, 5),  # speed & manoeuvrability
                aggression=clamp(random.uniform(0.3, 0.8) + 0.05 * n, 0, 1),
                detect_radius=random.uniform(3000, 6000),
                layer_sensitivity=random.uniform(0.3, 1.0),
                torpedo_speed=d["enemy_torp_kt"] * KNOT, seeker_range=d["enemy_seeker_yd"] * YARD,
                zigzag=d["zigzag"], decoys=d["sub_decoys"], cavitation_instant=d["cavitation_instant"]))
        events.append(("WAVE", self.wave, (merchants + lone, escorts, subs, brg)))

    @staticmethod
    def score(world):
        return sum(TONNAGE.get(t.kind, 0) for t in world.sunk)
