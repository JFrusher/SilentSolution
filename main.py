"""Silent Solution: game loop and screens (title, settings, training, replays, career, debrief, patrol).
Each screen is a Scene: it takes events, advances, draws, and hands back the next scene when it changes."""
import datetime
import traceback
from pathlib import Path

import pygame

import campaign
import replay
import settings
from audio import AudioSynthesizer
from console import Console
from graphics.tabletop import ReplayView
from layout import CRT_RECT, H, W
from tuning import DIFFICULTY
from tutorial import CHAPTERS, TRAINING, Tutorial
from version import __version__
from workstation import Workstation

FPS = 60
SIM_DT = 1 / 60  # s per sim step, fixed
CRASH_LOG = Path.home() / ".silent_solution" / "crash.log"


class App:
    """What every screen shares: the station, the audio, the career, and the key card."""

    def __init__(self):
        self.audio = AudioSynthesizer()
        settings.load()
        self.station = Workstation()
        self.station.career = self.career = campaign.Career()
        self.show_help = False

    def keep_replay(self, con, result, title):
        """Every patrol, however it ends, leaves an after-action replay."""
        path = replay.save(con.recorder, dict(mode=con.level, title=title, result=result, grt=con.score,
                                              wave=con.wave, seed=con.seed, version=__version__))
        self.station.last_replay = path
        return path

    def open_replay(self, path, back):
        """The tabletop for a saved patrol, returning to `back`; None if the file is gone or unreadable."""
        r = replay.load(path) if path else None
        if not r:
            return None
        self.station.replay_view = ReplayView(r, back.name)
        return Replay(self, back)

    def clicked(self, e):
        """The CRT button under a left click, if any."""
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            return next((name for rect, name in self.station.buttons if rect.collidepoint(e.pos)), None)
        return None


class Scene:
    name = ""          # the page the station draws
    esc_quits = False  # Esc leaves the game from here
    console = None     # the patrol on screen, if any
    holds_keys = False  # a question is up: F1 is just another key

    def __init__(self, app):
        self.app = app

    def event(self, e):
        return None

    def update(self, dt):
        return None

    def draw(self, screen, dt):
        self.app.station.draw(screen, self.console, self.name, False, self.app.show_help, dt)


class Title(Scene):
    name, esc_quits = "TITLE", True
    KEYS = {pygame.K_t: "TRAINING", pygame.K_s: "SETTINGS", pygame.K_c: "CAMPAIGN", pygame.K_r: "REPLAYS"}

    def event(self, e):
        app, st = self.app, self.app.station
        choice = app.clicked(e)
        if e.type == pygame.KEYDOWN and e.key in (pygame.K_1, pygame.K_2, pygame.K_3):
            choice = list(DIFFICULTY)[e.key - pygame.K_1]
        elif e.type == pygame.KEYDOWN:
            choice = self.KEYS.get(e.key)
        if choice == "CAMPAIGN":
            return Career(app)
        if choice == "SETTINGS":
            st.menu = settings.SettingsMenu()
            return Settings(app)
        if choice == "TRAINING":
            return Chapters(app)
        if choice == "REPLAYS":
            st.replays, st.replay_pick, st.replay_note = replay.listing(), 0, ""
            return Replays(app)
        if choice:
            return Patrol(app, Console(choice, app.audio))
        return None


class Settings(Scene):
    name = "SETTINGS"

    def event(self, e):
        menu = self.app.station.menu
        back = None
        if e.type == pygame.KEYDOWN:
            back = menu.key(e.key)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            back = menu.click(e.pos[0] - CRT_RECT.x, e.pos[1] - CRT_RECT.y)
        elif e.type == pygame.MOUSEWHEEL:
            menu.scroll(e.y)
        return Title(self.app) if back else None


class Chapters(Scene):
    name = "CHAPTERS"

    def event(self, e):
        app = self.app
        choice = app.clicked(e)
        if e.type == pygame.KEYDOWN:
            choice = "BACK" if e.key == pygame.K_ESCAPE else e.key - pygame.K_1
        if choice == "BACK":
            return Title(app)
        if isinstance(choice, int) and 0 <= choice < len(CHAPTERS):
            con = Console("TRAINING", app.audio, TRAINING)
            Tutorial(con, choice)
            return Patrol(app, con)
        return None


class Replays(Scene):
    name = "REPLAYS"

    def event(self, e):
        app, st = self.app, self.app.station
        choice, n = app.clicked(e), len(st.replays)
        if e.type == pygame.KEYDOWN and e.key in (pygame.K_UP, pygame.K_DOWN) and n:
            st.replay_pick = (st.replay_pick + (1 if e.key == pygame.K_DOWN else -1)) % n
        elif e.type == pygame.KEYDOWN:
            choice = {pygame.K_ESCAPE: "BACK", pygame.K_RETURN: st.replay_pick}.get(e.key)
        if choice == "BACK":
            return Title(app)
        if isinstance(choice, int) and choice < n:
            st.replay_pick = choice
            view = app.open_replay(st.replays[choice][0], self)
            if not view:
                st.replay_note = "THAT REPLAY CAN'T BE READ"
            return view
        return None


class Replay(Scene):
    """The tabletop has the whole screen; Esc goes back where it was opened from."""
    name = "REPLAY"

    def __init__(self, app, back):
        super().__init__(app)
        self.back, self.view = back, app.station.replay_view

    def event(self, e):
        view = self.view
        if e.type == pygame.KEYDOWN and view.key(e.key, e.mod) == "BACK":
            return self.back
        if e.type == pygame.MOUSEBUTTONDOWN:
            view.mouse_down(e.pos, e.button)
        elif e.type == pygame.MOUSEBUTTONUP:
            view.mouse_up()
        elif e.type == pygame.MOUSEMOTION:
            view.motion(e.pos)
        elif e.type == pygame.MOUSEWHEEL:
            view.wheel(e.y)
        return None

    def update(self, dt):
        self.view.update(dt)


class Career(Scene):
    """The career page, or (debrief=True) the debrief after a campaign patrol with its refit offer."""

    def __init__(self, app, debrief=False):
        super().__init__(app)
        self.debrief = debrief
        self.name = "DEBRIEF" if debrief else "CAREER"

    def event(self, e):
        app, st, career = self.app, self.app.station, self.app.career
        choice = app.clicked(e)
        if e.type == pygame.KEYDOWN:
            offer = st.debrief["offer"] if self.debrief else []
            picks = {pygame.K_1: 0, pygame.K_2: 1}
            choice = (offer[picks[e.key]] if e.key in picks and picks[e.key] < len(offer) else
                      {pygame.K_RETURN: "CONTINUE" if self.debrief else "SAIL", pygame.K_n: "NEW CAREER",
                       pygame.K_ESCAPE: "BACK", pygame.K_a: "REPLAY"}.get(e.key))
        if choice == "REPLAY" or isinstance(choice, tuple):  # the last patrol, or one from the log
            return app.open_replay(st.last_replay if choice == "REPLAY" else replay.DIR / choice[1], self)
        if self.debrief:
            if choice in campaign.UPGRADES:
                career.fit(choice)
                return Career(app)
            if choice == "CONTINUE" and not st.debrief["offer"]:
                return Career(app)
            return None
        if choice == "NEW CAREER" and not career.note:
            career.note = "PRESS N AGAIN TO RESIGN AND START A NEW CAREER (HIGH SCORES ARE KEPT)"
            return None
        if not choice:
            return None
        career.note = ""
        if choice == "NEW CAREER":
            career.new()
        elif choice == "BACK":
            return Title(app)
        elif choice == "SAIL" and not career.finished:
            con, run = campaign.sail(career, app.audio)
            return Patrol(app, con, run)
        return None


class Patrol(Scene):
    """At sea: an endless patrol, a training chapter (console.tutorial) or a campaign patrol (run).
    Esc asks before leaving; once the boat is lost the page turns to OVER."""

    def __init__(self, app, console, run=None):
        super().__init__(app)
        self.console, self.run = console, run
        self.over = self.confirm = self.paused = False
        self.lag = 0.0  # real time owed to the sim
        self.lost_at, self.leave_over = 0, False  # a lost campaign boat: when, and whether the player has moved on

    @property
    def name(self):
        return "OVER" if self.over else "PLAY"

    @property
    def esc_quits(self):
        return self.over and not self.run

    @property
    def holds_keys(self):
        return self.confirm

    def leave(self):
        """Y to the question: where to depends on what the patrol was."""
        app, con = self.app, self.console
        if con.tutorial:
            app.keep_replay(con, "TRAINING", "TRAINING")
            return Chapters(app)
        if self.run:
            app.keep_replay(con, "ABANDONED", self.run.patrol["name"])
            return Career(app)  # abandoned, not lost: the career doesn't move
        app.keep_replay(con, "QUIT", con.level)
        app.career.add_score(con.level, con.score, con.wave)
        return Title(app)

    def event(self, e):
        app, con = self.app, self.console
        if not self.over and e.type == pygame.KEYDOWN and (e.key == pygame.K_ESCAPE or self.confirm):
            if e.key == pygame.K_y and self.confirm:
                return self.leave()
            if e.key in (pygame.K_ESCAPE, pygame.K_n):
                self.confirm = not self.confirm and e.key == pygame.K_ESCAPE
                con.looking = False  # step back from the eyepiece so the question can be read
            return None
        if self.confirm:
            return None
        if e.type == pygame.WINDOWFOCUSLOST and not self.over:
            self.paused = True  # alt-tab mid-attack must not cost the boat
        elif self.over and self.run:  # campaign loss: any key on to the debrief
            self.leave_over = self.leave_over or e.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN)
        elif self.over:
            if e.type == pygame.KEYDOWN and e.key == pygame.K_r:  # straight back out at the same difficulty
                return Patrol(app, Console(con.level, app.audio))
            if e.type == pygame.KEYDOWN and e.key == pygame.K_t:
                return Title(app)
            if e.type == pygame.KEYDOWN and e.key == pygame.K_a:
                return app.open_replay(app.station.last_replay, self)
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_p:
            self.paused = not self.paused
        elif not self.paused:
            if e.type == pygame.KEYDOWN:
                con.key(e.key)
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                con.click(e.pos)
            elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                con.dragging = None
            elif e.type == pygame.MOUSEMOTION and con.dragging:
                con.drag(e.pos)
            elif e.type == pygame.MOUSEWHEEL:
                con.scroll(pygame.mouse.get_pos(), e.y)
        return None

    def update(self, dt):
        app, con = self.app, self.console
        running = not (self.paused or self.confirm or app.show_help)  # the key card covers the station
        self.lag = self.lag + dt if running else 0.0
        while self.lag >= SIM_DT:  # fixed sim step: the same seed plays out the same at any frame rate
            self.lag -= SIM_DT
            con.update(SIM_DT, pygame.key.get_pressed())
            if con.tutorial:
                con.tutorial.update(SIM_DT)
                if con.tutorial.finished:
                    app.keep_replay(con, "TRAINING", "TRAINING")
                    return Title(app)
            elif self.run:
                result = self.run.update(con)
                if result == "LOST" and not self.over:  # let the loss sink in before the debrief
                    self.over, self.lost_at = True, pygame.time.get_ticks()
                elif result and (not self.over or self.leave_over or pygame.time.get_ticks() - self.lost_at > 8000):
                    path = app.keep_replay(con, result, self.run.patrol["name"])
                    app.station.debrief = app.career.record(self.run, con, replay=path.name if path else None)
                    return Career(app, debrief=True)
            elif con.dead and not self.over:
                self.over = True
                app.keep_replay(con, "LOST", con.level)
                app.career.add_score(con.level, con.score, con.wave)
        return None

    def draw(self, screen, dt):
        st, con = self.app.station, self.console
        st.over_hint = "ANY KEY: DEBRIEF" if self.run else None
        st.confirm = None
        if self.confirm:
            question = (["LEAVE TRAINING?", "BACK TO THE CHAPTER LIST"] if con.tutorial else
                        ["ABANDON PATROL?", "IT WON'T COUNT FOR OR AGAINST YOU"] if self.run else
                        ["QUIT PATROL?", f"{con.score:,} GRT GOES ON THE SCORES"])
            st.confirm = question + ["", "[Y] YES      [N] NO"]
        st.draw(screen, con, self.name, self.paused, self.app.show_help, dt)


def main():
    pygame.init()
    screen = pygame.display.set_mode((W, H), pygame.SCALED | pygame.RESIZABLE)
    pygame.display.set_caption(f"SILENT SOLUTION {__version__}")
    clock = pygame.time.Clock()
    app = App()
    scene = Title(app)
    while True:
        dt = min(clock.tick(FPS) / 1000.0, 0.1)
        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE and scene.esc_quits):
                pygame.quit()
                return
            if e.type == pygame.KEYDOWN and e.key == pygame.K_F1 and not scene.holds_keys:
                app.show_help = not app.show_help
            else:
                scene = scene.event(e) or scene
        scene = scene.update(dt) or scene
        scene.draw(screen, dt)
        pygame.display.flip()


if __name__ == "__main__":
    try:
        main()
    except Exception:  # the packaged build has no console: leave the trace where a player can send it
        CRASH_LOG.parent.mkdir(parents=True, exist_ok=True)
        with CRASH_LOG.open("a", encoding="utf-8") as f:
            f.write(f"--- {datetime.datetime.now():%Y-%m-%d %H:%M:%S}  v{__version__}\n{traceback.format_exc()}\n")
        raise
