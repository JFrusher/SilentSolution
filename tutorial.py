"""Training patrol: a scripted walk through every station, then live drills against each threat.
Runs on top of an ordinary Console. It scripts the world (it may read ground truth to grade the trainee)
and only talks to the trainee through the console: teleprinter, order slip, highlighted controls."""
import math
from dataclasses import dataclass
from typing import Callable

from ai import PATROL, EscortAI, SubmarineAI
from sim import KNOT, YARD, Vessel, angle_diff, bearing
from tuning import DIFFICULTY

# Cadet rules with a working battery (for the snorkel drill) and a homing enemy fish (for the decoy drill)
TRAINING = dict(DIFFICULTY["CADET"], battery=True, enemy_torp_kt=35, enemy_seeker_yd=800, beam_width=2.0)
HULL_FLOOR = 25.0  # training warheads: shaken, never sunk
CHAPTERS = {  # chapter -> what it covers; each starts at the step tagged with its name
    "STATION DRILL": "EVERY CONTROL: TELEGRAPH, HELM, DIVING, BLOW, PAGES",
    "SONAR AND FIRE CONTROL": "WATERFALL, PROFILE, MARK, PING, TDC, TMA PLOT",
    "THE PERISCOPE": "MASTS, EYEPIECE, MARKS, BEING SEEN, SNORKEL, A LIVE SHOT",
    "LIVE EXERCISES": "WEATHER, ESCORT ATTACK, DAMAGE CONTROL, TORPEDO, SUB HUNT",
}


@dataclass
class Step:
    brief: str | Callable          # teleprinter text, or con -> text (built after setup runs)
    goal: str | Callable           # short order pinned on the slip
    done: Callable                 # (tutorial, con) -> bool
    setup: Callable | None = None  # (tutorial, con) -> None, once on entry
    highlight: tuple = ()          # workstation parts to ring
    outro: str | Callable = ""     # printed on completion
    chapter: str = ""              # first step of this chapter


def _spawn(world, rel_brg, rng_m, course, speed, **kw):
    p = world.player
    b = math.radians(p.heading + rel_brg)
    ship = Vessel(p.x + rng_m * math.sin(b), p.y + rng_m * math.cos(b), course % 360, speed, **kw)
    world.targets.append(ship)
    return ship


def _clear(world):
    world.targets.clear()
    world.ais.clear()
    world.torpedoes.clear()
    world.charges.clear()
    if hasattr(world.player, "damaged"):
        world.player.damaged.clear()


def _kt(con):
    return con.world.player.ordered_speed / KNOT


def _hostiles(con):
    return [t for t in con.world.torpedoes if t.hostile]


class Tutorial:
    def __init__(self, con, chapter=0):
        self.con = con
        con.tutorial = self
        con.world.director = None  # the tutorial places every contact itself
        con.world.min_hull = HULL_FLOOR
        con.world.systems_damage = False  # only the damage-control drill breaks things
        o = con.world.ocean
        o.rain = o.front = 0.0
        o.timer = 1e9  # the instructor orders the weather
        con.teletype.cps = 70.0
        self.steps = self._script()
        name = list(CHAPTERS)[chapter]
        self.i = next(i for i, s in enumerate(self.steps) if s.chapter == name) - 1
        self.timer = 0.0
        self.memo = {}
        self.merchant = self.escort = self.sub = None
        self.finished = False
        self.advance()

    @property
    def step(self):
        return self.steps[min(self.i, len(self.steps) - 1)]

    @property
    def goal(self):
        g = self.step.goal
        return g(self.con) if callable(g) else g

    @property
    def progress(self):
        return f"{min(self.i + 1, len(self.steps))}/{len(self.steps)}"

    def advance(self):
        self.i += 1
        if self.i >= len(self.steps):
            self.finished = True
            return
        self.con.actions.clear()
        self.timer = 0.0
        self.memo = {}
        step = self.step
        if step.setup:
            step.setup(self, self.con)
        brief = step.brief(self.con) if callable(step.brief) else step.brief
        self.con.teletype.print(f"DRILL {self.progress}: {brief}")

    def update(self, dt):
        if self.finished:
            return
        con = self.con
        self.timer += dt
        con.world.player.torpedoes = max(con.world.player.torpedoes, 4)  # training racks never run dry
        if "SKIP" in con.actions:
            con.teletype.print("INSTRUCTOR: DRILL SKIPPED.")
            return self.advance()
        for kind, a, b in con.frame_events:
            self._watch(kind, a, b)
        if con.teletype.queue or self.timer < 0.5:  # let the order finish printing first
            return
        if self.step.done(self, con):
            outro = self.step.outro
            outro = outro(self, con) if callable(outro) else outro
            if outro:
                con.teletype.print(outro)
            self.advance()

    def _watch(self, kind, a, b):
        """Running commentary for the live drills."""
        con, tt = self.con, self.con.teletype.print
        hostile = getattr(a, "hostile", False)
        if kind == "EXHAUSTED" and not hostile and self.merchant in con.world.targets:
            tt("INSTRUCTOR: MISS. CHECK TGT SPD/CRS - THE TDC TICK MUST SIT ON THE TRACE. RE-MARK (M) "
               "AND FIRE AGAIN WHEN A TUBE RELOADS.")
        elif kind in ("DECOYED", "PLAYER_HIT", "EXHAUSTED") and hostile:
            self.memo["outcome"] = kind
        elif kind == "PLAYER_HIT":
            self.memo["outcome"] = kind
        elif kind == "CHARGES":
            self.memo.setdefault("charges_at", self.timer)

    # ------------------------------------------------------------------ the syllabus
    def _script(self):
        S = Step
        return [
            # --- station drill: every command ---
            S("WELCOME ABOARD. THIS DRILL WALKS YOU THROUGH EVERY STATION, THEN LIVE EXERCISES. YOUR CURRENT "
              "ORDER IS PINNED ON THE SLIP ABOVE; THE PART OF THE STATION YOU NEED GLOWS. F1 SHOWS THE KEY CARD; "
              "F6 SKIPS A DRILL.",
              "PRESS ENTER (OR CLICK THIS SLIP)", lambda t, c: "ENTER" in c.actions, chapter="STATION DRILL"),
            S("ENGINEERING GAUGES, TOP RIGHT: DEPTH WITH HULL PRESSURE IN PSI (RED PAST 250 M IS CRUSH DEPTH), "
              "BATTERY, SELF NOISE (RED MEANS CAVITATION - ENEMIES HEAR IT), HULL INTEGRITY.",
              "STUDY THE GAUGES - ENTER", lambda t, c: "ENTER" in c.actions, highlight=("gauges",)),
            S("THE ALARM PANEL HAS A LIT TILE FOR EVERY SOUND CUE, LEGEND PRINTED ON IT: ENEMY SONAR, TORPEDO, CAVITATION, DIESEL, MASTS UP (RED "
              "WHEN YOU ARE LIKELY TO BE SEEN), BROACH, LEAK, HULL STRESS, BELOW LAYER. THIS BOAT CAN BE FOUGHT "
              "WITH THE SOUND OFF.",
              "STUDY THE LAMPS - ENTER", lambda t, c: "ENTER" in c.actions, highlight=("lamps",)),
            S("ENGINE ORDER, BOTTOM LEFT: Z / X OR PRESS A LIT BUTTON. THE LEDS SHOW ORDERED AND ACTUAL KNOTS. RING UP HALF.",
              "RING UP HALF  (X, PRESS HALF)", lambda t, c: _kt(c) == 8, highlight=("telegraph",)),
            S("SPEED IS NOISE. RING UP FLANK AND WATCH THE SELF NOISE NEEDLE SWING INTO THE RED AS THE SCREWS "
              "CAVITATE. DEEPER WATER LETS YOU RUN FASTER BEFORE THEY BOIL.",
              "RING UP FLANK UNTIL CAVITATING", lambda t, c: c.world.player.cavitating,
              highlight=("telegraph", "noise", "lamps"), outro="CAVITATING: EVERY ENEMY IN RANGE CAN HEAR YOU NOW."),
            S("QUIET AGAIN: RING DOWN TO SLOW.", "RING DOWN TO SLOW  (Z)",
              lambda t, c: _kt(c) == 4 and not c.world.player.cavitating, highlight=("telegraph", "noise")),
            S("HELM: LEFT / RIGHT ARROWS OR DRAG THE CONTROL YOKE. PUT ON RUDDER AND COME ROUND 30 DEGREES. "
              "THE BOAT ONLY ANSWERS THE HELM WITH WAY ON.",
              "TURN 30 DEG  (LEFT/RIGHT, DRAG YOKE)",
              lambda t, c: abs(angle_diff(c.world.player.heading, t.memo["h0"])) >= 30,
              setup=lambda t, c: t.memo.update(h0=c.world.player.heading), highlight=("wheel",)),
            S("RUDDER AMIDSHIPS: PRESS C OR CENTRE THE YOKE.", "RUDDER AMIDSHIPS  (C)",
              lambda t, c: abs(c.world.player.rudder) < 1, highlight=("wheel",)),
            S("DIVING STATION: Q / E OR CLICK THE ORDER DIAL. THE RED POINTER IS YOUR ORDER, THE THIN ONE THE "
              "ACTUAL DEPTH. ORDER 90 METRES.", "ORDER 90 M AND REACH IT  (E)",
              lambda t, c: c.world.player.ordered_depth >= 90 and c.world.player.z >= 88, highlight=("depth",)),
            S("HOLD: PRESS H OR THE HOLD BUTTON TO KEEP THE DEPTH YOU ARE AT.", "HOLD DEPTH  (H)",
              lambda t, c: "HOLD" in c.actions, highlight=("depth",)),
            S("EMERGENCY BLOW: PRESS B. COMPRESSED AIR DRIVES THE BOAT STRAIGHT UP TO PERISCOPE DEPTH (15 M). "
              "IT IS VERY LOUD - SAVE IT FOR FLOODING OR A FISH ON YOUR TAIL.",
              "BLOW MAIN BALLAST  (B)", lambda t, c: c.world.player.z <= 16, highlight=("depth",)),
            S("BACK DOWN TO PERISCOPE-SAFE DEPTH: ORDER 60 METRES.", "ORDER 60 M AND REACH IT  (E)",
              lambda t, c: c.world.player.z >= 55, highlight=("depth",)),

            # --- sensors and fire control on a live merchant ---
            S("A MERCHANT IS ON THE WATERFALL - THE BRIGHT VERTICAL TRACE. THE RED LINE IS YOUR HYDROPHONE DIAL: "
              "A / D OR CLICK THE WATERFALL. PUT IT ON THE TRACE UNTIL SIG READS LOCK.",
              "DIAL ONTO THE TRACE: SIG = LOCK  (A/D, CLICK)", lambda t, c: c.signal > 0.5,
              setup=self._spawn_merchant, highlight=("waterfall",), chapter="SONAR AND FIRE CONTROL"),
            S("THE ACOUSTIC PROFILE IS THE SPECTRUM OF WHATEVER THE DIAL HEARS. EVEN LOW PEAKS ARE A SLOW 2-BLADE "
              "MERCHANT SHAFT. THE LIBRARY BELOW IT MATCHES THE SHAPE: WARSHIPS WHINE HIGH, SUBS SHOW ONE FAINT "
              "LINE, TORPEDOES A SHARP HIGH SPIKE, NOISEMAKERS A FLAT WALL.",
              "KEEP THE DIAL ON IT: CLASS = MERCHANT", lambda t, c: c.classification == "MERCHANT",
              highlight=("spectrum",)),
            S("PRESS M TO MARK THE DIAL BEARING INTO THE TORPEDO DATA COMPUTER. THE BRIGHT TICKS ON THE TOP AND "
              "BOTTOM EDGE OF THE WATERFALL SHOW WHERE THE TDC THINKS THE TARGET IS.",
              "MARK BEARING  (M)", lambda t, c: "MARK" in c.actions, highlight=("tdc", "waterfall")),
            S("PASSIVE SONAR GIVES BEARING ONLY. FOR RANGE, PING: SPACE OR THE PING BUTTON. WATCH THE RING SPREAD "
              "ON THE TACTICAL SCOPE - THE ECHO'S DELAY GIVES RANGE. EVERY ENEMY IN EARSHOT HEARS IT TOO.",
              "PING (SPACE) AND WAIT FOR THE ECHO", lambda t, c: c.last_echo is not None,
              setup=lambda t, c: setattr(c, "last_echo", None), highlight=("scope", "ping")),
            S(lambda c: f"ECHO AT {c.last_echo[1] if c.last_echo else 2500:,.0f} YD. W / S SELECTS A TDC ROW (OR CLICK IT); UP / DOWN OR "
                        "THE MOUSE WHEEL ADJUSTS - HOLD TO RUN FAST. SET TGT RNG TO THE ECHO RANGE.",
              "SET TGT RNG = ECHO RANGE  (W/S, UP/DOWN)",
              lambda t, c: abs(c.tdc.get("RNG") * YARD - c.world.player.range_to(t.merchant)) < 400 * YARD,
              highlight=("tdc",)),
            S("F2 FLIPS THE LEFT OF THE MONITOR TO THE TMA PLOT: TRUE BEARING ACROSS, TIME DOWN. EVERY BEARING YOU "
              "HOLD WITH THE DIAL, MARK OR PING IS A DOT; THE BRIGHT CURVE IS WHERE THE TDC SAYS THE TARGET SHOULD "
              "HAVE BEEN.", "OPEN THE TMA PLOT  (F2)", lambda t, c: c.crt_page == "TMA", highlight=("waterfall",)),
            S(lambda c: f"TARGET MOTION ANALYSIS: SET TGT SPD AND TGT CRS UNTIL THE CURVE RUNS THROUGH THE DOTS AND THE "
                        f"FIT READS UNDER A DEGREE - F4 AUTO-SOLVES IN TRAINING. THEN F2 BACK TO THE WATERFALL. "
                        f"INTEL: ABOUT {self.merchant.speed / KNOT:.0f} KNOTS, COURSE ABOUT "
                        f"{round(self.merchant.heading / 10) * 10:03.0f}. RE-MARK (M) IF THE TICK HAS DRIFTED.",
              "SET TGT SPD AND TGT CRS, THEN F2",
              lambda t, c: abs(c.tdc.get("SPD") - t.merchant.speed / KNOT) <= 1.5 and c.crt_page == "SONAR" and
              abs(angle_diff(c.tdc.get("CRS"), t.merchant.heading)) <= 15, highlight=("tdc", "waterfall")),

            # --- the periscope: seeing, and being seen ---
            S("PERISCOPE DEPTH: G OR THE P.D. BUTTON ORDERS 15 METRES. MASTS CAN ONLY BE RAISED AT 18 M OR "
              "SHALLOWER.", "PERISCOPE DEPTH  (G, P.D. BUTTON)", lambda t, c: c.world.player.z <= 16,
              setup=self._ensure_merchant, highlight=("depth",), chapter="THE PERISCOPE"),
            S("UP SCOPE: U OR THE SCOPE SWITCH. THEN V OR LOOK PUTS YOUR EYE TO IT. AT THE EYEPIECE YOU CANNOT SEE "
              "THE STATION - THE STRIP ALONG THE BOTTOM STILL CARRIES THE WARNINGS.",
              "UP SCOPE (U) AND LOOK (V)", lambda t, c: c.looking, highlight=("masts",)),
            S(lambda c: f"TRAIN THE SCOPE: A / D OR DRAG ACROSS THE EYEPIECE. TAB OR THE MOUSE WHEEL SWITCHES TO "
                        f"HIGH POWER (6X). THE MERCHANT BEARS ABOUT {self._merchant_rel(c):03.0f} RELATIVE - PUT HER IN "
                        "THE WIRES.",
              "MERCHANT IN THE WIRES, HIGH POWER  (A/D, TAB)", self._merchant_in_wires),
            S("PRESS M: THE EXACT BEARING AND A RANGEFINDER RANGE (HER KNOWN MAST HEIGHT AGAINST THE GRADUATIONS) "
              "GO STRAIGHT INTO THE TDC - FAR BETTER THAN SONAR. HER BOW TELLS YOU WHICH WAY SHE IS HEADING.",
              "MARK  (M)", lambda t, c: "SCOPE_MARK" in c.actions and c.scope_fix is not None),
            S("EVERY SECOND THE SCOPE IS UP YOU CAN BE SEEN. THE EXPOSURE METER ON THE RIGHT PLATE IS THE RISK PER "
              "MINUTE; SPEED THROWS A FEATHER OF SPRAY. LOOK BRIEFLY, THEN GET IT DOWN: V BACK TO THE STATION, "
              "U DOWN SCOPE.", "BACK (V) AND DOWN SCOPE (U)",
              lambda t, c: not c.looking and not c.world.player.scope_up, highlight=("masts", "lamps")),
            S("SKR ARM IS HOW FAR THE FISH RUNS BEFORE ITS SEEKER WAKES. RUN DEP: SHALLOW (10 M) FOR SHIPS, DEEP "
              "FOR SUBS UNDER THE LAYER. GYRO AND RUN SHOW THE SOLUTION; A GREEN LAMP MEANS IN RANGE. FIRE WITH F, "
              "1 / 2, OR FLIP A TUBE SWITCH. TUBES RELOAD FROM THE RACKS (UNLIMITED IN TRAINING). THE RUN TAKES A MINUTE OR TWO - WATCH YOUR FISH AS RED DOTS ON THE SCOPE.",
              "SINK THE MERCHANT  (F, TUBE SWITCH)", lambda t, c: t.merchant in c.world.sunk,
              highlight=("tdc", "tubes"), outro="INSTRUCTOR: TARGET DESTROYED. WELL SHOT."),
            S("BATTERY IS DOWN TO 55%. AT PERISCOPE DEPTH (G), RAISE THE SNORKEL: K OR THE SNORT SWITCH. THE DIESELS "
              "CHARGE THE BATTERY, BUT THEIR ROAR DEAFENS YOUR OWN SONAR - WATCH THE WATERFALL FOG OVER - AND THE "
              "EXHAUST CAN BE SEEN. KEEP UNDER 8 KNOTS OR THE HEAD FLOODS.",
              "SNORKEL (K): CHARGE TO 60%", lambda t, c: c.world.player.snorkeling and c.world.player.battery >= 60,
              setup=lambda t, c: setattr(c.world.player, "battery", 55.0),
              highlight=("masts", "battery", "waterfall")),
            S("SECURE SNORKELLING WITH K - OR JUST ORDER DEEP: THE MASTS ARE HOUSED AUTOMATICALLY BELOW 20 M. "
              "ORDER 60 METRES.", "SNORKEL DOWN, ORDER 60 M",
              lambda t, c: not c.world.player.snorkel_up and c.world.player.z >= 55, highlight=("masts", "depth")),
            S("THE SCOPE RANGE: T CYCLES 5,000 / 10,000 / 20,000 YARDS. CLICKING THE SCOPE DOES TOO, UNLESS A FISH "
              "IS ON THE WIRE - THEN THE CLICK STEERS IT.",
              "CHANGE SCOPE RANGE  (T)", lambda t, c: "SCOPE" in c.actions, highlight=("scope",)),

            # --- live exercises ---
            S("WEATHER: A STORM IS PASSING OVERHEAD. RAIN HISS FLOODS THE WATERFALL AND THE PROFILE; WEAK CONTACTS "
              "DROWN AND SEA READS STORM. ON PATROL THE WEATHER CHANGES ON ITS OWN.",
              "WATCH THE NOISE FLOOR - ENTER", lambda t, c: "ENTER" in c.actions, setup=self._storm,
              chapter="LIVE EXERCISES",
              highlight=("waterfall", "spectrum"), outro="THE STORM IS EASING."),
            S("EXERCISE: AN ESCORT HEARD YOUR PING AND IS RUNNING IN AT 24 KNOTS - ITS TRACE BRIGHTENS AS IT REVS "
              "UP. ITS PINGS FLASH THE ENEMY SONAR LAMP AND A RED LINE ON THE SCOPE. GET UNDER THE LAYER (BELOW "
              "100 M), RING DOWN TO SLOW AND OPEN THE RANGE. SURVIVE ITS ATTACK UNTIL IT GIVES UP.",
              "DIVE BELOW 100 M, GO SLOW, EVADE",
              self._escort_done, setup=self._spawn_escort,
              highlight=("depth", "telegraph", "lamps"),
              outro=self._escort_outro),
            S("COME BACK UP TO 60 METRES AND RING UP SLOW FOR THE NEXT EXERCISE.", "ORDER 60 M AND SLOW",
              lambda t, c: c.world.player.z <= 70 and _kt(c) == 4, setup=lambda t, c: _clear(c.world),
              highlight=("depth", "telegraph")),
            S("DAMAGE CONTROL: THAT PATTERN SPRANG THE BOAT - HYDROPHONES, PLANES AND TUBE 2 ARE OUT. ONE PARTY "
              "WORKS DOWN THE LIST, TOP FIRST. F5 OPENS THE DAMAGE BOARD: CLICK A LINE TO SEND THE PARTY THERE "
              "FIRST. JAMMED PLANES CAN'T PULL YOU OUT OF A DIVE - PUT THEM FIRST, THEN F5 BACK TO THE WATERFALL.",
              "F5, PLANES FIRST, F5 BACK",
              lambda t, c: "REPAIR_FIRST" in c.actions and c.crt_page == "SONAR" and
              next(iter(c.world.player.damaged), None) == "PLANES",
              setup=lambda t, c: c.world.player.break_systems(["HYDROPHONES", "PLANES", "TUBE 2"]),
              highlight=("waterfall",),
              outro="INSTRUCTOR: GOOD. FOR THE EXERCISE THE DAMAGE IS MADE GOOD; ON PATROL HITS BREAK SYSTEMS AT "
                    "RANDOM AND THE PARTY TAKES MINUTES OVER EACH."),
            S("TORPEDO IN THE WATER! AN ENEMY SUBMARINE HAS FIRED ON YOU. THE TORPEDO LAMP FLASHES AND ITS TRACE IS "
              "BRIGHT AND NARROW, BEARING MOVING FAST. PUT THE DIAL ON IT: THE PROFILE SHOWS A SHARP HIGH SPIKE.",
              "CLASSIFY THE INCOMING FISH: CLASS = TORPEDO",
              lambda t, c: c.classification == "TORPEDO" or t.timer > 25 or not _hostiles(c),
              setup=self._spawn_sub_and_fire, highlight=("waterfall", "spectrum", "lamps")),
            S("IT IS HOMING ON YOU. WHEN IT CLOSES, DROP A NOISEMAKER (N) AND RING DOWN TO SLOW - A LOUD BOAT "
              "OUTSHOUTS ITS OWN DECOY. TURN AWAY, OR DIVE UNDER THE LAYER TO BREAK ITS LOCK.",
              "NOISEMAKER (N) WHEN CLOSE, THEN GO QUIET", lambda t, c: not _hostiles(c) and t.timer > 1,
              highlight=("nmkr", "telegraph", "depth"), outro=self._torpedo_outro),
            S("COUNTER-ATTACK: THE SUBMARINE IS STILL OUT THERE, STALKING YOU. FIND ITS FAINT NARROW LINE "
              "(CLASS SUBMARINE), MARK IT, PING FOR RANGE, SET RUN DEP TO 60 M AND SKR ARM SHORT (500 YD), "
              "THEN FIRE. THE SEEKER WILL HOME.",
              "SINK THE SUBMARINE",
              lambda t, c: t.sub in c.world.sunk or t.timer > 360, highlight=("waterfall", "spectrum", "tdc"),
              outro=lambda t, c: "INSTRUCTOR: SUBMARINE DESTROYED." if t.sub in c.world.sunk
              else "INSTRUCTOR: EXERCISE TIME. THE TARGET SUB IS BEING RECALLED."),

            # --- graduation ---
            S("DRILL COMPLETE: YOU HAVE WORKED EVERY STATION. ON PATROL, CONVOYS ARRIVE IN WAVES WITH ESCORTS "
              "(DEPTH CHARGES, NOISEMAKERS) AND SUBMARINES (RETURN FIRE). HITS BREAK SYSTEMS FOR THE DAMAGE PARTY "
              "(F5). YOU ARE RESUPPLIED BETWEEN WAVES. "
              "COMMANDER ADDS A REAL BATTERY YOU MUST SNORKEL TO CHARGE; IRON CAPTAIN ADDS OXYGEN, FLOODING LEAKS, "
              "SHARPER LOOKOUTS, A SCOPE THAT BENDS AT SPEED AND A LAYER THAT HIDES CONTACTS COMPLETELY. "
              "GOOD HUNTING.",
              "TRAINING COMPLETE - ENTER FOR THE TITLE", lambda t, c: "ENTER" in c.actions, setup=lambda t, c: _clear(c.world)),
        ]

    # ------------------------------------------------------------------ periscope grading
    def _merchant_rel(self, con):
        p = con.world.player
        return (bearing(p.x, p.y, self.merchant.x, self.merchant.y) - p.heading) % 360

    def _merchant_in_wires(self, t, con):
        if not (con.looking and con.high_power and con.view):
            return False
        seen = next((s for s in con.view[0] if s.uid == id(self.merchant)), None)
        aim = (con.scope_brg + con.world.player.heading) % 360
        return seen is not None and abs(angle_diff(seen.brg, aim)) < 1.0

    # ------------------------------------------------------------------ scenario setups
    def _spawn_merchant(self, t, con):
        _clear(con.world)
        rel = 45.0
        self.merchant = _spawn(con.world, rel, 2500 * YARD, con.world.player.heading + rel + 100, 8 * KNOT, noise=1.1)

    def _ensure_merchant(self, t, con):
        """The periscope chapter can be started on its own: give it the merchant the sonar chapter spawns."""
        if self.merchant not in con.world.targets:
            self._spawn_merchant(t, con)

    def _storm(self, t, con):
        o = con.world.ocean
        o.rain, o.front = 1.0, 0.0  # storm now, clearing over the next minute

    def _spawn_escort(self, t, con):
        _clear(con.world)
        w = con.world
        w.ocean.rain = w.ocean.front = 0.0
        self.escort = _spawn(w, 120.0, 1800.0, w.player.heading + 300, 0.0)
        self.escort_ai = EscortAI(self.escort, self.escort.heading, charges=10, decoys=0, aggression=0.5,
                                  detect_radius=2500.0)
        w.ais.append(self.escort_ai)
        self.escort_ai._mark(w, 150.0)  # it heard the earlier ping
        self.escort_ai.alarm = True

    def _escort_done(self, t, con):
        survived = "charges_at" in self.memo and self.timer - self.memo["charges_at"] > 40
        return self.escort_ai.state == PATROL or survived or self.timer > 240

    def _escort_outro(self, t, con):
        if self.escort_ai.state == PATROL:
            return "INSTRUCTOR: THE ESCORT HAS LOST YOU. THE LAYER IS YOUR FRIEND."
        if "charges_at" in self.memo:
            return (f"INSTRUCTOR: YOU RODE OUT A PATTERN - HULL {con.world.hull:.0f}%. CHARGES ARE SET TO A GUESSED "
                    "DEPTH: DEEP AND MOVING IS HARD TO HIT. EXERCISE ENDED.")
        return "INSTRUCTOR: EXERCISE TIME. THE ESCORT IS BEING RECALLED."

    def _spawn_sub_and_fire(self, t, con):
        w = con.world
        w.player.damaged.clear()  # the damage-control drill's damage is made good
        self.sub = _spawn(w, 300.0, 1800.0, w.player.heading + 120, 0.0, z=60.0)
        ai = SubmarineAI(self.sub, self.sub.heading, stealth=0.5, top_speed=12 * KNOT, aggression=0.8,
                         detect_radius=4000.0, layer_sensitivity=0.0, torpedo_speed=TRAINING["enemy_torp_kt"] * KNOT,
                         seeker_range=TRAINING["enemy_seeker_yd"] * YARD, torpedoes=1, zigzag=False)
        w.ais.append(ai)
        ai._mark(w, 30.0)
        events = []
        ai._fire(w, events)
        for kind, a, b in events:
            con.report(kind, a, b)

    def _torpedo_outro(self, t, con):
        return {"DECOYED": "INSTRUCTOR: IT TOOK THE DECOY. TEXTBOOK.",
                "PLAYER_HIT": "INSTRUCTOR: YOU WERE HIT - TRAINING WARHEAD. IN COMBAT THAT COSTS 50-90% OF THE HULL.",
                }.get(t.memo.get("outcome"), "INSTRUCTOR: IT RAN OUT OF FUEL. YOU OUTRAN IT.")
