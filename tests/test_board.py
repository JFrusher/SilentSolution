"""What the control room tells you away from the stations: the klaxon, the alarm lamps and legend, the attack plot.
Run: uv run checks.py"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np  # noqa: E402
import pygame  # noqa: E402

import settings  # noqa: E402
from audio import AudioSynthesizer  # noqa: E402
from console import Console  # noqa: E402
from geometry import offset  # noqa: E402
from graphics.room3d import legend_art, plot_art  # noqa: E402
from sim import KNOT, Torpedo  # noqa: E402
from workstation import ALERTS, alerts  # noqa: E402

pygame.init()
pygame.display.set_mode((1280, 720))
settings.reset()


class NoKeys(dict):
    def __getitem__(self, k):
        return 0


# the klaxon sounds once when a torpedo is first heard, not every frame it's still there
con = Console("COMMANDER", AudioSynthesizer(), seed=3)
con.world.director, con.world.targets, con.world.ais = None, [], []
calls = []
con.audio.play_klaxon = lambda: calls.append(con.world.time)
x, y = offset(0, 0, 90, 1500)
con.world.torpedoes.append(Torpedo(x, y, 270, 40 * KNOT, hostile=True, noise=1.4))
for _ in range(120):
    con.update(1 / 60, NoKeys())
assert con.torpedo_warning and len(calls) == 1, (con.torpedo_warning, calls)
assert [line for _, kind, line in con.heard if kind == "SOUND"] == ["[KLAXON]"], "deaf players see the klaxon"

# the orange lamps follow the alarms (not status like DIESEL), and the conn's legend lights the cause
lamps = alerts(con)
assert [n for n, _, _ in lamps] == list(ALERTS)
lit = legend_art([(n, n == "TORPEDO", c) for n, _, c in lamps])
dark = legend_art([(n, False, c) for n, _, c in lamps])
assert np.abs(pygame.surfarray.array3d(lit).astype(int) - pygame.surfarray.array3d(dark)).sum() > 0, "the cause lights"

# the attack plot draws the bearings we took and the TDC's target
track = [(t, 0.0, t * 4.0) for t in range(0, 300, 10)]
plain = pygame.surfarray.array3d(plot_art(track, 0.0)).astype(int)
marked = pygame.surfarray.array3d(plot_art(track, 0.0, [(100, 45.0, "MARK", None)], (2000.0, 2000.0, 0.0, -4.0)))
assert np.abs(marked - plain).sum() > 0, "marks and the solution show on the plot"
noted = pygame.surfarray.array3d(plot_art(track, 0.0, notes=[(50, 0.0, 200.0, 90.0, 3000.0, "CONVOY 2M 1E")]))
assert np.abs(noted - plain).sum() > 0, "a report goes on the plot"
# the TDC's cranks: take hold of a row's crank and wind it up a notch per few pixels; scroll on a row winds that row
from console import TDC_CRANK_NOTCH  # noqa: E402
from fire_control import FIELDS  # noqa: E402
from layout import TDC_CRANK_X, TDC_ROW_H, TDC_ROW_Y0  # noqa: E402

con = Console("COMMANDER", AudioSynthesizer(), seed=3)
y = TDC_ROW_Y0 + 2 * TDC_ROW_H + 9  # TGT SPD
before = con.tdc.get("SPD")
con.click((TDC_CRANK_X + 12, y))
assert con.tdc.selected == 2 and con.dragging == ("tdc", y), con.dragging
con.drag((TDC_CRANK_X + 12, y - 3 * TDC_CRANK_NOTCH))
assert abs(con.tdc.get("SPD") - (before + 3 * FIELDS["SPD"][3])) < 1e-9, con.tdc.get("SPD")
con.dragging = None
crs = con.tdc.get("CRS")
con.scroll((60, TDC_ROW_Y0 + 3 * TDC_ROW_H + 9), 1)
assert con.tdc.selected == 3 and con.tdc.get("CRS") != crs, "scrolling on a row winds that row"
print("board ok")
