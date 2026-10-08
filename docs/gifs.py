"""Film the README GIFs from scripted, headless runs of the real game: time-lapse with real-time beats, Dymo
captions, crossfaded loops. Run: uv run --with pillow docs/gifs.py [attack tma escort wire storm table]"""
import os
import random
import sys
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pygame  # noqa: E402
from PIL import Image  # noqa: E402

pygame.init()
screen = pygame.display.set_mode((1280, 720))

import settings  # noqa: E402
from ai import EscortAI  # noqa: E402
from audio import AudioSynthesizer  # noqa: E402
from console import Console  # noqa: E402
from geometry import fix, offset  # noqa: E402
from graphics import console_art as art  # noqa: E402
from graphics.tabletop import ReplayView  # noqa: E402
from layout import EYEPIECE_C, MONITOR, SCOPE_C, SCOPE_R  # noqa: E402
from replay import Replay  # noqa: E402
from sim import KNOT, YARD, Vessel  # noqa: E402
from workstation import Workstation  # noqa: E402

OUT = ROOT / "docs" / "images"
SUB = 1 / 30  # sim sub-step, s
AUDIO = AudioSynthesizer()


class NoKeys:
    def __getitem__(self, k):
        return 0


class Reel:
    """Frames for one GIF: each captured frame advances the sim `speed` x its screen time."""

    def __init__(self, name, crop=None, width=640, fps=10, colors=255):
        self.name, self.crop, self.width, self.fps, self.colors = name, crop, width, fps, colors
        self.frames, self.cursor = [], None

    def shoot(self, con, st, seconds, speed=1.0, caption="", until=None, hook=None, state="PLAY", crop=None):
        """Film `seconds` of GIF (or until until() is true), the sim running `speed` times faster."""
        for _ in range(int(seconds * self.fps)):
            for _ in range(max(1, round(speed / self.fps / SUB))):
                if hook:
                    hook(con)
                con.update(SUB, NoKeys())
            st.draw(screen, con, state, False, False, 1 / self.fps)
            self.grab(caption, speed, crop)
            if until and until():
                return

    def grab(self, caption, speed=1.0, crop=None):
        frame = screen.copy()
        if self.cursor:  # a drawn mouse pointer for the click-driven shots
            x, y = self.cursor
            pts = [(x, y), (x, y + 18), (x + 5, y + 13), (x + 9, y + 21), (x + 12, y + 19), (x + 8, y + 12),
                   (x + 14, y + 12)]
            pygame.draw.polygon(frame, (250, 250, 245), pts)
            pygame.draw.polygon(frame, (10, 10, 10), pts, 1)
        rect = pygame.Rect(crop or self.crop or frame.get_rect())
        frame = frame.subsurface(rect).copy()
        h = round(rect.h * self.width / rect.w)
        frame = pygame.transform.smoothscale(frame, (self.width, h))
        if caption:
            art.dymo(frame, (10, h - 30), caption, 15)
        if speed > 1:  # time-lapse badge, bottom right
            label = art.sans(14, True).render(f"x{speed:g}", True, (226, 222, 208))
            art.dymo(frame, (self.width - label.get_width() - 20, h - 30), f"x{speed:g}", 14)
        self.frames.append(Image.frombytes("RGB", frame.get_size(), pygame.image.tobytes(frame, "RGB")))

    def hold(self, seconds):
        self.frames += [self.frames[-1]] * int(seconds * self.fps)

    def save(self, fade=8):
        frames = list(self.frames)
        for i in range(1, fade + 1):  # crossfade the tail into the first frame: a seamless loop
            k = len(frames) - fade - 1 + i
            frames[k] = Image.blend(frames[k], frames[0], i / (fade + 1))
        # one palette for the whole reel (index 255 kept free), and pixels unchanged since the last frame written
        # as transparent: scattered small changes (needles, lamps, noise) then cost almost nothing
        sample = Image.new("RGB", (frames[0].width, frames[0].height * 6))
        for k in range(6):
            sample.paste(frames[k * (len(frames) - 1) // 5], (0, k * frames[0].height))
        palette = sample.quantize(colors=min(self.colors, 255), method=Image.Quantize.MEDIANCUT,
                                  dither=Image.Dither.NONE)
        out, prev = [], None
        for f in frames:
            idx = np.asarray(f.quantize(palette=palette, dither=Image.Dither.NONE))
            shown = idx.copy()
            if prev is not None:
                shown[idx == prev] = 255
            prev = idx
            img = Image.fromarray(shown.astype(np.uint8), "P")
            img.putpalette(palette.getpalette())
            out.append(img)
        path = OUT / f"gif_{self.name}.gif"
        out[0].save(path, save_all=True, append_images=out[1:], duration=int(1000 / self.fps), loop=0,
                    transparency=255, disposal=1, optimize=False)
        print(f"wrote {path.name}: {len(frames)} frames, {path.stat().st_size / 1e6:.1f} MB")


def calm(con, rain=0.0):
    w = con.world
    w.director = None
    w.ocean.rain = w.ocean.front = rain
    w.ocean.timer, w.ocean.wind = 1e9, 3 + 11 * rain


def place(con, rel, rng, course, kt, kind="MERCHANT", **kw):
    p = con.world.player
    ship = Vessel(*offset(p.x, p.y, p.heading + rel, rng), course % 360, kt * KNOT, **kw)
    ship.kind = kind
    con.world.targets.append(ship)
    return ship


def operator(con):
    """A trainee at the dial: train by the SIG guide until LOCK, then let the tracker have it."""
    if not (con.locked or con.tracking) and con.brg_err is not None:
        con.dial_true += 0.25 if con.brg_err > 0 else -0.25


def seed(n):
    random.seed(n)
    np.random.seed(n)


# ---------------------------------------------------------------------------------------------- the scenes
def attack():
    """Hero: contact to sinking on the full station."""
    seed(11)
    con, st = Console("COMMANDER", AUDIO), Workstation()
    calm(con)
    p = con.world.player
    merchant = place(con, 38, 4300, 300, 9, noise=1.15)
    place(con, 75, 7800, 285, 11, noise=0.9)  # two more ships further out: more slanting traces
    place(con, -60, 9000, 120, 7, noise=0.8)
    con.waterfall.row_interval = 3.0  # ten minutes of history, so the traces slant with their bearing drift
    for _ in range(int(600 / SUB)):
        con.update(SUB, NoKeys())
    con.dial_true = (fix(p, merchant).true_brg + 9) % 360
    reel = Reel("attack", width=960, fps=10, colors=220)

    def fish():
        return [t for t in con.world.torpedoes if not t.hostile]

    reel.shoot(con, st, 1.5, 20, "PASSIVE CONTACTS - TRACES SLANT AS THEY CROSS", hook=operator)
    reel.shoot(con, st, 2.0, 4, "TRAIN THE DIAL ONTO THE TRACE", hook=operator, until=lambda: con.tracking)
    reel.shoot(con, st, 1.0, 2, "LOCK - THE DIAL TRACKS HER")
    con.mark()
    con.ping()
    reel.shoot(con, st, 2.0, 3, "MARK - PING FOR RANGE",
               until=lambda: con.last_echo and con.world.time - con.ping_time > 7)
    con.tdc.set("RNG", p.range_to(merchant) / YARD)
    con.tdc.set("SPD", merchant.speed / KNOT)
    con.tdc.set("CRS", merchant.heading)
    con.tdc.set("SPR", 3.0)
    reel.shoot(con, st, 0.8, 1, "SOLUTION - GYRO AND RUN")
    con.fire()
    reel.shoot(con, st, 0.8, 1, "FIRE - TWO FISH, FANNED 3 DEG")
    reel.shoot(con, st, 5.0, 40, "ON THE WIRE",
               until=lambda: min((merchant.slant_to(t) for t in fish()), default=0) < 700)
    reel.shoot(con, st, 6.0, 10, "SEEKERS AWAKE - HOMING", until=lambda: merchant not in con.world.targets)
    assert merchant in con.world.sunk, "the hero shot must end in a hit"
    reel.shoot(con, st, 2.2, 1, "DETONATION - BREAKUP NOISES - SUNK")
    reel.save()


def tma():
    """Bearing dots over two legs, then auto-solve snaps the curve through them."""
    seed(5)
    con, st = Console("CADET", AUDIO), Workstation()
    calm(con)
    p = con.world.player
    target = place(con, 50, 6500, 210, 9, noise=1.2)
    con.dial = fix(p, target).rel_brg
    con.mark()  # the TDC starts on her bearing, but with the wrong course and speed: watch its curve peel away
    con.tdc.set("RNG", 5000.0)
    con.flip_page()
    reel = Reel("tma", crop=MONITOR)
    reel.shoot(con, st, 3.0, 50, "LEG ONE - EVERY BEARING IS A DOT")
    p.rudder = -30.0
    reel.shoot(con, st, 1.5, 10, "CHANGE COURSE FOR A SECOND LEG",
               until=lambda: abs((p.heading - 300 + 180) % 360 - 180) < 3)
    p.rudder = 0.0
    reel.shoot(con, st, 3.0, 50, "LEG TWO - THE DOTS BEND")
    con.ping()
    reel.shoot(con, st, 1.5, 6, "PING - ONE RANGE PINS IT DOWN")
    con.auto_solve()
    reel.shoot(con, st, 3.0, 1, "AUTO-SOLVE - THE CURVE RUNS THROUGH THE DOTS")
    reel.save()


def escort():
    """An escort runs in: fast screws, pings, a pattern, damage control."""
    seed(22)
    con, st = Console("COMMANDER", AUDIO), Workstation()
    calm(con)
    w, p = con.world, con.world.player
    w.min_hull = 30.0
    p.z = p.ordered_depth = 50.0
    p.speed = p.ordered_speed = 0.0
    ship = place(con, 140, 2600, 0, 0, kind="ESCORT")
    ai = EscortAI(ship, p.heading + 320, charges=15, decoys=0, aggression=0.9, detect_radius=3000.0)
    w.ais.append(ai)
    ai._mark(w, 40.0)
    ai.alarm = True
    con.dial = fix(p, ship).rel_brg
    seen = set()

    def log(c):
        seen.update(e[0] for e in c.frame_events)

    reel = Reel("escort", width=720)
    reel.shoot(con, st, 8.0, 25, "AN ESCORT HAS YOU - FAST SCREWS CLOSING", hook=log,
               until=lambda: p.range_to(ship) < 900)
    reel.shoot(con, st, 8.0, 10, "ATTACK RUN - SHE IS PINGING YOU", hook=log, until=lambda: "CHARGES" in seen)
    reel.shoot(con, st, 8.0, 3, "DEPTH CHARGES IN THE WATER", hook=log, until=lambda: "DAMAGE" in seen)
    assert "DAMAGE" in seen, "the escort shot must land a pattern"
    reel.shoot(con, st, 2.0, 1, "HIT - HULL AND SYSTEMS DAMAGED", hook=log)
    con.damage_board()
    reel.shoot(con, st, 2.5, 2, "DAMAGE CONTROL - SET THE REPAIR ORDER")
    reel.save()


def wire():
    """Click a fish on the tactical scope, click the water, watch it turn."""
    seed(8)
    con, st = Console("COMMANDER", AUDIO), Workstation()
    calm(con)
    p = con.world.player
    merchant = place(con, 25, 3300, 300, 10, noise=1.1)
    con.scope_range = 5000.0
    con.dial = fix(p, merchant).rel_brg
    for _ in range(int(60 / SUB)):
        con.update(SUB, NoKeys())
    con.mark()
    con.tdc.set("RNG", p.range_to(merchant) / YARD)
    con.tdc.set("SPD", merchant.speed / KNOT - 3)  # a deliberately poor solution: the wire has to save it
    con.tdc.set("CRS", merchant.heading)
    con.tdc.set("SPR", 6.0)
    con.fire()
    band = pygame.Rect(0, 0, 912, 470)
    reel = Reel("wire", crop=band)
    reel.shoot(con, st, 2.0, 8, "TWO FISH ON THE WIRE - BUT THE SOLUTION IS OFF")
    scale = (SCOPE_R - 6) / (con.scope_range * YARD)

    def on_scope(x, y):
        return SCOPE_C[0] + (x - p.x) * scale, SCOPE_C[1] - (y - p.y) * scale

    fish = [t for t in con.world.torpedoes if not t.hostile][0]
    reel.cursor = on_scope(fish.x, fish.y)
    reel.shoot(con, st, 1.0, 1, "CLICK A FISH TO TAKE IT")
    con.scope_click(reel.cursor)
    aim = offset(merchant.x, merchant.y, merchant.heading, 500)  # lead her
    reel.cursor = on_scope(*aim)
    reel.shoot(con, st, 1.0, 1, "CLICK WHERE TO SEND IT")
    con.scope_click(reel.cursor)
    reel.cursor = None
    ours = [t for t in con.world.torpedoes if not t.hostile]
    reel.shoot(con, st, 6.0, 30, "STEERING ONTO HER",
               until=lambda: min((merchant.slant_to(t) for t in ours if t in con.world.torpedoes), default=0) < 600)
    reel.shoot(con, st, 8.0, 6, "SEEKER AWAKE - HOMING", until=lambda: merchant not in con.world.targets)
    assert merchant in con.world.sunk, "the wire shot must end in a hit"
    reel.shoot(con, st, 2.5, 1, "HIT - SUNK")
    reel.save()


def storm():
    """Rain floods the sonar; heavy sea over the periscope; the diesels deafen the waterfall."""
    seed(3)
    con, st = Console("COMMANDER", AUDIO), Workstation()
    calm(con)
    w, p = con.world, con.world.player
    place(con, 30, 4000, 300, 9, noise=1.2)
    place(con, -50, 6000, 100, 8, noise=1.0)
    for _ in range(int(150 / SUB)):
        con.update(SUB, NoKeys())
    reel = Reel("storm", crop=MONITOR, colors=128)
    reel.shoot(con, st, 2.0, 6, "CALM - TWO CLEAN TRACES")
    w.ocean.front = 1.0
    reel.shoot(con, st, 3.0, 12, "A STORM ROLLS IN - RAIN DROWNS THE CONTACTS")
    p.z = p.ordered_depth = 15.0
    for _ in range(int(40 / SUB)):  # the sea builds with the wind
        con.update(SUB, NoKeys())
    con.toggle_scope()
    con.toggle_power()
    con.update(SUB, NoKeys())
    con.look()
    eye = pygame.Rect(0, 0, MONITOR.w, MONITOR.h)
    eye.center = EYEPIECE_C
    reel.shoot(con, st, 4.0, 1, "HEAVY SEA - WAVES BREAK OVER THE LENS", crop=eye)
    con.look()
    con.toggle_scope()
    w.ocean.front = 0.0
    w.ocean.rain = 0.0
    con.toggle_snorkel()
    reel.shoot(con, st, 3.0, 8, "SNORKEL - THE DIESELS DEAFEN THE SONAR")
    con.toggle_snorkel()
    reel.save()


def table():
    """The after-action replay of a convoy attack: an escort hunts back and a second boat waits under the layer."""
    seed(11)
    con = Console("COMMANDER", AUDIO)
    calm(con)
    w, p = con.world, con.world.player
    w.min_hull = 30.0
    p.z = p.ordered_depth = 60.0
    merchant = place(con, 38, 4300, 300, 9, noise=1.15)
    place(con, 75, 7800, 285, 11, noise=0.9)
    escort = place(con, 140, 3500, 0, 0, kind="ESCORT")
    w.ais.append(EscortAI(escort, p.heading + 320, charges=15, decoys=0, aggression=0.9, detect_radius=3000.0))
    sub = place(con, -70, 5000, 60, 6, kind="SUB", z=140.0)
    for _ in range(int(200 / SUB)):
        con.update(SUB, NoKeys())
    con.dial = fix(p, merchant).rel_brg
    con.mark()
    con.tdc.set("RNG", p.range_to(merchant) / YARD)
    con.tdc.set("SPD", merchant.speed / KNOT)
    con.tdc.set("CRS", merchant.heading)
    con.tdc.set("SPR", 3.0)
    fired = w.time
    con.fire()
    for _ in range(int(420 / SUB)):
        con.update(SUB, NoKeys())
    assert merchant in w.sunk, "the replay must show a sinking"
    r = Replay(con.recorder.data(dict(mode="COMMANDER", title="CONVOY ATTACK", result=f"{con.score:,} GRT SUNK")))
    sunk = r.bodies[merchant.uid]["sunk"]
    charges = [e["t"] for e in r.events if e["kind"] == "CHARGES"]
    assert charges, "the escort must come back for us"
    view = ReplayView(r, "TITLE")
    view.playing, cam = True, view.cam
    reel = Reel("table", crop=(0, 48, 1280, 576), width=768, colors=128)  # the table, not the replay's own HUD

    def beat(seconds, speed, caption, to=None, until=None, hover=False, ex=None):
        """Play `seconds` of GIF at `speed`, easing the camera to `to` (yaw, pitch, dist, target) and the depth
        exaggeration to `ex`."""
        start, ex0 = (cam.yaw, cam.pitch, cam.dist, list(cam.target)), view.tab.ex
        n = int(seconds * reel.fps)
        for i in range(n):
            if to:
                k = 0.5 - 0.5 * np.cos(np.pi * (i + 1) / n)
                cam.yaw = start[0] + ((to[0] - start[0] + 180) % 360 - 180) * k
                cam.pitch, cam.dist = start[1] + (to[1] - start[1]) * k, start[2] + (to[2] - start[2]) * k
                cam.target = [a + (b - a) * k for a, b in zip(start[3], to[3])]
                view.tab.ex = ex0 + ((ex or ex0) - ex0) * k
            view.speed = speed
            view.update(1 / reel.fps)
            if hover:  # the pointer rests on own boat: its hover label
                x, y, z, *_ = r.at(view.t)[view.own]
                sx, sy, _ = cam.project(x, y, view.tab.h(z))
                view.mouse = reel.cursor = (int(sx) + 3, int(sy) + 3)
            view.draw(screen)
            reel.grab(caption, speed)
            if until and view.t >= until:
                break
        reel.cursor, view.mouse = None, (0, 0)

    hit, boat, deep = r.at(sunk)[merchant.uid], r.at(charges[0])[view.own], r.at(charges[0])[sub.uid]
    side = float(np.degrees(np.arctan2(deep[0] - boat[0], deep[1] - boat[1]))) + 90  # square on to boat and sub
    yaw, pitch, dist, centre = cam.yaw, cam.pitch, cam.dist, list(cam.target)
    view.t = fired - 120
    beat(3.0, 40, "EVERY PATROL IS RECORDED - REPLAY IT ON THE PLOTTING TABLE", until=fired,
         to=(yaw + 20, pitch, dist, centre))
    beat(5.0, 40, "TWO FISH RUN OUT ON THE SOLUTION", until=sunk - 15,
         to=(yaw + 35, 38, dist * 0.32, [(boat[0] + hit[0]) / 2, (boat[1] + hit[1]) / 2]))
    beat(3.0, 6, "HIT - SHE SETTLES AND GOES DOWN", to=(yaw + 45, 32, dist * 0.18, hit[:2]))
    beat(2.5, 30, "THE ESCORT HUNTS BACK", until=charges[0] - 4, to=(yaw + 60, 30, dist * 0.2, boat[:2]))
    beat(3.0, 4, "DEPTH CHARGES OVER OWN BOAT", until=charges[0] + 12)
    beat(3.0, 4, "SIDE VIEW - DEPTH x5: A BOAT WAITS UNDER THE LAYER", ex=5,
         to=(side, 4, dist * 0.3, [(boat[0] + deep[0]) / 2, (boat[1] + deep[1]) / 2]))
    beat(2.0, 4, "HOVER FOR DEPTH, SPEED AND COURSE", hover=True)
    beat(2.5, 30, "PLAN VIEW - THE WHOLE ENGAGEMENT", to=(180, 89, dist * 0.8, centre))
    beat(1.5, 30, "PLAN VIEW - THE WHOLE ENGAGEMENT", to=(yaw, pitch, dist, centre), ex=10)
    reel.save()


SCENES = {"attack": attack, "tma": tma, "escort": escort, "wire": wire, "storm": storm, "table": table}

if __name__ == "__main__":
    settings.reset()
    for name in sys.argv[1:] or SCENES:
        SCENES[name]()
