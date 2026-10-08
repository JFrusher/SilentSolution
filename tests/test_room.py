"""The walkable control room through the real patrol scene: start at the conn, take stations, walk, use the
periscope. Needs OpenGL (any desktop; on a headless box run under xvfb-run). Run: uv run checks.py"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np  # noqa: E402
import pygame  # noqa: E402

import control_room as cr  # noqa: E402
import main  # noqa: E402
import settings  # noqa: E402
import stations  # noqa: E402
from console import Console  # noqa: E402
from graphics import room3d  # noqa: E402
from layout import TELEGRAPH_BTNS, TELEGRAPH_RECT  # noqa: E402
from sim import KNOT, TELEGRAPH  # noqa: E402

SHOTS = sys.argv[1] if len(sys.argv) > 1 else None  # a folder to save the frames in, to look at


class Held(dict):
    """pygame.key.get_pressed() stand-in: the keys in `down` are held."""
    down = set()

    def __getitem__(self, k):
        return int(k in self.down)


def key(k):
    return pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode="", scancode=0)


def click(pos):
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1)


pygame.init()
screen = pygame.display.set_mode((main.W, main.H))
pygame.key.get_pressed = Held
pygame.mouse.set_relative_mode = lambda on: None  # the dummy video driver has no mouse to capture
app = main.App()
settings.reset()
scene = main.Patrol(app, Console("COMMANDER", app.audio, seed=2))
con = scene.console
shot = [0]


def frames(n, *events, draw_all=False):
    global scene
    for e in events:
        scene = scene.event(e) or scene
    for k in range(n):
        scene = scene.update(1 / 60) or scene
        if draw_all or k == n - 1 or shot[0] % 10 == 0:  # software GL is slow: draw what's checked, and a sample
            scene.draw(screen, 1 / 60)
            if SHOTS:
                pygame.image.save(screen, f"{SHOTS}/room{shot[0]:04d}.png")
        shot[0] += 1


def pixels():
    return pygame.surfarray.array3d(screen).astype(int)


def take(station):
    """Stand in front of a station, press E, and ride the camera in; gives back the last 3D frame before the cut."""
    scene.on_foot.room.pose = cr.standing(station)
    frames(1, key(pygame.K_e))
    assert scene.on_foot.room.moving, f"E at {station.name} takes it"
    last = None
    while scene.on_foot:
        near = scene.on_foot.room.move[2] > 1 - 2.5 / (60 * cr.MOVE_TIME)  # the last frames before the cut
        last = pixels()
        frames(1, draw_all=near)
    return last


# the patrol starts on your feet at the conn, the crew on watch
frames(5)
manned = {s.name for s in cr.STATIONS if s.working} - {"HELM AND PLANES"} | {"HELM", "PLANES"}
assert set(app.room().crew) == manned, "every crewed station has its crewman, the helm its helmsman and planesman"

# a crewman making a call looks round at you; otherwise he keeps to his work
seated, place, _, _ = app.room().crew["SONAR"]
pivot = seated.parts["head"][0]
neck = place[:3, :3] @ pivot + place[:3, 3]
eye = neck + place[:3, :3] @ np.array((0.9, 0.3, 0.6))  # off to his side and above
look = place[:3, :3] @ room3d.head_turn(place, pivot, eye, 5.0, 0.0, age=1.0) @ np.array((0.0, 0.0, 1.0))
want = (eye - neck) / np.linalg.norm(eye - neck)
assert float(look @ want) > 0.99, "he faces you while he speaks"
idle = place[:3, :3] @ room3d.head_turn(place, pivot, eye, 5.0, 0.0) @ np.array((0.0, 0.0, 1.0))
assert float(idle @ want) < 0.8, "and not otherwise"
assert scene.on_foot and scene.at is None and con.crew.captain_at is None
assert np.linalg.norm(scene.on_foot.room.pose.pos - cr.by_periscope().pos) < 0.05

# each station is laid out for its own man: only his controls take a click, his own lamps, 2.5D instruments
from graphics import instruments as ins  # noqa: E402
from layout import BLOW_BTN, GAUGE_SPECS, LAMPS, LOOK_BTN, H, W  # noqa: E402

jobs = [v for v in stations.VIEWS.values() if v.name not in ("ALL", "PERISCOPE")]
assert not any(p.src.colliderect(BLOW_BTN) for p in stations.VIEWS["HELM AND PLANES"].pieces), "no BLOW at the helm"
assert not any(p.src.colliderect(LOOK_BTN) for v in jobs for p in v.pieces), "LOOK is the periscope's"
assert all(set(names) <= set(LAMPS) for v in jobs for _, names in v.lamps), "a station's lamps are real alarms"
dials = []
for v in (0.0, 250.0):
    surf = pygame.Surface((300, 300))
    ins.gauge(surf, (150, 150), 120, GAUGE_SPECS["DEPTH"], [(v, (255, 255, 255), 3, 1.0)])
    dials.append(pygame.surfarray.array3d(surf).astype(int))
assert np.abs(dials[0] - dials[1]).sum() > 0, "the needle moves"
ws = app.station
assert ws.overlay("DAMAGE") is not ws.overlay("SONAR"), "the monitor's plate names the job on its screen"
plain = pygame.Surface((W, H))
hovered = plain.copy()
ping = next(p for p in stations.VIEWS["SONAR"].pieces if p.keys == ("PING",))
stations.hover(hovered, stations.VIEWS["SONAR"], ping.dst.center)
assert np.abs(pygame.surfarray.array3d(hovered).astype(int) - pygame.surfarray.array3d(plain)).sum() > 0, \
    "hovering a control shows its key"

# sit at sonar: the last 3D frame and the first 2D frame are the same picture
sonar = cr.STATIONS[0]
before = take(sonar)
assert scene.at == "SONAR" and con.crew.captain_at == "SONAR"
diff = np.abs(pixels() - before).mean()
assert diff < 6, f"sitting down should be an invisible cut (mean difference {diff:.1f})"
seated = pixels()
frames(1, key(settings.code("STAND UP")), draw_all=True)
diff = np.abs(pixels() - seated).mean()
assert scene.on_foot and diff < 6, f"standing up should be an invisible cut too (mean difference {diff:.1f})"
frames(70)
assert not scene.on_foot.room.moving

# on your feet, A walks you; it must not train the hydrophone dial
dial = con.dial_true
Held.down = {pygame.K_a}
frames(60)
assert con.dial_true == dial
Held.down = {pygame.K_w}  # straight at the sonar console: it stops you
scene.on_foot.room.pose = cr.standing(sonar)
start = scene.on_foot.room.pose.pos.copy()
scene.on_foot.room.pose.yaw = -90.0
frames(120)
p = scene.on_foot.room.pose.pos
assert not cr.blocked(p[0], p[2]) and p[0] > -1.6, f"walked into the console: {p}"
assert np.linalg.norm(p - start) > 0.05, "up to it, then stopped"
Held.down = set()

# every crewed station can be taken, and shows its own job
for s in cr.STATIONS:
    if s.working:
        take(s)
        assert scene.at == s.name and con.crt_page == stations.VIEWS[s.name].page
        frames(1, key(settings.code("STAND UP")))
        frames(70)

# at fire control its keys work, a sonar key held does nothing, and an engine key becomes an order
take(next(s for s in cr.STATIONS if s.name == "FIRE CONTROL"))
row = con.tdc.selected
frames(1, key(settings.code("TDC ROW DOWN")))
assert con.tdc.selected == row + 1, "the TDC is fire control's"
Held.down = {settings.code("TRAIN RIGHT")}  # the dial is the sonarman's (he's training it himself meanwhile)
held = stations.HeldAt(scene.view, pygame.key.get_pressed(), settings.code)
assert not held[settings.code("TRAIN RIGHT")], "fire control's hands can't train the hydrophone dial"
Held.down = set()
frames(1, key(settings.code("FASTER")))
assert con.crew.pending and con.crew.pending[-1][1] == "ENGINES", "the engines are an order from here"
frames(1, key(settings.code("STAND UP")))
frames(70)

# at the helm, clicking FLANK on the station's telegraph rings it up
take(next(s for s in cr.STATIONS if s.name == "HELM AND PLANES"))
piece = next(pc for pc in stations.VIEWS["HELM AND PLANES"].pieces if pc.src == TELEGRAPH_RECT)
bx, by = TELEGRAPH_BTNS[-1].center
frames(1, click((piece.dst.x + (bx - piece.src.x) * piece.scale, piece.dst.y + (by - piece.src.y) * piece.scale)))
assert con.world.player.ordered_speed == TELEGRAPH[-1][1] * KNOT, con.world.player.ordered_speed
frames(1, key(settings.code("STAND UP")))
frames(70)

# to the periscope, deep: it won't go up; at periscope depth it does, and you step back into the room
scene.on_foot.room.pose = cr.by_periscope()
frames(1, key(pygame.K_e))
assert not scene.on_foot.room.moving and "TOO DEEP" in con.log[-1], con.log[-1]
con.world.player.z = con.world.player.ordered_depth = 15.0
frames(1, key(pygame.K_e))
assert con.world.player.scope_up and scene.on_foot.room.moving
frames(70)
assert scene.on_foot is None and con.looking, "at the eyepiece"
frames(2, key(settings.code("LOOK")))
assert scene.on_foot and not con.looking
frames(70)
assert np.linalg.norm(scene.on_foot.room.pose.pos - cr.by_periscope().pos) < 0.05
print(f"room ok ({shot[0]} frames)")
