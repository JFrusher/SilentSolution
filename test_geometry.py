"""The positional backbone, cross-checked: every sensor and display must agree with geometry.fix() about where
each contact is, steady and in a hard turn, with contacts on the surface and at depth.
Run: uv run test_geometry.py"""
import math
import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np  # noqa: E402
import pygame  # noqa: E402

pygame.init()
pygame.display.set_mode((1280, 720))

from fire_control import TargetDataComputer  # noqa: E402
from geometry import angle_diff, fix, offset  # noqa: E402
from graphics.periscope import EYE, PeriscopeRenderer, View  # noqa: E402
from sensors import ActiveSonar, PassiveSonar, PeriscopeOptics  # noqa: E402
from sim import KNOT, YARD, Submarine, Vessel, WorldSimulation  # noqa: E402
from tma import TMALog  # noqa: E402


def scenario(seed):
    """Own boat at periscope depth under way with full rudder on; contacts all round, on the surface and deep."""
    rng = random.Random(seed)
    own = Submarine(rng.uniform(-5e3, 5e3), rng.uniform(-5e3, 5e3), rng.uniform(0, 360), 6 * KNOT, z=15.0)
    own.rudder = rng.choice((-30.0, 30.0))
    ships = []
    for k in range(6):
        x, y = offset(own.x, own.y, rng.uniform(0, 360), rng.uniform(1500, 6000))
        ships.append(Vessel(x, y, rng.uniform(0, 360), rng.uniform(2, 14) * KNOT, z=(0.0, 0.0, 60.0, 160.0)[k % 4]))
    w = WorldSimulation(own, ships)
    w.ocean.layer_loss, w.ocean.timer, w.ocean.rain, w.ocean.front = 1.0, 1e9, 0.0, 0.0  # nothing hidden
    own.raise_mast("scope")
    return w


def check_fix_internals(w, dt=0.5):
    p = w.player
    before = [fix(p, t) for t in w.targets]
    for f, t in zip(before, w.targets):
        assert abs(angle_diff(f.rel_brg, f.true_brg - p.heading)) < 1e-9
        assert abs(f.slant ** 2 - f.rng ** 2 - (t.z - p.z) ** 2) < 1e-6 * f.slant ** 2
        assert abs(math.tan(math.radians(f.de)) * f.rng - (t.z - p.z)) < 1e-6 * max(f.rng, 1)
    w.step(dt)
    for f, t in zip(before, w.targets):  # the rates predict where the bearing and range went
        g = fix(p, t)
        assert abs(angle_diff(g.true_brg, f.true_brg) / dt - (f.brg_rate + g.brg_rate) / 2) < 0.02, (f, g)
        assert abs((g.rng - f.rng) / dt - (f.rng_rate + g.rng_rate) / 2) < 0.05, (f, g)


def check_sensors(w):
    p = w.player
    truth = [fix(p, t) for t in w.targets]
    rel, *_ = PassiveSonar(w, noise_deg=0.0, resolution=1e-6).listen()
    for f, b in zip(truth, rel):
        assert abs(angle_diff(b, f.rel_brg)) < 1e-3, ("passive", b, f.rel_brg)
    active = ActiveSonar(w, noise_deg=0.0, timing_jitter=0.0)
    active.ping()
    echoes = [e for e in active.update(30.0) if e[0] is not None]
    for f, t in zip(truth, w.targets):
        if w.ocean.crosses_layer(p, t):
            continue  # by design: the layer's shadow returns no echo
        assert any(abs(angle_diff(b, f.rel_brg)) < 1e-6 and abs(r - f.slant) < 1e-6 for b, r in echoes), ("echo", f)
    p.sense_surface(w.ocean, w.time)
    look = PeriscopeOptics(w).look()
    if look:
        for s in look[0]:  # sightings carry 0.1 deg of eyeball noise
            t = next(t for t in w.targets if id(t) == s.uid)
            assert abs(angle_diff(s.brg, fix(p, t).true_brg)) < 0.5, ("scope", s.brg, fix(p, t).true_brg)


def check_tdc_and_tma(w, seconds=120.0, dt=0.25):
    """A TDC set to the truth must keep the truth (position keeping through the turn), and the TMA plot's
    predicted curve must run through the true bearing history."""
    p, t = w.player, w.targets[0]
    tdc, log = TargetDataComputer(p), TMALog()
    f = fix(p, t)
    tdc.set("BRG", f.rel_brg)
    tdc.set("RNG", f.rng / YARD)
    tdc.set("SPD", t.speed / KNOT)
    tdc.set("CRS", t.heading)
    history = []
    for _ in range(int(seconds / dt)):
        w.step(dt)
        tdc.update(dt)
        log.update(w.time, p, False, 0.0)
        history.append((w.time, fix(p, t).true_brg))
    f = fix(p, t)
    assert abs(angle_diff(tdc.get("BRG"), f.rel_brg)) < 0.2, (tdc.get("BRG"), f.rel_brg)
    assert abs(tdc.get("RNG") * YARD - f.rng) < 0.01 * f.rng, (tdc.get("RNG") * YARD, f.rng)
    times = [h[0] for h in history[::8] if h[0] > log.track[0][0]]
    pred, _ = log.predicted(times, w.time, p, tdc)
    for (tm, b), q in zip([h for h in history[::8] if h[0] > log.track[0][0]], pred):
        assert abs(angle_diff(q, b)) < 0.5, ("tma", tm, q, b)


def check_eyepiece():
    """Train the scope exactly on a ship's true bearing: the hull is drawn on the cross-wire."""
    w = WorldSimulation(Submarine(0, 0, 70, 0, z=15), [Vessel(*offset(0, 0, 110, 2500), 200, 8 * KNOT)])
    w.ocean.timer = 1e9
    w.player.raise_mast("scope")
    w.step(0.05)
    look = PeriscopeOptics(w).look()
    brg = fix(w.player, w.targets[0]).true_brg
    r, h = PeriscopeRenderer(), PeriscopeOptics(w).eye_height()
    img = pygame.surfarray.array3d(r.render(View(brg, 8.0, h, 0, 0, w.time, w.ocean, *look))).astype(int)
    sea = pygame.surfarray.array3d(r.render(View(brg + 30, 8.0, h, 0, 0, w.time, w.ocean, [], [], []))).astype(int)
    cols = np.where(np.abs(img - sea).sum(axis=2).max(axis=1) > 60)[0]
    centre = (cols.min() + cols.max()) / 2 - EYE / 2
    assert abs(centre) / (EYE / 8.0) < 0.3, f"hull {centre:+.1f} px off the cross-wire"


if __name__ == "__main__":
    for seed in range(5):
        w = scenario(seed)
        for _ in range(8):  # through the turn
            check_fix_internals(w)
            check_sensors(w)
            for _ in range(10):
                w.step(1.0)
        check_tdc_and_tma(scenario(seed))
    check_eyepiece()
    print("ok")
