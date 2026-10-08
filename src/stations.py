"""Job stations: each one is the part of the all-in-one console its crewman works, laid out bigger for that job.
A view is a list of pieces cut from the full console frame and placed on a station canvas, so every panel keeps
its tested drawing and click handling: a click on a station maps back to the same spot on the full console.
The full console itself ("ALL") remains for training until it is rewritten for the room."""
from dataclasses import dataclass

import pygame

from layout import CRT_RECT, GAUGE_POS, GAUGE_R, MONITOR, SCOPE_PANEL, TDC_PANEL, TELEGRAPH_RECT, TELETYPE, H, W

R = pygame.Rect
GAUGE = {k: R(x - GAUGE_R - 7, y - GAUGE_R - 7, 2 * GAUGE_R + 14, 2 * GAUGE_R + (14 if y < 200 else 2))
         for k, (x, y) in GAUGE_POS.items()}  # the lower pair stop short of the SHIP SYSTEMS plate under them
HELM_PANEL = R(228, 476, 186, 234)
DIVING_PANEL = R(418, 476, 218, 234)
WEAPONS_PANEL = R(636, 480, 160, 156)
COUNTERMEASURES = R(636, 632, 160, 80)  # noisemaker and active-ping buttons
ALARMS = R(796, 480, 116, 228)


@dataclass(frozen=True)
class Piece:
    src: pygame.Rect   # on the full console frame
    at: tuple          # top-left on the station canvas
    scale: float

    @property
    def dst(self):
        return R(self.at, (round(self.src.w * self.scale), round(self.src.h * self.scale)))


@dataclass(frozen=True)
class View:
    name: str
    page: str          # what the CRT shows here: SONAR, TMA or DAMAGE
    actions: frozenset  # the station keys that work at this station; the rest become orders to the crew
    pieces: tuple


def P(src, at, scale):
    return Piece(src, at, scale)


GLOBAL = frozenset(("STAND UP", "DEBUG", "ACKNOWLEDGE", "SKIP DRILL"))
VIEWS = {v.name: v for v in (
    View("SONAR", "SONAR", frozenset(("TRAIN LEFT", "TRAIN RIGHT", "MARK", "PING", "WATERFALL SCALE",
                                     "BEARING MODE")),
         (P(MONITOR, (16, 36), 1.42), P(GAUGE["NOISE"], (948, 30), 1.4), P(ALARMS, (1100, 300), 1.4),
          P(COUNTERMEASURES, (940, 300), 0.95))),
    View("FIRE CONTROL", "TMA", frozenset(("TDC ROW UP", "TDC ROW DOWN", "TDC VALUE UP", "TDC VALUE DOWN",
                                            "AUTO-SOLVE", "FIRE", "FIRE TUBE 1", "FIRE TUBE 2", "WIRE LEFT",
                                            "WIRE RIGHT", "NEXT FISH", "CUT WIRE", "SCOPE RANGE", "NOISEMAKER")),
         (P(SCOPE_PANEL, (16, 16), 1.38), P(TDC_PANEL, (16, 376), 1.38), P(MONITOR, (382, 16), 1.0),
          P(WEAPONS_PANEL, (1040, 16), 1.42), P(COUNTERMEASURES, (1040, 250), 1.42))),
    View("RADIO", "SONAR", frozenset(),
         (P(TELETYPE, (290, 12), 2.12),)),
    View("HELM AND PLANES", "SONAR", frozenset(("SLOWER", "FASTER", "RUDDER LEFT", "RUDDER RIGHT",
                                               "RUDDER AMIDSHIPS", "SHALLOWER", "DEEPER", "HOLD DEPTH",
                                               "PERISCOPE DEPTH")),
         (P(GAUGE["DEPTH"], (60, 20), 1.6), P(GAUGE["NOISE"], (360, 20), 1.6), P(ALARMS, (1080, 20), 1.5),
          P(TELEGRAPH_RECT, (16, 384), 1.55), P(HELM_PANEL, (346, 384), 1.4), P(DIVING_PANEL, (620, 384), 1.4))),
    View("BALLAST CONTROL", "SONAR", frozenset(("BLOW", "RAISE SNORKEL", "RAISE SCOPE", "PERISCOPE DEPTH")),
         (P(GAUGE["BATTERY"], (40, 30), 1.8), P(GAUGE["DEPTH"], (40, 380), 1.6), P(DIVING_PANEL, (420, 100), 2.2),
          P(ALARMS, (1000, 60), 2.2))),
    View("DAMAGE CONTROL", "DAMAGE", frozenset(),
         (P(MONITOR, (16, 36), 1.42), P(GAUGE["HULL"], (948, 30), 1.4), P(ALARMS, (1100, 300), 1.4))),
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


def compose(view, frame, backdrop):
    """The station canvas: its pieces cut from the full console frame and laid on the console's own steelwork."""
    if len(view.pieces) == 1 and view.pieces[0].dst == frame.get_rect():
        return frame
    canvas = backdrop.copy()
    for p in view.pieces:
        canvas.blit(pygame.transform.smoothscale(frame.subsurface(p.src), p.dst.size), p.dst)
        pygame.draw.rect(canvas, (24, 24, 23), p.dst.inflate(4, 4), 2)
    return canvas


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
