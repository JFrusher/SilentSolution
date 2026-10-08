"""Silent Solution: game loop and screens (title, settings, training, replays, career, debrief, patrol).
Each screen is a Scene: it takes events, advances, draws, and hands back the next scene when it changes."""
import datetime
import traceback
from pathlib import Path

import pygame

import campaign
import control_room as cr
import crew
import replay
import settings
import stations
from audio import AudioSynthesizer
from console import Console
from graphics import console_art as art
from graphics.room3d import RoomRenderer, legend_art, plot_art
from graphics.tabletop import ReplayView
from layout import CRT_RECT, H, W
from orders_menu import OrderWheel
from tuning import DIFFICULTY
from tutorial import CHAPTERS, TRAINING, Tutorial
from version import __version__
from workstation import Workstation, alerts

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
        self.room3d = None  # the GL renderer, made the first time it's needed
        self.frame = pygame.Surface((W, H))  # the full console, drawn for whichever station is wanted
        self.backdrop = art.texture((W, H), art.STEEL_DARK, grain=4)  # a station's steelwork behind its panels

    def console_frame(self, con, page, paused, dt):
        """The full console with its CRT on `page`: every station on that page is cut from this one drawing."""
        con.crt_page = page
        self.station.draw(self.frame, con, "PLAY", paused, False, dt)
        return self.frame

    def canvas(self, view, con, paused, dt):
        """One station as its crewman sees it."""
        return stations.compose(view, self.console_frame(con, view.page, paused, dt), self.backdrop)

    def room(self):
        if self.room3d is None:
            self.room3d = RoomRenderer()
        return self.room3d

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


class NoKeys(dict):
    """Nothing held: what the console feels while you're away from it."""

    def __getitem__(self, k):
        return 0


def notice(screen, lines):
    """A question or the pause, over a station or the room (the full console shows these on its CRT)."""
    if not lines:
        return
    box = pygame.Rect(0, 0, 560, 40 + 28 * len(lines))
    box.center = (W // 2, H // 2 - 40)
    shade = pygame.Surface(box.size, pygame.SRCALPHA)
    shade.fill((0, 0, 0, 200))
    screen.blit(shade, box)
    for i, line in enumerate(lines):
        text = art.mono(20, True).render(line, True, (240, 226, 190))
        screen.blit(text, text.get_rect(center=(W // 2, box.y + 34 + i * 28)))


def subtitle(screen, said):
    text = art.mono(15, True).render(said, True, (150, 240, 160))
    back = text.get_rect(center=(W // 2, H - 30)).inflate(16, 8)
    shade = pygame.Surface(back.size, pygame.SRCALPHA)
    shade.fill((0, 0, 0, 170))
    screen.blit(shade, back)
    screen.blit(text, text.get_rect(center=back.center))


class OnFoot:
    """Away from the stations: walking the control room until you sit down or put your eye to the periscope.
    The boat fights on meanwhile, and every crewed station's screen shows it, live."""
    PLOT_EVERY = 0.5  # s of sim time between redraws of the plot table
    WORKING = tuple(s.name for s in cr.STATIONS if s.working)
    PAGES = tuple(dict.fromkeys(stations.VIEWS[n].page for n in WORKING))  # CRT pages the stations use

    def __init__(self, app, con, start, to=None, focus=None):
        self.app, self.con = app, con
        self.room = cr.ControlRoom()
        self.room.pose = start
        if to is not None:  # carried somewhere first: you have your feet once it's done
            self.room.carry(to, "ROOM")
        self.focus = focus  # the station being left or approached: its screen is kept exact for the cut
        self.plot_at, self.turn = -1e9, 0
        con.crew.captain_at = None  # the crew has the watch
        pygame.mouse.set_relative_mode(True)

    def leave(self):
        pygame.mouse.set_relative_mode(False)

    def event(self, e):
        """Look, walk, use, or order. Returns a line for the captain, if there is one."""
        use = (e.type == pygame.KEYDOWN and e.key == pygame.K_e) or (e.type == pygame.MOUSEBUTTONDOWN and e.button == 1)
        if self.room.moving and (use or e.type == pygame.MOUSEMOTION):
            return None  # the camera is carrying you; orders still go through
        if e.type == pygame.MOUSEMOTION:
            self.room.look(*e.rel, sensitivity=0.12 * settings.SETTINGS["mouse"])
        elif use:
            return self.use()
        elif e.type == pygame.KEYDOWN:  # a station's key, pressed away from it: an order to the crew
            order = crew.order_for(settings.action_for(e.key), self.con)
            if order:
                self.con.crew.order(*order)
        return None

    def use(self):
        con, thing = self.con, self.room.target()
        if thing == "PERISCOPE":
            if not con.world.player.scope_up:
                con.toggle_scope()  # take hold of the handles: up scope
            if con.world.player.scope_up:
                self.room.carry(cr.at_eyepiece(), "EYEPIECE")
            return None
        if thing is not None and thing.working:
            self.focus = thing.name
            self.room.carry(cr.seated(thing), ("SEATED", thing.name))
            return None
        return f"{thing.name}: NOT MANNED THIS PATROL" if thing is not None else None

    def update(self, dt):
        """Walk; returns where a finished camera move has put you: ("SEATED", station), "EYEPIECE" or "ROOM"."""
        k = pygame.key.get_pressed()
        shift = k[pygame.K_LSHIFT] or k[pygame.K_RSHIFT]
        then = self.room.update(dt, k[pygame.K_w] - k[pygame.K_s], k[pygame.K_d] - k[pygame.K_a], shift)
        if then == "ROOM":
            self.focus = None
        return then

    def draw(self, screen, dt):
        app, con, w = self.app, self.con, self.con.world
        if self.focus:  # gliding to or from a station: only its screen, kept exact for the cut
            page, names = stations.VIEWS[self.focus].page, (self.focus,)
        else:  # one CRT page a frame, in turn, and every station on it
            self.turn = (self.turn + 1) % len(self.PAGES)
            page = self.PAGES[self.turn]
            names = [n for n in self.WORKING if stations.VIEWS[n].page == page]
        frame = app.console_frame(con, page, False, dt)  # the full console is drawn once a frame, at most
        screens = {n: stations.compose(stations.VIEWS[n], frame, app.backdrop) for n in names}
        plot = None
        if w.time - self.plot_at >= self.PLOT_EVERY:  # from our own navigation and the TMA log: what we know
            tdc, p = con.tdc, w.player
            solution = (tdc.x, tdc.y, *tdc.target_velocity())
            marks = [b for b in con.tma.recent(w.time, 600.0) if b[2] != "HYD"]  # marks and fixes, not the trace
            plot = plot_art(list(con.tma.track), p.heading, marks, solution, con.plot_notes)
            self.plot_at = w.time
        lamps = alerts(con)  # the lamps flash with their alarms; the legend at the conn says which
        alert = float(any(on for _, on, _ in lamps))
        screen.blit(app.room().render(self.room.pose, screens, plot, legend_art(lamps), alert), (0, 0))
        if self.room.moving:
            return
        font = art.mono(15, True)
        pygame.draw.circle(screen, (230, 220, 190), (W // 2, H // 2), 2)
        thing = self.room.target()
        if thing is not None:
            label = "E  LOOK THROUGH THE PERISCOPE" if thing == "PERISCOPE" else (
                f"E  TAKE {thing.name}" if thing.working else thing.name)
            text = font.render(label, True, (240, 226, 190))
            screen.blit(text, text.get_rect(center=(W // 2, H // 2 + 40)))
        hint = art.mono(12).render("WASD WALK   SHIFT RUN   MOUSE LOOK   E USE   HOLD RIGHT MOUSE: ORDERS", True,
                                   (150, 146, 130))
        screen.blit(hint, (16, 12))


class Patrol(Scene):
    """At sea: an endless patrol, a training chapter (console.tutorial) or a campaign patrol (run).
    You start on your feet at the conn and take whichever station you like; training keeps the full console.
    Esc asks before leaving; once the boat is lost the page turns to OVER, on the full console."""
    SUBTITLE_TIME = 5000  # ms a crew report stays up

    def __init__(self, app, console, run=None):
        super().__init__(app)
        self.console, self.run = console, run
        self.over = self.confirm = self.paused = False
        self.lag = 0.0  # real time owed to the sim
        self.lost_at, self.leave_over = 0, False  # a lost campaign boat: when, and whether the player has moved on
        self.wheel = OrderWheel()  # the captain's orders, on the right mouse button
        self.from_room = False     # at the eyepiece by way of the room: stepping back puts you there again
        self.grip = None           # the station piece a drag started on
        self.note = ("", 0)        # the line on the subtitle and when it went up
        self.log_seen = console.log[-1] if console.log else ""
        self.at, self.on_foot = None, None  # the station you're working, or OnFoot while you walk the room
        if console.tutorial:
            self.at = "ALL"
            console.crew.captain_at = "SONAR"
        else:
            self.on_foot = OnFoot(app, console, cr.by_periscope())

    @property
    def name(self):
        return "OVER" if self.over else "PLAY"

    @property
    def esc_quits(self):
        return self.over and not self.run

    @property
    def holds_keys(self):
        return self.confirm

    @property
    def view(self):
        """The station view your hands are on."""
        con = self.console
        return stations.VIEWS["PERISCOPE" if con.looking and self.at != "ALL" else self.at]

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
        elif self.paused:
            pass
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 3:
            self.wheel.press()
        elif self.wheel.open and e.type == pygame.MOUSEMOTION:
            self.wheel.motion(*e.rel)
        elif self.wheel.open and e.type == pygame.MOUSEBUTTONUP and e.button == 3:
            order = self.wheel.release()
            if order:
                con.crew.order(*order)
        elif self.on_foot:
            said = self.on_foot.event(e)
            if said:
                self.say(said)
        else:
            self.station_event(e)
        return None

    def station_event(self, e):
        """Your hands on a station: its own keys and panels work; any other station key is an order."""
        con, view = self.console, self.view
        if e.type == pygame.KEYDOWN:
            action = settings.action_for(e.key)
            if action == "STAND UP" and self.at != "ALL" and not con.looking:
                station = next(s for s in cr.STATIONS if s.name == self.at)
                self.on_foot = OnFoot(self.app, con, cr.seated(station), cr.standing(station), focus=self.at)
                self.at = None
            elif stations.allows(view, action):
                con.key(e.key)
            elif crew.order_for(action, con):
                con.crew.order(*crew.order_for(action, con))
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            self.grip = stations.piece_at(view, e.pos)
            if self.grip:
                con.click(stations.through(self.grip, e.pos))
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            con.dragging, self.grip = None, None
        elif e.type == pygame.MOUSEMOTION and con.dragging and self.grip:
            con.drag(stations.through(self.grip, e.pos))
        elif e.type == pygame.MOUSEWHEEL:
            piece = stations.piece_at(view, pygame.mouse.get_pos())
            if piece:
                con.scroll(stations.through(piece, pygame.mouse.get_pos()), e.y)

    def say(self, text):
        self.note = (text, pygame.time.get_ticks())

    def update(self, dt):
        app, con = self.app, self.console
        running = not (self.paused or self.confirm or app.show_help)  # the key card covers the station
        self.lag = self.lag + dt if running else 0.0
        if con.log and con.log[-1] != self.log_seen:  # the crew's reports reach you wherever you are
            self.log_seen = con.log[-1]
            self.say(self.log_seen[6:])
        if self.over and self.at != "ALL":  # the boat is lost: the reckoning comes on the full console
            if self.on_foot:
                self.on_foot.leave()
            self.on_foot, self.at = None, "ALL"
        elif self.on_foot and running:
            then = self.on_foot.update(dt)
            if isinstance(then, tuple):
                self.sit(then[1])
            elif then == "EYEPIECE":
                self.sit("PERISCOPE")
                con.look()
                self.from_room = con.looking
        elif self.from_room and not con.looking:  # stepped back from the eyepiece: into the room again
            self.from_room = False
            self.at, self.on_foot = None, OnFoot(app, con, cr.at_eyepiece(), cr.by_periscope())
        while self.lag >= SIM_DT:  # fixed sim step: the same seed plays out the same at any frame rate
            self.lag -= SIM_DT
            held = NoKeys() if self.on_foot else stations.HeldAt(self.view, pygame.key.get_pressed(), settings.code)
            con.update(SIM_DT, held)
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

    def sit(self, station):
        self.on_foot.leave()
        self.on_foot, self.at = None, station
        con = self.console
        con.crew.captain_at = station
        con.crt_page = stations.VIEWS[station].page

    def draw(self, screen, dt):
        st, con = self.app.station, self.console
        st.over_hint = "ANY KEY: DEBRIEF" if self.run else None
        st.confirm = None
        if self.confirm:
            question = (["LEAVE TRAINING?", "BACK TO THE CHAPTER LIST"] if con.tutorial else
                        ["ABANDON PATROL?", "IT WON'T COUNT FOR OR AGAINST YOU"] if self.run else
                        ["QUIT PATROL?", f"{con.score:,} GRT GOES ON THE SCORES"])
            st.confirm = question + ["", "[Y] YES      [N] NO"]
        full = not self.on_foot and (self.at == "ALL" or con.looking)
        if full:  # the full console and the eyepiece draw their own questions, pause and log
            st.draw(screen, con, self.name, self.paused, self.app.show_help, dt)
        else:
            if self.on_foot:
                self.on_foot.draw(screen, dt)
            else:
                screen.blit(self.app.canvas(self.view, con, self.paused, dt), (0, 0))
            notice(screen, st.confirm or (["PATROL PAUSED", "", "[P] RESUME"] if self.paused else []))
            said, at = self.note
            if said and pygame.time.get_ticks() - at < self.SUBTITLE_TIME:
                subtitle(screen, said)
            if self.app.show_help:
                st.draw_help(screen)
        if self.wheel.open:
            self.wheel.draw(screen, (W // 2, H // 2))


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
