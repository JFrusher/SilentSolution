"""The crew: orders carried out after their reaction time, the helmsman's course, the sonarman's watch, the order
wheel, and station keys turned into orders when the captain is on his feet. Run: uv run checks.py"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

import crew  # noqa: E402
import main  # noqa: E402
import settings  # noqa: E402
import sim  # noqa: E402
from audio import AudioSynthesizer  # noqa: E402
from console import Console  # noqa: E402
from geometry import offset  # noqa: E402
from orders_menu import OrderWheel  # noqa: E402
from sim import KNOT, Vessel, angle_diff  # noqa: E402

pygame.init()
pygame.display.set_mode((main.W, main.H))
settings.reset()
AUDIO = AudioSynthesizer()


class NoKeys(dict):
    def __getitem__(self, k):
        return 0


def quiet_console():
    """A patrol with nobody else at sea."""
    con = Console("COMMANDER", AUDIO, seed=3)
    con.world.director, con.world.targets, con.world.ais = None, [], []
    return con


def run(con, seconds):
    for _ in range(int(seconds * 60)):
        con.update(1 / 60, NoKeys())


# an order is acknowledged at once and carried out after the crew's reaction time
con = quiet_console()
con.crew.order("RUDDER", 20)
assert con.log[-1].endswith("HELM, AYE: RIGHT 20 RUDDER"), con.log[-1]
run(con, con.diff["crew_delay"] - 0.2)
assert con.world.player.rudder == 0.0, "not before the crew has reacted"
run(con, 0.4)
assert con.world.player.rudder == 20.0

# the helmsman comes to an ordered course and holds it
con = quiet_console()
con.telegraph(2)
con.crew.order("COURSE", 90)
run(con, 150)
p = con.world.player
assert abs(angle_diff(p.heading, 90)) < 2 and abs(p.rudder) <= 3, (p.heading, p.rudder)
run(con, 60)
assert abs(angle_diff(p.heading, 90)) < 2, "and keeps her there"

# a hand on the wheel cancels the course order
con.rudder_by_hand(5)
assert con.crew.course is None and "COURSE ORDER CANCELLED" in con.log[-1]

# engines and depth go through the console's own orders
con.crew.order("ENGINES", 3)
con.crew.order("DEPTH", 150)
run(con, con.diff["crew_delay"] + 0.1)
assert abs(p.ordered_speed - sim.TELEGRAPH[3][1] * KNOT) < 1e-9 and p.ordered_depth == 150

# every order the wheel can give runs
con = quiet_console()
for name, arg in (("STEADY", None), ("PERISCOPE DEPTH", None), ("HOLD DEPTH", None), ("FIRE", None), ("FIRE", 1),
                  ("NOISEMAKER", None), ("PING", None), ("BLOW", None), ("SCOPE", None), ("SNORKEL", None),
                  ("CRASH DIVE", None), ("EVADE", -1)):
    con.crew.order(name, arg)
run(con, con.diff["crew_delay"] + 0.1)
assert not con.crew.pending and con.world.player.rudder == -30

# with the captain away, the sonarman finds the loudest contact, reports it, and fire control marks it
con = quiet_console()
ship = Vessel(*offset(0, 0, 120, 3000), 200, 8 * KNOT, noise=1.4)
con.world.targets.append(ship)
run(con, 20)
assert not con.locked, "the captain is at sonar: nobody else trains the dial"
con.crew.captain_at = None
run(con, 60)
assert con.locked and abs(angle_diff(con.dial_true, sim.bearing(0, 0, ship.x, ship.y))) < 5, con.dial_true
assert any("CONN, SONAR: CONTACT" in line for line in con.log), list(con.log)
assert con.tma.recent(con.world.time, 60.0), "fire control marked it"

# station keys away from the station become orders
con = quiet_console()
con.telegraph(1)
assert crew.order_for("FASTER", con) == ("ENGINES", 2)
assert crew.order_for("RUDDER LEFT", con) == ("RUDDER", -10)
assert crew.order_for("TDC ROW UP", con) is None, "a station's own controls are not orders"

# the wheel: drag to a heading, let go, drag to an order, let go
w = OrderWheel()
w.press()
w.motion(0, -100)
assert w.release() is None and w.title == "HELM"
w.motion(100, 0)  # three o'clock on the helm ring: drag right for right rudder
assert w.release() == ("RUDDER", 20) and not w.open
w.press()
w.motion(5, 5)
assert w.release() is None and not w.open, "letting go in the middle closes it"

# a patrol starts with the captain on his feet at the conn: his station keys reach the crew as orders
app = main.App()
settings.reset()
pygame.mouse.set_relative_mode = lambda on: None
scene = main.Patrol(app, Console("COMMANDER", app.audio, seed=2))
assert scene.on_foot and scene.console.crew.captain_at is None
scene.event(pygame.event.Event(pygame.KEYDOWN, key=settings.code("FASTER"), mod=0, unicode="", scancode=0))
assert scene.console.crew.pending and scene.console.crew.pending[0][1] == "ENGINES"
print("crew ok")
