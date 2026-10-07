"""Operator-side game state and logic: input, sensors, events -> what the crew sees, reads and hears."""
import math
import random
from collections import deque

import numpy as np
import pygame

from ai import ThreatDirector
from displays import CLASSES, SpectrumAnalyzer, Teletype, WaterfallDisplay
from fire_control import FIELDS, TargetDataComputer
from graphics import console_art as art
from graphics.periscope import EYE
from layout import (BLOW_BTN, CRT_RECT, DEPTH_C, DEPTH_R, HOLD_BTN, LOOK_BTN, NMKR_BTN, ORDER_SLIP, PD_BTN,
                    PING_BTN, RUDDER_BAR, SCOPE_C, SCOPE_LEVER, SCOPE_R, SNORT_LEVER, TDC_PANEL, TDC_ROW_H,
                    TDC_ROW_Y0, TELEGRAPH_BTNS, TELEGRAPH_RECT, TUBE_SW, WF_H, WF_POS, WF_W, WHEEL_C, WHEEL_R)
from sensors import SCOPE_FOV, SCOPE_TRAIN_RATE, ActiveSonar, PassiveSonar, PeriscopeOptics, cone_gain
from sim import (CRUSH_DEPTH, KNOT, MAX_DEPTH, MAX_RUDDER, MIN_ORDER_DEPTH, PERISCOPE_DEPTH, TELEGRAPH,
                 YARD, Decoy, Submarine, Torpedo, WorldSimulation, angle_diff, clamp, spot_probability)
from tma import TMALog
from tuning import DIFFICULTY


DIAL_RATE = 60.0          # hydrophone dial deg/s
RUDDER_RATE = 20.0        # deg/s while LEFT/RIGHT held
HOLD_DELAY = 0.35         # s of holding UP/DOWN before the TDC value starts to run
DIESEL_DEAFNESS = 3.0     # contacts sound this many times quieter while our diesels run
DIESEL_FLOOR = 40.0       # waterfall noise our diesels add
MAST_MESSAGES = {  # own mast events: (sonar log line, teleprinter line or "")
    "MASTS_LOWERED": ("MASTS HOUSED FOR DEPTH", ""),
    "HEAD_VALVE": ("HEAD VALVE SHUT - WAVE OVER SNORKEL", ""),
    "SNORKEL_FLOODED": ("SNORKEL FLOODED - DIESELS TRIPPED", "ENGINE ROOM: SNORKEL HEAD FLOODED AT SPEED. DIESELS "
                        "STOPPED FOR TEN SECONDS. KEEP UNDER EIGHT KNOTS WHILE SNORKELLING."),
    "SCOPE_DAMAGED": ("PERISCOPE BENT", "CONTROL ROOM: PERISCOPE BENT BY SPEED. FREEING IT - TWO MINUTES."),
}
ECHO_FADE = 40.0          # s an echo blip glows on the scope
SCOPE_RANGES = (5000.0, 10000.0, 20000.0)  # yd



# ---------- game state behind the workstation ----------
def build_world(d):
    world = WorldSimulation(Submarine(0, 0, 0, 4 * KNOT, z=60, uses_battery=d["battery"], uses_oxygen=d["oxygen"],
                                      mast_damage=d["mast_damage"], lower_delay=d["lower_delay"]), [])
    world.ocean.layer_loss = d["layer_loss"]
    world.leaks_enabled, world.torp_damage, world.spot_mult = d["leaks"], d["torp_damage"], d["spot_mult"]
    world.director = ThreatDirector(d)
    return world


def stamp(t):
    return f"{int(t // 60):02d}:{int(t % 60):02d}"


class Console:
    """Operator-side state and logic: input, sensors, events -> what the crew sees and hears."""

    def __init__(self, level, audio, diff=None):
        self.level, self.diff = level, diff or DIFFICULTY[level]
        self.world = build_world(self.diff)
        self.audio = audio
        self.passive = PassiveSonar(self.world, self.diff["beam_width"])
        self.active = ActiveSonar(self.world)
        self.waterfall, self.spectrum = WaterfallDisplay(), SpectrumAnalyzer()
        self.tdc = TargetDataComputer(self.world.player)
        self.teletype = Teletype(audio)
        self.dial = self.signal = self.held = 0.0
        self.tubes = [0.0, 0.0]  # reload s remaining; 0 = ready; inf = empty, waiting on the racks
        self.log = deque(maxlen=7)
        self.echoes = []         # (x, y, time) absolute fixes for the scope
        self.enemy_pings = []    # (true bearing, time)
        self.ping_time = -99.0
        self.lamp_enemy = self.flash = self.shake = 0.0
        self.banner = ("", 0.0)
        self.torpedo_warning = False
        self.scope_range = SCOPE_RANGES[1]
        self.dead, self.cause = False, ""
        self.dragging = None
        self.actions = set()     # orders given since last asked (the tutorial grades these)
        self.frame_events = []   # world events from the last tick
        self.last_echo = None    # (rel bearing, range yd)
        self.tutorial = None     # set by tutorial.Tutorial
        self.optics = PeriscopeOptics(self.world)
        self.looking = False     # at the eyepiece (the station is out of sight)
        self.scope_brg = 0.0     # relative bearing the scope is trained on
        self.high_power = False
        self.view = None         # last optics.look(): (sightings, wakes, bursts) or None
        self.scope_fix = None    # (true bearing, range m, time) from the last scope mark
        self.exposure = 0.0      # estimated chance of being spotted per minute, 0..1
        self.last_valve = -99.0
        self.debug = False       # F3: truth overlay for playtesting and tuning
        self.tma = TMALog()      # bearing history for the TMA plot
        self.crt_page = "SONAR"  # F2 flips the left of the monitor between waterfall and TMA plot
        self.say("SONAR ONLINE. PASSIVE ARRAY NOMINAL")
        if diff is None:
            self.teletype.print(f"FROM FLAG OFFICER SUBMARINES: {level} PATROL. INTERCEPT CONVOYS IN YOUR SECTOR. "
                                "STAY DEEP, STAY QUIET. F1 FOR STATION DRILL.")

    @property
    def score(self):
        return ThreatDirector.score(self.world)

    @property
    def wave(self):
        return self.world.director.wave if self.world.director else 0

    @property
    def classification(self):
        return CLASSES[self.spectrum.best] if self.spectrum.best is not None else None

    def say(self, msg):
        self.log.append(f"{stamp(self.world.time)} {msg}")

    # --- orders ---
    def telegraph_index(self):
        p = self.world.player
        return min(range(len(TELEGRAPH)), key=lambda i: abs(TELEGRAPH[i][1] * KNOT - p.ordered_speed))

    def telegraph(self, index):
        index = int(clamp(index, 0, len(TELEGRAPH) - 1))
        self.world.player.ordered_speed = TELEGRAPH[index][1] * KNOT
        self.say(f"ENGINES {TELEGRAPH[index][0]}")

    def order_depth(self, depth):
        p = self.world.player
        p.ordered_depth = clamp(depth, MIN_ORDER_DEPTH, MAX_DEPTH)
        p.blowing = False  # a new depth order takes the boat back from the blow

    # --- masts ---
    def periscope_depth(self):
        self.order_depth(PERISCOPE_DEPTH)
        self.actions.add("PD")
        self.say("MAKE YOUR DEPTH ONE FIVE METRES")

    def toggle_scope(self):
        p = self.world.player
        if p.scope_up:
            p.scope_up, self.looking = False, False
            self.actions.add("SCOPE_DOWN")
            self.say("DOWN SCOPE")
        else:
            why = p.raise_mast("scope")
            if why:
                return self.say(why)
            self.actions.add("SCOPE_UP")
            self.say("UP SCOPE")
        self.audio.play_mast()

    def toggle_snorkel(self):
        p = self.world.player
        if p.snorkel_up:
            p.snorkel_up = False
            self.actions.add("SNORKEL_DOWN")
            self.say("SECURE SNORKELLING")
        else:
            why = p.raise_mast("snorkel")
            if why:
                return self.say(why)
            self.actions.add("SNORKEL_UP")
            self.say("RAISE SNORKEL. START DIESELS")
        self.audio.play_mast()

    def look(self):
        if self.looking:
            self.looking = False
        elif not self.world.player.scope_up:
            self.say("SCOPE IS DOWN  (U TO RAISE)")
        else:
            self.looking = True
            self.actions.add("LOOK")

    def toggle_power(self):
        self.high_power = not self.high_power
        self.actions.add("POWER")

    def scope_mark(self):
        """Exact bearing - and rangefinder range if a ship is in the wires - straight into the TDC."""
        p = self.world.player
        fov = SCOPE_FOV[self.high_power]
        true_brg = (self.scope_brg + p.heading) % 360
        sightings = self.view[0] if self.view else []
        target = min((s for s in sightings if abs(angle_diff(s.brg, true_brg)) < fov * 0.06),
                     key=lambda s: abs(angle_diff(s.brg, true_brg)), default=None)
        self.actions.add("SCOPE_MARK")
        if target is None:
            self.tdc.set("BRG", self.scope_brg)
            self.tma.add(self.world.time, true_brg, "SCOPE")
            return self.say(f"MARK {self.scope_brg:05.1f}R. NOTHING IN THE WIRES")
        rel = (target.brg - p.heading) % 360
        rng = self.optics.rangefinder(target, self.high_power)
        self.tdc.set("BRG", rel)
        self.tdc.set("RNG", rng / YARD)
        self.scope_fix = (target.brg, rng, self.world.time)
        self.tma.add(self.world.time, target.brg, "SCOPE", rng)
        self.say(f"MARK! {rel:05.1f}R RANGE {rng / YARD:,.0f} YD")

    def estimate_exposure(self):
        """Chance per minute of being spotted. Cadet sees the truth; otherwise it's our own estimate from
        what we know: masts, speed, sea, and the nearest ship we have actually seen through the scope."""
        p, o = self.world.player, self.world.ocean
        exposed = getattr(p, "exposed", None)
        if not exposed:
            return 0.0
        mult = self.world.spot_mult
        if self.diff["ping_warning"]:  # cadet: the honest number
            per_s = max((spot_probability(exposed, p.speed / KNOT, ai.ship.range_to(p), o.visibility, o.sea_state,
                                          ai._alertness()) for ai in self.world.ais if ai.lookouts), default=0.0)
        else:
            seen = [s.rng for s in self.view[0]] if self.view else []
            near = min(seen, default=3000.0)
            alert = 2.5 if self.lamp_enemy > 0 else 1.5
            per_s = spot_probability(exposed, p.speed / KNOT, near, o.visibility, o.sea_state, alert)
        return 1 - (1 - min(1.0, per_s * mult)) ** 60

    def ping(self):
        self.active.ping()
        self.audio.play_ping()
        self.ping_time = self.world.time
        self.actions.add("PING")
        self.say("PING OUT. POSITION EXPOSED")

    def fire(self, tube=None):
        if tube is None:
            tube = next((i for i, r in enumerate(self.tubes) if r == 0), None)
        if tube is None or self.tubes[tube] != 0:
            return self.say("NO TUBE READY")
        sol = self.tdc.solve()
        if sol is None:
            return self.say("NO FIRING SOLUTION")
        self.world.fire(sol.gyro, arm_distance=self.tdc.values["ARM"] * YARD, run_depth=self.tdc.values["DEP"],
                        tube=tube + 1)
        self.tubes[tube] = math.inf
        self.actions.add("FIRE")
        self.say(f"T{tube + 1} AWAY. GYRO {sol.gyro:05.1f}")

    def noisemaker(self):
        p = self.world.player
        if not p.noisemakers:
            return self.say("NO NOISEMAKERS LEFT")
        p.noisemakers -= 1
        self.world.drop_noisemaker()
        self.audio.play_hiss(0.5)
        self.actions.add("NOISEMAKER")
        self.say("NOISEMAKER AWAY")

    def blow(self):
        self.world.player.blowing = True
        self.audio.play_blow()
        self.actions.add("BLOW")
        self.say("BLOW ALL MAIN BALLAST!")

    def hold_depth(self):
        self.order_depth(round(self.world.player.z))
        self.actions.add("HOLD")

    def mark(self):
        self.tdc.set("BRG", self.dial)
        self.tma.add(self.world.time, self.dial + self.world.player.heading, "MARK")
        self.actions.add("MARK")
        self.say(f"MARK BEARING {self.dial:05.1f}R")

    # --- input ---
    def key(self, k):
        if self.dead:
            return
        p = self.world.player
        actions = {
            pygame.K_SPACE: self.ping,
            pygame.K_f: self.fire,
            pygame.K_1: lambda: self.fire(0),
            pygame.K_2: lambda: self.fire(1),
            pygame.K_w: lambda: self.tdc.cycle(-1),
            pygame.K_s: lambda: self.tdc.cycle(1),
            pygame.K_UP: lambda: self.tdc.nudge(1),
            pygame.K_DOWN: lambda: self.tdc.nudge(-1),
            pygame.K_m: self.scope_mark if self.looking else self.mark,
            pygame.K_u: self.toggle_scope,
            pygame.K_k: self.toggle_snorkel,
            pygame.K_g: self.periscope_depth,
            pygame.K_v: self.look,
            pygame.K_TAB: self.toggle_power,
            pygame.K_q: lambda: self.order_depth(p.ordered_depth - 10),
            pygame.K_e: lambda: self.order_depth(p.ordered_depth + 10),
            pygame.K_h: self.hold_depth,
            pygame.K_b: self.blow,
            pygame.K_z: lambda: self.telegraph(self.telegraph_index() - 1),
            pygame.K_x: lambda: self.telegraph(self.telegraph_index() + 1),
            pygame.K_c: lambda: setattr(p, "rudder", 0.0),
            pygame.K_n: self.noisemaker,
            pygame.K_t: self.cycle_scope,
            pygame.K_RETURN: lambda: self.actions.add("ENTER"),
            pygame.K_KP_ENTER: lambda: self.actions.add("ENTER"),
            pygame.K_F3: lambda: setattr(self, "debug", not self.debug),
            pygame.K_F2: self.flip_page,
            pygame.K_F4: self.auto_solve,
        }
        if k in actions:
            actions[k]()

    def flip_page(self):
        self.crt_page = "TMA" if self.crt_page == "SONAR" else "SONAR"
        self.actions.add("PAGE_" + self.crt_page)

    def auto_solve(self):
        """Least-squares fit of the bearing history: fitted on Cadet / Training consoles only."""
        if not self.diff["ping_warning"]:
            return self.say("AUTO-SOLVE NOT FITTED - PLOT IT YOURSELF")
        result = self.tma.auto_solve(self.world.time, self.world.player, self.tdc)
        self.actions.add("AUTOSOLVE")
        if isinstance(result, str):
            return self.say(result)
        fit, ambiguous = result
        self.say(f"AUTO-SOLVE: FIT {fit:.1f} DEG" + (". AMBIGUOUS - CHANGE COURSE, NEW LEG" if ambiguous else ". CHECK IT"))

    def cycle_scope(self):
        self.scope_range = SCOPE_RANGES[(SCOPE_RANGES.index(self.scope_range) + 1) % len(SCOPE_RANGES)]
        self.actions.add("SCOPE")

    def click(self, pos):
        if self.dead:
            return
        x, y = pos
        wf = pygame.Rect(CRT_RECT.x + WF_POS[0], CRT_RECT.y + WF_POS[1], WF_W, WF_H)
        buttons = ((HOLD_BTN, self.hold_depth), (BLOW_BTN, self.blow), (PD_BTN, self.periscope_depth),
                   (LOOK_BTN, self.look), (NMKR_BTN, self.noisemaker), (PING_BTN, self.ping))
        if self.looking:  # at the eyepiece: grab the training handles
            self.dragging = ("scope", x)
            return
        if math.hypot(x - SCOPE_LEVER[0], y - SCOPE_LEVER[1]) <= 24:
            return self.toggle_scope()
        if math.hypot(x - SNORT_LEVER[0], y - SNORT_LEVER[1]) <= 24:
            return self.toggle_snorkel()
        if self.tutorial and ORDER_SLIP.collidepoint(pos):
            self.actions.add("ENTER")
        elif wf.collidepoint(pos):
            self.dial = (x - wf.x) / WF_W * 360
        elif math.hypot(x - SCOPE_C[0], y - SCOPE_C[1]) <= SCOPE_R:
            self.cycle_scope()
        elif any(b.collidepoint(pos) for b in TELEGRAPH_BTNS):
            self.telegraph(next(i for i, b in enumerate(TELEGRAPH_BTNS) if b.collidepoint(pos)))
        elif math.hypot(x - WHEEL_C[0], y - WHEEL_C[1]) <= WHEEL_R + 18 or RUDDER_BAR.inflate(0, 16).collidepoint(pos):
            self.dragging = "wheel"
            self.drag(pos)
        elif math.hypot(x - DEPTH_C[0], y - DEPTH_C[1]) <= DEPTH_R:
            a = math.degrees(math.atan2(DEPTH_C[1] - y, x - DEPTH_C[0]))
            self.order_depth(round(art.angle_value(a, 0, 300) / 5) * 5)
        elif TDC_PANEL.collidepoint(pos) and 0 <= (y - TDC_ROW_Y0) // TDC_ROW_H < len(FIELDS):
            self.tdc.selected = int((y - TDC_ROW_Y0) // TDC_ROW_H)
        else:
            for i, (sx, sy) in enumerate(TUBE_SW):
                if math.hypot(x - sx, y - sy) <= 26:
                    return self.fire(i)
            for rect, action in buttons:
                if rect.collidepoint(pos):
                    return action()

    def drag(self, pos):
        if isinstance(self.dragging, tuple):  # training the scope: the scene follows the hand
            dx = pos[0] - self.dragging[1]
            self.scope_brg = (self.scope_brg - dx * SCOPE_FOV[self.high_power] / EYE) % 360
            self.dragging = ("scope", pos[0])
        elif self.dragging == "wheel":
            self.world.player.rudder = round(clamp((pos[0] - WHEEL_C[0]) / (WHEEL_R + 16) * MAX_RUDDER, -MAX_RUDDER, MAX_RUDDER))

    def scroll(self, pos, dy):
        x, y = pos
        p = self.world.player
        if self.looking:
            if (dy > 0) != self.high_power:
                self.toggle_power()
        elif TDC_PANEL.collidepoint(pos):
            self.tdc.nudge(dy)
        elif math.hypot(x - DEPTH_C[0], y - DEPTH_C[1]) <= DEPTH_R:
            self.order_depth(p.ordered_depth - 10 * dy)
        elif math.hypot(x - WHEEL_C[0], y - WHEEL_C[1]) <= WHEEL_R + 18:
            p.rudder = clamp(p.rudder + 5 * dy, -MAX_RUDDER, MAX_RUDDER)
        elif TELEGRAPH_RECT.collidepoint(pos):
            self.telegraph(self.telegraph_index() + dy)
        elif CRT_RECT.collidepoint(pos):
            self.dial = (self.dial + dy) % 360

    # --- simulation tick ---
    def update(self, dt, keys):
        self.teletype.update(dt)
        if self.dead:
            return
        p, world = self.world.player, self.world
        train = keys[pygame.K_d] - keys[pygame.K_a]
        if self.looking:  # A/D train the scope; the hydrophone dial stays where it was
            self.scope_brg = (self.scope_brg + train * SCOPE_TRAIN_RATE[self.high_power] * dt) % 360
        else:
            self.dial = (self.dial + train * DIAL_RATE * dt) % 360
        rudder = keys[pygame.K_RIGHT] - keys[pygame.K_LEFT]
        if rudder:
            p.rudder = clamp(p.rudder + rudder * RUDDER_RATE * dt, -MAX_RUDDER, MAX_RUDDER)
        adj = keys[pygame.K_UP] - keys[pygame.K_DOWN]
        self.held = self.held + dt if adj else 0.0
        if self.held > HOLD_DELAY:
            self.tdc.hold(adj, dt)

        for i, r in enumerate(self.tubes):
            if r == math.inf and p.torpedoes > 0:
                p.torpedoes -= 1
                self.tubes[i] = self.diff["reload"]
            elif 0 < r <= dt:
                self.say(f"TUBE {i + 1} LOADED")
        self.tubes = [r if r == math.inf else max(0.0, r - dt) for r in self.tubes]

        self.frame_events = world.step(dt)
        for kind, a, b in self.frame_events:
            self.report(kind, a, b)
        self.tdc.update(dt)
        self.view = self.optics.look() if p.scope_up else None
        self.looking = self.looking and p.scope_up
        self.exposure = self.estimate_exposure()
        self.audio.set_diesel(p.snorkeling)
        self.audio.set_surface(self.looking, world.ocean.sea_state)

        strain = max(0.0, (p.z - 80) / 170) + max(0.0, (p.speed / KNOT - 12) / 8) + (p.z > CRUSH_DEPTH)
        if random.random() < 0.3 * strain * dt:
            self.audio.play_creak(0.3 + 0.5 * min(strain, 1.0))

        bearings, levels, widths, kinds, hostile = self.passive.listen()
        for brg, rng in self.active.update(dt):
            if brg is None:
                self.waterfall.blip(0.0, 60, WF_W)  # layer reverb smears every bearing
                self.say(f"LAYER RETURN {rng:.0f} M")
                continue
            self.audio.play_echo(2500 / rng)
            self.waterfall.blip(brg, 230)
            b = math.radians(brg + p.heading)
            self.echoes.append((p.x + rng * math.sin(b), p.y + rng * math.cos(b), world.time))
            self.last_echo = (brg, rng / YARD)
            tdc_true = math.degrees(math.atan2(self.tdc.x, self.tdc.y)) % 360
            if abs(angle_diff(brg + p.heading, tdc_true)) < 3:  # an echo on the plotted target: range for TMA
                self.tma.add(world.time, brg + p.heading, "ECHO", rng)
            self.say(f"ECHO {brg:05.1f}R {rng / YARD:,.0f} YD")
        self.echoes = [e for e in self.echoes if world.time - e[2] < ECHO_FADE]
        rain = world.ocean.rain
        diesel = getattr(p, "snorkeling", False)
        if diesel:  # our own diesels thunder through the hull: the hydrophones are nearly deaf while we charge
            levels = levels / DIESEL_DEAFNESS
        self.waterfall.update(dt, bearings, levels, widths, rain, floor=DIESEL_FLOOR if diesel else 0.0)
        gains = cone_gain(self.dial, bearings, self.diff["cone"])
        self.signal = float((gains * levels / 160).max(initial=0.0)) / (1 + 2 * rain)
        self.spectrum.update(dt, world.time, gains, levels, kinds, rain + (0.35 if diesel else 0.0))
        self.audio.set_hydrophone(self.signal)
        self.tma.update(world.time, p, self.signal > 0.5, self.dial + p.heading)
        self.torpedo_warning = bool(np.any(hostile & (levels > 30)))

        self.flash = max(0.0, self.flash - dt * 2.5)
        self.shake = max(0.0, self.shake - dt * 1.5)
        self.lamp_enemy = max(0.0, self.lamp_enemy - dt)
        self.banner = (self.banner[0], max(0.0, self.banner[1] - dt))
        self.enemy_pings = [e for e in self.enemy_pings if world.time - e[1] < 1.5]

        if world.hull <= 0 or (p.uses_oxygen and p.o2 <= 0):
            self.dead = True
            self.cause = "HULL BREACHED" if world.hull <= 0 else "OXYGEN EXHAUSTED"
            self.audio.set_hydrophone(0.0)
            self.teletype.print(f"{self.cause}. CONTACT LOST WITH BOAT AT {stamp(world.time)}. "
                                f"WAVE {self.wave}. {self.score:,} GRT SUNK.")

    def jolt(self, strength):
        self.shake = max(self.shake, strength)
        self.flash = max(self.flash, strength * 0.8)

    def report(self, kind, a, b):
        """Turn world events into what the operator sees, reads and hears."""
        tt, world = self.teletype.print, self.world
        if kind == "WAVE":
            m, e, s, brg = b
            fuzz = 0 if self.diff["ping_warning"] else random.uniform(-25, 25)
            tt(f"DISPATCH WAVE {a}: CONVOY OF {m} MERCHANTS, {e} ESCORT(S) REPORTED NEAR {(brg + fuzz) % 360:03.0f} TRUE, "
               f"8 KM." + (f" {s} HOSTILE SUBMARINE(S) SUSPECTED." if s else "") + " ATTACK AT DISCRETION.")
            return
        if kind == "WAVE_CLEAR":
            tt(f"WAVE {a} DISPERSED. TENDER RESUPPLY: +4 TORPEDOES, +2 NOISEMAKERS. TOTAL {self.score:,} GRT.")
            return
        if kind == "ESCAPED":
            if a.kind == "MERCHANT":
                tt("CONVOY STRAGGLER HAS SLIPPED OUT OF RANGE.")
            return
        if kind == "LEAK":
            tt(f"DAMAGE CONTROL: FLOODING. {b} LEAK(S). PUMPS ON.")
            return
        if kind in MAST_MESSAGES:  # own-ship mast trouble
            log, teletype = MAST_MESSAGES[kind]
            if kind == "HEAD_VALVE" and world.time - self.last_valve < 6:
                return  # in a seaway it slams every few seconds; don't spam the log
            self.last_valve = world.time if kind == "HEAD_VALVE" else self.last_valve
            self.say(log)
            if teletype:
                tt(teletype)
            if kind in ("HEAD_VALVE", "SNORKEL_FLOODED"):
                self.audio.play_thunk()
            if kind == "MASTS_LOWERED":
                self.looking = False
            return
        if kind == "SPOTTED":  # truth: only cadets are told; everyone else may see a signal lamp in the scope
            if self.diff["ping_warning"]:
                brg = self.passive.bearing_of(a)
                self.banner = (f"SPOTTED BY {a.kind} {brg:03.0f}R!", 4.0)
                tt(f"INSTRUCTOR: LOOKOUTS ON THE {a.kind} AT {brg:03.0f}R HAVE SEEN YOUR "
                   f"{'MASTS' if b == 'both' else b.upper()}. GET DOWN.")
            return
        if kind == "PLAYER_HIT":
            self.audio.play_explosion(1.0)
            self.audio.play_creak(1.0)
            self.jolt(1.0)
            self.say("WE'RE HIT!")
            tt(f"TORPEDO HIT! HULL {world.hull:.0f}%.")
            return
        if kind == "CHARGE":
            loud = self.passive.loudness(a, ref=400.0)
            self.audio.play_explosion(loud)
            self.jolt(loud * 0.7)
            if b >= 1:
                self.audio.play_creak(1.0)
                self.say(f"CHARGE CLOSE. HULL {world.hull:.0f}%")
            return
        brg = self.passive.bearing_of(a)
        if isinstance(a, Torpedo) and a.hostile:
            if kind == "DECOYED":
                self.audio.play_explosion(self.passive.loudness(a))
                self.jolt(0.3)
                self.say(f"DETONATION {brg:05.1f}R. DECOY TOOK IT")
            return  # nothing else about their fish is observable
        if kind == "HOSTILE_LAUNCH":
            if self.passive.loudness(a, ref=6000.0) > 0.05:
                self.say(f"LAUNCH TRANSIENT {brg:05.1f}R!")
                tt(f"CONN, SONAR: TORPEDO IN THE WATER, BEARING {brg:03.0f} RELATIVE.")
        elif kind == "ESCORT_PING":
            self.audio.play_enemy_ping(self.passive.loudness(a, ref=5000.0))
            self.waterfall.blip(brg, 200)
            self.enemy_pings.append(((brg + world.player.heading) % 360, world.time))
            self.lamp_enemy = 1.5
            if self.diff["ping_warning"]:
                self.banner = (f"ENEMY SONAR {brg:03.0f}R - " + ("WE ARE HELD" if b else "NOT HELD"), 3.0)
        elif kind.startswith("AI_"):  # what a sonarman hears: revs, pinging, bearings drawing apart
            msg = {("ESCORT", "AI_ALERT"): "REVS UP, CLOSING" if b in ("PATROL", "SEARCH") else None,
                   ("ESCORT", "AI_ATTACK"): "FAST SCREWS CLOSING",
                   ("ESCORT", "AI_SEARCH"): "SEARCHING, ACTIVE SONAR",
                   ("ESCORT", "AI_PATROL"): "REVS DOWN",
                   ("MERCHANT", "AI_ALARMED"): "REVS UP, ZIG-ZAGGING",
                   ("MERCHANT", "AI_SCATTER"): "FULL REVS, TURNING AWAY",
                   ("MERCHANT", "AI_CRUISE"): "REVS DOWN, STEADY"}.get((a.kind, kind))
            if msg:
                self.say(f"CONTACT {brg:05.1f}R {msg}")
        elif kind == "CONVOY_ALARM":
            self.say(f"CONVOY {brg:05.1f}R REVS UP. ZIG-ZAG")
            tt("CONN, SONAR: CONVOY HAS WOKEN UP - REVS INCREASING, STARTING A ZIG-ZAG.")
        elif kind == "CONVOY_CALM":
            self.say(f"CONVOY {brg:05.1f}R REVS DOWN")
        elif kind == "CONVOY_SCATTER":
            self.say("CONVOY SCATTERING")
            tt("CONN, SONAR: CONVOY IS SCATTERING - CONTACTS FANNING OUT AT FULL REVS. ESCORTS WILL HUNT THE "
               "TORPEDO TRACK BACK TO US.")
        elif kind == "CHARGES":
            self.say(f"SPLASHES {brg:05.1f}R. CHARGES")
            tt("CONN, SONAR: DEPTH CHARGES IN THE WATER.")
        elif kind == "DECOY_DROP":
            self.audio.play_hiss(max(0.4, self.passive.loudness(a)))
            self.say(f"HISS {brg:05.1f}R. COUNTERMEASURE")
        elif kind in ("ARMED", "HOMING", "LOST"):
            self.say(f"T{a.tube} " + {"ARMED": "SEEKER ACTIVE", "HOMING": "HOMING", "LOST": "LOST LOCK"}[kind])
        elif kind == "EXHAUSTED":
            self.say(f"T{a.tube} FUEL OUT. " + ("DECOYED" if isinstance(b, Decoy) else "MISS"))
        elif kind in ("HIT", "DECOYED"):
            self.audio.play_explosion(self.passive.loudness(a, ref=4000.0))
            self.waterfall.blip(brg, 255)
            self.jolt(0.25)
            self.say(f"T{a.tube} DETONATION {brg:05.1f}R")
            if kind == "HIT":
                self.say("BREAKUP NOISES. SUNK")
                tt(f"CONFIRMED: {b.kind} SUNK. {self.score:,} GRT TOTAL.")
            else:
                self.say("NO BREAKUP. DECOYED")
