"""Silent Solution: game loop and screens (title, settings, training, replays, career, debrief, patrol).
Each screen is a Scene: it takes events, advances, draws, and hands back the next scene when it changes."""
import datetime
import math
import textwrap
import traceback
from collections import deque
from pathlib import Path

import numpy as np
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
from graphics.room3d import COXSWAIN_AT, RoomRenderer, crew_places, legend_art, plot_art
from graphics.tabletop import ReplayView
from layout import CRT_RECT, HIGHLIGHTS, STRIP, H, W
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
        return stations.compose(view, self.console_frame(con, view.page, paused, dt), self.backdrop, con, self.station)

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
        if isinstance(choice, int) and 0 < choice < len(CHAPTERS) and not settings.SETTINGS["trained"]:
            return None  # the station drills open once the first watch is done
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


def speaker(line):
    """("HELM, AYE", "RIGHT 20 RUDDER") for a line that names who's calling it, else ("", line)."""
    who, sep, said = line.partition(": ")
    return (who, said) if sep and len(who) <= 30 and not any(c.isdigit() for c in who) else ("", line)


def voice(who):
    """The crewman behind a caption's caller ("CONN, SONAR" or "CHIEF, AYE"), or None for nobody in the room."""
    who = who.removeprefix("CONN, ").removesuffix(", AYE")
    who = {"CHIEF": "BALLAST CONTROL", "MANEUVERING": "HELM"}.get(who, who)
    return who if who in ("SONAR", "FIRE CONTROL", "RADIO", "BALLAST CONTROL", "DAMAGE CONTROL", "HELM",
                          "PLANES", "COXSWAIN") else None


def captions(screen, lines, bottom):
    """What's said, printed and heard aboard, newest at the bottom: the caller in amber, a sound in [brackets].
    lines: (text, opacity 0..1, turn) where turn, when set, is how far round (deg, + to the right) the speaker is
    from where you look, and an arrow points the way."""
    scale = settings.SETTINGS["caption_scale"]
    font = art.mono(round(15 * scale), True)
    rows = []
    for line, fade, turn in lines:
        who, said = speaker(line)
        wrapped = textwrap.wrap(said, round(100 / scale)) or [""]
        rows += [(who if i == 0 else "", part, said.startswith("["), fade, turn if i == 0 else None)
                 for i, part in enumerate(wrapped)]
    step = font.get_linesize() + 4
    for i, (who, part, sound, fade, turn) in enumerate(reversed(rows)):
        tag = font.render(f"{who}: " if who else "", True, (240, 190, 90))
        text = font.render(part, True, (170, 200, 235) if sound else (150, 240, 160))
        arrow = step if turn is not None else 0
        row = pygame.Surface((arrow + tag.get_width() + text.get_width() + 16, step - 2), pygame.SRCALPHA)
        row.fill((0, 0, 0, 180))
        if turn is not None:  # which way to look for him: left, right, or behind you
            c, a, r = (step / 2 + 4, row.get_height() / 2), math.radians(turn), step * 0.32
            tip = (c[0] + math.sin(a) * r, c[1] - math.cos(a) * r)
            wing = [(c[0] + math.sin(a + k) * r * 0.75, c[1] - math.cos(a + k) * r * 0.75) for k in (2.4, -2.4)]
            pygame.draw.polygon(row, (240, 190, 90), [tip, *wing])
        row.blit(tag, (arrow + 8, 2))
        row.blit(text, (arrow + 8 + tag.get_width(), 2))
        row.set_alpha(round(255 * fade))
        screen.blit(row, row.get_rect(midbottom=(W // 2, bottom - i * step)))


CREW_AT = {k: sat[:3, 3] + (0.0, 1.2, 0.0) for k, (sat, _) in crew_places().items()}  # each watchkeeper's head
CREW_AT["COXSWAIN"] = np.array(COXSWAIN_AT) + (0.0, 1.7, 0.0)
HALF_VIEW = math.degrees(math.atan(math.tan(math.radians(cr.FOVY / 2)) * W / H)) - 4  # just inside the screen edge


def turn_to(pose, who):
    """How far round (deg, + to the right) crewman `who` is from where `pose` looks, or None if he's in view."""
    d = CREW_AT[who] - pose.pos
    rel = (math.degrees(math.atan2(d[0], -d[2])) - pose.yaw + 180) % 360 - 180
    return rel if abs(rel) > HALF_VIEW else None


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
        self.fade = 0.0     # s left of a quick-travel's dip to black
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
            action = settings.action_for(e.key)
            order = crew.order_for(action, self.con)
            if order:
                self.con.crew.order(*order)
            elif action in stations.GLOBAL:  # acknowledge, skip drill, debug work wherever you stand
                self.con.key(e.key)
        return None

    def use(self):
        thing = self.room.target()
        if thing == "PERISCOPE":
            self.periscope()
        elif thing is not None and thing.working:
            self.take(thing)
        elif thing is not None:
            return f"{thing.name}: NOT MANNED THIS PATROL"
        return None

    def periscope(self):
        p = self.con.world.player
        if not p.scope_up:
            self.con.toggle_scope()  # take hold of the handles: up scope
        if p.scope_up:
            self.room.carry(cr.at_eyepiece(), "EYEPIECE")

    def take(self, station):
        self.focus = station.name
        self.room.carry(cr.seated(station), ("SEATED", station.name))

    def go(self, name):
        """Quick travel: a dip to black, and you're at the station (or the periscope), being carried in."""
        self.fade = 0.35
        if name == "PERISCOPE":
            self.room.pose = cr.by_periscope()
            self.periscope()
        else:
            station = next(s for s in cr.STATIONS if s.name == name)
            self.room.pose = cr.standing(station)
            self.take(station)

    def update(self, dt):
        """Walk; returns where a finished camera move has put you: ("SEATED", station), "EYEPIECE" or "ROOM"."""
        k = pygame.key.get_pressed()
        shift = k[pygame.K_LSHIFT] or k[pygame.K_RSHIFT]
        then = self.room.update(dt, k[pygame.K_w] - k[pygame.K_s], k[pygame.K_d] - k[pygame.K_a], shift)
        self.fade = max(0.0, self.fade - dt)
        if then == "ROOM":
            self.focus = None
        return then

    def draw(self, screen, dt, spoke=None):
        """spoke: crewman -> ticks of his last call."""
        app, con, w = self.app, self.con, self.con.world
        if self.focus:  # gliding to or from a station: only its screen, kept exact for the cut
            page, names = stations.VIEWS[self.focus].page, (self.focus,)
        else:  # one CRT page a frame, in turn, and every station on it
            self.turn = (self.turn + 1) % len(self.PAGES)
            page = self.PAGES[self.turn]
            names = [n for n in self.WORKING if stations.VIEWS[n].page == page]
        frame = app.console_frame(con, page, False, dt)  # the full console is drawn once a frame, at most
        screens = {n: stations.compose(stations.VIEWS[n], frame, app.backdrop, con, app.station) for n in names}
        plot = None
        if w.time - self.plot_at >= self.PLOT_EVERY:  # from our own navigation and the TMA log: what we know
            tdc, p = con.tdc, w.player
            solution = (tdc.x, tdc.y, *tdc.target_velocity())
            marks = [b for b in con.tma.recent(w.time, 600.0) if b[2] != "HYD"]  # marks and fixes, not the trace
            plot = plot_art(list(con.tma.track), p.heading, marks, solution, con.plot_notes)
            self.plot_at = w.time
        lamps = alerts(con)  # the lamps flash with their alarms; the legend at the conn says which
        alert = float(any(on for _, on, _ in lamps))
        aside = (self.focus,) if self.focus else ()  # his crewman steps out of the way of the station you take
        now = pygame.time.get_ticks()
        speaking = {k: (now - at) / 1000 for k, at in (spoke or {}).items() if now - at < 4000}
        working = {k: w.time - at for k, at in con.crew.worked.items() if w.time - at < 1.0}
        p = w.player
        wheels = (p.rudder * 1.5, max(-30.0, min(30.0, (p.ordered_depth - p.z) * 1.5)))  # helm; planes diving or rising
        tut = con.tutorial
        coxswain = tut.step.station if tut and not tut.finished else None  # in training he's at the conn
        screen.blit(app.room().render(self.room.pose, screens, plot, legend_art(lamps), alert, aside, now / 1000,
                                      speaking, working, wheels, coxswain), (0, 0))
        if self.fade:
            dark = pygame.Surface((W, H))
            dark.set_alpha(int(255 * self.fade / 0.35))
            screen.blit(dark, (0, 0))
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
    CAPTION_TIME = 8000  # ms a caption stays up

    def __init__(self, app, console, run=None):
        super().__init__(app)
        self.console, self.run = console, run
        self.over = self.confirm = self.paused = False
        self.lag = 0.0  # real time owed to the sim
        self.lost_at, self.leave_over = 0, False  # a lost campaign boat: when, and whether the player has moved on
        self.wheel = OrderWheel()  # the captain's orders, on the right mouse button
        self.from_room = False     # at the eyepiece by way of the room: stepping back puts you there again
        self.grip = None           # the station piece a drag started on
        self.captions = deque(maxlen=4)  # (line, when it went up, its crewman): the newest heard aboard
        self.spoke = {}  # crewman -> when he last made a call, so he looks round at you as he does
        self.heard = console.heard[-1][0] if console.heard else 0  # the last of console.heard captioned
        self.at = None  # the station you're working (the full console, "ALL", once the boat is lost)
        self.on_foot = OnFoot(app, console, cr.by_periscope())  # you start on your feet at the conn

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
            if order and order[0] == "GOTO":
                self.go(order[1])
            elif order:
                con.crew.order(*order)
        elif self.on_foot:
            said = self.on_foot.event(e)
            if said:
                self.say(said)
        else:
            self.station_event(e)
        return None

    def go(self, name):
        """Quick travel from the order wheel, from wherever you are; training keeps the full console."""
        con = self.console
        if self.at == "ALL" or self.over:
            return
        if not self.on_foot:
            station = next((s for s in cr.STATIONS if s.name == self.at), None)
            start = cr.seated(station) if station else cr.at_eyepiece()
            con.looking, self.from_room = False, False
            self.on_foot, self.at = OnFoot(self.app, con, start), None
        self.on_foot.go(name)

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
        now = pygame.time.get_ticks()
        who = voice(speaker(text)[0])
        self.captions.append((text, now, who))
        if who:
            self.spoke[who] = now

    def hear(self):
        """Caption every new line heard aboard, wherever you are. Sounds only with SOUND CAPTIONS on; the
        teleprinter not in training, whose card already shows it."""
        con = self.console
        training = con.tutorial and not con.tutorial.finished
        for n, kind, line in con.heard:
            if n > self.heard and not (kind == "SOUND" and not settings.SETTINGS["sound_captions"]
                                       or kind == "PRINT" and training):
                self.say(line if kind != "PRINT" or speaker(line)[0] else f"RADIO: {line}")
        self.heard = con.heard[-1][0] if con.heard else 0

    def update(self, dt):
        app, con = self.app, self.console
        running = not (self.paused or self.confirm or app.show_help)  # the key card covers the station
        self.lag = self.lag + dt if running else 0.0
        self.hear()
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

    def training(self, screen):
        """The instructor's card over the room or a station: the order, his last words, and where to go for it;
        at a station, rings round the parts the order is about."""
        tut, con = self.console.tutorial, self.console
        step = tut.step
        if not self.on_foot:
            pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 160)
            for name in step.highlight:
                for rect in stations.rings(self.view, HIGHLIGHTS[name]):
                    pygame.draw.rect(screen, (255, int(150 + 90 * pulse), 40), rect.inflate(6, 6), 3, border_radius=8)
        needed = "PERISCOPE" if "periscope" in step.highlight else stations.station_for(step.highlight, HIGHLIGHTS)
        lines = textwrap.wrap(f"ORDER {tut.progress}: {tut.goal}", 64)
        at_scope = self.on_foot and self.on_foot.room.target() == "PERISCOPE"
        if needed and needed != self.at and not con.looking and not (needed == "PERISCOPE" and at_scope):
            lines.append("GO TO THE PERISCOPE STAND" if needed == "PERISCOPE" else f"TAKE THE {needed} STATION")
        said = [*list(con.teletype.lines)[-4:], con.teletype.typing]
        card = pygame.Rect(0, 0, 720, 18 + 22 * len(lines) + 17 * len(said))
        card.midtop = (W // 2, 34)
        pygame.draw.rect(screen, (246, 242, 222), card)
        pygame.draw.rect(screen, art.INK_RED, card, 2)
        for i, line in enumerate(lines):
            colour = art.INK_RED if line.startswith(("TAKE", "GO TO")) else art.INK
            screen.blit(art.mono(16, True).render(line, True, colour), (card.x + 12, card.y + 8 + 22 * i))
        top = card.y + 12 + 22 * len(lines)
        for i, line in enumerate(said):
            screen.blit(art.mono(13).render(line, True, (90, 88, 80)), (card.x + 12, top + 17 * i))

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
                self.on_foot.draw(screen, dt, self.spoke)
                if con.shake > 0:  # a hit or a near charge throws the whole boat about
                    j, t = con.shake * 8, pygame.time.get_ticks()
                    screen.scroll(int(j * math.sin(t * 0.09)), int(j * math.cos(t * 0.13)))
            else:
                screen.blit(self.app.canvas(self.view, con, self.paused, dt), (0, 0))  # its frame shakes already
                stations.hover(screen, self.view, pygame.mouse.get_pos())
            if con.flash > 0:  # and the lights flare
                v = int(110 * con.flash)
                screen.fill((v, v, v), special_flags=pygame.BLEND_RGB_ADD)
            if con.tutorial and not con.tutorial.finished:
                self.training(screen)
            notice(screen, st.confirm or (["PATROL PAUSED", "", "[P] RESUME"] if self.paused else []))
        if self.at != "ALL":  # the full console has its own log; the eyepiece's strip shows only the last line
            now = pygame.time.get_ticks()
            pose = self.on_foot.room.pose if self.on_foot else None if full else cr.seated(
                next(s for s in cr.STATIONS if s.name == self.at))
            captions(screen, [(t, min(1.0, (self.CAPTION_TIME - (now - at)) / 1000), turn_to(pose, who)
                               if pose is not None and who else None)
                              for t, at, who in self.captions if now - at < self.CAPTION_TIME],
                     STRIP.top - 6 if full else H - 12)
        if not full and self.app.show_help:
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
