"""Plain-assert checks. Run: uv run test_sim.py"""
import math
import random

import numpy as np

from ai import (ALARMED, ALERT, ATTACK, CRUISE, PATROL, SCATTER, SEARCH, Convoy, EscortAI, MerchantAI,
                frame_point)
from audio import AudioSynthesizer
from console import Console, build_world
from displays import ROW_INTERVAL, TEMPLATES, SpectrumAnalyzer, WaterfallDisplay
from fire_control import TargetDataComputer
from layout import WF_W
from sensors import PeriscopeOptics, cone_gain
from tma import TMALog
from sim import (EXHAUSTED, KNOT, YARD, Decoy, Submarine, Torpedo, Vessel, WorldSimulation, angle_diff,
                 bearing)
from tuning import DIFFICULTY


def calm_or_storm(w, rain):
    w.ocean.rain = w.ocean.front = rain
    w.ocean.timer = 1e9
    w.ocean.wind = 3.0 + 11.0 * rain


def spotted_within(masts, rng, seconds, seed, rain=0.0, speed_kt=0.0):
    """Does an unaware escort `rng` m off spot our raised `masts` within `seconds`?"""
    random.seed(seed)
    w = WorldSimulation(Submarine(0, 0, 0, speed_kt * KNOT, z=15), [Vessel(0, rng, 90, 0)])
    calm_or_storm(w, rain)
    w.ais.append(EscortAI(w.targets[0], 90.0, detect_radius=0.0))  # deaf: eyes only
    for mast in masts:
        w.player.raise_mast(mast)
    for _ in range(int(seconds / 0.5)):
        if any(k == "SPOTTED" for k, _, _ in w.step(0.5)):
            return True
    return False


def convoy_world(player=(0.0, -8000.0, 60.0)):
    """Three merchants in column on 090 at 8 kt with one escort screening ahead; our boat stopped and quiet."""
    w = WorldSimulation(Submarine(player[0], player[1], 0, 0, z=player[2]), [])
    convoy = Convoy(90.0, 8 * KNOT)
    for i in range(3):
        offset = (-500.0 * i, 0.0)
        ship = Vessel(*frame_point(0, 0, 90.0, *offset), 90.0, 8 * KNOT)
        w.targets.append(ship)
        w.ais.append(MerchantAI(ship, convoy, offset, max_speed=13 * KNOT))
    escort = Vessel(*frame_point(0, 0, 90.0, 1200, 0), 90.0, 0, decoys=0)
    w.targets.append(escort)
    w.ais.append(EscortAI(escort, 90.0, convoy=convoy, station=(1200.0, 0.0), detect_radius=3000.0))
    return w, convoy, w.ais[:3], w.ais[3]


def run(w, seconds, dt=0.1):
    kinds = []
    for _ in range(int(seconds / dt)):
        kinds += [e[0] for e in w.step(dt)]
    return kinds


def engagement(speed_error_kts, arm_yd=None, decoy=False):
    """Fire one fish from a TDC solution on a 12 kt crossing target at 4000 yd; return event kinds."""
    w = WorldSimulation(Vessel(0, 0, 0, 0), [Vessel(0, 4000 * YARD, 90, 12 * KNOT)])
    tdc = TargetDataComputer(w.player)
    tdc.set("BRG", 0.0)
    tdc.set("RNG", 4000.0)
    tdc.set("SPD", 12.0 + speed_error_kts)
    tdc.set("CRS", 90.0)
    sol = tdc.solve()
    assert sol, "no firing solution"
    if decoy:  # loud noisemaker sitting on the torpedo track
        ix, iy = sol.intercept
        w.targets.append(Decoy(ix / 2, iy / 2, 0, 0, noise=3.0, ttl=999))
    w.fire(sol.gyro, arm_distance=(arm_yd or 1e6) * YARD)
    kinds = []
    while w.torpedoes:
        kinds += [e[0] for e in w.step(0.05)]
    return kinds


def hunt(depth):
    """An escort 6 km off hears (or doesn't hear) one ping; 10 minutes later, what happened?"""
    random.seed(1)
    w = WorldSimulation(Submarine(0, 0, 0, 0, z=depth), [Vessel(0, 6000, 90, 0)])
    w.ais.append(ai := EscortAI(w.targets[0], base_course=90))
    w.emit_ping()
    states = set()
    for _ in range(6000):
        w.step(0.1)
        states.add(ai.state)
    return states, w.hull


def counterfire(depth, noisemaker=False, layer_loss=0.0):
    """A homing fish fired straight at our stopped boat from 3 km; returns (event kinds, hull)."""
    random.seed(2)
    w = WorldSimulation(Submarine(0, 0, 90, 0, z=depth), [])
    w.ocean.layer_loss = layer_loss
    w.launch_hostile(Vessel(0, 3000, 180, 0, z=60), 180.0, 40 * KNOT, seeker_range=1200 * YARD,
                     arm_distance=600 * YARD, max_run=9000 * YARD, run_depth=60)
    kinds = []
    while w.torpedoes:
        if noisemaker and w.player.range_to(w.torpedoes[0]) < 800:  # decoy only lives 45 s: wait for the fish
            w.drop_noisemaker()
            noisemaker = False
        kinds += [e[0] for e in w.step(0.05)]
    return kinds, w.hull


if __name__ == "__main__":
    # fire control: gyro solution, homing rescue, decoys
    assert engagement(0)[-1] == "HIT", "perfect gyro solution should hit"
    miss = engagement(2)
    assert miss[-1] == EXHAUSTED and "HIT" not in miss, miss
    homed = engagement(2, arm_yd=3000)
    assert "HOMING" in homed and homed[-1] == "HIT", homed
    assert engagement(0, decoy=True)[-1] == "DECOYED"

    # position keeper: correct estimates track the real contact
    own, tgt = Vessel(0, 0, 0, 5 * KNOT), Vessel(2000, 3000, 135, 15 * KNOT)
    tdc = TargetDataComputer(own)
    tdc.set("BRG", bearing(0, 0, tgt.x, tgt.y))
    tdc.set("RNG", math.hypot(tgt.x, tgt.y) / YARD)
    tdc.set("SPD", 15.0)
    tdc.set("CRS", 135.0)
    for _ in range(1200):
        own.step(0.05), tgt.step(0.05), tdc.update(0.05)
    assert abs(tdc.get("BRG") - bearing(own.x, own.y, tgt.x, tgt.y)) < 0.1
    assert abs(tdc.get("RNG") * YARD - own.range_to(tgt)) < 1.0

    # escort AI + thermal layer: a ping above the layer brings a depth-charge attack; below it, nobody hears
    states, hull = hunt(50)
    assert {ALERT, ATTACK} <= states and hull < 100, (states, hull)
    states, hull = hunt(200)
    assert states == {PATROL} and hull == 100, (states, hull)

    # counter-fire: a homing fish hits a boat on its side of the layer, loses one under it, takes a noisemaker
    kinds, hull = counterfire(60)
    assert "PLAYER_HIT" in kinds and hull < 100, (kinds, hull)
    kinds, hull = counterfire(200)
    assert kinds[-1] == EXHAUSTED and hull == 100, (kinds, hull)
    kinds, hull = counterfire(60, noisemaker=True)
    assert "DECOYED" in kinds and hull == 100, (kinds, hull)

    # own boat: running fast and shallow cavitates and is loud; slow is quiet
    boat = Submarine(0, 0, 0, 20 * KNOT, z=60)
    boat.step(0.1)
    assert boat.cavitating and boat.noise > 1.2, boat.noise
    boat = Submarine(0, 0, 0, 4 * KNOT, z=60)
    boat.step(0.1)
    assert not boat.cavitating and boat.noise < 0.5, boat.noise

    # acoustic profile library: each clean signature is identified as itself
    for i in range(len(TEMPLATES)):
        sa = SpectrumAnalyzer()
        for _ in range(30):
            sa.update(0.1, 0.0, np.array([1.0]), np.array([160.0]), np.array([i]), 0.0)
        assert sa.best == i, (i, sa.best, sa.confidence)

    # wave director: a wave spawns, and clearing it brings resupply
    random.seed(3)
    w = build_world(DIFFICULTY["COMMANDER"])
    kinds = []
    while not w.targets:
        kinds += [e[0] for e in w.step(0.1)]
    assert "WAVE" in kinds and any(t.kind == "ESCORT" for t in w.targets)
    torps = w.player.torpedoes
    w.targets.clear()
    w.ais.clear()
    assert "WAVE_CLEAR" in [e[0] for e in w.step(0.1)] and w.player.torpedoes == torps + 4

    # ship behaviour: an unaware convoy holds formation and its escort holds station
    random.seed(4)
    w, convoy, merchants, escort = convoy_world()
    run(w, 300)
    lead, second = merchants[0].ship, merchants[1].ship
    assert all(m.state == CRUISE for m in merchants) and escort.state == PATROL
    assert 350 < lead.range_to(second) < 700, lead.range_to(second)
    assert abs(((lead.heading - 90) + 180) % 360 - 180) < 2, lead.heading
    station = frame_point(lead.x, lead.y, lead.heading, 1200, 0)
    assert math.hypot(station[0] - escort.ship.x, station[1] - escort.ship.y) < 700

    # ... a ping wakes it: full revs and the zig-zag plan, escort runs at us
    w.emit_ping()
    kinds = run(w, 5)
    assert "CONVOY_ALARM" in kinds and all(m.state == ALARMED for m in merchants) and escort.state == ALERT

    # ... a sinking scatters the survivors and sends the escort to search the back-plotted torpedo track
    random.seed(5)
    w, convoy, merchants, escort = convoy_world(player=(0.0, -30000.0, 60.0))  # boat well clear of the search
    run(w, 60)
    lead = merchants[0].ship
    fish = Torpedo(lead.x, lead.y - 40, 0.0, 20.0, seeker_range=0, arm_distance=1e9, run_depth=0)
    fish.ox, fish.oy = 0.0, -8000.0  # where it was fired from
    w.torpedoes.append(fish)
    sink_point = (lead.x, lead.y)
    survivors = [m.ship for m in merchants[1:]]
    before = [math.hypot(s.x - sink_point[0], s.y - sink_point[1]) for s in survivors]
    kinds = run(w, 2)
    assert "HIT" in kinds and "CONVOY_SCATTER" in kinds
    assert all(m.state == SCATTER for m in merchants[1:]) and escort.state == SEARCH
    assert math.hypot(escort.datum[0] - 0.0, escort.datum[1] + 8000.0) < 1500, escort.datum
    kinds = run(w, 240)  # ships astern have to come round ~180 deg first
    after = [math.hypot(s.x - sink_point[0], s.y - sink_point[1]) for s in survivors]
    assert all(a > b + 300 for a, b in zip(after, before)), (before, after)
    assert all(s.speed > 11 * KNOT for s in survivors) and "ESCORT_PING" in kinds
    run(w, 1500)  # run to the datum, search the square, give up
    assert escort.state == PATROL, escort.state

    # lookouts: masts down at periscope depth are invisible; a snorkel near the convoy gets seen and wakes everyone
    random.seed(6)
    w, convoy, merchants, escort = convoy_world(player=(1200.0, 1500.0, 15.0))
    run(w, 30)
    assert escort.state == PATROL and not convoy.alarmed, (escort.state, convoy.alarmed)
    w.player.raise_mast("snorkel")
    run(w, 60)
    assert escort.state in (ALERT, ATTACK) and convoy.alarmed, (escort.state, convoy.alarmed)

    # masts: depth envelope, diesel only with the head clear, auto-lower, flooding at speed, head valve in a seaway
    assert Submarine(0, 0, 0, 0, z=60).raise_mast("scope") == "TOO DEEP FOR MASTS"
    w = WorldSimulation(Submarine(0, 0, 0, 0, z=15, battery=50.0), [])
    calm_or_storm(w, 0.0)
    p = w.player
    assert p.raise_mast("snorkel") is None
    run(w, 30)
    assert p.snorkeling and p.battery > 55 and p.noise > 1.0, (p.snorkeling, p.battery, p.noise)
    p.ordered_depth = 60
    assert "MASTS_LOWERED" in run(w, 1) and not p.snorkel_up and not p.snorkeling
    w = WorldSimulation(Submarine(0, 0, 0, 0, z=15), [])
    calm_or_storm(w, 1.0)
    w.player.raise_mast("snorkel")
    assert "HEAD_VALVE" in run(w, 60), "storm seas should wash over the snorkel head"
    w = WorldSimulation(Submarine(0, 0, 0, 10 * KNOT, z=15), [])
    w.player.raise_mast("snorkel")
    assert "SNORKEL_FLOODED" in run(w, 2)

    # being seen: snorkel worse than scope, speed (feather) worse than slow, storm + range nearly invisible
    snorkel = sum(spotted_within(["snorkel"], 1500, 60, s) for s in range(10))
    scope = sum(spotted_within(["scope"], 1500, 60, s) for s in range(10))
    feather = sum(spotted_within(["scope"], 1500, 60, s, speed_kt=8) for s in range(10))
    storm = sum(spotted_within(["scope"], 5000, 60, s, rain=1.0) for s in range(10))
    assert snorkel >= 8 and snorkel > scope and feather > scope and storm == 0, (snorkel, scope, feather, storm)

    # optics: visibility and horizon limit what the eye sees; bearings are sharp, the rangefinder is close
    w = WorldSimulation(Submarine(0, 0, 0, 0, z=15), [Vessel(0, 15000, 90, 0), Vessel(0, 11000, 90, 0),
                                                      Vessel(3000, 0, 90, 0)])
    calm_or_storm(w, 0.0)
    w.player.raise_mast("scope")
    w.step(0.1)
    seen = sorted(PeriscopeOptics(w).look()[0], key=lambda s: s.rng)
    assert [round(s.rng / 1000) for s in seen] == [3, 11], seen          # 15 km is beyond 12 km visibility
    assert seen[0].drop == 0 and seen[1].drop > 0                      # far one is partly below our horizon
    assert abs(angle_diff(seen[0].brg, 90.0)) < 0.5 and abs(angle_diff(seen[1].brg, 0.0)) < 0.5
    ranges = [PeriscopeOptics.rangefinder(seen[0], True) for _ in range(200)]
    assert abs(sum(ranges) / len(ranges) - seen[0].rng) / seen[0].rng < 0.02
    calm_or_storm(w, 1.0)
    assert PeriscopeOptics(w).look()[0] == [], "storm visibility (~1.4 km) hides both"
    w.player.z = 40.0
    w.step(0.1)
    assert PeriscopeOptics(w).look() is None, "masts struck below periscope depth: blind"

    # spread salvo: F with SPREAD set fires every ready tube, fanned symmetrically about the solution, on the wire
    con = Console("COMMANDER", AudioSynthesizer())
    con.tdc.set("SPR", 6.0)
    con.fire()
    fish = con.world.torpedoes
    assert len(fish) == 2 and all(t.wired for t in fish), fish
    assert abs(abs(angle_diff(fish[0].heading, fish[1].heading)) - 6.0) < 0.01

    # wire guidance: a wired fish steers to its aim point; the wire parts at speed and at the end of the spool
    w = WorldSimulation(Submarine(0, 0, 0, 0, z=60), [])
    t = w.fire(0.0, wired=True, arm_distance=1e9)
    t.wire_aim = (3000.0, 3000.0)
    run(w, 60)
    assert t.wired and abs(angle_diff(bearing(0, 0, t.x, t.y), 45)) < 12, (t.x, t.y, t.heading)
    w.player.speed = w.player.ordered_speed = 14 * KNOT
    assert "WIRE_CUT" in run(w, 0.2) and not t.wired
    t2 = w.fire(0.0, wired=True, arm_distance=1e9)
    w.player.speed = w.player.ordered_speed = 0.0
    t2.run = 8001.0
    assert "WIRE_CUT" in run(w, 0.2) and not t2.wired

    # TMA: noisy bearings across an own-ship leg change plus one echo let auto-solve recover the target
    random.seed(7)
    own, tgt = Vessel(0, 0, 0, 5 * KNOT), Vessel(3000, 6000, 250, 10 * KNOT)
    log, tdc = TMALog(), TargetDataComputer(own)
    t = 0.0
    while t < 300:
        if t == 150:
            own.heading = 90.0  # leg change: makes range observable from bearings
        log.update(t, own, True, bearing(own.x, own.y, tgt.x, tgt.y) + random.gauss(0, 0.5))
        if t == 200:
            log.add(t, bearing(own.x, own.y, tgt.x, tgt.y), "ECHO", own.range_to(tgt))
        own.step(0.5), tgt.step(0.5), tdc.update(0.5)
        t += 0.5
    result = log.auto_solve(t, own, tdc)
    assert result[1] is False, "two legs and an echo: the solution should be well conditioned"
    assert abs(angle_diff(tdc.get("CRS"), 250)) <= 15 and abs(tdc.get("SPD") - 10) <= 2, (tdc.get("CRS"), tdc.get("SPD"), result)
    assert abs(tdc.get("RNG") * YARD - own.range_to(tgt)) / own.range_to(tgt) < 0.15, tdc.get("RNG")
    assert log.fit(t, own, tdc) < 1.5

    wf = WaterfallDisplay()
    wf.update(ROW_INTERVAL, np.array([90.0, 0.0]), np.array([200.0, 200.0]))
    row = wf.buffer[0]
    assert np.argmax(row[50:200]) + 50 == WF_W // 4, "090 rel should land a quarter across"
    assert row[0] > 150 and row[-1] > 100, "contact at 000 should blur across the 359/000 seam"

    g = cone_gain(350.0, np.array([350.0, 5.0, 20.0]))
    assert g[0] == 1.0 and 0 < g[1] < 1 and g[2] == 0, g
    print("ok")
