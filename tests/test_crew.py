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
from sim import KNOT, TORP_AIR, Vessel, angle_diff  # noqa: E402

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
assert {"HELM", "PLANES"} <= set(con.crew.worked), "the men who carried them out put their hands to their controls"
from graphics.room3d import reach, wheel_pose  # noqa: E402

assert reach(None) == reach(1.0) == 0 and abs(reach(0.45) - 2) < 1e-9 and 0 < reach(0.1) < reach(0.2) < 2, \
    "out to his switches and back, smoothly"
assert wheel_pose(0.0) == (6.0, 0.0) and wheel_pose(48.75)[1] == 45.0 and abs(wheel_pose(41.25)[0] - 11.5) < 1e-9, \
    "the wheels turn smoothly between the posed turns, no further"
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
con.crew.order(*crew.order_for("FASTER", con))
assert crew.order_for("FASTER", con) == ("ENGINES", 3), "a second press goes on from the order still to be done"
con.crew.order("COURSE", 90.0)
con.crew.hand_on_wheel()
run(con, 5)
assert con.crew.course is None, "the captain's hand on the wheel cancels a course order not yet carried out"

# a spread with air for one fish: that one goes, the rest are refused, and it counts as fired
con = quiet_console()
p = con.world.player
ship = Vessel(*offset(0, 0, 40, 3000), 300.0, 8 * KNOT)
con.world.targets.append(ship)
con.tdc.set("BRG", 40.0), con.tdc.set("RNG", 3000 / 0.9144), con.tdc.set("SPD", 8.0), con.tdc.set("CRS", 300.0)
con.tdc.set("SPR", 4.0)
p.air = [TORP_AIR + 1, 0.0, 0.0]
con.fire()
assert len(con.world.torpedoes) == 1 and "FIRE" in con.actions, (con.world.torpedoes, con.actions)

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

# captions: everything heard aboard reaches you, two lines in one frame too, with the caller named
con = scene.console
con.say("T1 DETONATION 045.0R", "SONAR")
con.say("BREAKUP NOISES. SUNK", "SONAR")
con.teletype.print("DAMAGE CONTROL: FLOODING. 1 LEAK(S). PUMPS ON.")
con.teletype.print("WAVE 2 DISPERSED.")
con.hear("SOUND", "[ENEMY SONAR PING 045R]")
scene.hear()
said = [t for t, _, _ in scene.captions]
assert said == ["SONAR: BREAKUP NOISES. SUNK", "DAMAGE CONTROL: FLOODING. 1 LEAK(S). PUMPS ON.",
                "RADIO: WAVE 2 DISPERSED.", "[ENEMY SONAR PING 045R]"], said
assert main.speaker(said[0]) == ("SONAR", "BREAKUP NOISES. SUNK") and main.speaker(said[3])[0] == ""
settings.SETTINGS["sound_captions"] = False
con.hear("SOUND", "[HULL CREAKS]")
scene.hear()
assert scene.captions[-1][0] == said[3], "SOUND CAPTIONS off: noises aren't captioned"
settings.reset()
assert [main.voice(w) for w in ("CONN, SONAR", "HELM, AYE", "CHIEF, AYE", "MANEUVERING, AYE", "RADIO", "INSTRUCTOR")] \
    == ["SONAR", "HELM", "BALLAST CONTROL", "HELM", "RADIO", None], "a caller's caption is his crewman's to say"
scene.say("CONN, SONAR: CONTACT 045, CLASSIFIED MERCHANT")
assert "SONAR" in scene.spoke, "the sonarman made that call"
assert scene.captions[-1][2] == "SONAR", "a caption knows its crewman"
# turn to him: no arrow when he's in view, which way to look when he isn't
facing = main.cr.Pose(main.CREW_AT["SONAR"] + (1.5, 0.0, 0.0), -90.0, 0.0)  # starboard of him, looking to port
assert main.turn_to(facing, "SONAR") is None
behind = main.cr.Pose(facing.pos, 90.0, 0.0)
assert abs(main.turn_to(behind, "SONAR")) > 170, main.turn_to(behind, "SONAR")
screen = pygame.display.get_surface()
main.captions(screen, [("CONN, SONAR: CONTACT", 0.5, 120.0), ("[KLAXON]", 1.0, None)], 700)  # fades, arrows draw
menu = settings.SettingsMenu()
menu._select(next(i for i, r in enumerate(menu.rows) if r[0] == "CAPTION SIZE"))
for want in (1.3, 1.7, 1.0):  # CAPTION SIZE cycles SMALL, LARGE, HUGE
    menu._adjust(1)
    assert settings.SETTINGS["caption_scale"] == want
import json  # noqa: E402
import tempfile  # noqa: E402

with tempfile.TemporaryDirectory() as d:
    path = f"{d}/settings.json"
    with open(path, "w") as f:
        json.dump({"caption_scale": 1.55}, f)
    settings.load(path)
    assert settings.SETTINGS["caption_scale"] == 1.0, "only the sizes on offer"
settings.reset()
print("captions ok")

# quick travel from the order wheel: on foot or from another station, a dip to black and you're carried in
scene.go("HELM AND PLANES")
assert scene.on_foot.fade > 0 and scene.on_foot.room.moving
for _ in range(80):
    scene = scene.update(1 / 60) or scene
assert scene.at == "HELM AND PLANES" and scene.on_foot is None
scene.go("SONAR")  # from a seat: up and across
for _ in range(80):
    scene = scene.update(1 / 60) or scene
assert scene.at == "SONAR"
print("quick travel ok")

# training in the room: the drill sends you to the right station, rings land on it, ENTER works on your feet
import stations  # noqa: E402
from layout import HIGHLIGHTS  # noqa: E402
from tutorial import TRAINING, Tutorial  # noqa: E402

con = Console("TRAINING", app.audio, TRAINING)
Tutorial(con, 3)  # SONAR AND FIRE CONTROL: the coxswain sends you to sonar, then the waterfall drill
scene = main.Patrol(app, con)
assert scene.on_foot, "training starts on your feet at the conn too"
assert con.tutorial.step.station == "SONAR", "first, take the sonar station"
assert stations.station_for(con.tutorial.steps[con.tutorial.i + 1].highlight, HIGHLIGHTS) == "SONAR"
assert stations.station_for(("tdc", "waterfall"), HIGHLIGHTS) == "FIRE CONTROL"
assert stations.station_for(("waterfall", "hull"), HIGHLIGHTS) == "DAMAGE CONTROL"
scene.go("SONAR")
for _ in range(80):
    scene = scene.update(1 / 60) or scene
assert scene.at == "SONAR" and stations.rings(scene.view, HIGHLIGHTS["waterfall"]), "the waterfall ring shows here"
screen = pygame.display.get_surface()
scene.draw(screen, 1 / 60)  # the instructor's card over the station
first = main.Patrol(app, Console("TRAINING", app.audio, TRAINING))
Tutorial(first.console, 0)
step = first.console.tutorial.i
first.event(pygame.event.Event(pygame.KEYDOWN, key=settings.code("ACKNOWLEDGE"), mod=0, unicode="", scancode=0))
for _ in range(900):  # the drill moves on once the teleprinter has finished printing its briefing
    first.update(1 / 60)
assert not first.console.teletype.queue and first.console.tutorial.i > step, "ENTER acknowledges a drill on your feet"
print("training in the room ok")
