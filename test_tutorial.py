"""Scripted trainee plays the whole training patrol through the real console. Run: uv run test_tutorial.py
The trainee cheats only where a human would read the screen (where to point the dial, what to dial into the TDC)."""
import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

import layout  # noqa: E402
from audio import AudioSynthesizer  # noqa: E402
from console import Console  # noqa: E402
from sim import KNOT, YARD, bearing  # noqa: E402
import settings  # noqa: E402
from settings import keyed  # noqa: E402
from tutorial import CHAPTERS, TRAINING, Tutorial  # noqa: E402

DT = 0.05


class NoKeys(dict):
    def __getitem__(self, k):
        return 0


def rel(con, v):
    p = con.world.player
    return (bearing(p.x, p.y, v.x, v.y) - p.heading) % 360


def aim(con, v, dep=None, arm=None):
    con.dial = rel(con, v)
    con.mark()
    con.tdc.set("RNG", con.world.player.range_to(v) / YARD)
    con.tdc.set("SPD", v.speed / KNOT)
    con.tdc.set("CRS", v.heading)
    if dep:
        con.tdc.set("DEP", dep)
    if arm:
        con.tdc.set("ARM", arm)


def act(tut, con, once):
    """One tick of a diligent trainee reading the order slip."""
    g, w, p = tut.goal, con.world, con.world.player
    ours_running = any(not t.hostile for t in w.torpedoes)
    hostile = [t for t in w.torpedoes if t.hostile]

    def do(tag, fn):
        if tag not in once:
            once.add(tag)
            fn()

    if g.startswith(("PRESS ENTER", "STUDY", "WATCH THE NOISE", "TRAINING COMPLETE")):
        do("enter", lambda: con.key(pygame.K_RETURN))
    elif g.startswith("RING UP HALF"):
        do("half", lambda: con.click(layout.TELEGRAPH_BTNS[2].center))  # press the HALF button
    elif g.startswith("RING UP FLANK"):
        do("flank", lambda: (con.key(pygame.K_x), con.key(pygame.K_x)))
    elif g.startswith("RING DOWN TO SLOW"):
        do("slow", lambda: con.telegraph(1))
    elif g.startswith("TURN 30"):
        do("wheel", lambda: (con.click((layout.WHEEL_C[0] + 70, layout.WHEEL_C[1])), setattr(con, "dragging", None)))
    elif g.startswith("RUDDER AMIDSHIPS"):
        do("c", lambda: con.key(pygame.K_c))
    elif g.startswith("ORDER 90"):
        do("e", lambda: [con.key(pygame.K_e) for _ in range(3)])
    elif g.startswith("HOLD DEPTH"):
        do("hold", lambda: con.click(layout.HOLD_BTN.center))
    elif g.startswith("BLOW"):
        do("b", lambda: con.key(pygame.K_b))
    elif g.startswith("PERISCOPE DEPTH"):
        do("pd", lambda: con.key(pygame.K_g))
    elif g.startswith("UP SCOPE"):
        do("up", lambda: (con.key(pygame.K_u), con.key(pygame.K_v)))
    elif g.startswith("MERCHANT IN THE WIRES"):
        do("power", lambda: con.key(pygame.K_TAB))
        con.scope_brg = rel(con, tut.merchant)
    elif g.startswith("BACK (V)"):
        do("down", lambda: (con.key(pygame.K_v), con.key(pygame.K_u)))
    elif g.startswith("SNORKEL (K)"):
        do("pd", lambda: con.key(pygame.K_g))
        if p.z <= 18:
            do("k", lambda: con.key(pygame.K_k))
    elif g.startswith("SNORKEL DOWN"):
        do("deep", lambda: con.order_depth(60))
    elif g.startswith("ORDER 60 M AND SLOW"):
        do("up", lambda: (con.order_depth(60), con.telegraph(1)))
    elif g.startswith("ORDER 60"):
        do("up", lambda: con.order_depth(60))
    elif g.startswith(("DIAL ONTO", "KEEP THE DIAL")):
        con.dial = rel(con, tut.merchant)
    elif g.startswith("MARK"):
        do("m", lambda: con.key(pygame.K_m))
    elif g.startswith("PING"):
        do("ping", lambda: con.click(layout.PING_BTN.center))
    elif g.startswith("SET TGT RNG"):
        con.tdc.selected = 1
        con.tdc.set("RNG", p.range_to(tut.merchant) / YARD)
    elif g.startswith("OPEN THE TMA"):
        do("page", lambda: con.key(pygame.K_F2))
    elif g.startswith("SET TGT SPD"):
        do("tma", lambda: (aim(con, tut.merchant), con.key(pygame.K_F2)))
    elif g.startswith("SINK THE MERCHANT"):
        if not ours_running and 0 in con.tubes:
            aim(con, tut.merchant)
            con.click(layout.TUBE_SW[con.tubes.index(0)])
    elif g.startswith("CHANGE SCOPE"):
        do("t", lambda: con.key(pygame.K_t))
    elif g.startswith("F5, PLANES"):
        def board():
            con.key(pygame.K_F5)
            k = con.damage_rows().index("PLANES")
            wf = layout.CRT_RECT.x + layout.WF_POS[0], layout.CRT_RECT.y + layout.WF_POS[1]
            con.click((wf[0] + 60, wf[1] + layout.DC_ROW_Y0 + k * layout.DC_ROW_H + layout.DC_ROW_H // 2))
            con.key(pygame.K_F5)
        do("dc", board)
    elif g.startswith("DIVE BELOW"):
        do("deep", lambda: (con.order_depth(150), con.telegraph(1)))
    elif g.startswith("CLASSIFY") and hostile:
        con.dial = rel(con, hostile[0])
    elif g.startswith("NOISEMAKER") and hostile and p.range_to(hostile[0]) < 700:
        do("n", lambda: (con.key(pygame.K_n), con.telegraph(1)))
    elif g.startswith("SINK THE SUBMARINE"):
        if tut.sub in w.targets and not ours_running and 0 in con.tubes:
            aim(con, tut.sub, dep=60, arm=500)
            con.key(pygame.K_f)


def play(seed, chapter=0):
    random.seed(seed)
    con = Console("TRAINING", AudioSynthesizer(), TRAINING)
    tut = Tutorial(con, chapter)
    once, step, times = set(), tut.i, {}
    start = 0.0
    while not tut.finished and con.world.time < 3600:
        if tut.i != step:
            times[step + 1] = con.world.time - start
            step, start, once = tut.i, con.world.time, set()
        act(tut, con, once)
        con.update(DT, NoKeys())
        tut.update(DT)
    return tut, con, times


if __name__ == "__main__":
    pygame.init()
    pygame.display.set_mode((layout.W, layout.H))
    for seed in (1, 2, 3):
        tut, con, times = play(seed)
        assert tut.finished, f"seed {seed}: stuck on drill {tut.progress}: {tut.goal}"
        assert not con.dead
        sunk = {v.kind for v in con.world.sunk}
        assert {"MERCHANT"} <= sunk, (seed, sunk)
        slowest = max(times, key=times.get)
        print(f"seed {seed}: {len(tut.steps)} drills in {con.world.time / 60:.1f} sim min; sunk {sorted(sunk)}; "
              f"slowest drill {slowest} ({times[slowest]:.0f} s)")
    for chapter in range(1, len(CHAPTERS)):  # every chapter stands on its own
        tut, con, _ = play(4, chapter)
        assert tut.finished and not con.dead, f"chapter {chapter}: stuck on drill {tut.progress}: {tut.goal}"
    # every key named in the syllabus comes from the bindings: no raw {TOKEN} survives, and a rebind shows up
    tut, con, _ = play(1)
    for st in tut.steps:
        for field, args in ((st.brief, (con,)), (st.goal, (con,)), (st.outro, (tut, con))):
            text = keyed(field(*args) if callable(field) else field)
            assert not settings.TOKEN.search(text), text
    settings.bind("FIRE", pygame.K_g)
    assert "(G, TUBE SWITCH)" in keyed(next(st.goal for st in tut.steps if "SINK THE MERCHANT" in st.goal))
    settings.reset()
    con = Console("TRAINING", AudioSynthesizer(), TRAINING)  # skipping every drill must never trip a later one
    tut = Tutorial(con)
    for _ in range(len(tut.steps)):
        con.key(pygame.K_F6)
        con.update(DT, NoKeys())
        tut.update(DT)
    assert tut.finished, tut.progress
    print("ok")
