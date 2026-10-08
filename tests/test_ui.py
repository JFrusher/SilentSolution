"""Smoke test of the real game loop: a scripted player sails, quits, and opens the after-action replay every way in.
Run: uv run test_ui.py"""
import gzip
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import pygame  # noqa: E402

import campaign  # noqa: E402
import main  # noqa: E402
import replay  # noqa: E402
from graphics.tabletop import BAR  # noqa: E402

TMP = Path(tempfile.mkdtemp())
replay.DIR = TMP / "replays"
campaign.Career.__init__.__defaults__ = (TMP / "career.json",)  # the player's own career stays untouched
seen = []  # the state each frame was drawn in


class Station(main.Workstation):
    def draw(self, screen, con, state, *args):
        seen.append(state)
        super().draw(screen, con, state, *args)


def key(k, mod=0):
    return [pygame.event.Event(pygame.KEYDOWN, key=k, mod=mod, unicode="", scancode=0)]


def mouse(kind, pos, **kw):
    return [pygame.event.Event(kind, pos=pos, **kw)]


def script():
    """One list of events per frame; reads the station between frames like a player reading the screen."""
    yield key(pygame.K_1)  # an endless CADET patrol
    for _ in range(150):
        yield []
    assert seen[-1] == "PLAY", seen[-1]
    yield key(pygame.K_ESCAPE)
    yield key(pygame.K_y)  # quit: the patrol leaves a replay
    yield []
    st = main.station
    assert seen[-1] == "TITLE" and st.last_replay and st.last_replay.exists(), (seen[-1], st.last_replay)
    with gzip.open(replay.DIR / "00000000-000000-junk.json.gz", "wb") as f:
        f.write(b"{not json")  # the list must survive a bad file
    yield key(pygame.K_r)
    yield []
    assert seen[-1] == "REPLAYS" and len(st.replays) == 2 and st.replays[1][1] is None, st.replays
    yield key(pygame.K_DOWN)
    yield key(pygame.K_RETURN)
    yield []
    assert seen[-1] == "REPLAYS" and st.replay_note, "an unreadable replay stays on the list with a note"
    yield key(pygame.K_UP)
    yield key(pygame.K_RETURN)
    yield []
    assert seen[-1] == "REPLAY", seen[-1]
    view = st.replay_view
    yield mouse(pygame.MOUSEBUTTONDOWN, (640, 360), button=1)
    yield mouse(pygame.MOUSEMOTION, (700, 380), rel=(60, 20), buttons=(1, 0, 0))
    yield mouse(pygame.MOUSEBUTTONUP, (700, 380), button=1)
    yield mouse(pygame.MOUSEBUTTONDOWN, (640, 360), button=3)
    yield mouse(pygame.MOUSEMOTION, (600, 340), rel=(-40, -20), buttons=(0, 0, 1))
    yield mouse(pygame.MOUSEBUTTONUP, (600, 340), button=3)
    yield [pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=2, flipped=False)]
    yield mouse(pygame.MOUSEBUTTONDOWN, BAR.center, button=1)  # scrub to halfway
    yield mouse(pygame.MOUSEBUTTONUP, BAR.center, button=1)
    assert abs(view.t - (view.r.start + view.r.end) / 2) < 1.0, view.t
    for k in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_0, pygame.K_SPACE, pygame.K_RIGHT,
              pygame.K_LEFTBRACKET, pygame.K_RIGHTBRACKET, pygame.K_EQUALS, pygame.K_HOME):
        yield key(k)
    yield key(pygame.K_RIGHT, pygame.KMOD_SHIFT)
    yield key(pygame.K_ESCAPE)
    yield []
    assert seen[-1] == "REPLAYS", seen[-1]
    yield key(pygame.K_ESCAPE)
    st.career.log.append(dict(patrol="NORTH CAPE", result="SUCCESS", grt=9000, date="", replay=st.last_replay.name))
    yield key(pygame.K_c)
    yield []
    row = next(rect for rect, name in st.buttons if isinstance(name, tuple))  # a logged patrol with its replay
    yield mouse(pygame.MOUSEBUTTONDOWN, row.center, button=1)
    yield []
    assert seen[-1] == "REPLAY" and st.replay_view.back == "CAREER", seen[-1]
    yield key(pygame.K_ESCAPE)
    yield key(pygame.K_a)  # the last patrol, straight from the career page too
    yield []
    assert seen[-1] == "REPLAY", seen[-1]
    yield key(pygame.K_ESCAPE)
    yield []
    assert seen[-1] == "CAREER", seen[-1]
    yield [pygame.event.Event(pygame.QUIT)]


frames = script()
pygame.event.get = lambda *a, **kw: next(frames)
pygame.time.Clock = lambda: SimpleNamespace(tick=lambda fps=0: 1000 // 60)  # as fast as it will go


def capture():  # main makes its own Workstation: keep a handle on it
    main.station = Station()
    return main.station


def scenes():
    """Every screen the scripted loop doesn't reach, driven scene by scene with a frame drawn after each step.
    Runs first, on its own replay folder and career, so the loop's counts are its own."""
    keep = replay.DIR, campaign.Career.__init__.__defaults__
    replay.DIR, campaign.Career.__init__.__defaults__ = TMP / "scene-replays", (TMP / "scene-career.json",)
    pygame.init()
    screen = pygame.display.set_mode((main.W, main.H))
    app = main.App()

    def go(scene, *events, frames=1):
        for e in events:
            scene = scene.event(e) or scene
        for _ in range(frames):
            scene = scene.update(1 / 60) or scene
            scene.draw(screen, 1 / 60)
        return scene

    s = go(main.Title(app), *key(pygame.K_s))
    assert s.name == "SETTINGS" and go(s, *key(pygame.K_ESCAPE)).name == "TITLE"
    s = go(main.Title(app), *key(pygame.K_t), *key(pygame.K_1), frames=5)  # a training chapter
    assert s.name == "PLAY" and s.console.tutorial
    s = go(s, *key(pygame.K_ESCAPE), *key(pygame.K_y))
    assert s.name == "CHAPTERS", s.name
    s = go(main.Title(app), *key(pygame.K_1), frames=5)  # endless: the key card holds the sim
    app.show_help, t = True, s.console.world.time
    s = go(s, frames=30)
    assert s.console.world.time == t, "the sim ran under the key card"
    app.show_help = False
    s.console.world.hull = 0.0
    s = go(s, frames=2)
    assert s.name == "OVER" and s.esc_quits and go(s, *key(pygame.K_t)).name == "TITLE"
    s = go(main.Title(app), *key(pygame.K_c), *key(pygame.K_RETURN), frames=5)  # a campaign patrol, lost
    assert s.name == "PLAY" and s.run, s.name
    s.console.world.hull = 0.0
    s = go(s, frames=2)
    assert s.name == "OVER" and not s.esc_quits
    s = go(s, *key(pygame.K_SPACE), frames=2)
    assert s.name == "DEBRIEF", s.name
    replay.DIR, campaign.Career.__init__.__defaults__ = keep


scenes()
main.Workstation = capture
main.main()
assert "REPLAY" in seen and next(frames, None) is None, "the script ran to the end"
print(f"ui ok ({len(seen)} frames)")
