"""The crew: they take the captain's orders and man the stations he isn't at. Operator side, like Console: every
order is carried out through the same Console methods a player's hands use, so the crew has no back door into the
world. Orders are acknowledged at once and carried out after the crew's reaction time."""
from sim import MAX_RUDDER, TELEGRAPH, angle_diff, clamp

REPORT_GAP = 45.0   # s before sonar reports the same contact again
MARK_EVERY = 20.0   # s between the fire-control man's marks while sonar holds a contact
NEW_BEARING = 12.0  # deg away from the last report that makes a contact new


def rudder_words(angle):
    if angle == 0:
        return "RUDDER AMIDSHIPS"
    return f"{'RIGHT' if angle > 0 else 'LEFT'} {'FULL' if abs(angle) >= MAX_RUDDER else f'{abs(angle):.0f}'} RUDDER"


# order -> (who answers, what he says back, what he does). The words take the order's argument.
ORDERS = {
    "RUDDER": ("HELM", rudder_words, lambda crew, a: crew.steer(None, a)),
    "COURSE": ("HELM", lambda c: f"COME TO {c % 360:03.0f}", lambda crew, c: crew.steer(c % 360)),
    "STEADY": ("HELM", lambda _: "STEADY AS SHE GOES", lambda crew, _: crew.steer(crew.con.world.player.heading)),
    "ENGINES": ("MANEUVERING", lambda i: f"ALL AHEAD {TELEGRAPH[i][0]}" if i else "ALL STOP",
                lambda crew, i: crew.con.telegraph(i)),
    "DEPTH": ("PLANES", lambda d: f"MAKE YOUR DEPTH {d:.0f} METRES", lambda crew, d: crew.con.order_depth(d)),
    "PERISCOPE DEPTH": ("PLANES", lambda _: "PERISCOPE DEPTH", lambda crew, _: crew.con.periscope_depth()),
    "HOLD DEPTH": ("PLANES", lambda _: "HOLD THIS DEPTH", lambda crew, _: crew.con.hold_depth()),
    "FIRE": ("FIRE CONTROL", lambda t: "FIRE SALVO" if t is None else f"FIRE TUBE {t + 1}",
             lambda crew, t: crew.con.fire(t)),
    "NOISEMAKER": ("FIRE CONTROL", lambda _: "LAUNCH NOISEMAKER", lambda crew, _: crew.con.noisemaker()),
    "PING": ("SONAR", lambda _: "ONE PING", lambda crew, _: crew.con.ping()),
    "BLOW": ("CHIEF", lambda _: "EMERGENCY BLOW", lambda crew, _: crew.con.blow()),
    "SCOPE": ("CHIEF", lambda _: "PERISCOPE", lambda crew, _: crew.con.toggle_scope()),
    "SNORKEL": ("CHIEF", lambda _: "SNORKEL", lambda crew, _: crew.con.toggle_snorkel()),
    "CRASH DIVE": ("CHIEF", lambda _: "CRASH DIVE", lambda crew, _: crew.crash_dive()),
    "EVADE": ("HELM", lambda side: f"EVADE {'RIGHT' if side > 0 else 'LEFT'}", lambda crew, side: crew.evade(side)),
}


class Crew:
    """Orders in flight, the helmsman's standing course, and the watch kept at stations the captain has left."""

    def __init__(self, con):
        self.con = con
        self.pending = []      # (due time, order, argument)
        self.course = None     # ordered course the helmsman steers to, or None
        self.captain_at = "SONAR"  # the station the captain is working himself, or None on his feet
        self.reported = (None, -1e9)  # last contact sonar reported: (true bearing, time)
        self.marked = -1e9

    @property
    def delay(self):
        return self.con.diff["crew_delay"]

    def order(self, name, arg=None):
        """The captain's order: acknowledged now, carried out after the crew's reaction time."""
        who, words, _ = ORDERS[name]
        self.con.say(f"{who}, AYE: {words(arg)}")
        self.pending.append((self.con.world.time + self.delay, name, arg))

    def steer(self, course=None, rudder=None):
        """The helmsman: a standing course to steer to, or a rudder angle and no course."""
        self.course = course
        if rudder is not None:
            self.con.world.player.rudder = float(clamp(rudder, -MAX_RUDDER, MAX_RUDDER))

    def hand_on_wheel(self):
        """The captain has taken the wheel himself: any standing course is off."""
        if self.course is not None:
            self.course = None
            self.con.say("HELM: COURSE ORDER CANCELLED")

    def crash_dive(self):
        p = self.con.world.player
        self.con.telegraph(len(TELEGRAPH) - 1)
        self.con.order_depth(max(p.z + 60, 150.0))
        if p.scope_up or p.snorkel_up:
            p.lower_masts()

    def evade(self, side):
        self.con.telegraph(len(TELEGRAPH) - 1)
        self.steer(None, side * MAX_RUDDER)

    def update(self, dt, bearings, heard):
        now = self.con.world.time
        due = [o for o in self.pending if o[0] <= now]
        self.pending = [o for o in self.pending if o[0] > now]
        for _, name, arg in due:
            ORDERS[name][2](self, arg)
        if self.course is not None:
            self._helm()
        if self.captain_at != "SONAR":
            self._sonar(dt, bearings, heard)

    def _helm(self):
        """Rudder from the heading error, eased off as she comes round so she settles on the course."""
        p = self.con.world.player
        err = angle_diff(self.course, p.heading)
        p.rudder = float(round(clamp(err * 1.2, -MAX_RUDDER, MAX_RUDDER)))
        if abs(err) < 0.5:
            p.rudder = 0.0

    def _sonar(self, dt, bearings, heard):
        """The sonarman keeps the dial on the loudest contact; fire control marks it; new contacts are reported."""
        con = self.con
        if len(heard) and not con.tracking:
            target = bearings[int(heard.argmax())]  # relative bearing he hears it on: operator data, not truth
            step = angle_diff(target, con.dial)
            con.dial = con.dial + clamp(step, -60 * dt, 60 * dt)  # trains the dial like a hand would
        if not con.locked:
            return
        now, true = con.world.time, (con.dial + con.world.player.heading) % 360
        last, at = self.reported
        if last is None or abs(angle_diff(true, last)) > NEW_BEARING or now - at > REPORT_GAP:
            self.reported = (true, now)
            kind = con.classification or "UNKNOWN"
            con.say(f"CONN, SONAR: CONTACT {true:03.0f}, CLASSIFIED {kind}")
        if now - self.marked > MARK_EVERY:
            self.marked = now
            con.mark()

    def pending_words(self):
        """What's been ordered and not yet done, for a station's screen."""
        return [f"{ORDERS[n][0]}: {ORDERS[n][1](a)}" for _, n, a in self.pending]



def order_for(action, con):
    """A station key pressed away from the station: the order the captain means by it, or None."""
    p = con.world.player
    engine = con.telegraph_index()
    steps = {
        "FASTER": ("ENGINES", min(engine + 1, len(TELEGRAPH) - 1)),
        "SLOWER": ("ENGINES", max(engine - 1, 0)),
        "SHALLOWER": ("DEPTH", p.ordered_depth - 10),
        "DEEPER": ("DEPTH", p.ordered_depth + 10),
        "RUDDER LEFT": ("RUDDER", max(p.rudder - 10, -MAX_RUDDER)),
        "RUDDER RIGHT": ("RUDDER", min(p.rudder + 10, MAX_RUDDER)),
        "RUDDER AMIDSHIPS": ("RUDDER", 0),
        "PERISCOPE DEPTH": ("PERISCOPE DEPTH", None),
        "HOLD DEPTH": ("HOLD DEPTH", None),
        "BLOW": ("BLOW", None),
        "PING": ("PING", None),
        "NOISEMAKER": ("NOISEMAKER", None),
        "FIRE": ("FIRE", None),
        "FIRE TUBE 1": ("FIRE", 0),
        "FIRE TUBE 2": ("FIRE", 1),
        "RAISE SCOPE": ("SCOPE", None),
        "RAISE SNORKEL": ("SNORKEL", None),
    }
    return steps.get(action)
