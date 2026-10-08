"""The walkable control room through the real patrol scene: stand up, walk, sit down, go to the periscope.
Needs OpenGL (any desktop; on a headless box run under xvfb-run). Run: uv run checks.py"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np  # noqa: E402
import pygame  # noqa: E402

import control_room as cr  # noqa: E402
import main  # noqa: E402
import settings  # noqa: E402
from console import Console  # noqa: E402

SHOTS = sys.argv[1] if len(sys.argv) > 1 else None  # a folder to save the frames in, to look at


class Held(dict):
    """pygame.key.get_pressed() stand-in: the keys in `down` are held."""
    down = set()

    def __getitem__(self, k):
        return int(k in self.down)


def key(k):
    return pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode="", scancode=0)


pygame.init()
screen = pygame.display.set_mode((main.W, main.H))
pygame.key.get_pressed = Held
pygame.mouse.set_relative_mode = lambda on: None  # the dummy video driver has no mouse to capture
app = main.App()
settings.reset()
scene = main.Patrol(app, Console("COMMANDER", app.audio, seed=2))
shot = [0]


def frames(n, *events):
    global scene
    for e in events:
        scene = scene.event(e) or scene
    for k in range(n):
        scene = scene.update(1 / 60) or scene
        if k == n - 1 or shot[0] % 10 == 0:  # software GL is slow: draw what the checks look at, and a sample
            scene.draw(screen, 1 / 60)
        if SHOTS and shot[0] % 6 == 0:
            pygame.image.save(screen, f"{SHOTS}/room{shot[0]:04d}.png")
        shot[0] += 1


def pixels():
    return pygame.surfarray.array3d(screen).astype(int)


con = scene.console
frames(30)
seated = pixels()
frames(1, key(settings.code("STAND UP")))
assert scene.on_foot, "R stands you up"
diff = np.abs(pixels() - seated).mean()
assert diff < 6, f"the first 3D frame should be the console you were sitting at (mean difference {diff:.1f})"
frames(70)
assert not scene.on_foot.room.moving, "the camera has carried you back from the console"
dial = con.dial_true
Held.down = {pygame.K_a}
frames(60)
assert con.dial_true == dial, "A walks you; it must not train the hydrophone dial while you're away from it"
Held.down = {pygame.K_w}  # straight at the sonar console: it stops you
scene.on_foot.room.pose = cr.standing(cr.STATIONS[0])
start = scene.on_foot.room.pose.pos.copy()
scene.on_foot.room.pose.yaw = -90.0
frames(120)
p = scene.on_foot.room.pose.pos
assert not cr.blocked(p[0], p[2]) and p[0] > -1.6, f"walked into the console: {p}"
assert np.linalg.norm(p - start) > 0.05, "you can move about"  # up to it, then stopped
Held.down = set()
scene.on_foot.room.pose = cr.standing(cr.STATIONS[0])
frames(1, key(pygame.K_e))
assert scene.on_foot.room.moving, "E at the sonar console sits you down"
frames(70)
assert scene.on_foot is None, "seated again at the console"

frames(1, key(settings.code("STAND UP")))  # to the periscope, deep: it won't go up
frames(70)
scene.on_foot.room.pose = cr.by_periscope()
frames(1, key(pygame.K_e))
assert not scene.on_foot.room.moving and "TOO DEEP" in con.log[-1], con.log[-1]
con.world.player.z = con.world.player.ordered_depth = 15.0  # at periscope depth it does
frames(1, key(pygame.K_e))
assert con.world.player.scope_up and scene.on_foot.room.moving
frames(70)
assert scene.on_foot is None and con.looking, "at the eyepiece"
frames(2, key(settings.code("LOOK")))  # step back from it: into the room again, by the scope
assert scene.on_foot and not con.looking
frames(70)
assert np.linalg.norm(scene.on_foot.room.pose.pos - cr.by_periscope().pos) < 0.05
print(f"room ok ({shot[0]} frames)")
