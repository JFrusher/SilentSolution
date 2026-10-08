"""Job stations: each one is laid out for its crewman's job, from the all-in-one console's parts.
A view is a list of pieces. A piece covers a region of the full console (`src`) and shows it on the station canvas:
the green screens, plot and printer are cut from the full console frame, and the dials, switches and buttons are
redrawn natively at the station's size in 2.5D (graphics/instruments.py). Either way a click on a station maps back
to the same spot on the full console, so every control keeps one tested click path. Only controls this station's
man works are given a piece, so nothing else can be clicked here."""
import math
from dataclasses import dataclass

import pygame

from graphics import console_art as art
from graphics import instruments as ins
from layout import (
    BLOW_BTN,
    CRT_RECT,
    DEPTH_C,
    DEPTH_R,
    GAUGE_POS,
    GAUGE_R,
    GAUGE_SPECS,
    HOLD_BTN,
    MONITOR,
    NMKR_BTN,
    PD_BTN,
    PING_BTN,
    RUDDER_BAR,
    SCOPE_LEVER,
    SCOPE_PANEL,
    SNORT_LEVER,
    TDC_PANEL,
    TELEGRAPH_BTNS,
    TELEGRAPH_RECT,
    TELETYPE,
    TUBE_SW,
    WHEEL_C,
    WHEEL_R,
    H,
    W,
)
from settings import label as keys_for
from sim import CRUSH_DEPTH, KNOT, MAST_DEPTH, MAX_RUDDER, PERISCOPE_DEPTH, TELEGRAPH
from workstation import alarm_states

R = pygame.Rect
GAUGE = {k: R(x - GAUGE_R - 7, y - GAUGE_R - 7, 2 * GAUGE_R + 14, 2 * GAUGE_R + 14) for k, (x, y) in GAUGE_POS.items()}
DEPTH_DIAL = R(DEPTH_C[0] - DEPTH_R, DEPTH_C[1] - DEPTH_R, 2 * DEPTH_R, 2 * DEPTH_R)
WEAPONS_PANEL = R(636, 480, 160, 156)
HELM_PANEL = R(228, 476, 186, 234)
LEVER = {"SCOPE": R(SCOPE_LEVER[0] - 24, SCOPE_LEVER[1] - 24, 48, 48),
         "SNORT": R(SNORT_LEVER[0] - 24, SNORT_LEVER[1] - 24, 48, 48)}
WHITE_NEEDLE, BLACK_NEEDLE = (240, 236, 222), (26, 24, 22)


@dataclass(frozen=True)
class Piece:
    src: pygame.Rect   # on the full console frame
    at: tuple          # top-left on the station canvas
    scale: float
    draw: object = None  # draw(canvas, piece, con, ws) to redraw it natively; None cuts it from the frame
    keys: tuple = ()     # the key actions that work it, shown faintly when you hover over it

    @property
    def dst(self):
        return R(self.at, (round(self.src.w * self.scale), round(self.src.h * self.scale)))

    def map(self, pt):
        """A point on the full console to this piece on the station canvas."""
        return self.at[0] + (pt[0] - self.src.x) * self.scale, self.at[1] + (pt[1] - self.src.y) * self.scale

    def rect(self, r):
        x, y = self.map(r.topleft)
        return R(round(x), round(y), round(r.w * self.scale), round(r.h * self.scale))


@dataclass(frozen=True)
class View:
    name: str
    page: str          # what the CRT shows here: SONAR, TMA or DAMAGE
    actions: frozenset  # the station keys that work at this station; the rest become orders to the crew
    pieces: tuple
    plates: tuple = ()  # (rect, legend): the steel faceplates the instruments sit on, painted once
    lamps: tuple = ()   # (rect, legends): this man's warning lamps
    extras: tuple = ()  # draw(canvas, con, ws): readouts that belong to no one control


def P(src, at, scale, draw=None, keys=()):
    return Piece(src, at, scale, draw, keys)


# ---------- the instruments, drawn natively ----------
def gauge(name, white=False):
    """One of the ship-systems gauges, its needle where the console's own needle stands."""
    def draw(s, pc, con, ws):
        p, nd = con.world.player, ws.needles
        c = pc.map(GAUGE_POS[name])
        r = round(GAUGE_R * pc.scale * 0.94)
        needles = [(nd[name].v, BLACK_NEEDLE if white else WHITE_NEEDLE, 3.2, 1.0)]
        if name == "BATTERY" and p.uses_oxygen:
            needles.append((nd["O2"].v, art.BLUE, 2.4, 0.78))
        ins.gauge(s, c, r, GAUGE_SPECS[name], needles, white)
        if name == "BATTERY" and p.uses_oxygen:
            art.engrave(s, "BLUE: O2", (c[0], c[1] - r * 0.24), max(10, r // 9), art.BLUE, center=True)
        if name == "DEPTH":  # the fine-reading counter under the hub, in the gauge's own metres
            size = max(11, r // 7)
            art.counter(s, (c[0] - size * 1.6, c[1] + r * 0.58), f"{p.z:5.1f}", size)
    return draw


def depth_order(s, pc, con, ws):
    """The planesman's depth-order dial: drag or scroll the orange needle; the white one is where we are."""
    p = con.world.player
    spec = dict(title="DEPTH ORDER", lo=0, hi=300, major=50, minor=10, red=(CRUSH_DEPTH, 300), units="METRES")
    ins.gauge(s, pc.map(DEPTH_C), round(DEPTH_R * pc.scale * 0.92), spec,
              [(ws.needles["ORDER"].v, art.WARN, 4.0, 1.0), (p.z, WHITE_NEEDLE, 2.2, 0.8)])


def telegraph(s, pc, con, ws):
    """The engine order telegraph: backlit STOP to FLANK, the ordered and shaft speeds on drum counters."""
    p = con.world.player
    idx = con.telegraph_index()
    for i, (b, (name, _)) in enumerate(zip(TELEGRAPH_BTNS, TELEGRAPH)):
        ins.button(s, pc.rect(b), name, i == idx, art.RED if name == "FLANK" else art.AMBER)
    size = round(15 * pc.scale)
    for k, (label, text, colour) in enumerate((("ORDERED", f"{TELEGRAPH[idx][1]:4.1f}", art.AMBER),
                                               ("SHAFT KTS", f"{p.speed / KNOT:4.1f}", art.GREEN))):
        x, y = pc.map((TELEGRAPH_RECT.x + 16 + 98 * k, 530))
        art.engrave(s, label, (x, y), round(10 * pc.scale), art.LEGEND_DIM)
        art.counter(s, (x, y + 22 * pc.scale), text, size, colour)


def helm(s, pc, con, ws):
    """The helmsman's rudder angle indicator over the wheel (drag it, or the bar), the rudder bar, heading and rudder
    counters."""
    p = con.world.player
    spec = dict(title="RUDDER", lo=-MAX_RUDDER, hi=MAX_RUDDER, major=10, minor=5, units="PORT    STBD")
    ins.gauge(s, pc.map(WHEEL_C), round(WHEEL_R * pc.scale * 0.95), spec, [(p.rudder, WHITE_NEEDLE, 3.4, 1.0)])
    bar = pc.rect(RUDDER_BAR)
    pygame.draw.rect(s, (8, 8, 9), bar.inflate(6, 6), border_radius=3)
    for k in range(-3, 4):
        x = bar.centerx + k * (bar.w / 2 - 4) / 3
        pygame.draw.line(s, art.LEGEND_DIM, (x, bar.top), (x, bar.bottom), 2)
    px = bar.centerx + p.rudder / MAX_RUDDER * (bar.w / 2 - 4)
    pygame.draw.rect(s, art.WARN, (px - 4, bar.top - 3, 8, bar.h + 6), border_radius=2)
    y = bar.bottom + 10 * pc.scale
    side = "R" if p.rudder > 0.5 else "L" if p.rudder < -0.5 else "-"
    for k, (label, text) in enumerate((("HDG", f"{p.heading:05.1f}"), ("RUD", f"{abs(p.rudder):2.0f}" + side))):
        x = bar.x + k * bar.w * 0.55
        art.engrave(s, label, (x, y + 4), round(10 * pc.scale), art.LEGEND_DIM)
        art.counter(s, (x + 32 * pc.scale, y), text, round(11 * pc.scale))


def button(rect, legend, lit, colour):
    def draw(s, pc, con, ws):
        ins.button(s, pc.dst, legend, lit(con), colour)
    return draw


def mast(which):
    """A mast-raising lever: the tumbler, its lamp, and its name on a tape."""
    def draw(s, pc, con, ws):
        p = con.world.player
        up, colour = (p.scope_up, art.AMBER) if which == "SCOPE" else (p.snorkel_up, art.GREEN)
        ready = p.z <= MAST_DEPTH and int(con.world.time * 4) % 2 == 0 and con.tutorial is not None
        c = pc.dst.center
        size = round(pc.dst.w * 1.25)
        ins.blit_centred(s, ins.toggle_sprite(up, False, size), c)
        ins.lamp(s, (c[0], c[1] + size * 0.62), up or ready, colour, round(size * 0.32))
        art.dymo(s, (c[0] - size * 0.3, c[1] - size * 0.82), "SCOPE" if which == "SCOPE" else "SNORT",
                 round(size * 0.13))
        if which == "SCOPE" and "PERISCOPE" in p.damaged:
            art.engrave(s, "JAMMED", (c[0], c[1] + size * 0.95), round(size * 0.12), art.RED, center=True)
    return draw


def weapons(s, pc, con, ws):
    """The firing panel: a guarded firing switch per tube with its ready lamp and state, torpedoes and decoys left."""
    p = con.world.player
    blink = int(con.world.time * 4) % 2 == 0
    for i, (sx, sy) in enumerate(TUBE_SW):
        r = con.tubes[i]
        broken = f"TUBE {i + 1}" in p.damaged
        ready, empty = r == 0 and not broken, r == math.inf
        c = pc.map((sx, sy))
        size = round(64 * pc.scale)
        art.engrave(s, f"TUBE {i + 1}", (c[0], c[1] - 40 * pc.scale), round(10 * pc.scale), center=True)
        ins.blit_centred(s, ins.toggle_sprite(ready, True, size), c)
        ins.lamp(s, (c[0] + 30 * pc.scale, c[1] - 18 * pc.scale), ready or (not empty and blink),
                 art.GREEN if ready else art.AMBER, round(15 * pc.scale))
        state = "DAMAGED" if broken else "READY" if ready else "EMPTY" if empty else f"{r:2.0f} S"
        art.engrave(s, state, (c[0], c[1] + 38 * pc.scale), round(10 * pc.scale),
                    art.RED if empty or broken else art.LEGEND, center=True)
    for k, (label, n) in enumerate((("TORPS", p.torpedoes), ("DECOYS", p.noisemakers))):
        x, y = pc.map((650 + 68 * k, 590))
        art.engrave(s, label, (x, y), round(10 * pc.scale), art.LEGEND_DIM)
        art.counter(s, (x, y + 14 * pc.scale), f"{n:02d}", round(13 * pc.scale))


def planes_state(s, con, ws, at, size):
    p = con.world.player
    holding = abs(p.ordered_depth - p.z) < 1 and not p.blowing
    planes = "BLOWING" if p.blowing else "LEVEL" if holding else "DIVE" if p.ordered_depth > p.z else "RISE"
    art.engrave(s, f"PLANES {planes}    ORDER {p.ordered_depth:.0f} M", at, size, art.LEGEND, center=True)


def holding(con):
    p = con.world.player
    return abs(p.ordered_depth - p.z) < 1 and not p.blowing


GLOBAL = frozenset(("STAND UP", "DEBUG", "ACKNOWLEDGE", "SKIP DRILL"))
VIEWS = {v.name: v for v in (
    View("SONAR", "SONAR", frozenset(("TRAIN LEFT", "TRAIN RIGHT", "MARK", "PING", "WATERFALL SCALE",
                                     "BEARING MODE")),
         (P(MONITOR, (16, 36), 1.42, keys=("TRAIN LEFT", "TRAIN RIGHT", "MARK")),
          P(GAUGE["NOISE"], (972, 24), 1.6, gauge("NOISE")),
          P(PING_BTN, (978, 600), 1.9, button(PING_BTN, "ACTIVE PING",
                                               lambda con: con.world.time - con.ping_time < 0.6, art.RED), ("PING",))),
         plates=((R(944, 12, 320, 300), "SELF NOISE"), (R(944, 330, 320, 210), "WARNING"),
                 (R(944, 556, 320, 140), "ACTIVE SONAR")),
         lamps=((R(966, 350, 280, 140), ("ENEMY SONAR", "TORPEDO")),)),
    View("FIRE CONTROL", "TMA", frozenset(("TDC ROW UP", "TDC ROW DOWN", "TDC VALUE UP", "TDC VALUE DOWN",
                                            "AUTO-SOLVE", "FIRE", "FIRE TUBE 1", "FIRE TUBE 2", "WIRE LEFT",
                                            "WIRE RIGHT", "NEXT FISH", "CUT WIRE", "SCOPE RANGE", "NOISEMAKER")),
         (P(SCOPE_PANEL, (16, 16), 1.38, keys=("SCOPE RANGE",)),
          P(TDC_PANEL, (16, 376), 1.38, keys=("TDC ROW UP", "TDC ROW DOWN", "AUTO-SOLVE")),
          P(MONITOR, (382, 16), 1.0), P(WEAPONS_PANEL, (400, 500), 1.25, weapons, ("FIRE TUBE 1", "FIRE TUBE 2")),
          P(NMKR_BTN, (700, 600), 1.6, button(NMKR_BTN, "NOISEMAKER", lambda con: False, art.AMBER), ("NOISEMAKER",))),
         plates=((R(382, 486, 560, 222), "FIRING PANEL"), (R(956, 486, 308, 222), "WARNING")),
         lamps=((R(978, 540, 270, 70), ("TORPEDO",)),)),
    View("RADIO", "SONAR", frozenset(),
         (P(TELETYPE, (290, 12), 2.12),)),
    View("HELM AND PLANES", "SONAR", frozenset(("SLOWER", "FASTER", "RUDDER LEFT", "RUDDER RIGHT",
                                               "RUDDER AMIDSHIPS", "SHALLOWER", "DEEPER", "HOLD DEPTH",
                                               "PERISCOPE DEPTH")),
         (P(GAUGE["DEPTH"], (34, 26), 1.8, gauge("DEPTH")), P(GAUGE["NOISE"], (360, 40), 1.5, gauge("NOISE")),
          P(TELEGRAPH_RECT, (24, 410), 1.5, telegraph, ("SLOWER", "FASTER")),
          P(HELM_PANEL, (372, 380), 1.3, helm, ("RUDDER LEFT", "RUDDER RIGHT")),
          P(DEPTH_DIAL, (668, 390), 2.0, depth_order, ("SHALLOWER", "DEEPER")),
          P(HOLD_BTN, (952, 430), 2.0, button(HOLD_BTN, "HOLD", holding, art.GREEN), ("HOLD DEPTH",)),
          P(PD_BTN, (952, 510), 2.0, button(PD_BTN, "P.D.", lambda con: abs(con.world.player.ordered_depth
                                                                                - PERISCOPE_DEPTH) < 0.5, art.BLUE),
            ("PERISCOPE DEPTH",))),
         plates=((R(16, 12, 640, 352), "DEPTH  /  SELF NOISE"), (R(672, 12, 592, 352), "WARNING"),
                 (R(16, 378, 318, 330), "ENGINE ORDER"), (R(342, 378, 300, 330), "HELM"),
                 (R(650, 378, 614, 330), "PLANES")),
         lamps=((R(700, 60, 330, 200), ("CAVITATION", "BROACH", "BELOW LAYER")),),
         extras=(lambda s, con, ws: planes_state(s, con, ws, (1080, 640), 16),)),
    View("BALLAST CONTROL", "SONAR", frozenset(("BLOW", "RAISE SNORKEL", "RAISE SCOPE", "PERISCOPE DEPTH")),
         (P(GAUGE["BATTERY"], (40, 30), 1.75, gauge("BATTERY")), P(GAUGE["DEPTH"], (60, 396), 1.45, gauge("DEPTH")),
          P(LEVER["SCOPE"], (452, 120), 2.4, mast("SCOPE"), ("RAISE SCOPE",)),
          P(LEVER["SNORT"], (662, 120), 2.4, mast("SNORT"), ("RAISE SNORKEL",)),
          P(BLOW_BTN, (482, 500), 5.0, button(BLOW_BTN, "BLOW",
                                              lambda con: con.world.player.blowing and int(con.world.time * 4) % 2
                                              == 0, art.RED), ("BLOW",))),
         plates=((R(16, 12, 370, 696), "BATTERY  /  DEPTH"), (R(400, 12, 468, 380), "MASTS"),
                 (R(400, 406, 468, 302), "EMERGENCY BLOW"), (R(882, 12, 382, 696), "WARNING")),
         lamps=((R(906, 70, 340, 320), ("DIESEL", "MASTS UP", "LEAK", "HULL STRESS")),),
         extras=(lambda s, con, ws: art.tape(s, (634, 450), "CAPTAIN'S ORDER ONLY", -2, 16),)),
    View("DAMAGE CONTROL", "DAMAGE", frozenset(),
         (P(MONITOR, (16, 36), 1.42), P(GAUGE["HULL"], (972, 24), 1.6, gauge("HULL", white=True))),
         plates=((R(944, 12, 320, 300), "HULL"), (R(944, 330, 320, 180), "WARNING")),
         lamps=((R(966, 350, 280, 120), ("LEAK", "HULL STRESS")),)),
    View("PERISCOPE", "SONAR", frozenset(("LOOK", "MARK", "SCOPE POWER", "TRAIN LEFT", "TRAIN RIGHT",
                                          "SCOPE TO SONAR", "RAISE SCOPE")), (P(R(0, 0, W, H), (0, 0), 1.0),)),
    View("ALL", "SONAR", frozenset(), (P(R(0, 0, W, H), (0, 0), 1.0),)),
)}


def piece_at(view, pos):
    """The piece under a point on the station canvas, or None."""
    return next((p for p in view.pieces if p.dst.collidepoint(pos)), None)


def through(piece, pos):
    """A point on the station canvas carried back to the full console through `piece` (a drag may leave it)."""
    d = piece.dst
    return (piece.src.x + (pos[0] - d.x) / piece.scale, piece.src.y + (pos[1] - d.y) / piece.scale)


def allows(view, action):
    return view.name == "ALL" or action in view.actions or action in GLOBAL


def shape_rect(shape):
    """A tutorial highlight (a rect, or a centre and radius) as a rect on the full console."""
    if isinstance(shape, pygame.Rect):
        return shape
    (cx, cy), r = shape
    return R(cx - r, cy - r, 2 * r, 2 * r)


def rings(view, shape):
    """Where a highlight on the full console lands on a station canvas: a rect per piece that shows it."""
    box = shape_rect(shape)
    out = []
    for p in view.pieces:
        cut = box.clip(p.src)
        if cut.w > 4 and cut.h > 4:
            d = p.dst
            out.append(R(d.x + (cut.x - p.src.x) * p.scale, d.y + (cut.y - p.src.y) * p.scale,
                         cut.w * p.scale, cut.h * p.scale))
    return out


def station_for(highlights, shapes):
    """The station that shows most of a drill step's highlighted parts, or None when there are none to show."""
    best, most = None, 0
    for v in VIEWS.values():
        if v.name in ("ALL", "PERISCOPE"):
            continue
        n = sum(bool(rings(v, shapes[h])) for h in highlights)
        if n > most:
            best, most = v.name, n
    return best


class HeldAt:
    """pygame.key.get_pressed() as one station sees it: only that station's held keys count."""

    def __init__(self, view, pressed, code):
        self.held = {code(a) for a in view.actions if pressed[code(a)]} if view.name != "ALL" else None
        self.pressed = pressed

    def __getitem__(self, k):
        return self.pressed[k] if self.held is None else int(k in self.held)


def compose(view, frame, backdrop, con, ws):
    """The station canvas: its faceplates, then each piece cut from the full console frame or drawn natively, its
    warning lamps, and its loose readouts."""
    if len(view.pieces) == 1 and view.pieces[0].dst == frame.get_rect():
        return frame
    canvas = _base(view.name, backdrop).copy()
    for p in view.pieces:
        if p.draw:
            p.draw(canvas, p, con, ws)
        else:
            canvas.blit(pygame.transform.smoothscale(frame.subsurface(p.src), p.dst.size), p.dst)
            pygame.draw.rect(canvas, (24, 24, 23), p.dst.inflate(4, 4), 2)
    states = {name: (name, lit, colour) for name, lit, colour in alarm_states(con)}
    for rect, names in view.lamps:
        ins.lamp_strip(canvas, rect, [states[n] for n in names])
    for extra in view.extras:
        extra(canvas, con, ws)
    return canvas


_BASES = {}


def _base(name, backdrop):
    """A station's steelwork with its faceplates and their engraved names, painted once."""
    if name not in _BASES:
        base = backdrop.copy()
        for rect, legend in VIEWS[name].plates:
            art.faceplate(base, rect)
            art.label_plate(base, (rect.centerx, rect.bottom - 16), legend, 13)
        _BASES[name] = base
    return _BASES[name]



if __name__ == "__main__":  # self-check: every piece fits its canvas, none overlap, clicks map back exactly
    screen = R(0, 0, W, H)
    for v in VIEWS.values():
        for i, p in enumerate(v.pieces):
            assert screen.contains(p.dst), f"{v.name}: piece {i} {p.dst} falls off the canvas"
            assert screen.contains(p.src), f"{v.name}: piece {i} cuts outside the console"
            for q in v.pieces[i + 1:]:
                assert not p.dst.colliderect(q.dst), f"{v.name}: pieces overlap {p.dst} {q.dst}"
            mid = p.dst.center
            back = through(piece_at(v, mid), mid)
            assert abs(back[0] - p.src.centerx) <= 1 and abs(back[1] - p.src.centery) <= 1, (v.name, i, back)
    assert CRT_RECT.colliderect(MONITOR)
    print("stations ok")


def hover(canvas, view, pos):
    """The keys for the control under the pointer, faint by the pointer: the panels themselves carry no key hints."""
    piece = piece_at(view, pos)
    if piece and piece.keys:
        text = art.sans(14, True).render(keys_for(*piece.keys), True, (210, 204, 186))
        box = text.get_rect(topleft=(pos[0] + 16, pos[1] + 18)).inflate(10, 6)
        shade = pygame.Surface(box.size, pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        canvas.blit(shade, box)
        canvas.blit(text, text.get_rect(center=box.center))
