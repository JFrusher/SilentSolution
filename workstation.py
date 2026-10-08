"""The physical workstation: a 1970s/80s control-room console around the CRTs, and the periscope eyepiece."""
import math
import random
import textwrap

import numpy as np
import pygame

from campaign import PATROLS, UPGRADES, objective
from console import ECHO_FADE
from displays import CLASS_TAGS, CLASSES, SPEC_BINS, TEMPLATES
from fire_control import FIELDS
from geometry import offset
from graphics import console_art as art
from graphics.crt_renderer import DIM, PHOSPHOR, RED, CRTRenderer
from graphics.periscope import EYE, PeriscopeRenderer, View
from layout import (
    ANNUNCIATORS,
    BLOW_BTN,
    CONSOLE,
    CRT_RECT,
    DC_ROW_H,
    DC_ROW_Y0,
    DEPTH_C,
    DEPTH_R,
    EYEPIECE_C,
    GAUGE_POS,
    GAUGE_R,
    GAUGE_SPECS,
    GAUGES,
    HIGHLIGHTS,
    HOLD_BTN,
    HYD_POS,
    LAMPS,
    LIB_RECT,
    LOG_POS,
    LOOK_BTN,
    MONITOR,
    NMKR_BTN,
    ORDER_SLIP,
    PAPER_RECT,
    PD_BTN,
    PING_BTN,
    RUDDER_BAR,
    SCOPE_C,
    SCOPE_LEVER,
    SCOPE_PANEL,
    SCOPE_R,
    SNORT_LEVER,
    SPEC_RECT,
    STRIP,
    TDC_PANEL,
    TDC_ROW_H,
    TDC_ROW_Y0,
    TELEGRAPH_BTNS,
    TELEGRAPH_RECT,
    TELETYPE,
    TUBE_SW,
    WF_H,
    WF_POS,
    WF_W,
    WHEEL_C,
    WHEEL_R,
    H,
    W,
)
from sensors import SCOPE_FOV
from settings import BAR_W, BAR_X, ROW_H, ROW_Y0, SETTINGS, VISIBLE
from settings import label as keylabel
from sim import (
    CRUSH_DEPTH,
    FEATHER_KT,
    KNOT,
    MAST_DEPTH,
    MAX_RUDDER,
    PERISCOPE_DEPTH,
    SCOPE_TOP,
    SOUND_SPEED,
    TELEGRAPH,
    TORP_MAX_RUN,
    YARD,
)
from tma import PLOT_SPAN
from tma import PLOT_WINDOW as TMA_WINDOW
from tuning import REPAIR_TIME
from tutorial import CHAPTERS
from version import __version__

FX = random.Random()  # presentation-only randomness: never touches the simulation's dice

# console sections: black faceplates set into the painted steel
HELM_PLATE = pygame.Rect(234, 486, 178, 212)
DIVE_PLATE = pygame.Rect(414, 486, 216, 214)
WEAPONS_PLATE = pygame.Rect(634, 486, 160, 214)
ALARM_PLATE = pygame.Rect(796, 486, 114, 214)


class Workstation:
    """Renders the operator station around the console state."""

    def __init__(self):
        self.frame = pygame.Surface((W, H))
        self.crt_surf = pygame.Surface(CRT_RECT.size)
        self.crt = CRTRenderer(CRT_RECT.size)
        self.scope_surf = pygame.Surface((SCOPE_R * 2, SCOPE_R * 2))
        self.scope_crt = CRTRenderer(self.scope_surf.get_size(), ghost_decay=200)  # long-persistence PPI phosphor
        self.background = self._background()
        self.overlay = self._overlay()
        self.yoke = art.helm_yoke(WHEEL_R)
        self.yoke_cache = {}
        self.paper = self._greenbar(PAPER_RECT.size)
        self.needles = {k: art.Needle() for k in ("DEPTH", "BATTERY", "NOISE", "HULL", "O2", "ORDER")}
        self.buttons = []  # (screen rect, name): what a click on the current CRT page can hit
        self.menu = None     # the settings page, while it is open
        self.career = None   # campaign career, for its page
        self.debrief = None  # the last patrol's debrief
        self.confirm = None  # lines of a yes/no question over the patrol, or None
        self.over_hint = None  # game-over key line, when it isn't the endless one
        self.last_replay = None  # path of the replay the last patrol left
        self.periscope = PeriscopeRenderer()
        self.scope_bg = self._periscope_background()
        self.scope_surround = self.scope_bg.convert_alpha()  # same art with a round hole: hides the square corners
        x, y = np.ogrid[:W, :H]
        hole = np.hypot(x - EYEPIECE_C[0], y - EYEPIECE_C[1]) < EYE // 2 - 2
        alpha = pygame.surfarray.pixels_alpha(self.scope_surround)
        alpha[hole] = 0
        del alpha

    @staticmethod
    def _greenbar(size):
        """Tractor-feed computer paper: pale green bands every few lines."""
        paper = art.texture(size, art.PAPER, grain=2.5, light=(1.02, 0.94))
        for y in range(0, size[1], 30):
            band = pygame.Surface((size[0] - 28, 15), pygame.SRCALPHA)
            band.fill((*art.PAPER_BAND, 120))
            paper.blit(band, (14, y))
        ring = pygame.Surface(size, pygame.SRCALPHA)  # somebody's mug
        for k, a in ((30, 70), (28, 40), (24, 18)):
            pygame.draw.circle(ring, (120, 84, 44, a), (size[0] - 70, 60), k, 2)
        paper.blit(ring, (0, 0))
        return paper

    # --- periscope screen ---
    def _periscope_background(self):
        """The optics module of an attack periscope: grey housing, rubber eyecup, training handles, readout panels."""
        bg = art.texture((W, H), (40, 43, 46), grain=2.5, light=(1.0, 0.8))
        cx, cy = EYEPIECE_C
        r = EYE // 2
        pygame.draw.circle(bg, (12, 12, 13), EYEPIECE_C, r + 34)        # rubber eyecup
        pygame.draw.circle(bg, (28, 29, 31), EYEPIECE_C, r + 30, 18)
        pygame.draw.circle(bg, art.CHROME, EYEPIECE_C, r + 13, 3)
        pygame.draw.circle(bg, (60, 62, 66), EYEPIECE_C, r + 9, 6)
        for k in range(6):
            art.screw(bg, art.polar(EYEPIECE_C, r + 40, k * 60 + 30), 5)
        for side in (-1, 1):  # training handles: black rubber grips on chrome arms
            hx = cx + side * (r + 54)
            pygame.draw.rect(bg, art.CHROME, (hx - 26 if side > 0 else hx, cy - 6, 26, 12))
            pygame.draw.rect(bg, (16, 16, 18), (hx - 16 + side * 12, cy - 78, 30, 156), border_radius=14)
            for k in range(-60, 61, 12):
                pygame.draw.line(bg, (40, 40, 44), (hx - 12 + side * 12, cy + k), (hx + 10 + side * 12, cy + k), 2)
        for rect in (pygame.Rect(30, 120, 230, 300), pygame.Rect(W - 260, 120, 230, 300)):
            art.faceplate(bg, rect)
        art.label_plate(bg, (145, 136), "SCOPE DATA", 12)
        art.tape(bg, (150, 404), "TRUE = REL + SHIP'S HEAD", 2, 11)
        art.label_plate(bg, (W - 145, 136), "SHIP CONTROL", 12)
        return bg.convert()

    def draw_periscope(self, f, con, paused):
        p, w = con.world.player, con.world
        sightings, wakes, bursts = con.view if con.view else ([], [], [])
        fov = SCOPE_FOV[con.high_power]
        true_brg = con.scope_true
        kt = p.speed / KNOT
        shake = max(0.0, kt - FEATHER_KT) * 0.8 + (1.0 if p.snorkeling else 0.0)
        marks = [(con.dial_true, "S", (40, 120, 60))]  # S: the sonar dial; T: where the TDC puts the target
        marks.append(((con.tdc.get("BRG") + p.heading) % 360, "T", (170, 40, 30)))
        view = View(true_brg, fov, con.optics.eye_height(), p.x, p.y, w.time, w.ocean, sightings, wakes, bursts,
                    under=con.view is None, shake=shake, scale_ref=0.0 if con.true_mode() else p.heading,
                    marks=marks)
        f.blit(self.periscope.render(view), (EYEPIECE_C[0] - EYE // 2, EYEPIECE_C[1] - EYE // 2))
        f.blit(self.scope_surround, (0, 0))
        keys = (f"{keylabel('TRAIN LEFT', 'TRAIN RIGHT')}  or drag   TRAIN",
                f"{keylabel('SCOPE POWER')}  or wheel   POWER",
                f"{keylabel('MARK')}     MARK TO FIRE CONTROL", f"{keylabel('LOOK')}     BACK TO STATION",
                f"{keylabel('RAISE SCOPE')}     LOWER SCOPE")  # drawn live: the bindings can change
        for i, line in enumerate(keys):
            art.engrave(f, line, (40, 440 + i * 20), 12, art.LEGEND_DIM, bold=False)

        # left panel: where the scope points and what it last measured
        x, y = 48, 164
        rows = [("TRUE BRG", f"{true_brg:05.1f}"), ("REL BRG", f"{con.scope_brg:05.1f}"),
                ("POWER", " 6" if con.high_power else "1.5")]
        if con.scope_fix:
            brg, rng, t = con.scope_fix
            rows += [("LAST MARK", f"{(brg - p.heading) % 360:05.1f}"), ("RANGE YD", f"{rng / YARD:6,.0f}"),
                     ("AGE S", f"{w.time - t:4.0f}")]
        for i, (k, v) in enumerate(rows):
            art.engrave(f, k, (x, y + i * 42), 12)
            art.counter(f, (x + 100, y - 4 + i * 42), v, 16)
        # right panel: the boat, and how visible we are
        x = W - 248
        rows = [("DEPTH M", f"{p.z:5.1f}"), ("LENS  M", f"{max(0.0, SCOPE_TOP - p.z - p.wave):4.1f}"),
                ("SPEED KT", f"{kt:4.1f}"), ("BATTERY", f"{p.battery:4.0f}")]
        for i, (k, v) in enumerate(rows):
            art.engrave(f, k, (x, y + i * 42), 12)
            art.counter(f, (x + 110, y - 4 + i * 42), v, 16)
        risk = con.exposure
        art.engrave(f, "EXPOSURE / MIN", (x, y + 4 * 42), 12, art.WARN if risk > 0.25 else art.LEGEND)
        bar = pygame.Rect(x, y + 4 * 42 + 20, 150, 12)  # LED bar graph
        for k in range(15):
            on = k < round(15 * min(risk, 1.0))
            color = art.RED if k >= 10 else art.AMBER if k >= 5 else art.GREEN
            pygame.draw.rect(f, color if on else tuple(v // 7 for v in color), (bar.x + k * 10, bar.y, 8, bar.h))
        art.engrave(f, f"{risk * 100:3.0f} %", (bar.right + 8, bar.y - 2), 12)
        if kt > FEATHER_KT:
            art.engrave(f, "FEATHER - SLOW DOWN", (x, bar.bottom + 10), 12, art.RED)
        if p.snorkeling:
            art.engrave(f, "DIESELS RUNNING - SONAR DEAF", (x, bar.bottom + 28), 12, art.WARN)

        # annunciator strip under the eyepiece: what you can still see from the scope
        pygame.draw.rect(f, (14, 15, 16), STRIP, border_radius=4)
        blink = int(w.time * 4) % 2 == 0
        lamps = (("TORPEDO", con.torpedo_warning and blink, art.RED),
                 ("ENEMY SONAR", con.lamp_enemy > 0 and blink, art.AMBER),
                 ("EXPOSED", risk > 0.25 and blink, art.RED), ("BROACH", p.broached and blink, art.RED),
                 ("DIESEL", p.snorkeling, art.GREEN))
        for i, (name, on, color) in enumerate(lamps):
            art.annunciator(f, (STRIP.x + 8 + i * 118, STRIP.y + 8, 110, 20), name, on, color)
        line = con.log[-1] if con.log else ""
        if con.tutorial and not con.tutorial.finished:
            line = f"ORDER {con.tutorial.progress}: {con.tutorial.goal}"
        if con.banner[1] > 0:
            line = con.banner[0]
        art.engrave(f, line, (STRIP.x + 610, STRIP.y + 10), 12, art.AMBER, bold=False)
        if paused:
            art.label_plate(f, EYEPIECE_C, "PAUSED  -  P TO RESUME", 16)

    # --- the station, built once ---
    def _background(self):
        bg = art.texture((W, H), art.WALL, grain=3)
        for rect in (TDC_PANEL, CONSOLE, GAUGES):
            art.panel(bg, rect)
        art.panel(bg, TELETYPE, base=(146, 140, 124))  # the printer's beige enamel, nicotine-stained
        art.faceplate(bg, TDC_PANEL.inflate(-12, -12))
        art.faceplate(bg, GAUGES.inflate(-14, -14))
        for plate in (TELEGRAPH_RECT, HELM_PLATE, DIVE_PLATE, WEAPONS_PLATE, ALARM_PLATE):
            art.faceplate(bg, plate, screws=False)
        for name, c in GAUGE_POS.items():
            face, fc = art.gauge_face(GAUGE_R, **GAUGE_SPECS[name])
            bg.blit(face, (c[0] - fc[0], c[1] - fc[1]))
        face, fc = art.gauge_face(DEPTH_R, "", 0, 300, 50, 10, red=(CRUSH_DEPTH, 300))
        bg.blit(face, (DEPTH_C[0] - fc[0], DEPTH_C[1] - fc[1]))
        column = (WHEEL_C[0] - 14, WHEEL_C[1], 28, HELM_PLATE.bottom - WHEEL_C[1] - 30)  # the yoke's column
        pygame.draw.rect(bg, (16, 16, 18), column)

        art.label_plate(bg, (TELEGRAPH_RECT.centerx, TELEGRAPH_RECT.top + 12), "ENGINE ORDER", 11)
        art.label_plate(bg, (HELM_PLATE.centerx, HELM_PLATE.top + 12), "SHIP CONTROL - HELM", 11)
        art.label_plate(bg, (DIVE_PLATE.centerx, DIVE_PLATE.bottom - 12), "DIVING  /  MASTS", 11)
        art.label_plate(bg, (WEAPONS_PLATE.centerx, WEAPONS_PLATE.top + 12), "WEAPONS", 11)
        art.label_plate(bg, (ALARM_PLATE.centerx, ALARM_PLATE.top + 2), "ALARMS", 10)
        art.label_plate(bg, (TDC_PANEL.centerx, TDC_PANEL.top + 14), "FIRE CONTROL - TDC", 12)
        art.label_plate(bg, (GAUGES.centerx, GAUGES.bottom - 16), "SHIP SYSTEMS", 12)
        art.label_plate(bg, (TELETYPE.x + 70, TELETYPE.y + 18), "TELEPRINTER", 12)
        art.engrave(bg, "ORDERED", (TELEGRAPH_RECT.x + 14, 530), 10, art.LEGEND_DIM)
        art.engrave(bg, "SHAFT KTS", (TELEGRAPH_RECT.x + 112, 530), 10, art.LEGEND_DIM)
        for i, (label, units, *_) in enumerate(FIELDS.values()):
            y = TDC_ROW_Y0 + i * TDC_ROW_H
            art.engrave(bg, label, (30, y + 2), 12)
            art.engrave(bg, units, (214, y + 3), 10, art.WARN)
        art.engrave(bg, "GYRO", (22, 440), 11)
        art.engrave(bg, "RUN YD", (124, 440), 11)
        for i, (sx, sy) in enumerate(TUBE_SW):
            art.engrave(bg, f"TUBE {i + 1}", (sx, sy - 33), 10, center=True)
        art.engrave(bg, "TORPS", (650, 590), 10, art.LEGEND_DIM)
        art.engrave(bg, "DECOYS", (718, 590), 10, art.LEGEND_DIM)
        art.dymo(bg, (SCOPE_LEVER[0] - 22, SCOPE_LEVER[1] - 44), "SCOPE")
        art.dymo(bg, (SNORT_LEVER[0] - 22, SNORT_LEVER[1] - 44), "SNORT")
        art.engrave(bg, "L30", (RUDDER_BAR.left - 22, RUDDER_BAR.top - 3), 9, art.LEGEND_DIM)
        art.engrave(bg, "R30", (RUDDER_BAR.right + 4, RUDDER_BAR.top - 3), 9, art.LEGEND_DIM)
        # the crew's amendments to the manual
        art.tape(bg, (226, 274), "CHECK BRG!", 7, 10)
        art.tape(bg, (598, 604), "MAX 8 KTS ON SNORT", -6, 9)
        art.tape(bg, (1200, 366), "HULL GAUGE LOW", -3, 10)
        art.tape(bg, (122, 688), "NO FLANK UNDER 60M", 2, 10)
        art.engrave(bg, "WAVE", (TELETYPE.x + 150, TELETYPE.y + 10), 10, art.INK)
        art.engrave(bg, "GRT", (TELETYPE.x + 210, TELETYPE.y + 10), 10, art.INK)
        return bg.convert()

    def _overlay(self):
        hole = pygame.Rect(0, 0, SCOPE_R * 2, SCOPE_R * 2)
        hole.center = SCOPE_C
        ov = art.bezel_overlay((W, H), [(MONITOR, CRT_RECT, 26), (SCOPE_PANEL, hole, None)])
        for c in [*GAUGE_POS.values()]:
            g = art.glint(GAUGE_R)
            ov.blit(g, (c[0] - g.get_width() / 2, c[1] - g.get_height() / 2))
        g = art.glint(DEPTH_R)
        ov.blit(g, (DEPTH_C[0] - g.get_width() / 2, DEPTH_C[1] - g.get_height() / 2))
        art.label_plate(ov, (MONITOR.centerx, MONITOR.bottom - 13), "SONAR  -  PASSIVE / ACTIVE / ACOUSTIC ANALYSIS",
                        11)
        art.tape(ov, (MONITOR.right - 70, MONITOR.top + 14), "DO NOT ADJUST", 3, 11)
        art.tape(ov, (MONITOR.right - 96, MONITOR.bottom - 12), "TUBE 2 STICKS - HIT IT TWICE", -2, 10)
        art.label_plate(ov, (SCOPE_C[0], SCOPE_PANEL.bottom - 12), "TACTICAL PPI", 10)
        return ov

    # --- frame ---
    def draw(self, screen, con, state, paused, show_help, dt):
        f = self.frame
        art.SAFE_LAMPS = SETTINGS["colorblind"]
        if con and con.looking and state == "PLAY":
            self.draw_periscope(f, con, paused)
        else:
            f.blit(self.background, (0, 0))
            self.draw_crt(con, state, paused)
            f.blit(self.crt_surf, CRT_RECT.topleft)
            self.draw_scope(con)
            f.blit(self.scope_surf, (SCOPE_C[0] - SCOPE_R, SCOPE_C[1] - SCOPE_R))
            if con:
                self.draw_needles(f, con, dt)
            f.blit(self.overlay, (0, 0))
            if con:
                self.draw_controls(f, con)
            self.draw_teletype(f, con)
            if con and con.tutorial and not con.tutorial.finished:
                self.draw_tutorial(f, con.tutorial)
        if con and con.debug:
            self.draw_debug(f, con, dt)
        if show_help:
            self.draw_help(f)
        jitter = con.shake * 6 if con else 0
        screen.fill((0, 0, 0))
        screen.blit(f, (FX.uniform(-jitter, jitter), FX.uniform(-jitter, jitter)))

    # --- centre monitor ---
    def draw_crt(self, con, state, paused):
        s, crt = self.crt_surf, self.crt
        s.fill((0, 0, 0))
        self.buttons = []
        if state == "SETTINGS":
            self._crt_settings(s, crt, self.menu)
        elif state == "CAREER":
            self._crt_career(s, crt, self.career)
        elif state == "DEBRIEF":
            self._crt_debrief(s, crt, self.debrief)
        elif state == "CHAPTERS":
            self._crt_chapters(s, crt)
        elif state == "TITLE" or con is None:
            self._crt_title(s, crt)
        else:
            self._crt_sonar(s, crt, con)
            if state == "OVER":
                self._crt_box(s, crt, ["LOST WITH ALL HANDS" if con.cause == "HULL BREACHED" else "CREW UNCONSCIOUS",
                                       con.cause, f"WAVE {con.wave}   {con.score:,} GRT SUNK", "",
                                       self.over_hint or "[R] NEW PATROL   [T] TITLE   [ESC] QUIT"])
            elif self.confirm:
                self._crt_box(s, crt, self.confirm)
            elif paused:
                self._crt_box(s, crt, ["PATROL PAUSED", "", "[P] RESUME"])
            if con.flash > 0:
                v = int(140 * con.flash)
                s.fill((v, v, v), special_flags=pygame.BLEND_RGB_ADD)
        crt.apply_post_processing(s)

    def _crt_box(self, s, crt, lines):
        box = pygame.Rect(0, 0, 420, 40 + 26 * len(lines))
        box.center = (s.get_width() // 2, s.get_height() // 2)
        crt.rect(s, box, (0, 0, 0))
        crt.frame(s, box, color=PHOSPHOR)
        for i, line in enumerate(lines):
            crt.text(s, line, (box.centerx, box.y + 30 + i * 26), RED if i == 0 else PHOSPHOR, big=i == 0, center=True)

    def _crt_title(self, s, crt):
        cx = s.get_width() // 2
        crt.text(s, "SILENT SOLUTION", (cx, 50), PHOSPHOR, huge=True, center=True)
        crt.text(s, "SUBMARINE OPERATOR WORKSTATION", (cx, 84), DIM, center=True)
        options = (("T", "TRAINING", "GUIDED DRILL: EVERY STATION, THEN LIVE EXERCISES"),
                   ("C", "CAMPAIGN", "SIX PATROLS - BRIEFINGS - RANKS - REFITS - CAREER SAVE"),
                   ("1", "CADET", "CLEAR WARNINGS - SLOW ENEMY FISH - SHORE POWER"),
                   ("2", "COMMANDER", "REAL ACOUSTICS - ZIG-ZAGS - DECOYS - BATTERY"),
                   ("3", "IRON CAPTAIN", "CAVITATION HEARD - HOMING COUNTER-FIRE - LEAKS - O2"))
        for i, (key, name, blurb) in enumerate(options):
            box = pygame.Rect(70, 108 + i * 46, 440, 42)
            crt.frame(s, box, color=PHOSPHOR)
            crt.text(s, f"[{key}]  {name}", (box.x + 16, box.y + 4), PHOSPHOR, big=True)
            if key.isdigit():
                crt.text(s, "ENDLESS", (box.right - 70, box.y + 8), DIM, small=True)
            crt.text(s, blurb, (box.x + 16, box.y + 26), DIM, small=True)
            self.buttons.append((box.move(CRT_RECT.topleft), name))
        box = pygame.Rect(70, 342, 440, 24)
        crt.frame(s, box, color=DIM)
        crt.text(s, "[S]  SETTINGS - SOUND, KEYS, MOUSE, TEXT, LAMPS", (box.x + 16, box.y + 5), PHOSPHOR, small=True)
        self.buttons.append((box.move(CRT_RECT.topleft), "SETTINGS"))
        crt.text(s, f"V{__version__} - BY JACOB FRUSHER - PYGAME-CE + NUMPY - F1 KEYS - ESC QUIT",
                 (cx, 380), DIM, small=True, center=True)

    def _crt_chapters(self, s, crt):
        cx = s.get_width() // 2
        crt.text(s, "TRAINING", (cx, 40), PHOSPHOR, huge=True, center=True)
        crt.text(s, f"PICK A CHAPTER. EACH STANDS ON ITS OWN; {keylabel('SKIP DRILL')} SKIPS A DRILL INSIDE ONE.",
                 (cx, 76), DIM, small=True, center=True)
        for i, (name, blurb) in enumerate(CHAPTERS.items()):
            box = pygame.Rect(70, 100 + i * 56, 440, 48)
            crt.frame(s, box, color=PHOSPHOR)
            crt.text(s, f"[{i + 1}]  {name}", (box.x + 16, box.y + 6), PHOSPHOR, big=True)
            crt.text(s, blurb, (box.x + 16, box.y + 30), DIM, small=True)
            self.buttons.append((box.move(CRT_RECT.topleft), i))
        self._crt_button(s, crt, (220, 336, 140, 26), "[ESC] TITLE", "BACK", DIM)

    def _crt_button(self, s, crt, rect, label, name, color=PHOSPHOR):
        rect = pygame.Rect(rect)
        crt.frame(s, rect, color=color)
        crt.text(s, label, rect.center, color, small=True, center=True)
        self.buttons.append((rect.move(CRT_RECT.topleft), name))

    def _crt_career(self, s, crt, career):
        cx = s.get_width() // 2
        crt.text(s, career.rank, (cx, 24), PHOSPHOR, big=True, center=True)
        if career.finished:
            crt.text(s, "CAMPAIGN COMPLETE. SIX PATROLS - FLAG RANK. ENJOY THE SHORE.", (cx, 60), PHOSPHOR, small=True,
                     center=True)
            y = 84
        else:
            p = PATROLS[career.patrol]
            crt.text(s, f"PATROL {career.patrol + 1} OF {len(PATROLS)}:  {p['name']}", (40, 50), PHOSPHOR)
            lines = textwrap.wrap(p["brief"], 70)
            for i, line in enumerate(lines):
                crt.text(s, line, (40, 74 + i * 15), DIM, small=True)
            y = 78 + len(lines) * 15
            crt.text(s, f"OBJECTIVE: {objective(p)} IN {p['waves']} WAVES - {p['rules']} RULES", (40, y), PHOSPHOR,
                     small=True)
            y += 20
        crt.text(s, "REFITS: " + (", ".join(career.upgrades) or "NONE YET"), (40, y), DIM, small=True)
        crt.text(s, "PATROL LOG", (40, y + 26), PHOSPHOR, small=True)
        crt.text(s, "HIGH SCORES (ENDLESS TOO)", (300, y + 26), PHOSPHOR, small=True)
        for i, e in enumerate(career.log[-6:][::-1]):
            crt.text(s, f"{e['patrol'][:14]:<14} {e['result']:<7} {e['grt']:>6,}", (40, y + 44 + i * 15),
                     RED if e["result"] == "LOST" else DIM, small=True)
        for i, e in enumerate(career.scores[:6]):
            crt.text(s, f"{e['grt']:>7,}  {e['mode'][:19]}", (300, y + 44 + i * 15), DIM, small=True)
        if not career.finished:
            self._crt_button(s, crt, (40, 340, 150, 26), "[ENTER] SAIL", "SAIL")
        self._crt_button(s, crt, (210, 340, 170, 26), "[N] NEW CAREER", "NEW CAREER", RED if career.note else DIM)
        self._crt_button(s, crt, (400, 340, 140, 26), "[ESC] TITLE", "BACK", DIM)
        if career.note:
            crt.text(s, career.note, (cx, 378), RED, small=True, center=True)

    def _crt_debrief(self, s, crt, d):
        cx = s.get_width() // 2
        p, ok = d["patrol"], d["result"] == "SUCCESS"
        title = {"SUCCESS": "PATROL COMPLETE", "FAILED": "PATROL FAILED", "LOST": "BOAT LOST"}[d["result"]]
        crt.text(s, title, (cx, 28), PHOSPHOR if ok else RED, huge=True, center=True)
        crt.text(s, f"{p['name']}  -  OBJECTIVE {objective(p)}", (cx, 64), DIM, small=True, center=True)
        kinds = {k: d["sunk"].count(k) for k in dict.fromkeys(d["sunk"])}
        rows = [f"SUNK: {d['grt']:,} GRT" + (" - " + ", ".join(f"{n} {k}" for k, n in kinds.items()) if kinds else ""),
                f"HULL {d['hull']:.0f}%    TIME ON PATROL {int(d['time'] // 60)} MIN"]
        if d["promoted"]:
            rows.append(f"PROMOTED: {d['promoted']}")
        elif d["result"] == "LOST":
            rows.append("THE FLOTILLA HAS ANOTHER BOAT FOR YOU. THE PATROL STANDS.")
        elif not ok:
            rows.append("OBJECTIVES NOT MET. THE PATROL STANDS - SAIL AGAIN.")
        for i, row in enumerate(rows):
            crt.text(s, row, (cx, 100 + i * 24), PHOSPHOR, center=True)
        if d["offer"]:
            crt.text(s, "CHOOSE A REFIT FOR THE NEXT PATROL", (cx, 196), PHOSPHOR, small=True, center=True)
            for i, name in enumerate(d["offer"]):
                self._crt_button(s, crt, (60, 216 + i * 44, 460, 36), f"[{i + 1}]  {name} - {UPGRADES[name]}", name)
        else:
            self._crt_button(s, crt, (190, 330, 200, 30), "[ENTER] CONTINUE", "CONTINUE")

    def _crt_settings(self, s, crt, menu):
        cx = s.get_width() // 2
        crt.text(s, "SETTINGS", (cx, 22), PHOSPHOR, big=True, center=True)
        crt.text(s, "UP/DOWN PICK - LEFT/RIGHT CHANGE - ENTER TOGGLE OR REBIND - ESC SAVE AND BACK", (cx, 44), DIM,
                 small=True, center=True)
        for k, row in enumerate(menu.rows[menu.top:menu.top + VISIBLE]):
            y, sel = ROW_Y0 + k * ROW_H, menu.top + k == menu.sel
            name, bar, text = menu.label(row)
            color = PHOSPHOR if sel else DIM
            if sel:
                crt.rect(s, (40, y, 500, ROW_H - 2), (0, 34, 10))
            crt.text(s, ("> " if sel else "  ") + name, (48, y + 3), color, small=True)
            if bar is not None:
                crt.frame(s, (BAR_X, y + 4, BAR_W, 10), color=DIM)
                crt.rect(s, (BAR_X + 1, y + 5, int((BAR_W - 2) * bar), 8), color)
                crt.text(s, text, (BAR_X + BAR_W + 12, y + 3), color, small=True)
            else:
                crt.text(s, text, (BAR_X, y + 3), RED if text == "PRESS A KEY..." else color, small=True)
        crt.text(s, menu.note or f"{menu.sel + 1} / {len(menu.rows)}   WHEEL SCROLLS", (cx, 360), DIM, small=True,
                 center=True)

    def _crt_sonar(self, s, crt, con):
        x0, y0 = WF_POS
        if con.crt_page == "TMA":
            self._crt_tma(s, crt, con)
        elif con.crt_page == "DAMAGE":
            self._crt_damage(s, crt, con)
        else:
            true = con.true_mode()
            wf = con.waterfall
            mode = "TRUE" if true else "REL"
            pages = f"{keylabel('TMA PAGE')}: TMA  {keylabel('DAMAGE BOARD')}: DAMAGE"
            crt.text(s, f"WATERFALL {mode} {wf.row_interval:g}S/LN  {pages}", (x0 + 14, 12), DIM, small=True)
            s.blit(wf.draw(relative=not true), WF_POS)
            crt.frame(s, (x0 - 1, y0 - 1, WF_W + 2, WF_H + 2))
            for b in (0, 90, 180, 270, 359):
                crt.text(s, f"{b:03d}", (x0 + b / 360 * WF_W - 10, y0 + WF_H + 3), DIM, small=True)
            per_min = 60 / wf.row_interval  # time axis: a tick a minute when the history is that long
            for m in range(1, int(WF_H / per_min) + 1):
                gy = y0 + m * per_min
                crt.line(s, (x0, gy), (x0 + 5, gy), DIM)
                crt.text(s, f"-{m}M", (x0 + 7, gy - 6), DIM, small=True)
            if true:  # own ship's head, so a true picture still says which way the boat points
                hx = x0 + con.world.player.heading / 360 * WF_W
                crt.line(s, (hx, y0 + WF_H - 6), (hx, y0 + WF_H + 6), (220, 255, 220), 2)
            dx = x0 + con.display_brg(con.dial_true) / 360 * WF_W
            crt.line(s, (dx, y0), (dx, y0 + WF_H - 1), RED)
            tdc_true = con.tdc.get("BRG") + con.world.player.heading
            tx = x0 + con.display_brg(tdc_true) / 360 * WF_W  # TDC estimate tick: stays on the trace if TMA is right
            crt.line(s, (tx, y0 - 5), (tx, y0 + 8), PHOSPHOR, 2)
            crt.line(s, (tx, y0 + WF_H - 8), (tx, y0 + WF_H + 1), PHOSPHOR, 2)
        self._spectrum(s, crt, con)

        for i, msg in enumerate(con.log):
            crt.text(s, msg, (LOG_POS[0], LOG_POS[1] + i * 15), PHOSPHOR if i == len(con.log) - 1 else DIM, small=True)

        p, ocean, sp = con.world.player, con.world.ocean, con.spectrum
        lock = "LOCK" if con.locked else "WEAK" if con.signal > 0.15 else "NONE"
        if con.tracking:
            lock = "TRACK"
        elif con.brg_err is not None and not con.locked:  # which way to train the dial onto the trace
            lock += f" {'<' if con.brg_err < 0 else '>'}{abs(con.brg_err):.1f}"
        cls = f"{CLASSES[sp.best]} {sp.confidence * 100:.0f}%" if sp.best is not None else "NO SIGNAL"
        sea = "STORM" if ocean.rain > 0.5 else "RAIN" if ocean.rain > 0.15 else "CALM"
        sol = con.tdc.solve()
        hyd = f"{con.display_brg(con.dial_true):05.1f} {'T' if con.true_mode() else 'R'}"
        rows = [("HYD", hyd, PHOSPHOR), ("SIG", lock, RED if con.locked or con.tracking else PHOSPHOR),
                ("CLASS", cls, PHOSPHOR if sp.best is not None else DIM),
                ("LAYER", ("BELOW" if p.z >= ocean.layer_depth else "ABOVE") + f" {ocean.layer_depth:.0f}M", PHOSPHOR),
                ("SEA", sea + (f"  EXP {con.exposure * 100:.0f}%" if p.scope_up or p.snorkel_up else ""),
                 RED if sea == "STORM" or con.exposure > 0.25 else PHOSPHOR),
                ("SOLN", f"GYRO {sol.gyro:05.1f}" if sol else "NONE", PHOSPHOR if sol else RED)]
        hx, hy = HYD_POS
        for i, (k, v, color) in enumerate(rows):
            crt.text(s, k, (hx, hy + i * 19), DIM, small=True)
            crt.text(s, v, (hx + 52, hy + i * 19 - 1), color)
        crt.rect(s, (hx + 52, hy + 35, int(min(con.signal, 1.0) * 96), 2))  # signal strength, under SIG

        text, left = con.banner
        if left > 0 and int(left * 4) % 2 == 0:  # cadet: clear visual ping warning
            crt.rect(s, (x0 + 10, y0 + 90, WF_W - 20, 34), (0, 0, 0))
            crt.frame(s, (x0 + 10, y0 + 90, WF_W - 20, 34), color=RED)
            crt.text(s, text, (x0 + WF_W / 2, y0 + 107), RED, big=True, center=True)

    def _crt_damage(self, s, crt, con):
        """Damage board: the repair list in the party's work order. Click a line to send them there first."""
        x0, y0 = WF_POS
        p, w = con.world.player, con.world
        crt.text(s, f"DAMAGE CONTROL  CLICK: WORK IT FIRST  {keylabel('DAMAGE BOARD')}: SONAR", (x0 + 14, 12), DIM,
                 small=True)
        crt.frame(s, (x0 - 1, y0 - 1, WF_W + 2, WF_H + 2))
        leaks = len(getattr(p, "leaks", ()))
        crt.text(s, f"HULL {w.hull:3.0f}%" + (f"   LEAKS {leaks}" if leaks else ""), (x0 + 10, y0 + 6),
                 RED if leaks or w.hull < 40 else PHOSPHOR, small=True)
        for k, name in enumerate(con.damage_rows()):
            y = y0 + DC_ROW_Y0 + k * DC_ROW_H
            left = p.damaged.get(name)
            if left is None:
                crt.text(s, f"   {name:<14}OK", (x0 + 10, y + 3), DIM, small=True)
                continue
            state = "WORKING" if k == 0 else f"QUEUED {k}"
            crt.text(s, f"{k + 1:>2} {name:<14}{state:<10}{int(left) // 60}:{int(left) % 60:02d}", (x0 + 10, y + 3),
                     PHOSPHOR if k == 0 else RED, small=True)
            if k == 0:  # the party's progress on the job in hand
                done = 1 - left / REPAIR_TIME[name]
                crt.frame(s, (x0 + 250, y + 5, 100, 8), color=DIM)
                crt.line(s, (x0 + 251, y + 9), (x0 + 251 + 98 * done, y + 9), PHOSPHOR, 6)

    def _crt_tma(self, s, crt, con):
        """Bearing (true) across, time down: your bearings as dots, the TDC's estimate as a curve. When course,
        speed and range are right, the curve runs through the dots."""
        x0, y0 = WF_POS
        now, own, tdc, log = con.world.time, con.world.player, con.tdc, con.tma
        centre = con.tma_centre()
        span = PLOT_SPAN

        def X(b):
            return x0 + WF_W / 2 + ((b - centre + 180) % 360 - 180) / span * WF_W

        def Y(t):
            return y0 + (now - t) / TMA_WINDOW * WF_H

        crt.text(s, f"TMA  BRG TRUE vs TIME      {keylabel('TMA PAGE')}: WATERFALL", (x0 + 14, 12), DIM, small=True)
        crt.frame(s, (x0 - 1, y0 - 1, WF_W + 2, WF_H + 2))
        grid = (12, 46, 22)
        for k in range(-20, 21, 10):
            gx = X(centre + k)
            crt.line(s, (gx, y0), (gx, y0 + WF_H - 1), grid)
            crt.text(s, f"{(centre + k) % 360:03.0f}", (gx - 10, y0 + WF_H + 3), DIM, small=True)
        for m in range(1, int(TMA_WINDOW // 60)):
            gy = Y(now - 60 * m)
            crt.line(s, (x0, gy), (x0 + WF_W - 1, gy), grid)
            crt.text(s, f"-{m}M", (x0 + 2, gy - 12), DIM, small=True)
        times = np.linspace(max(now - TMA_WINDOW, log.track[0][0] if log.track else now), now, 48)
        pred = log.predicted(times, now, own, tdc)
        if pred is not None:
            shown = [(X(b), Y(t)) for b, t in zip(pred[0], times) if abs((b - centre + 180) % 360 - 180) < span / 2]
            crt.lines(s, shown, PHOSPHOR, 2)
        for t, b, kind, _rng in log.recent(now, TMA_WINDOW):
            if abs((b - centre + 180) % 360 - 180) > span / 2:
                continue
            px, py = X(b), Y(t)
            if kind == "HYD":
                crt.circle(s, (px, py), 1, DIM, 0)
            elif kind == "MARK":
                crt.circle(s, (px, py), 3, PHOSPHOR, 0)
            elif kind == "SCOPE":
                crt.rect(s, (px - 3, py - 3, 7, 7), (220, 255, 220), 0)
            else:  # ECHO: ranged
                crt.circle(s, (px, py), 4, RED, 1)
        fit = log.fit(now, own, tdc)
        good = None if fit is None else PHOSPHOR if fit < 1.0 else RED if fit > 3 else DIM
        verdict = ("NO DATA", DIM) if fit is None else (f"FIT {fit:4.1f} DEG", good)
        crt.text(s, verdict[0], (x0 + WF_W - 100, y0 + 4), verdict[1], small=True)
        if con.diff["ping_warning"]:
            crt.text(s, f"{keylabel('AUTO-SOLVE')}: AUTO-SOLVE", (x0 + WF_W - 100, y0 + 18), DIM, small=True)

    def _spectrum(self, s, crt, con):
        r, sp = SPEC_RECT, con.spectrum
        crt.text(s, "ACOUSTIC PROFILE", (r.x, 12), DIM, small=True)
        crt.frame(s, r)
        for f, label in ((50, "50"), (200, "200"), (1000, "1K")):
            gx = r.x + math.log(f / 20) / math.log(100) * r.w
            crt.line(s, (gx, r.y + 1), (gx, r.bottom - 2), (12, 50, 24))
            crt.text(s, label, (gx - 8, r.bottom + 2), DIM, small=True)
        crt.text(s, "HZ", (r.right - 16, r.bottom + 2), DIM, small=True)
        ys = r.bottom - 2 - np.clip(sp.curve / 1.6, 0, 1) * (r.h - 6)
        xs = r.x + np.arange(SPEC_BINS) * (r.w - 1) / (SPEC_BINS - 1)
        crt.lines(s, list(zip(xs, ys)), PHOSPHOR, 2)
        cw = LIB_RECT.w // len(CLASSES)
        for i in range(len(CLASSES)):
            cell = pygame.Rect(LIB_RECT.x + i * cw, LIB_RECT.y, cw - 3, LIB_RECT.h - 14)
            hot = sp.best == i
            crt.frame(s, cell, color=PHOSPHOR if hot else DIM)
            tx = cell.x + 2 + np.arange(0, SPEC_BINS, 4) * (cell.w - 4) / SPEC_BINS
            ty = cell.bottom - 3 - TEMPLATES[i, ::4] * (cell.h - 6)
            crt.lines(s, list(zip(tx, ty)), PHOSPHOR if hot else DIM, 1)
            crt.text(s, CLASS_TAGS[i], (cell.centerx, cell.bottom + 7), PHOSPHOR if hot else DIM, small=True,
                     center=True)

    # --- tactical scope ---
    def draw_scope(self, con):
        s, crt, R = self.scope_surf, self.scope_crt, SCOPE_R
        s.fill((0, 0, 0))
        c = (R, R)
        for k in (1, 2, 3, 4):
            crt.circle(s, c, (R - 6) * k / 4, (14, 60, 30))
        crt.line(s, (R, 6), (R, 2 * R - 6), (14, 60, 30))
        crt.line(s, (6, R), (2 * R - 6, R), (14, 60, 30))
        crt.text(s, "N", (R - 4, 8), DIM, small=True)
        if con:
            self._scope_contents(s, crt, con, c)
        crt.apply_post_processing(s)

    def _scope_contents(self, s, crt, con, c):
        R, world = SCOPE_R, con.world
        own = world.player
        scale = (R - 6) / (con.scope_range * YARD)

        def P(x, y):
            return c[0] + x * scale, c[1] - y * scale

        age = world.time - con.ping_time
        ring = SOUND_SPEED * age / 2 * scale  # echo arrives when the ring reaches the reflector
        if 0 < ring < R:
            crt.circle(s, c, ring, PHOSPHOR, 2)
        for ex, ey, t in con.echoes:
            fade = 1 - (world.time - t) / ECHO_FADE
            crt.circle(s, P(ex - own.x, ey - own.y), 3, (int(70 * fade), int(255 * fade), int(120 * fade)), 0)
        for brg, color, on in ((con.dial_true, (150, 40, 30), True), (con.scope_true, (190, 150, 60),
                                                                       world.player.scope_up)):
            if on:  # sonar dial and periscope bearings: where the sensors are looking, on the same plot
                crt.line(s, c, P(*offset(0, 0, brg, 1e6)), color, 1)
        for brg, _ in con.enemy_pings:
            crt.line(s, c, P(math.sin(math.radians(brg)) * 1e6, math.cos(math.radians(brg)) * 1e6), RED, 2)
        tdc, sol = con.tdc, con.tdc.solve()
        vx, vy = tdc.target_velocity()
        ahead = sol.time * 1.3 if sol else 300.0
        crt.line(s, P(tdc.x - vx * 60, tdc.y - vy * 60), P(tdc.x + vx * ahead, tdc.y + vy * ahead), DIM)
        px, py = P(tdc.x, tdc.y)
        crt.rect(s, (px - 3, py - 3, 7, 7), PHOSPHOR, 1)
        if sol:
            ix, iy = sol.intercept
            crt.line(s, c, P(ix, iy), PHOSPHOR)
            qx, qy = P(ix, iy)
            crt.line(s, (qx - 3, qy - 3), (qx + 3, qy + 3), RED, 2)
            crt.line(s, (qx - 3, qy + 3), (qx + 3, qy - 3), RED, 2)
        for t in world.torpedoes:
            if not t.hostile:  # own fish only: wire telemetry while the wire holds
                fx, fy = P(t.x - own.x, t.y - own.y)
                crt.circle(s, (fx, fy), 2 if t.wired else 1, RED, 0)
                if t is con.wire_sel:
                    crt.circle(s, (fx, fy), 6, RED, 1)
                    if t.wire_aim:
                        ax, ay = P(t.wire_aim[0] - own.x, t.wire_aim[1] - own.y)
                        crt.line(s, (fx, fy), (ax, ay), DIM)
                        crt.line(s, (ax - 3, ay), (ax + 3, ay), RED)
                        crt.line(s, (ax, ay - 3), (ax, ay + 3), RED)
                    keys = f"{keylabel('WIRE LEFT')} {keylabel('WIRE RIGHT')} {keylabel('CUT WIRE')}"
                    crt.text(s, f"WIRE T{t.tube}  {keys}", (R, 26), RED, small=True, center=True)
        h = math.radians(own.heading)
        crt.circle(s, c, 3, PHOSPHOR)
        crt.line(s, c, (c[0] + 12 * math.sin(h), c[1] - 12 * math.cos(h)), PHOSPHOR, 2)
        crt.text(s, f"{con.scope_range:,.0f} YD", (R, 2 * R - 30), PHOSPHOR, small=True, center=True)

    # --- instruments ---
    def draw_needles(self, f, con, dt):
        p, world, nd = con.world.player, con.world, self.needles
        stress = 0.6 if p.z > CRUSH_DEPTH else 0.05
        values = {"DEPTH": (p.z, stress), "BATTERY": (p.battery, 0.15), "NOISE": (p.noise, 0.02 + 0.04 * p.cavitating),
                  "HULL": (world.hull, 0.1 + 0.2 * (world.hull < 50))}
        for name, (v, jitter) in values.items():
            spec, c = GAUGE_SPECS[name], GAUGE_POS[name]
            shown = nd[name].update(v, dt, jitter * (spec["hi"] - spec["lo"]) / 100)
            art.needle(f, c, art.value_angle(shown, spec["lo"], spec["hi"]), GAUGE_R - 20)
        if p.uses_oxygen:
            c = GAUGE_POS["BATTERY"]
            art.needle(f, c, art.value_angle(nd["O2"].update(p.o2, dt), 0, 100), GAUGE_R - 30, art.BLUE, 2)
            art.engrave(f, "BLUE: O2", (c[0], c[1] - 26), 9, art.BLUE, center=True)
        dc = GAUGE_POS["DEPTH"]
        art.counter(f, (dc[0] - 36, dc[1] + 44), f"{14.7 + p.z * 1.4228:4.0f}", 11, art.RED)
        art.engrave(f, "PSI", (dc[0] + 28, dc[1] + 47), 9, art.WARN)
        order = nd["ORDER"].update(p.ordered_depth, dt)
        art.needle(f, DEPTH_C, art.value_angle(order, 0, 300), DEPTH_R - 16, art.WARN, 3)
        art.needle(f, DEPTH_C, art.value_angle(p.z, 0, 300), DEPTH_R - 22, art.WHITE, 1, tail=6)

    def draw_controls(self, f, con):
        p, world = con.world.player, con.world
        blink = int(world.time * 4) % 2 == 0
        # engine order telegraph: backlit buttons, LED ordered/actual
        idx = con.telegraph_index()
        art.counter(f, (TELEGRAPH_RECT.x + 16, 548), f"{TELEGRAPH[idx][1]:4.1f}", 18)
        art.counter(f, (TELEGRAPH_RECT.x + 114, 548), f"{p.speed / KNOT:4.1f}", 18, art.GREEN)
        for i, (b, (name, _)) in enumerate(zip(TELEGRAPH_BTNS, TELEGRAPH)):
            art.button(f, b, name, lit=i == idx, color=art.RED if name == "FLANK" else art.AMBER)
        # helm: control yoke turns with the rudder
        angle = int(p.rudder * 2)
        if angle not in self.yoke_cache:
            self.yoke_cache[angle] = pygame.transform.rotate(self.yoke, -angle)
        y = self.yoke_cache[angle]
        f.blit(y, y.get_rect(center=WHEEL_C))
        pygame.draw.rect(f, (8, 8, 9), RUDDER_BAR.inflate(4, 4))
        for k in range(-3, 4):
            x = RUDDER_BAR.centerx + k * (RUDDER_BAR.w / 2 - 3) / 3
            pygame.draw.line(f, art.LEGEND_DIM, (x, RUDDER_BAR.top), (x, RUDDER_BAR.bottom), 1)
        px = RUDDER_BAR.centerx + p.rudder / MAX_RUDDER * (RUDDER_BAR.w / 2 - 3)
        pygame.draw.rect(f, art.WARN, (px - 3, RUDDER_BAR.top - 2, 6, RUDDER_BAR.h + 4))
        art.engrave(f, "HDG", (HELM_PLATE.x + 14, RUDDER_BAR.bottom + 8), 10, art.LEGEND_DIM)
        art.counter(f, (HELM_PLATE.x + 40, RUDDER_BAR.bottom + 6), f"{p.heading:05.1f}", 11)
        art.engrave(f, "RUD", (HELM_PLATE.x + 106, RUDDER_BAR.bottom + 8), 10, art.LEGEND_DIM)
        side = "R" if p.rudder > 0.5 else "L" if p.rudder < -0.5 else "-"
        art.counter(f, (HELM_PLATE.x + 132, RUDDER_BAR.bottom + 6), f"{abs(p.rudder):2.0f}" + side, 11)
        # diving station and masts
        holding = abs(p.ordered_depth - p.z) < 1 and not p.blowing
        art.button(f, HOLD_BTN, "HOLD", lit=holding, color=art.GREEN)
        art.button(f, BLOW_BTN, "BLOW", lit=p.blowing and blink, color=art.RED)
        art.button(f, PD_BTN, "P.D.", lit=abs(p.ordered_depth - PERISCOPE_DEPTH) < 0.5, color=art.BLUE)
        for (lx, ly), up, ready, color in ((SCOPE_LEVER, p.scope_up, p.z <= MAST_DEPTH, art.AMBER),
                                           (SNORT_LEVER, p.snorkel_up, p.z <= MAST_DEPTH, art.GREEN)):
            art.toggle(f, (lx, ly), up)
            art.lamp(f, (lx, ly + 28), up or (ready and blink and con.tutorial is not None), color, 5)
        art.button(f, LOOK_BTN, "LOOK", lit=p.scope_up, color=art.AMBER)
        if "PERISCOPE" in p.damaged:
            art.engrave(f, "JAMMED", (SCOPE_LEVER[0], SCOPE_LEVER[1] + 40), 9, art.RED, center=True)
        planes = "BLOWING" if p.blowing else "LEVEL" if holding else "DIVE" if p.ordered_depth > p.z else "RISE"
        art.engrave(f, f"PLANES {planes}   ORDER {p.ordered_depth:.0f} M", (DEPTH_C[0], HOLD_BTN.bottom + 10), 10,
                    art.LEGEND, center=True)
        # weapons: guarded firing switches
        for i, (sx, sy) in enumerate(TUBE_SW):
            r = con.tubes[i]
            broken = f"TUBE {i + 1}" in p.damaged
            ready, empty = r == 0 and not broken, r == math.inf
            art.toggle(f, (sx, sy), ready, guard_color=art.RED)
            art.lamp(f, (sx + 26, sy - 16), ready or (not empty and blink), art.GREEN if ready else art.AMBER, 5)
            state = "DAMAGED" if broken else "READY" if ready else "EMPTY" if empty else f"{r:2.0f} S"
            art.engrave(f, state, (sx, sy + 36), 10, art.RED if empty or broken else art.LEGEND, center=True)
        art.counter(f, (650, 604), f"{p.torpedoes:02d}", 14)
        art.counter(f, (718, 604), f"{p.noisemakers:02d}", 14)
        art.button(f, NMKR_BTN, f"NOISEMAKER  [{keylabel('NOISEMAKER')}]", color=art.AMBER)
        art.button(f, PING_BTN, f"ACTIVE PING  [{keylabel('PING')}]", lit=world.time - con.ping_time < 0.6,
                   color=art.RED)
        # annunciator panel: legend on every tile, so colour is never the only cue
        exposed = con.exposure > 0.25
        masts = p.scope_up or p.snorkel_up
        states = (con.lamp_enemy > 0 and blink, con.torpedo_warning and blink, p.cavitating, p.snorkeling,
                  masts and (blink or not exposed), p.broached and blink, bool(p.leaks),
                  p.z > CRUSH_DEPTH - 20 and blink, p.z >= world.ocean.layer_depth)
        colors = (art.AMBER, art.RED, art.AMBER, art.GREEN, art.RED if exposed else art.AMBER, art.RED, art.RED,
                  art.RED, art.BLUE)
        for rect, name, on, color in zip(ANNUNCIATORS, LAMPS, states, colors):
            art.annunciator(f, rect, name, on, color)
        # TDC readouts
        for i, (name, (_, _, fmt, *_)) in enumerate(FIELDS.items()):
            y = TDC_ROW_Y0 + i * TDC_ROW_H
            if i == con.tdc.selected:
                pygame.draw.polygon(f, art.WARN, [(17, y + 3), (17, y + 15), (25, y + 9)])
            art.counter(f, (112, y), fmt.format(con.tdc.get(name)), 12)
        sol = con.tdc.solve()
        far = sol is not None and sol.run > TORP_MAX_RUN
        art.counter(f, (56, 438), f"{sol.gyro:05.1f}" if sol else "---.-", 11)
        art.counter(f, (172, 438), f"{sol.run / YARD:6,.0f}" if sol else "------", 11, art.RED if far else art.AMBER)
        art.lamp(f, (250, 448), sol is not None, art.RED if far else art.GREEN, 5)

    def draw_teletype(self, f, con):
        r = PAPER_RECT
        f.blit(self.paper, r.topleft)
        tt = con.teletype if con else None
        fed = tt.fed if tt else 0
        for k in range(0, r.h + 14, 14):  # tractor-feed holes creep up as the paper feeds
            y = r.bottom - ((k + fed * 7) % (r.h + 14))
            for x in (r.x + 7, r.right - 7):
                pygame.draw.circle(f, (176, 180, 170), (x, int(y)), 3)
        if tt:
            big = SETTINGS["large_text"]
            font, lh = art.mono(15 if big else 12), 19 if big else 15
            rows = (r.h - 16 - (ORDER_SLIP.h + 8 if con.tutorial else 0)) // lh
            lines = [*list(tt.lines)[-(rows - 1):], tt.typing]
            for i, line in enumerate(lines):
                f.blit(font.render(line, True, art.INK), (r.x + 20, r.bottom - 12 - (len(lines) - i) * lh))
            if tt.queue and int(pygame.time.get_ticks() / 150) % 2:
                cx = r.x + 20 + font.size(tt.typing)[0]
                pygame.draw.rect(f, art.INK, (cx, r.bottom - 12 - lh, 7, lh - 3))
            art.counter(f, (TELETYPE.x + 184, TELETYPE.y + 8), f"{con.wave:02d}", 13)
            art.counter(f, (TELETYPE.x + 234, TELETYPE.y + 8), f"{con.score:6d}", 12)
        pygame.draw.rect(f, (60, 58, 52), r, 2)

    def draw_tutorial(self, f, tut):
        pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 160)
        color = (255, int(150 + 90 * pulse), 40)
        for name in tut.step.highlight:
            shape = HIGHLIGHTS[name]
            if isinstance(shape, pygame.Rect):
                pygame.draw.rect(f, color, shape, 3, border_radius=8)
            else:
                pygame.draw.circle(f, color, shape[0], shape[1], 3)
        slip = ORDER_SLIP
        pygame.draw.rect(f, (250, 246, 226), slip)
        pygame.draw.rect(f, art.INK_RED, slip, 2)
        art.engrave(f, f"ORDER {tut.progress}", (slip.x + 8, slip.y + 4), 11, art.INK_RED)
        art.engrave(f, f"{SETTINGS['keys']['SKIP DRILL'].upper()} SKIPS", (slip.right - 34, slip.y + 11), 10, art.INK,
                    center=True)
        font = art.mono(13, True)
        for i, line in enumerate(textwrap.wrap(tut.goal, 34)[:2]):
            f.blit(font.render(line, True, art.INK), (slip.x + 8, slip.y + 22 + i * 17))

    def draw_debug(self, f, con, dt):
        """Playtest overlay: frame rate, ocean and own-boat state, and the truth about every contact."""
        self.fps = 0.9 * getattr(self, "fps", 60.0) + 0.1 * (1.0 / max(dt, 1e-3))
        w, p, o = con.world, con.world.player, con.world.ocean
        font = art.mono(12, True)
        states = {}
        for ai in w.ais:
            key = f"{ai.ship.kind[:3]}:{ai.state}"
            states[key] = states.get(key, 0) + 1
        lines = [f"FPS {self.fps:5.1f}   T+ {w.time:7.1f} s   WAVE {con.wave}",
                 f"SEA {o.sea_state}  HS {o.wave_height:3.1f} m  WIND {o.wind:4.1f}  RAIN {o.rain:3.2f}  "
                 f"VIS {o.visibility:5.0f}",
                 f"OWN z {p.z:5.1f} kt {p.speed / KNOT:4.1f} noise {p.noise:4.2f} cav {int(p.cavitating)} "
                 f"exp {p.exposed or '-'}",
                 f"EXPOSURE/MIN {con.exposure * 100:4.1f}%   HULL {w.hull:5.1f}   BATT {p.battery:5.1f}",
                 f"TARGETS {len(w.targets)}  TORPS {len(w.torpedoes)}  CHARGES {len(w.charges)}",
                 *[f"  {k:14s} x{n}" for k, n in sorted(states.items())]]
        box = pygame.Surface((420, 18 * len(lines) + 12), pygame.SRCALPHA)
        box.fill((0, 0, 0, 190))
        for i, line in enumerate(lines):
            box.blit(font.render(line, True, (255, 230, 120)), (8, 6 + i * 18))
        f.blit(box, (W - 430, H - box.get_height() - 10))
        if con.looking:
            return
        scale = (SCOPE_R - 6) / (con.scope_range * YARD)  # truth on the tactical scope, same projection
        state = {id(ai.ship): ai.state for ai in w.ais}
        for t in [*w.targets, *w.torpedoes]:
            x, y = SCOPE_C[0] + (t.x - p.x) * scale, SCOPE_C[1] - (t.y - p.y) * scale
            if math.hypot(x - SCOPE_C[0], y - SCOPE_C[1]) > SCOPE_R:
                continue
            hostile = getattr(t, "hostile", False)
            color = (255, 80, 60) if hostile else (255, 230, 120)
            pygame.draw.circle(f, color, (int(x), int(y)), 3, 1)
            tag = t.kind[0] + (":" + state[id(t)][:3] if id(t) in state else "") + (f" {t.z:.0f}m" if t.z > 20 else "")
            f.blit(font.render(tag, True, color), (x + 4, y - 7))

    HELP_ROWS = (  # (actions, what, mouse); keys come from the live bindings
        (("TRAIN LEFT", "TRAIN RIGHT"), "hydrophone dial (scope at the eyepiece)", "click waterfall / wheel"),
        (("MARK",), "mark bearing into TDC (scope: + range)", ""),
        (("TDC ROW UP", "TDC ROW DOWN"), "select TDC field", "click row"),
        (("TDC VALUE UP", "TDC VALUE DOWN"), "adjust TDC field (hold to run)", "mouse wheel"),
        (("RUDDER LEFT", "RUDDER RIGHT", "RUDDER AMIDSHIPS"), "rudder / amidships", "drag the yoke"),
        (("SLOWER", "FASTER"), "engine order", "click a button"),
        (("SHALLOWER", "DEEPER"), "depth order -/+ 10 m", "click order dial"),
        (("HOLD DEPTH", "BLOW", "PERISCOPE DEPTH"), "hold / blow / periscope depth", "buttons"),
        (("PING",), "active ping - reveals you", "button"),
        (("FIRE", "FIRE TUBE 1", "FIRE TUBE 2"), "fire salvo (SPREAD) / tube 1 / tube 2", "tube switch"),
        (("NOISEMAKER",), "noisemaker decoy astern", "button"),
        (("SCOPE RANGE",), "tactical scope range", "click scope (no fish)"),
        (("RAISE SCOPE", "RAISE SNORKEL"), "periscope / snorkel up-down", "levers"),
        (("LOOK", "SCOPE POWER"), "look through scope / power", "LOOK / wheel"),
        (("WIRE LEFT", "WIRE RIGHT", "NEXT FISH", "CUT WIRE"), "wire: nudge / next fish / cut", "click fish, aim"),
        (("TMA PAGE", "AUTO-SOLVE", "DAMAGE BOARD"), "TMA / auto-solve / damage board", ""),
        (("BEARING MODE", "WATERFALL SCALE", "SCOPE TO SONAR"), "true-rel / waterfall time / scope to sonar", ""),
        (("ACKNOWLEDGE", "SKIP DRILL", "DEBUG"), "acknowledge / skip drill / debug", "click order slip"),
        ((), "pause / this card / quit (asks first)", ""),
    )

    def draw_help(self, f):
        """The key card, rendered once per set of bindings: the paper texture alone costs ~70 ms."""
        stamp = tuple(SETTINGS["keys"].values())
        if getattr(self, "_help", (None,))[0] != stamp:
            card = art.texture((600, 614), art.PAPER, grain=3)
            pygame.draw.rect(card, (40, 44, 48), card.get_rect(), 4)
            art.engrave(card, "STATION DRILL", (300, 26), 20, art.INK, center=True)
            for i, (actions, what, mouse) in enumerate(self.HELP_ROWS):
                y = 56 + i * 28
                art.engrave(card, keylabel(*actions) if actions else "P / F1 / ESC", (30, y), 13, art.INK)
                art.engrave(card, what, (210, y), 13, art.INK, bold=False)
                art.engrave(card, mouse, (440, y), 12, art.INK_RED, bold=False)
            self._help = (stamp, card)
        card = self._help[1]
        f.blit(card, card.get_rect(center=(W // 2, H // 2)))
