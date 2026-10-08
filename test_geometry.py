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

import settings  # noqa: E402
from audio import AudioSynthesizer  # noqa: E402
from console import Console  # noqa: E402
from displays import WaterfallDisplay  # noqa: E402
from fire_control import TargetDataComputer  # noqa: E402
from geometry import angle_diff, fix, offset  # noqa: E402
from graphics.periscope import EYE, PeriscopeRenderer, View  # noqa: E402
from layout import WF_W  # noqa: E402
from sensors import SCOPE_FOV, ActiveSonar, PassiveSonar, PeriscopeOptics  # noqa: E402
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


class NoKeys:
    def __getitem__(self, k):
        return 0


def station(level="COMMANDER", rel=40.0, rng=2500.0):
    """A console with one merchant at a known relative bearing, nothing else in the sea."""
    random.seed(3)
    np.random.seed(3)
    con = Console(level, AudioSynthesizer())
    w = con.world
    w.director, w.ocean.timer, w.ocean.rain, w.ocean.front = None, 1e9, 0.0, 0.0
    p = w.player
    ship = Vessel(*offset(p.x, p.y, p.heading + rel, rng), p.heading + rel + 100, 8 * KNOT)
    w.targets.append(ship)
    return con, ship


def check_lock_links_scope_to_sonar():
    """The bug that started this: a LOCK could sit 9.5 deg off the ship, outside the high-power eyepiece."""
    con, ship = station()
    p = con.world.player
    con.dial = fix(p, ship).rel_brg + 5.0  # in the cone, well off the trace
    for _ in range(3):
        con.update(1 / 30, NoKeys())
    assert not con.locked, "5 deg off the trace must not read LOCK"
    for _ in range(int(8 * 30)):  # an operator trains by the SIG < / > guide until LOCK, then the tracker has it
        if not (con.locked or con.tracking) and con.brg_err is not None:
            con.dial_true += 0.2 if con.brg_err > 0 else -0.2
        con.update(1 / 30, NoKeys())
    truth = fix(p, ship)
    assert con.locked or con.tracking, (con.brg_err, con.signal)
    assert abs(angle_diff(con.dial_true, truth.true_brg)) < 1.5, (con.dial_true, truth.true_brg)
    con.scope_to_sonar()
    assert abs(angle_diff(con.scope_true, truth.true_brg)) < SCOPE_FOV[True] / 2, "ship outside the eyepiece"
    con.mark()
    assert abs(angle_diff(con.tdc.get("BRG"), truth.rel_brg)) < 1.5


def check_stabilisation():
    """True mode: dial and scope hold their true bearing through a turn. Relative mode: they swing with the hull."""
    for true in (True, False):
        settings.SETTINGS["true_bearings"] = true
        con, _ = station(rel=180.0, rng=15000.0)  # far astern: nothing to track
        p = con.world.player
        p.speed = p.ordered_speed = 6 * KNOT
        con.dial_true, con.scope_true = 30.0, 60.0
        rel0 = (con.dial, con.scope_brg)
        p.rudder = 30.0
        for _ in range(20 * 30):
            con.update(1 / 30, NoKeys())
        assert abs(angle_diff(p.heading, 0.0)) > 20, "the boat must actually have turned"
        if true:
            assert abs(angle_diff(con.dial_true, 30.0)) < 1e-6 and abs(angle_diff(con.scope_true, 60.0)) < 1e-6
        else:
            assert abs(angle_diff(con.dial, rel0[0])) < 1e-6 and abs(angle_diff(con.scope_brg, rel0[1])) < 1e-6
    settings.reset()


def check_waterfall_frames():
    """Rows are stored true; drawn relative, each row shifts by the heading it was painted at."""
    wf = WaterfallDisplay(row_interval=1.0)
    wf.update(1.0, np.array([0.0]), np.array([200.0]), heading=90.0)  # dead ahead while heading 090
    assert abs(int(np.argmax(wf.buffer[0])) - WF_W // 4) <= 1, "stored at 090 true"
    rel = pygame.surfarray.array3d(wf.draw(relative=True))[:, 0, 1]
    assert int(np.argmax(rel)) in (0, 1, WF_W - 1), "drawn at 000 relative"
    tru = pygame.surfarray.array3d(wf.draw(relative=False))[:, 0, 1]
    assert abs(int(np.argmax(tru)) - WF_W // 4) <= 1


def check_rendering_never_moves_the_world():
    """Drawing the station (shake, needle wobble, periscope spray) must not consume the simulation's dice."""
    from workstation import Workstation
    screen = pygame.display.get_surface()
    worlds = []
    for draw in (False, True):
        random.seed(9)
        np.random.seed(9)
        con, ship = station(rng=1800.0)
        st = Workstation() if draw else None
        con.world.ais.clear()
        con.jolt(1.0)  # shake on: the jitter path draws random numbers every frame
        for _ in range(300):
            con.update(1 / 30, NoKeys())
            if st:
                st.draw(screen, con, "PLAY", False, False, 1 / 30)
        worlds.append((ship.x, ship.y, con.world.ocean.rain, random.random()))
    assert worlds[0] == worlds[1], worlds


if __name__ == "__main__":
    check_rendering_never_moves_the_world()
    check_lock_links_scope_to_sonar()
    check_stabilisation()
    check_waterfall_frames()
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
