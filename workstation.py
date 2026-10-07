"""The physical workstation: renders the brass-and-iron station, the CRTs and the periscope eyepiece."""
import math
import random
import textwrap

import numpy as np
import pygame

from console import ECHO_FADE
from displays import CLASSES, CLASS_TAGS, SPEC_BINS, TEMPLATES
from fire_control import FIELDS
from graphics import brass
from graphics.crt_renderer import DIM, PHOSPHOR, RED, CRTRenderer
from graphics.periscope import EYE, PeriscopeRenderer, View
from layout import (BLOW_BTN, CONSOLE, CRT_RECT, DEPTH_C, DEPTH_R, EYEPIECE_C, GAUGES, GAUGE_POS, GAUGE_R,
                    GAUGE_SPECS, H, HIGHLIGHTS, HOLD_BTN, HYD_POS, LAMPS, LAMP_DY, LAMP_X, LAMP_Y0, LIB_RECT,
                    LOG_POS, LOOK_BTN, MONITOR, NMKR_BTN, ORDER_SLIP, PAPER_RECT, PD_BTN, PING_BTN, RUDDER_BAR,
                    SCOPE_C, SCOPE_LEVER, SCOPE_PANEL, SCOPE_R, SNORT_LEVER, SPEC_RECT, STRIP, TDC_PANEL, TDC_ROW_H,
                    TDC_ROW_Y0, TELEGRAPH_C, TELEGRAPH_R, TELETYPE, TUBE_SW, W, WF_H, WF_POS, WF_W, WHEEL_C,
                    WHEEL_R)
from sensors import SCOPE_FOV
from sim import (CRUSH_DEPTH, FEATHER_KT, KNOT, MAST_DEPTH, MAX_RUDDER, PERISCOPE_DEPTH, SCOPE_TOP, SOUND_SPEED,
                 TELEGRAPH, TORP_MAX_RUN, YARD)


# ---------- the physical workstation ----------
class Workstation:
    """Renders the brass-and-iron operator station around the console state."""

    def __init__(self):
        self.frame = pygame.Surface((W, H))
        self.crt_surf = pygame.Surface(CRT_RECT.size)
        self.crt = CRTRenderer(CRT_RECT.size)
        self.scope_surf = pygame.Surface((SCOPE_R * 2, SCOPE_R * 2))
        self.scope_crt = CRTRenderer(self.scope_surf.get_size(), ghost_decay=200)  # long-persistence PPI phosphor
        self.background = self._background()
        self.overlay = self._overlay()
        self.wheel = brass.ship_wheel(WHEEL_R)
        self.wheel_cache = {}
        self.paper = brass.texture(PAPER_RECT.size, brass.PAPER, grain=5, light=(1.05, 0.9))
        self.needles = {k: brass.Needle() for k in ("DEPTH", "BATTERY", "NOISE", "HULL", "O2", "ORDER")}
        self.title_buttons = []  # (screen rect, difficulty)
        self.periscope = PeriscopeRenderer()
        self.scope_bg = self._periscope_background()
        self.scope_surround = self.scope_bg.convert_alpha()  # same art with a round hole: hides the square corners
        x, y = np.ogrid[:W, :H]
        hole = np.hypot(x - EYEPIECE_C[0], y - EYEPIECE_C[1]) < EYE // 2 - 2
        alpha = pygame.surfarray.pixels_alpha(self.scope_surround)
        alpha[hole] = 0
        del alpha

    def _periscope_background(self):
        """The view from the eyepiece: dark trunk, brass eyepiece ring, training handles, engraved plates."""
        bg = brass.texture((W, H), (34, 34, 33), grain=4, light=(1.0, 0.8))
        cx, cy = EYEPIECE_C
        r = EYE // 2
        pygame.draw.circle(bg, brass.IRON_DARK, EYEPIECE_C, r + 34)
        pygame.draw.circle(bg, brass.BRASS_DARK, EYEPIECE_C, r + 26, 14)
        pygame.draw.circle(bg, brass.BRASS, EYEPIECE_C, r + 22, 6)
        pygame.draw.circle(bg, brass.BRASS_LIGHT, (cx - 3, cy - 3), r + 24, 2)
        for k in range(12):
            brass.rivet(bg, brass.polar(EYEPIECE_C, r + 26, k * 30 + 15), 4)
        for side in (-1, 1):  # training handles
            hx = cx + side * (r + 70)
            pygame.draw.rect(bg, brass.IRON_DARK, (hx - 22, cy - 20, 44, 40), border_radius=6)
            pygame.draw.rect(bg, brass.BRASS, (hx - 18 + side * 10, cy - 70, 26, 140), border_radius=10)
            pygame.draw.line(bg, brass.BRASS_LIGHT, (hx - 12 + side * 10, cy - 64), (hx - 12 + side * 10, cy + 64), 2)
        for rect in (pygame.Rect(30, 120, 230, 300), pygame.Rect(W - 260, 120, 230, 300)):
            brass.plate(bg, rect, brass.BRASS, spacing=200)
        brass.plaque(bg, (145, 136), "ATTACK PERISCOPE", 12)
        brass.plaque(bg, (W - 145, 136), "CONTROL ROOM", 12)
        keys = ("A / D  or drag   TRAIN", "TAB  or wheel   POWER", "M     MARK INTO TDC", "V     BACK TO STATION",
                "U     DOWN SCOPE")
        for i, line in enumerate(keys):
            brass.engrave(bg, line, (40, 440 + i * 20), 12, brass.BRASS_LIGHT, bold=False)
        return bg.convert()

    def draw_periscope(self, f, con, paused):
        p, w = con.world.player, con.world
        sightings, wakes, bursts = con.view if con.view else ([], [], [])
        fov = SCOPE_FOV[con.high_power]
        true_brg = (con.scope_brg + p.heading) % 360
        kt = p.speed / KNOT
        shake = max(0.0, kt - FEATHER_KT) * 0.8 + (1.0 if p.snorkeling else 0.0)
        view = View(true_brg, fov, con.optics.eye_height(), p.x, p.y, w.time, w.ocean, sightings, wakes, bursts,
                    under=con.view is None, shake=shake)
        f.blit(self.periscope.render(view), (EYEPIECE_C[0] - EYE // 2, EYEPIECE_C[1] - EYE // 2))
        f.blit(self.scope_surround, (0, 0))

        # left plate: where the scope points and what it last measured
        x, y = 48, 160
        rows = [("TRUE BRG", f"{true_brg:05.1f}"), ("REL BRG", f"{con.scope_brg:05.1f}"),
                ("POWER", "6 X" if con.high_power else "1.5X")]
        if con.scope_fix:
            brg, rng, t = con.scope_fix
            rows += [("LAST MARK", f"{(brg - p.heading) % 360:05.1f}"), ("RANGE YD", f"{rng / YARD:6,.0f}"),
                     ("AGE S", f"{w.time - t:4.0f}")]
        for i, (k, v) in enumerate(rows):
            brass.engrave(f, k, (x, y + i * 42), 12)
            brass.counter(f, (x + 100, y - 2 + i * 42), v, 14)
        # right plate: the boat, and how visible we are
        x = W - 248
        rows = [("DEPTH M", f"{p.z:5.1f}"), ("LENS  M", f"{max(0.0, SCOPE_TOP - p.z - p.wave):4.1f}"),
                ("SPEED KT", f"{kt:4.1f}"), ("BATTERY", f"{p.battery:4.0f}")]
        for i, (k, v) in enumerate(rows):
            brass.engrave(f, k, (x, y + i * 42), 12)
            brass.counter(f, (x + 110, y - 2 + i * 42), v, 14)
        risk = con.exposure
        brass.engrave(f, "EXPOSURE / MIN", (x, y + 4 * 42), 12, brass.INK_RED if risk > 0.25 else brass.INK)
        bar = pygame.Rect(x, y + 4 * 42 + 20, 150, 14)
        pygame.draw.rect(f, brass.IRON_DARK, bar)
        pygame.draw.rect(f, (200, 60, 30) if risk > 0.25 else (80, 170, 80), (bar.x, bar.y, int(bar.w * min(risk, 1.0)), bar.h))
        brass.engrave(f, f"{risk * 100:3.0f} %", (bar.right + 8, bar.y - 1), 12)
        if kt > FEATHER_KT:
            brass.engrave(f, "FEATHER! SLOW DOWN", (x, bar.bottom + 8), 12, brass.INK_RED)
        if p.snorkeling:
            brass.engrave(f, "DIESELS RUNNING - DEAF", (x, bar.bottom + 26), 12, brass.INK_RED)

        # warning strip: lamps you can still see from the scope, and the last thing sonar said
        pygame.draw.rect(f, brass.IRON_DARK, STRIP, border_radius=6)
        blink = int(w.time * 4) % 2 == 0
        lamps = (("TORPEDO", con.torpedo_warning and blink, (240, 50, 30)),
                 ("ENEMY SONAR", con.lamp_enemy > 0 and blink, (240, 170, 40)),
                 ("EXPOSED", risk > 0.25 and blink, (240, 50, 30)),
                 ("BROACH", p.broached and blink, (240, 50, 30)),
                 ("DIESEL", p.snorkeling, (80, 220, 90)))
        for i, (name, on, color) in enumerate(lamps):
            lx = STRIP.x + 20 + i * 132
            brass.lamp(f, (lx, STRIP.centery), on, color, 6)
            brass.engrave(f, name, (lx + 12, STRIP.y + 10), 11, brass.BRASS_LIGHT)
        line = con.log[-1] if con.log else ""
        if con.tutorial and not con.tutorial.finished:
            line = f"ORDER {con.tutorial.progress}: {con.tutorial.goal}"
        if con.banner[1] > 0:
            line = con.banner[0]
        brass.engrave(f, line, (STRIP.x + 690, STRIP.y + 10), 12, (236, 226, 200), bold=False)
        if paused:
            brass.plaque(f, EYEPIECE_C, "PAUSED  -  P TO RESUME", 16)

    def _background(self):
        bg = brass.texture((W, H), brass.WALL, grain=4)
        for rect, base in ((TDC_PANEL, brass.BRASS), (CONSOLE, brass.BRASS), (GAUGES, brass.BRASS),
                           (TELETYPE, brass.IRON)):
            brass.plate(bg, rect, base)
        for name, c in GAUGE_POS.items():
            face, fc = brass.gauge_face(GAUGE_R, **GAUGE_SPECS[name])
            bg.blit(face, (c[0] - fc[0], c[1] - fc[1]))
        face, fc = brass.telegraph_face(TELEGRAPH_R, [n for n, _ in TELEGRAPH])
        bg.blit(face, (TELEGRAPH_C[0] - fc[0], TELEGRAPH_C[1] - fc[1]))
        face, fc = brass.gauge_face(DEPTH_R, "", 0, 300, 50, 10, red=(CRUSH_DEPTH, 300))
        bg.blit(face, (DEPTH_C[0] - fc[0], DEPTH_C[1] - fc[1]))

        bottom = CONSOLE.bottom - 16
        brass.plaque(bg, (TELEGRAPH_C[0], bottom), "ENGINE TELEGRAPH")
        brass.plaque(bg, (WHEEL_C[0], bottom), "HELM")
        brass.plaque(bg, (DEPTH_C[0], bottom), "DIVING STATION")
        brass.plaque(bg, (712, CONSOLE.top + 14), "TORPEDO ROOM")
        brass.plaque(bg, (858, CONSOLE.top + 14), "WARNINGS")
        brass.plaque(bg, (TDC_PANEL.centerx, TDC_PANEL.top + 14), "TORPEDO DATA COMPUTER")
        brass.plaque(bg, (GAUGES.centerx, GAUGES.bottom - 14), "ENGINEERING")
        brass.plaque(bg, (TELETYPE.x + 70, TELETYPE.y + 18), "TELEPRINTER")
        for i, name in enumerate(LAMPS):
            brass.engrave(bg, name, (LAMP_X + 16, LAMP_Y0 + i * LAMP_DY - 7), 10)
        for i, (label, units, *_) in enumerate(FIELDS.values()):
            y = TDC_ROW_Y0 + i * TDC_ROW_H
            brass.engrave(bg, label, (30, y + 2), 12)
            brass.engrave(bg, units, (214, y + 3), 10, brass.INK_RED)
        brass.engrave(bg, "GYRO", (30, 430), 12)
        brass.engrave(bg, "RUN", (30, 448), 12)
        for i, (sx, sy) in enumerate(TUBE_SW):
            brass.engrave(bg, f"TUBE {i + 1}", (sx, sy - 34), 11, center=True)
        brass.engrave(bg, "TORPS", (650, 590), 10)
        brass.engrave(bg, "DECOYS", (718, 590), 10)
        brass.engrave(bg, "SCOPE", (SCOPE_LEVER[0], SCOPE_LEVER[1] - 36), 10, center=True)
        brass.engrave(bg, "SNORT", (SNORT_LEVER[0], SNORT_LEVER[1] - 36), 10, center=True)
        brass.engrave(bg, "L30", (RUDDER_BAR.left - 26, RUDDER_BAR.top - 2), 9)
        brass.engrave(bg, "R30", (RUDDER_BAR.right + 4, RUDDER_BAR.top - 2), 9)
        brass.engrave(bg, "WAVE", (TELETYPE.x + 150, TELETYPE.y + 10), 10, brass.BRASS_LIGHT)
        brass.engrave(bg, "GRT", (TELETYPE.x + 232, TELETYPE.y + 10), 10, brass.BRASS_LIGHT)
        return bg.convert()

    def _overlay(self):
        hole = pygame.Rect(0, 0, SCOPE_R * 2, SCOPE_R * 2)
        hole.center = SCOPE_C
        ov = brass.bezel_overlay((W, H), [(MONITOR, CRT_RECT, 26), (SCOPE_PANEL, hole, None)])
        for c in [*GAUGE_POS.values()]:
            g = brass.glint(GAUGE_R)
            ov.blit(g, (c[0] - g.get_width() / 2, c[1] - g.get_height() / 2))
        g = brass.glint(DEPTH_R)
        ov.blit(g, (DEPTH_C[0] - g.get_width() / 2, DEPTH_C[1] - g.get_height() / 2))
        brass.plaque(ov, (MONITOR.centerx, MONITOR.bottom - 13), "SONAR STATION No.1  -  HYDROPHONE ARRAY", 11)
        brass.plaque(ov, (SCOPE_C[0], SCOPE_PANEL.bottom - 12), "ACTIVE / TACTICAL", 10)
        return ov

    # --- frame ---
    def draw(self, screen, con, state, paused, show_help, dt):
        f = self.frame
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
        screen.blit(f, (random.uniform(-jitter, jitter), random.uniform(-jitter, jitter)))

    # --- centre monitor ---
    def draw_crt(self, con, state, paused):
        s, crt = self.crt_surf, self.crt
        s.fill((0, 0, 0))
        if state == "TITLE" or con is None:
            self._crt_title(s, crt)
        else:
            self._crt_sonar(s, crt, con)
            if state == "OVER":
                self._crt_box(s, crt, ["LOST WITH ALL HANDS" if con.cause == "HULL BREACHED" else "CREW UNCONSCIOUS",
                                       con.cause, f"WAVE {con.wave}   {con.score:,} GRT SUNK", "",
                                       "[R] NEW PATROL     [ESC] QUIT"])
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
        crt.text(s, "SILENT SOLUTION", (cx, 62), PHOSPHOR, huge=True, center=True)
        crt.text(s, "SUBMARINE OPERATOR WORKSTATION", (cx, 98), DIM, center=True)
        options = (("TRAINING", "GUIDED DRILL: EVERY STATION, THEN LIVE EXERCISES"),
                   ("CADET", "CLEAR WARNINGS - SLOW ENEMY FISH - SHORE POWER"),
                   ("COMMANDER", "REAL ACOUSTICS - ZIG-ZAGS - DECOYS - BATTERY"),
                   ("IRON CAPTAIN", "CAVITATION HEARD - HOMING COUNTER-FIRE - LEAKS - O2"))
        self.title_buttons = []
        for i, (name, blurb) in enumerate(options):
            box = pygame.Rect(70, 124 + i * 58, 440, 50)
            crt.frame(s, box, color=PHOSPHOR)
            crt.text(s, f"[{i or 'T'}]  {name}", (box.x + 16, box.y + 6), PHOSPHOR, big=True)
            crt.text(s, blurb, (box.x + 16, box.y + 31), DIM, small=True)
            self.title_buttons.append((box.move(CRT_RECT.topleft), name))
        crt.text(s, "NEW? START WITH [T]  -  F1 STATION DRILL  -  ESC QUIT", (cx, 372), DIM, small=True, center=True)

    def _crt_sonar(self, s, crt, con):
        x0, y0 = WF_POS
        crt.text(s, "PASSIVE WATERFALL  BRG REL", (x0 + 14, 12), DIM, small=True)
        s.blit(con.waterfall.draw(), WF_POS)
        crt.frame(s, (x0 - 1, y0 - 1, WF_W + 2, WF_H + 2))
        for b in (0, 90, 180, 270, 359):
            crt.text(s, f"{b:03d}", (x0 + b / 360 * WF_W - 10, y0 + WF_H + 3), DIM, small=True)
        dx = x0 + con.dial / 360 * WF_W
        crt.line(s, (dx, y0), (dx, y0 + WF_H - 1), RED)
        tx = x0 + con.tdc.get("BRG") / 360 * WF_W  # TDC estimate tick: stays on the trace if TMA is right
        crt.line(s, (tx, y0 - 5), (tx, y0 + 8), PHOSPHOR, 2)
        crt.line(s, (tx, y0 + WF_H - 8), (tx, y0 + WF_H + 1), PHOSPHOR, 2)
        self._spectrum(s, crt, con)

        for i, msg in enumerate(con.log):
            crt.text(s, msg, (LOG_POS[0], LOG_POS[1] + i * 15), PHOSPHOR if i == len(con.log) - 1 else DIM, small=True)

        p, ocean, sp = con.world.player, con.world.ocean, con.spectrum
        lock = "LOCK" if con.signal > 0.5 else "WEAK" if con.signal > 0.15 else "NONE"
        cls = f"{CLASSES[sp.best]} {sp.confidence * 100:.0f}%" if sp.best is not None else "NO SIGNAL"
        sea = "STORM" if ocean.rain > 0.5 else "RAIN" if ocean.rain > 0.15 else "CALM"
        sol = con.tdc.solve()
        rows = [("HYD", f"{con.dial:05.1f} R", PHOSPHOR), ("SIG", lock, RED if lock == "LOCK" else PHOSPHOR),
                ("CLASS", cls, PHOSPHOR if sp.best is not None else DIM),
                ("LAYER", ("BELOW" if p.z >= ocean.layer_depth else "ABOVE") + f" {ocean.layer_depth:.0f}M", PHOSPHOR),
                ("SEA", sea + (f"  EXP {con.exposure * 100:.0f}%" if p.scope_up or p.snorkel_up else ""),
                 RED if sea == "STORM" or con.exposure > 0.25 else PHOSPHOR),
                ("SOLN", f"GYRO {sol.gyro:05.1f}" if sol else "NONE", PHOSPHOR if sol else RED)]
        hx, hy = HYD_POS
        for i, (k, v, color) in enumerate(rows):
            crt.text(s, k, (hx, hy + i * 19), DIM, small=True)
            crt.text(s, v, (hx + 52, hy + i * 19 - 1), color)
        crt.rect(s, (hx + 104, hy + 24, int(min(con.signal, 1.0) * 64), 5))

        text, left = con.banner
        if left > 0 and int(left * 4) % 2 == 0:  # cadet: clear visual ping warning
            crt.rect(s, (x0 + 10, y0 + 90, WF_W - 20, 34), (0, 0, 0))
            crt.frame(s, (x0 + 10, y0 + 90, WF_W - 20, 34), color=RED)
            crt.text(s, text, (x0 + WF_W / 2, y0 + 107), RED, big=True, center=True)

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
        for i, name in enumerate(CLASSES):
            cell = pygame.Rect(LIB_RECT.x + i * cw, LIB_RECT.y, cw - 3, LIB_RECT.h - 14)
            hot = sp.best == i
            crt.frame(s, cell, color=PHOSPHOR if hot else DIM)
            tx = cell.x + 2 + np.arange(0, SPEC_BINS, 4) * (cell.w - 4) / SPEC_BINS
            ty = cell.bottom - 3 - TEMPLATES[i, ::4] * (cell.h - 6)
            crt.lines(s, list(zip(tx, ty)), PHOSPHOR if hot else DIM, 1)
            crt.text(s, CLASS_TAGS[i], (cell.centerx, cell.bottom + 7), PHOSPHOR if hot else DIM, small=True, center=True)

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
            if not t.hostile:  # own fish only: wire telemetry
                crt.circle(s, P(t.x - own.x, t.y - own.y), 2, RED, 0)
        h = math.radians(own.heading)
        crt.circle(s, c, 3, PHOSPHOR)
        crt.line(s, c, (c[0] + 12 * math.sin(h), c[1] - 12 * math.cos(h)), PHOSPHOR, 2)
        crt.text(s, f"{con.scope_range:,.0f} YD", (R, 2 * R - 30), PHOSPHOR, small=True, center=True)

    # --- brass instruments ---
    def draw_needles(self, f, con, dt):
        p, world, nd = con.world.player, con.world, self.needles
        stress = 0.6 if p.z > CRUSH_DEPTH else 0.05
        values = {"DEPTH": (p.z, stress), "BATTERY": (p.battery, 0.15), "NOISE": (p.noise, 0.02 + 0.04 * p.cavitating),
                  "HULL": (world.hull, 0.1 + 0.2 * (world.hull < 50))}
        for name, (v, jitter) in values.items():
            spec, c = GAUGE_SPECS[name], GAUGE_POS[name]
            shown = nd[name].update(v, dt, jitter * (spec["hi"] - spec["lo"]) / 100)
            brass.needle(f, c, brass.value_angle(shown, spec["lo"], spec["hi"]), GAUGE_R - 20)
        if p.uses_oxygen:
            c = GAUGE_POS["BATTERY"]
            brass.needle(f, c, brass.value_angle(nd["O2"].update(p.o2, dt), 0, 100), GAUGE_R - 30, brass.INK_RED, 2)
            brass.engrave(f, "RED: O2", (c[0], c[1] - 26), 9, brass.INK_RED, center=True)
        dc = GAUGE_POS["DEPTH"]
        brass.counter(f, (dc[0] - 24, dc[1] + 46), f"{14.7 + p.z * 1.4228:4.0f}", 11)
        brass.engrave(f, "PSI", (dc[0] + 28, dc[1] + 49), 9, brass.INK_RED)
        brass.needle(f, DEPTH_C, brass.value_angle(nd["ORDER"].update(p.ordered_depth, dt), 0, 300), DEPTH_R - 16,
                     brass.INK_RED, 3)
        brass.needle(f, DEPTH_C, brass.value_angle(p.z, 0, 300), DEPTH_R - 22, brass.INK, 1, tail=6)

    def draw_controls(self, f, con):
        p, world = con.world.player, con.world
        blink = int(world.time * 4) % 2 == 0
        # telegraph handle
        idx = con.telegraph_index()
        tip = brass.polar(TELEGRAPH_C, TELEGRAPH_R - 16, brass.telegraph_angle(idx, len(TELEGRAPH)))
        pygame.draw.line(f, brass.BRASS_DARK, TELEGRAPH_C, tip, 9)
        pygame.draw.line(f, brass.BRASS_LIGHT, TELEGRAPH_C, tip, 3)
        pygame.draw.circle(f, brass.IRON_DARK, [int(v) for v in tip], 9)
        pygame.draw.circle(f, brass.BRASS, [int(v) for v in tip], 7)
        pygame.draw.circle(f, brass.BRASS, TELEGRAPH_C, 12)
        brass.engrave(f, f"{p.speed / KNOT:4.1f} KT", (TELEGRAPH_C[0], TELEGRAPH_C[1] + 22), 12, center=True)
        # helm
        angle = int(p.rudder * 4)
        if angle not in self.wheel_cache:
            self.wheel_cache[angle] = pygame.transform.rotate(self.wheel, -angle)
        w = self.wheel_cache[angle]
        f.blit(w, w.get_rect(center=WHEEL_C))
        pygame.draw.rect(f, brass.IRON_DARK, RUDDER_BAR)
        px = RUDDER_BAR.centerx + p.rudder / MAX_RUDDER * (RUDDER_BAR.w / 2 - 3)
        pygame.draw.line(f, brass.BRASS_LIGHT, (RUDDER_BAR.centerx, RUDDER_BAR.top), (RUDDER_BAR.centerx, RUDDER_BAR.bottom))
        pygame.draw.polygon(f, brass.INK_RED, [(px, RUDDER_BAR.top - 1), (px - 5, RUDDER_BAR.top - 8), (px + 5, RUDDER_BAR.top - 8)])
        side = "AMIDSHIPS" if abs(p.rudder) < 0.5 else f"{abs(p.rudder):.0f} {'RIGHT' if p.rudder > 0 else 'LEFT'}"
        brass.engrave(f, f"RUDDER {side}  HDG {p.heading:05.1f}", (WHEEL_C[0], RUDDER_BAR.bottom + 10), 11, center=True)
        # diving station
        holding = abs(p.ordered_depth - p.z) < 1 and not p.blowing
        brass.button(f, HOLD_BTN, "HOLD", lit=holding, color=(60, 140, 70))
        brass.button(f, BLOW_BTN, "BLOW", lit=p.blowing and blink)
        brass.button(f, PD_BTN, "P.D.", lit=abs(p.ordered_depth - PERISCOPE_DEPTH) < 0.5, color=(60, 110, 160))
        for (lx, ly), up, ready, color in ((SCOPE_LEVER, p.scope_up, p.z <= MAST_DEPTH, (240, 170, 40)),
                                           (SNORT_LEVER, p.snorkel_up, p.z <= MAST_DEPTH, (80, 220, 90))):
            brass.toggle(f, (lx, ly), up)
            brass.lamp(f, (lx, ly + 24), up or (ready and blink and con.tutorial is not None), color, 5)
        brass.button(f, LOOK_BTN, "LOOK", lit=p.scope_up, color=(160, 120, 40))
        if p.scope_damage > 0:
            brass.engrave(f, "JAMMED", (SCOPE_LEVER[0], SCOPE_LEVER[1] + 22), 9, brass.INK_RED, center=True)
        planes = "BLOWING" if p.blowing else "LEVEL" if holding else "DIVE" if p.ordered_depth > p.z else "RISE"
        brass.engrave(f, f"PLANES {planes}  ORD {p.ordered_depth:.0f} M", (DEPTH_C[0], HOLD_BTN.bottom + 10), 11, center=True)
        # torpedo room
        for i, (sx, sy) in enumerate(TUBE_SW):
            r = con.tubes[i]
            ready, empty = r == 0, r == math.inf
            brass.toggle(f, (sx, sy), ready)
            brass.lamp(f, (sx + 26, sy - 16), ready or (not empty and blink),
                       (80, 220, 90) if ready else (230, 160, 40), 6)
            state = "READY" if ready else "EMPTY" if empty else f"{r:2.0f} S"
            brass.engrave(f, state, (sx, sy + 34), 11, brass.INK_RED if empty else brass.INK, center=True)
        brass.counter(f, (650, 604), f"{p.torpedoes:02d}", 14)
        brass.counter(f, (718, 604), f"{p.noisemakers:02d}", 14)
        brass.button(f, NMKR_BTN, "NOISEMAKER  [N]")
        brass.button(f, PING_BTN, "ACTIVE PING  [SPACE]", lit=world.time - con.ping_time < 0.6)
        # warning lamps
        exposed = con.exposure > 0.25
        masts = p.scope_up or p.snorkel_up
        states = (con.lamp_enemy > 0 and blink, con.torpedo_warning and blink, p.cavitating, p.snorkeling,
                  masts and (blink or not exposed), p.broached and blink, bool(p.leaks),
                  p.z > CRUSH_DEPTH - 20 and blink, p.z >= world.ocean.layer_depth)
        colors = ((240, 170, 40), (240, 50, 30), (240, 170, 40), (80, 220, 90),
                  (240, 50, 30) if exposed else (240, 170, 40), (240, 50, 30), (240, 50, 30), (240, 50, 30),
                  (90, 170, 240))
        for i, (on, color) in enumerate(zip(states, colors)):
            brass.lamp(f, (LAMP_X, LAMP_Y0 + i * LAMP_DY), on, color, 6)
        # TDC
        for i, (name, (_, _, fmt, *_)) in enumerate(FIELDS.items()):
            y = TDC_ROW_Y0 + i * TDC_ROW_H
            if i == con.tdc.selected:
                pygame.draw.polygon(f, brass.INK_RED, [(16, y + 3), (16, y + 15), (25, y + 9)])
            brass.counter(f, (112, y), fmt.format(con.tdc.get(name)), 13)
        sol = con.tdc.solve()
        far = sol is not None and sol.run > TORP_MAX_RUN
        brass.counter(f, (112, 428), f"{sol.gyro:05.1f}" if sol else "---.-", 13)
        brass.counter(f, (112, 446), f"{sol.run / YARD:6,.0f}" if sol else "------", 13)
        brass.lamp(f, (238, 446), sol is not None, (240, 50, 30) if far else (80, 220, 90), 6)

    def draw_teletype(self, f, con):
        r = PAPER_RECT
        f.blit(self.paper, r.topleft)
        tt = con.teletype if con else None
        fed = tt.fed if tt else 0
        for k in range(0, r.h + 14, 14):  # tractor-feed perforations creep up as paper feeds
            y = r.bottom - ((k + fed * 7) % (r.h + 14))
            for x in (r.x + 9, r.right - 9):
                pygame.draw.circle(f, (150, 138, 108), (x, int(y)), 3)
        if tt:
            font = brass.mono(12)
            rows = (r.h - 16 - (ORDER_SLIP.h + 8 if con.tutorial else 0)) // 15
            lines = [*list(tt.lines)[-(rows - 1):], tt.typing]
            for i, line in enumerate(lines):
                f.blit(font.render(line, True, brass.INK), (r.x + 20, r.bottom - 12 - (len(lines) - i) * 15))
            if tt.queue and int(pygame.time.get_ticks() / 150) % 2:
                cx = r.x + 20 + font.size(tt.typing)[0]
                pygame.draw.rect(f, brass.INK, (cx, r.bottom - 27, 7, 12))
            brass.counter(f, (TELETYPE.x + 184, TELETYPE.y + 8), f"{con.wave:02d}", 13)
            brass.counter(f, (TELETYPE.x + 258, TELETYPE.y + 8), f"{con.score:6d}", 13)
        pygame.draw.rect(f, brass.IRON_DARK, r, 2)

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
        pygame.draw.rect(f, (246, 238, 214), slip)
        pygame.draw.rect(f, brass.INK_RED, slip, 2)
        brass.engrave(f, f"ORDER {tut.progress}", (slip.x + 8, slip.y + 4), 11, brass.INK_RED)
        font = brass.mono(13, True)
        for i, line in enumerate(textwrap.wrap(tut.goal, 34)[:2]):
            f.blit(font.render(line, True, brass.INK), (slip.x + 8, slip.y + 22 + i * 17))

    def draw_debug(self, f, con, dt):
        """Playtest overlay: frame rate, ocean and own-boat state, and the truth about every contact."""
        self.fps = 0.9 * getattr(self, "fps", 60.0) + 0.1 * (1.0 / max(dt, 1e-3))
        w, p, o = con.world, con.world.player, con.world.ocean
        font = brass.mono(12, True)
        states = {}
        for ai in w.ais:
            key = f"{ai.ship.kind[:3]}:{ai.state}"
            states[key] = states.get(key, 0) + 1
        lines = [f"FPS {self.fps:5.1f}   T+ {w.time:7.1f} s   WAVE {con.wave}",
                 f"SEA {o.sea_state}  HS {o.wave_height:3.1f} m  WIND {o.wind:4.1f}  RAIN {o.rain:3.2f}  VIS {o.visibility:5.0f}",
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

    def draw_help(self, f):
        card = pygame.Rect(0, 0, 600, 562)
        card.center = (W // 2, H // 2)
        f.blit(brass.texture(card.size, brass.PAPER, grain=5), card.topleft)
        pygame.draw.rect(f, brass.BRASS_DARK, card, 4)
        brass.engrave(f, "STATION DRILL", (card.centerx, card.y + 26), 20, center=True)
        rows = (("A / D", "hydrophone dial", "click waterfall / wheel"), ("M", "mark dial bearing into TDC", ""),
                ("W / S", "select TDC field", "click row"), ("UP / DOWN", "adjust TDC field", "mouse wheel"),
                ("LEFT / RIGHT", "rudder   (C amidships)", "drag the wheel"), ("Z / X", "engine telegraph", "click sector"),
                ("Q / E", "depth order -/+ 10 m", "click order dial"), ("H / B", "hold depth / blow ballast", "buttons"),
                ("SPACE", "active ping - reveals you", "button"), ("F  1  2", "fire next / tube 1 / tube 2", "tube switch"),
                ("N", "noisemaker decoy astern", "button"), ("T", "tactical scope range", "click scope"),
                ("G", "periscope depth (15 m)", "P.D. button"), ("U / K", "periscope / snorkel up-down", "levers"),
                ("V", "look through the periscope", "LOOK button"),
                ("A/D TAB M", "scope: train / power / mark", "drag / wheel"),
                ("P / F1 / ESC", "pause / this card / quit", ""))
        for i, (keys, what, mouse) in enumerate(rows):
            y = card.y + 58 + i * 26
            brass.engrave(f, keys, (card.x + 30, y), 13)
            brass.engrave(f, what, (card.x + 180, y), 13, bold=False)
            brass.engrave(f, mouse, (card.x + 420, y), 12, brass.INK_RED, bold=False)
