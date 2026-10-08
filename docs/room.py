"""Film the control room for the README: the room and its crew, each station's panel, the coxswain's training,
captions, the attack plot and the H.P. air. The real Patrol scene, driven headless on a frame clock of its own.
Needs OpenGL (headless: xvfb-run -a). Run: uv run --with pillow docs/room.py [stills hero training captions blow]"""
import sys

import numpy as np
import pygame
from gifs import OUT, Reel, screen  # gifs sets up the dummy display, the paths and src/ on sys.path
from PIL import Image

import control_room as cr  # noqa: E402
import main  # noqa: E402
import settings  # noqa: E402
import stations  # noqa: E402
from console import Console  # noqa: E402
from geometry import offset  # noqa: E402
from graphics.room3d import COXSWAIN_AT, plot_art  # noqa: E402
from sim import KNOT, YARD, Vessel, bearing  # noqa: E402
from tutorial import TRAINING, Tutorial  # noqa: E402

FPS = 10
NOW = [0]  # ms: captions fade and the crew look round on this clock, not on how slowly software GL draws
pygame.time.get_ticks = lambda: NOW[0]
pygame.mouse.set_relative_mode = lambda on: None  # the dummy video driver has no mouse to capture


class Held(dict):
    def __getitem__(self, k):
        return 0


pygame.key.get_pressed = Held
app = main.App()
OVERVIEW = cr.Pose(np.array([0.9, 1.65, 3.3]), -8.0, -10.0)  # aft by the chart table, looking forward


def key(k):
    return pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode="", scancode=0)


def tick(scene, dt=1 / FPS, draw=True):
    NOW[0] += round(dt * 1000)
    scene = scene.update(dt) or scene
    if draw:
        scene.draw(screen, dt)
    return scene


def still(name):
    """Full size, one adaptive palette: the dials stay crisp and the file stays small."""
    img = Image.frombytes("RGB", screen.get_size(), pygame.image.tobytes(screen, "RGB"))
    img.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG).save(
        OUT / f"{name}.png", optimize=True)
    print(f"wrote {name}.png: {(OUT / f'{name}.png').stat().st_size / 1e6:.2f} MB")


def seat(scene, name):
    if scene.on_foot:
        scene.sit(name)
    else:
        scene.at, scene.console.crew.captain_at = name, name
        scene.console.crt_page = stations.VIEWS[name].page


def place(con, rel, rng, course, kt, kind="MERCHANT"):
    p = con.world.player
    ship = Vessel(*offset(p.x, p.y, p.heading + rel, rng), course % 360, kt * KNOT, noise=1.1)
    ship.kind = kind
    con.world.targets.append(ship)
    return ship


def patrol():
    """A patrol twenty minutes in: a convoy on the screens, a target marked and pinged, the TDC wound, one fish
    gone (so one air group is down), the plot worked."""
    con = Console("COMMANDER", app.audio, seed=2)
    w = con.world
    w.director = None
    o = w.ocean
    o.rain = o.front = 0.0
    o.timer, o.wind = 1e9, 6.0
    target = place(con, 40, 5200, w.player.heading + 120, 8)
    place(con, 52, 6400, w.player.heading + 120, 8)
    place(con, 28, 7000, w.player.heading + 120, 8)
    place(con, 65, 8200, w.player.heading + 135, 14, "ESCORT")
    scene = main.Patrol(app, con)
    for i in range(int(900 * 30)):
        p = w.player
        con.dial = (bearing(p.x, p.y, target.x, target.y) - p.heading) % 360
        if i == 540 * 30:
            p.rudder = -20.0  # a second leg for the plot
        if i == 560 * 30:
            p.rudder = 0.0
        if i % (150 * 30) == 0:
            con.mark()
        con.update(1 / 30, Held())
    con.ping()
    for _ in range(12 * 30):
        con.update(1 / 30, Held())
    p = w.player
    con.tdc.set("RNG", p.range_to(target) / YARD)
    con.tdc.set("SPD", target.speed / KNOT)
    con.tdc.set("CRS", target.heading)
    con.fire()
    if con.wire_sel is None:
        con.fire()
    for _ in range(20 * 30):
        con.update(1 / 30, Held())
    scene.heard = con.heard[-1][0] if con.heard else 0  # the warm-up's calls are old news: no captions for them
    return scene


def stills():
    scene = patrol()
    scene.on_foot.room.pose = OVERVIEW
    for _ in range(6):
        scene = tick(scene)
    still("room")
    for name, file in (("SONAR", "st_sonar"), ("FIRE CONTROL", "st_fire"), ("HELM AND PLANES", "st_helm"),
                       ("BALLAST CONTROL", "st_ballast"), ("RADIO", "st_radio"), ("DAMAGE CONTROL", "st_damage")):
        seat(scene, name)
        scene.captions.clear()  # the room shot shows one; six of the same would be noise
        for _ in range(12):
            scene = tick(scene)
        still(file)
    # the plot from a clean approach: two legs on a crossing merchant, a bearing every 90 s, two reports, the TDC's
    # solution; drawn by the same plot_art the table uses
    track, x, y, hdg = [], 0.0, 0.0, 20.0
    for t in range(0, 1201, 30):
        if t == 600:
            hdg = 320.0
        track.append((t, x, y))
        x, y = x + 3 * KNOT * 30 * np.sin(np.radians(hdg)), y + 3 * KNOT * 30 * np.cos(np.radians(hdg))
    ship = lambda t: (3200.0 - 8 * KNOT * t, 4800.0 - 2 * KNOT * t)  # noqa: E731
    marks = [(t, bearing(ox, oy, *ship(t)), "MARK", None) for t, ox, oy in track[::3]]
    notes = [(360, *track[12][1:], marks[4][1], None, "SONAR MERCHANT"),
             (1080, *track[36][1:], marks[12][1], 5100.0, "PING 5,100 YD")]
    sx, sy = ship(1200)
    lx, ly = track[-1][1:]
    screen.blit(plot_art(track, hdg, marks, (sx - lx, sy - ly, -8 * KNOT, -2 * KNOT), notes, size=(1280, 720),
                         span=9000.0), (0, 0))
    still("chart")


def hero():
    """The overview, a walk to sonar past the crew, E, the sonarman stands aside, and the cut to his panel."""
    scene = patrol()
    reel = Reel("room", width=800, fps=FPS, colors=128)
    room = scene.on_foot.room
    sonar = next(s for s in cr.STATIONS if s.name == "SONAR")
    room.pose = OVERVIEW
    for _ in range(6):  # the room fills its screens a CRT page a frame: let every one show first
        scene = tick(scene)
    for _ in range(12):
        scene = tick(scene)
        reel.grab("THE CONTROL ROOM")
    goal = cr.standing(sonar)
    for i in range(1, 26):
        room.pose = cr.blend(OVERVIEW, goal, i / 25)
        scene = tick(scene)
        reel.grab("WASD: WALK TO A STATION")
    scene = scene.event(key(pygame.K_e)) or scene
    while scene.on_foot:
        scene = tick(scene)
        reel.grab("E: TAKE SONAR")
    for _ in range(18):
        scene = tick(scene)
        reel.grab("SONAR: THE WATERFALL")
    reel.save()


def training():
    """The station drill: the coxswain at the conn turns and points to the helm, the card says take it."""
    con = Console("TRAINING", app.audio, TRAINING)
    tut = Tutorial(con, 2)
    scene = main.Patrol(app, con)
    tut.i = next(i for i, s in enumerate(tut.steps) if s.station == "HELM AND PLANES") - 1
    tut.advance()
    for _ in range(80):  # let the coxswain's order finish printing
        scene = tick(scene, draw=False)
    head = np.array(COXSWAIN_AT) + (0.0, 1.3, 0.0)
    eye = np.array([1.1, 1.65, -1.3])  # forward of him, looking aft: he turns from you to the helm and points
    start = cr.Pose(eye, *cr.facing(head - eye))
    helm = next(s for s in cr.STATIONS if s.name == "HELM AND PLANES")
    end = cr.Pose(eye, *cr.facing(np.array(helm.centre) - eye))
    reel = Reel("training", width=800, fps=FPS)
    room = scene.on_foot.room
    room.pose = start
    for _ in range(6):
        scene = tick(scene)
    for i in range(55):
        room.pose = cr.blend(start, end, max(0.0, (i - 25) / 25))
        scene = tick(scene)
        reel.grab("TRAINING: THE COXSWAIN")
    reel.save()


def captions():
    """THE ROOM drill: an escort pings, the sonar lamp flashes, his report is captioned with an arrow to him, and he
    looks round; you turn to him."""
    con = Console("TRAINING", app.audio, TRAINING)
    tut = Tutorial(con, 1)
    scene = main.Patrol(app, con)
    tut.i = next(i for i, s in enumerate(tut.steps) if s.goal.startswith("WHEN THE LAMP")) - 1
    tut.advance()
    room = scene.on_foot.room
    table = cr.Pose(np.array([0.7, 1.65, -1.0]), 30.0, -14.0)  # by the plot table, sonar behind you to port
    room.pose = table
    while not tut.memo.get("pinged"):
        scene = tick(scene, 0.5, draw=False)
    sonar = next(s for s in cr.STATIONS if s.name == "SONAR")
    face = cr.Pose(table.pos, *cr.facing(np.array(sonar.centre) + (0.6, 0.0, 0.0) - table.pos))
    reel = Reel("captions", width=800, fps=FPS)
    for i in range(55):
        room.pose = cr.blend(table, face, max(0.0, (i - 22) / 18))
        scene = tick(scene)
        reel.grab("CAPTIONS")
    reel.save()


def blow():
    """Ballast control at 120 m: blow main ballast, the three H.P. air gauges fall as she rises."""
    con = Console("COMMANDER", app.audio, seed=4)
    con.world.director = None
    p = con.world.player
    p.z = p.ordered_depth = 120.0
    scene = main.Patrol(app, con)
    seat(scene, "BALLAST CONTROL")
    reel = Reel("blow", crop=(390, 340, 890, 380), width=800, fps=FPS)
    for _ in range(8):
        scene = tick(scene)
        reel.grab("120 M")
    scene = scene.event(key(settings.code("BLOW"))) or scene
    for _ in range(42):
        scene = tick(scene, 0.4)
        reel.grab("BLOW: H.P. AIR DRAINS", speed=4)
    reel.save()


if __name__ == "__main__":
    settings.reset()
    jobs = dict(stills=stills, hero=hero, training=training, captions=captions, blow=blow)
    for name in sys.argv[1:] or jobs:
        jobs[name]()
