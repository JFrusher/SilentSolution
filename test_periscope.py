"""Periscope renderer checks. Run: uv run test_periscope.py"""
import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np  # noqa: E402
import pygame  # noqa: E402

import sim  # noqa: E402

pygame.init()
pygame.display.set_mode((1280, 720))

from graphics.periscope import EYE, PeriscopeRenderer, View  # noqa: E402
from sensors import PeriscopeOptics  # noqa: E402
from sim import KNOT, Submarine, Vessel, WorldSimulation  # noqa: E402


def scene(ships, rain=0.0):
    w = WorldSimulation(Submarine(0, 0, 0, 0, z=15), ships)
    w.ocean.rain = w.ocean.front = rain
    w.ocean.timer, w.ocean.wind = 1e9, 3 + 11 * rain
    w.player.raise_mast("scope")
    w.step(0.05)
    return w


def frame(renderer, w, brg, fov=8.0):
    optics = PeriscopeOptics(w)
    look = optics.look()
    p = w.player
    v = View(brg, fov, optics.eye_height(), p.x, p.y, w.time, w.ocean, *(look or ([], [], [])), under=look is None)
    return pygame.surfarray.array3d(renderer.render(v)).astype(int)


if __name__ == "__main__":
    sim.seed(1)
    r = PeriscopeRenderer()
    empty = frame(r, scene([]), 0.0)
    with_ship = frame(r, scene([Vessel(0, 2000, 90, 8 * KNOT)]), 0.0)
    band = slice(EYE // 2 - 40, EYE // 2 + 5)  # just above the horizon, centre of the eyepiece
    diff = np.abs(with_ship[EYE // 2 - 60:EYE // 2 + 60, band] - empty[EYE // 2 - 60:EYE // 2 + 60, band]).sum(axis=2)
    assert (diff > 60).sum() > 200, "a merchant at 2 km dead ahead should be drawn on the horizon"
    away = frame(r, scene([Vessel(0, 2000, 90, 8 * KNOT)]), 180.0)
    assert np.abs(away - frame(r, scene([]), 180.0)).sum(axis=2).max() < 120, "nothing astern: no ship pixels"

    w = scene([])
    w.player.z = 16.9  # lens awash
    w.player.wave = 0.5
    w.player.scope_clear = False
    washed = frame(r, w, 0.0)
    c = washed[EYE // 2 - 100:EYE // 2 + 100, EYE // 2 - 100:EYE // 2 + 100]
    assert c[..., 1].mean() > c[..., 0].mean() + 15, "a wave over the lens turns the view sea-green"

    for rain in (0.0, 1.0):
        w = scene([Vessel(-400, 2400, 80, 8 * KNOT), Vessel(1300, 2900, 120, 8 * KNOT, kind="ESCORT")], rain)
        frame(r, w, 10.0, 32.0)
        t0 = time.perf_counter()
        for _ in range(30):
            w.step(1 / 60)
            frame(r, w, 10.0, 32.0)
        ms = (time.perf_counter() - t0) / 30 * 1000
        print(f"rain {rain}: {ms:.1f} ms per eyepiece frame (incl. world step + readback)")
        assert ms < (150 if os.environ.get("CI") else 40), "eyepiece rendering far too slow"  # CI runners are slow
    print("ok")
