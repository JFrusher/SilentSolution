"""Operator-side game state and logic: input, sensors, events -> what the crew sees, reads and hears."""
import math
import random
from collections import deque

import numpy as np
import pygame

import settings
from ai import ThreatDirector
from displays import CLASSES, SCALES, SpectrumAnalyzer, Teletype, WaterfallDisplay
from fire_control import FIELDS, TargetDataComputer
from geometry import bearing, offset
from graphics import console_art as art
from graphics.periscope import EYE
from layout import (
    BLOW_BTN,
    CRT_RECT,
    DC_ROW_H,
    DC_ROW_Y0,
    DEPTH_C,
    DEPTH_R,
    HOLD_BTN,
    LOOK_BTN,
    NMKR_BTN,
    ORDER_SLIP,
    PD_BTN,
    PING_BTN,
    RUDDER_BAR,
    SCOPE_C,
    SCOPE_LEVER,
    SCOPE_R,
    SNORT_LEVER,
    TDC_PANEL,
    TDC_ROW_H,
    TDC_ROW_Y0,
    TELEGRAPH_BTNS,
    TELEGRAPH_RECT,
    TUBE_SW,
    WF_H,
    WF_POS,
    WF_W,
    WHEEL_C,
    WHEEL_R,
)
from replay import Recorder
from sensors import SCOPE_FOV, SCOPE_TRAIN_RATE, ActiveSonar, PassiveSonar, PeriscopeOptics, cone_gain
from sim import (
    CRUSH_DEPTH,
    KNOT,
    MAX_DEPTH,
    MAX_RUDDER,
    MIN_ORDER_DEPTH,
    PERISCOPE_DEPTH,
    TELEGRAPH,
    TORP_MAX_RUN,
    YARD,
    Decoy,
    Submarine,
    Torpedo,
    WorldSimulation,
    angle_diff,
    clamp,
    spot_probability,
)
from tma import PLOT_SPAN, TMALog
from tuning import DIFFICULTY, REPAIR_TIME

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
    "SCOPE_DAMAGED": ("PERISCOPE BENT", "CONTROL ROOM: PERISCOPE BENT BY SPEED. ON THE DAMAGE LIST ({DAMAGE BOARD})."),
}
ECHO_FADE = 40.0          # s an echo blip glows on the scope
SCOPE_RANGES = (5000.0, 10000.0, 20000.0)  # yd



# ---------- game state behind the workstation ----------
def build_world(d):
    world = WorldSimulation(Submarine(0, 0, 0, 4 * KNOT, z=60, uses_battery=d["battery"], uses_oxygen=d["oxygen"],
                                      mast_damage=d["mast_damage"], lower_delay=d["lower_delay"]), [])
    world.ocean.layer_loss = d["layer_loss"]
    world.leaks_enabled, world.torp_damage, world.spot_mult = d["leaks"], d["torp_damage"], d["spot_mult"]
    world.systems_damage = True
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
        self.signal = self.held = 0.0
        self.dial_true = self.scope_true = 0.0  # where the hydrophone and the periscope point, TRUE bearing
        self.last_heading = self.world.player.heading
        self.locked = self.tracking = False  # dial on the trace (within lock_deg); dial following it by itself
        self.brg_err = None  # smoothed bearing of the loudest contact in the cone, relative to the dial
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
        self.high_power = False
        self.view = None         # last optics.look(): (sightings, wakes, bursts) or None
        self.scope_fix = None    # (true bearing, range m, time) from the last scope mark
        self.exposure = 0.0      # estimated chance of being spotted per minute, 0..1
        self.last_valve = -99.0
        self.debug = False       # F3: truth overlay for playtesting and tuning
        self.tma = TMALog()      # bearing history for the TMA plot
        self.recorder = Recorder()  # world truth for the after-action replay (read-only)
        self.wire_sel = None     # the wired fish the scope clicks steer
        self.wire_hint = False
        self.long_shot = -99.0  # when F was last refused on a beyond-range solution
        self.crt_page = "SONAR"  # left of the monitor: waterfall, F2 TMA plot, F5 damage board
        self.say("SONAR ONLINE. PASSIVE ARRAY NOMINAL")
        if diff is None:
            self.teletype.print(f"FROM FLAG OFFICER SUBMARINES: {level} PATROL. INTERCEPT CONVOYS IN YOUR SECTOR. "
                                "STAY DEEP, STAY QUIET. F1 FOR STATION DRILL.")

    # --- bearings: stored TRUE; relative is a view of them from the ship's head ---
    @property
    def dial(self):
        return (self.dial_true - self.world.player.heading) % 360

    @dial.setter
    def dial(self, rel):
        self.dial_true = (rel + self.world.player.heading) % 360

    @property
    def scope_brg(self):
        return (self.scope_true - self.world.player.heading) % 360

    @scope_brg.setter
    def scope_brg(self, rel):
        self.scope_true = (rel + self.world.player.heading) % 360

    @staticmethod
    def true_mode():
        return settings.SETTINGS["true_bearings"]

    def display_brg(self, true_brg):
        """A true bearing as the station currently shows bearings (true, or relative to the ship's head)."""
        return true_brg % 360 if self.true_mode() else (true_brg - self.world.player.heading) % 360

    def from_display(self, b):
        return b % 360 if self.true_mode() else (b + self.world.player.heading) % 360

    def toggle_bearing_mode(self):
        settings.SETTINGS["true_bearings"] = not self.true_mode()
        settings.save()
        self.say("BEARINGS " + ("TRUE (NORTH-STABILISED)" if self.true_mode() else "RELATIVE (SHIP'S HEAD)"))

    def cycle_waterfall(self):
        wf = self.waterfall
        wf.row_interval = SCALES[(SCALES.index(wf.row_interval) + 1) % len(SCALES)] if wf.row_interval in SCALES \
            else SCALES[0]
        self.say(f"WATERFALL {wf.row_interval:g} S A LINE")

    def scope_to_sonar(self):
        self.scope_true = self.dial_true
        self.actions.add("SCOPE_TO_SONAR")
        self.say(f"SCOPE ON THE SONAR BEARING {self.display_brg(self.dial_true):05.1f}"
                 + ("T" if self.true_mode() else "R"))

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
            self.say(settings.keyed("SCOPE IS DOWN  ({RAISE SCOPE} TO RAISE)"))
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
        if "ACTIVE SONAR" in self.world.player.damaged:
            return self.say("ACTIVE SONAR DAMAGED")
        self.active.ping()
        self.audio.play_ping()
        self.ping_time = self.world.time
        self.actions.add("PING")
        self.say("PING OUT. POSITION EXPOSED")

    def fire(self, tube=None):
        """F: a salvo from every ready tube, fanned across SPREAD (one fish if SPREAD is 0); 1/2: that tube."""
        ready = [i for i, r in enumerate(self.tubes) if r == 0 and f"TUBE {i + 1}" not in self.world.player.damaged]
        if tube is not None:
            ready = [tube] if tube in ready else []
        elif self.tdc.values["SPR"] <= 0:
            ready = ready[:1]
        if not ready:
            return self.say("NO TUBE READY")
        sol = self.tdc.solve()
        if sol is None:
            return self.say("NO FIRING SOLUTION")
        if sol.run > TORP_MAX_RUN and self.world.time - self.long_shot > 3:  # a second press within 3 s is a long shot
            self.long_shot = self.world.time
            return self.say(f"BEYOND RANGE: RUN {sol.run / YARD:,.0f} YD. FIRE AGAIN TO SHOOT")
        spread = self.tdc.values["SPR"]
        for k, i in enumerate(ready):
            gyro = (sol.gyro + (k - (len(ready) - 1) / 2) * spread) % 360
            fish = self.world.fire(gyro, arm_distance=self.tdc.values["ARM"] * YARD, run_depth=self.tdc.values["DEP"],
                                   tube=i + 1, wired=True)
            self.tubes[i] = math.inf
            self.say(f"T{i + 1} AWAY. GYRO {gyro:05.1f}")
            self.wire_sel = fish
        self.actions.add("FIRE")
        if not self.wire_hint:
            self.wire_hint = True
            self.teletype.print(settings.keyed(
                "WEAPONS: FISH ARE ON THE WIRE. CLICK ONE ON THE TACTICAL SCOPE, THEN CLICK WHERE TO SEND IT. "
                "{WIRE LEFT} {WIRE RIGHT} NUDGE, {NEXT FISH} NEXT FISH, {CUT WIRE} CUTS THE WIRE. OVER 12 KNOTS THE "
                "WIRE PARTS."))

    # --- wire guidance ---
    def wired_fish(self):
        return [t for t in self.world.torpedoes if t.wired and not t.hostile]

    def next_fish(self):
        fish = self.wired_fish()
        if fish:
            self.wire_sel = fish[(fish.index(self.wire_sel) + 1) % len(fish)] if self.wire_sel in fish else fish[0]
            self.say(f"T{self.wire_sel.tube} SELECTED ON THE WIRE")

    def nudge_fish(self, d):
        t = self.wire_sel
        if t in self.wired_fish():
            h = math.radians(t.heading + d * 10)
            t.wire_aim = (t.x + 4000 * math.sin(h), t.y + 4000 * math.cos(h))
            self.actions.add("WIRE")

    def cut_wire(self):
        t = self.wire_sel
        if t in self.wired_fish():
            t.wired, t.wire_aim = False, None
            self.say(f"T{t.tube} WIRE CUT")

    def scope_click(self, pos):
        """Tactical scope: click a wired fish to take it, click the water to send it there; else change range."""
        own = self.world.player
        scale = (SCOPE_R - 6) / (self.scope_range * YARD)
        for t in self.wired_fish():
            sx, sy = SCOPE_C[0] + (t.x - own.x) * scale, SCOPE_C[1] - (t.y - own.y) * scale
            if math.hypot(pos[0] - sx, pos[1] - sy) <= 10:
                self.wire_sel = t
                return self.say(f"T{t.tube} SELECTED ON THE WIRE")
        if self.wire_sel in self.wired_fish():
            self.wire_sel.wire_aim = (own.x + (pos[0] - SCOPE_C[0]) / scale, own.y - (pos[1] - SCOPE_C[1]) / scale)
            self.actions.add("WIRE")
            return self.say(f"T{self.wire_sel.tube} STEERING")
        self.cycle_scope()

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
            "PING": self.ping,
            "FIRE": self.fire,
            "FIRE TUBE 1": lambda: self.fire(0),
            "FIRE TUBE 2": lambda: self.fire(1),
            "TDC ROW UP": lambda: self.tdc.cycle(-1),
            "TDC ROW DOWN": lambda: self.tdc.cycle(1),
            "TDC VALUE UP": lambda: self.tdc.nudge(1),
            "TDC VALUE DOWN": lambda: self.tdc.nudge(-1),
            "MARK": self.scope_mark if self.looking else self.mark,
            "RAISE SCOPE": self.toggle_scope,
            "RAISE SNORKEL": self.toggle_snorkel,
            "PERISCOPE DEPTH": self.periscope_depth,
            "LOOK": self.look,
            "SCOPE POWER": self.toggle_power,
            "SHALLOWER": lambda: self.order_depth(p.ordered_depth - 10),
            "DEEPER": lambda: self.order_depth(p.ordered_depth + 10),
            "HOLD DEPTH": self.hold_depth,
            "BLOW": self.blow,
            "SLOWER": lambda: self.telegraph(self.telegraph_index() - 1),
            "FASTER": lambda: self.telegraph(self.telegraph_index() + 1),
            "RUDDER AMIDSHIPS": lambda: setattr(p, "rudder", 0.0),
            "NOISEMAKER": self.noisemaker,
            "SCOPE RANGE": self.cycle_scope,
            "WIRE LEFT": lambda: self.nudge_fish(-1),
            "WIRE RIGHT": lambda: self.nudge_fish(1),
            "NEXT FISH": self.next_fish,
            "CUT WIRE": self.cut_wire,
            "ACKNOWLEDGE": lambda: self.actions.add("ENTER"),
            "DEBUG": lambda: setattr(self, "debug", not self.debug),
            "TMA PAGE": self.flip_page,
            "AUTO-SOLVE": self.auto_solve,
            "DAMAGE BOARD": self.damage_board,
            "BEARING MODE": self.toggle_bearing_mode,
            "WATERFALL SCALE": self.cycle_waterfall,
            "SCOPE TO SONAR": self.scope_to_sonar,
            "SKIP DRILL": lambda: self.actions.add("SKIP"),  # training only: the tutorial reads it
        }
        name = settings.action_for(k)
        if name in actions:
            actions[name]()

    def flip_page(self):
        self.crt_page = "TMA" if self.crt_page == "SONAR" else "SONAR"
        self.actions.add("PAGE_" + self.crt_page)

    def damage_board(self):
        self.crt_page = "SONAR" if self.crt_page == "DAMAGE" else "DAMAGE"
        self.actions.add("PAGE_" + self.crt_page)

    def damage_rows(self):
        """Damage board lines: the repair list in work order, then the systems that are fine."""
        hurt = self.world.player.damaged
        return [*hurt, *(s for s in REPAIR_TIME if s not in hurt)]

    def tma_centre(self):
        """The TMA plot centres on your own recent bearings, so the dots are in view before there is a solution;
        with none yet, on the TDC's bearing."""
        recent = self.tma.recent(self.world.time, 60.0)
        if not recent:
            return bearing(0.0, 0.0, self.tdc.x, self.tdc.y)
        b = np.radians([r[1] for r in recent])
        return math.degrees(math.atan2(np.sin(b).mean(), np.cos(b).mean())) % 360

    def auto_solve(self):
        """Least-squares fit of the bearing history: fitted on Cadet / Training consoles only."""
        if not self.diff["ping_warning"]:
            return self.say("AUTO-SOLVE NOT FITTED - PLOT IT YOURSELF")
        result = self.tma.auto_solve(self.world.time, self.world.player, self.tdc)
        self.actions.add("AUTOSOLVE")
        if isinstance(result, str):
            return self.say(result)
        fit, ambiguous = result
        self.say(f"AUTO-SOLVE: FIT {fit:.1f} DEG. " + ("AMBIGUOUS - NEW LEG" if ambiguous else "CHECK IT"))

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
        elif wf.collidepoint(pos) and self.crt_page == "DAMAGE":
            rows = self.damage_rows()
            k = (y - wf.y - DC_ROW_Y0) // DC_ROW_H
            if 0 <= k < len(rows) and rows[k] in self.world.player.damaged:
                self.world.player.repair_first(rows[k])
                self.actions.add("REPAIR_FIRST")
                self.say(f"PARTY TO THE {rows[k]}")
        elif wf.collidepoint(pos) and self.crt_page == "TMA":  # the plot's x is true bearing round the TDC's
            centre = self.tma_centre()
            self.dial = (centre + (x - wf.centerx) / WF_W * PLOT_SPAN - self.world.player.heading) % 360
        elif wf.collidepoint(pos):
            self.dial_true = self.from_display((x - wf.x) / WF_W * 360)
            self.tracking = False
        elif math.hypot(x - SCOPE_C[0], y - SCOPE_C[1]) <= SCOPE_R:
            self.scope_click(pos)
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
            self.scope_brg = (self.scope_brg - dx * settings.SETTINGS["mouse"] * SCOPE_FOV[self.high_power] / EYE) % 360
            self.dragging = ("scope", pos[0])
        elif self.dragging == "wheel":
            ordered = (pos[0] - WHEEL_C[0]) / (WHEEL_R + 16) * MAX_RUDDER
            self.world.player.rudder = round(clamp(ordered, -MAX_RUDDER, MAX_RUDDER))

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
        elif CRT_RECT.collidepoint(pos) and self.crt_page == "SONAR":
            self.dial_true = (self.dial_true + dy) % 360
            self.tracking = False

    # --- simulation tick ---
    def update(self, dt, keys):
        self.teletype.update(dt)
        if self.dead:
            return
        p, world = self.world.player, self.world
        held = lambda action: keys[settings.code(action)]
        train = held("TRAIN RIGHT") - held("TRAIN LEFT")
        if self.looking:  # A/D train the scope; the hydrophone dial stays where it was
            self.scope_true = (self.scope_true + train * SCOPE_TRAIN_RATE[self.high_power] * dt) % 360
        else:
            self.dial_true = (self.dial_true + train * DIAL_RATE * dt) % 360
            self.tracking = self.tracking and not train  # a hand on the wheel takes the dial back
        rudder = held("RUDDER RIGHT") - held("RUDDER LEFT")
        if rudder:
            p.rudder = clamp(p.rudder + rudder * RUDDER_RATE * dt, -MAX_RUDDER, MAX_RUDDER)
        adj = held("TDC VALUE UP") - held("TDC VALUE DOWN")
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
        turned = angle_diff(p.heading, self.last_heading)
        self.last_heading = p.heading
        if not self.true_mode():  # ship's-head mode: dial and scope are fixed to the hull and swing with it
            self.dial_true = (self.dial_true + turned) % 360
            self.scope_true = (self.scope_true + turned) % 360
        for kind, a, b in self.frame_events:
            self.report(kind, a, b)
        self.recorder.sample(world, self.frame_events)
        self.tdc.update(dt)
        self.view = self.optics.look() if p.scope_up else None
        if self.wire_sel is not None and self.wire_sel not in world.torpedoes:
            self.wire_sel = None
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
            self.audio.play_echo(2500 / rng, brg)
            self.waterfall.blip(brg, 230)
            self.echoes.append((*offset(p.x, p.y, brg + p.heading, rng), world.time))
            self.last_echo = (brg, rng / YARD)
            tdc_true = bearing(0.0, 0.0, self.tdc.x, self.tdc.y)
            if abs(angle_diff(brg + p.heading, tdc_true)) < 3:  # an echo on the plotted target: range for TMA
                self.tma.add(world.time, brg + p.heading, "ECHO", rng)
            self.say(f"ECHO {brg:05.1f}R {rng / YARD:,.0f} YD")
        self.echoes = [e for e in self.echoes if world.time - e[2] < ECHO_FADE]
        rain = world.ocean.rain
        diesel = getattr(p, "snorkeling", False)
        if diesel:  # our own diesels thunder through the hull: the hydrophones are nearly deaf while we charge
            levels = levels / DIESEL_DEAFNESS
        self.waterfall.update(dt, bearings, levels, widths, rain, floor=DIESEL_FLOOR if diesel else 0.0,
                              heading=p.heading)
        gains = cone_gain(self.dial, bearings, self.diff["cone"])
        heard = gains * levels / 160
        self.signal = float(heard.max(initial=0.0)) / (1 + 2 * rain)
        self._track(dt, bearings, heard)
        self.spectrum.update(dt, world.time, gains, levels, kinds, rain + (0.35 if diesel else 0.0))
        self.audio.set_hydrophone(self.signal, self.dial)
        self.tma.update(world.time, p, self.locked, self.dial_true)
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

    def _track(self, dt, bearings, heard):
        """LOCK means the dial is ON the trace, not merely near it; once locked the dial follows the contact."""
        if self.signal < 0.15 or not len(heard):
            self.brg_err, self.locked, self.tracking = None, False, False
            return
        err = angle_diff(bearings[int(np.argmax(heard))], self.dial)  # noisy measured bearing: operator data
        self.brg_err = err if self.brg_err is None else self.brg_err + (err - self.brg_err) * min(1.0, dt * 4)
        lock = self.diff.get("lock_deg", 2.0)
        self.locked = self.signal > 0.5 and abs(self.brg_err) <= lock
        self.tracking = (self.tracking or self.locked) and self.signal > 0.3 and abs(self.brg_err) < 3 * lock
        if self.tracking:  # a tracker servo: the dial walks onto the smoothed bearing
            self.dial_true = (self.dial_true + self.brg_err * min(1.0, dt * 2)) % 360

    def jolt(self, strength):
        self.shake = max(self.shake, strength)
        self.flash = max(self.flash, strength * 0.8)

    def report(self, kind, a, b):
        """Turn world events into what the operator sees, reads and hears."""
        tt, world = self.teletype.print, self.world
        if kind == "WAVE":
            m, e, s, brg = b
            fuzz = 0 if self.diff["ping_warning"] else random.uniform(-25, 25)
            tt(f"DISPATCH WAVE {a}: CONVOY OF {m} MERCHANTS, {e} ESCORT(S) REPORTED NEAR "
               f"{(brg + fuzz) % 360:03.0f} TRUE, "
               f"8 KM." + (f" {s} HOSTILE SUBMARINE(S) SUSPECTED." if s else "") + " ATTACK AT DISCRETION.")
            return
        if kind == "WAVE_CLEAR":
            torps, decoys = b
            tt(f"WAVE {a} DISPERSED. TENDER RESUPPLY: +{torps} TORPEDOES{' (RACKS FULL)' if torps < 4 else ''}, "
               f"+{decoys} NOISEMAKERS{' (LOCKER FULL)' if decoys < 2 else ''}. TOTAL {self.score:,} GRT.")
            return
        if kind == "ESCAPED":
            if a.kind == "MERCHANT":
                tt("CONVOY STRAGGLER HAS SLIPPED OUT OF RANGE.")
            return
        if kind == "WIRE_CUT":
            self.say(f"T{a.tube} WIRE PARTED - " + ("TOO FAST" if b == "SPEED" else "END OF SPOOL"))
            return
        if kind == "DAMAGE":
            tt(f"DAMAGE CONTROL: {', '.join(b)} DAMAGED. ONE PARTY WORKS THE LIST TOP FIRST - "
               + settings.keyed("{DAMAGE BOARD} TO SET IT."))
            return
        if kind == "REPAIRED":
            self.say(f"{b} REPAIRED")
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
                tt(settings.keyed(teletype))
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
            self.audio.play_explosion(loud, self.passive.bearing_of(a))
            self.jolt(loud * 0.7)
            if b >= 1:
                self.audio.play_creak(1.0)
                self.say(f"CHARGE CLOSE. HULL {world.hull:.0f}%")
            return
        brg = self.passive.bearing_of(a)
        if isinstance(a, Torpedo) and a.hostile:
            if kind == "DECOYED":
                self.audio.play_explosion(self.passive.loudness(a), brg)
                self.jolt(0.3)
                self.say(f"DETONATION {brg:05.1f}R. DECOY TOOK IT")
            return  # nothing else about their fish is observable
        if kind == "HOSTILE_LAUNCH":
            if self.passive.loudness(a, ref=6000.0) > 0.05:
                self.say(f"LAUNCH TRANSIENT {brg:05.1f}R!")
                tt(f"CONN, SONAR: TORPEDO IN THE WATER, BEARING {brg:03.0f} RELATIVE.")
        elif kind == "ESCORT_PING":
            self.audio.play_enemy_ping(self.passive.loudness(a, ref=5000.0), brg)
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
                   ("ESCORT", "AI_WITHDRAW"): "REVS UP, OPENING",
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
            self.audio.play_hiss(max(0.4, self.passive.loudness(a)), brg)
            self.say(f"HISS {brg:05.1f}R. COUNTERMEASURE")
        elif kind in ("ARMED", "HOMING", "LOST"):
            self.say(f"T{a.tube} " + {"ARMED": "SEEKER ACTIVE", "HOMING": "HOMING", "LOST": "LOST LOCK"}[kind])
        elif kind == "EXHAUSTED":
            self.say(f"T{a.tube} FUEL OUT. " + ("DECOYED" if isinstance(b, Decoy) else "MISS"))
        elif kind in ("HIT", "DECOYED"):
            self.audio.play_explosion(self.passive.loudness(a, ref=4000.0), brg)
            self.waterfall.blip(brg, 255)
            self.jolt(0.25)
            self.say(f"T{a.tube} DETONATION {brg:05.1f}R")
            if kind == "HIT":
                self.say("BREAKUP NOISES. SUNK")
                tt(f"CONFIRMED: {b.kind} SUNK. {self.score:,} GRT TOTAL.")
            else:
                self.say("NO BREAKUP. DECOYED")
