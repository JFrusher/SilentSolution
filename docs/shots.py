"""Regenerate the README images from live, headless game states.
Run: uv run --with pillow docs/shots.py   ->  docs/images/*.png and *.gif"""
import math
import os
import random
import sys
import tempfile
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pygame  # noqa: E402

pygame.init()
screen = pygame.display.set_mode((1280, 720))

import campaign  # noqa: E402
import settings  # noqa: E402
from audio import AudioSynthesizer  # noqa: E402
from console import Console  # noqa: E402
from sim import KNOT, YARD, Vessel, bearing  # noqa: E402
from workstation import Workstation  # noqa: E402

OUT = ROOT / "docs" / "images"
OUT.mkdir(parents=True, exist_ok=True)
DT = 1 / 30
AUDIO = AudioSynthesizer()


class NoKeys:
    def __getitem__(self, k):
        return 0


def rel(con, ship):
    p = con.world.player
    return (bearing(p.x, p.y, ship.x, ship.y) - p.heading) % 360


def run(con, seconds, station=None, state="PLAY", track=None):
    """Step the console; draw the last second so the phosphor settles. `track`: an operator holding the dial on
    a ship, with a hand's worth of wobble."""
    n = int(seconds / DT)
    for i in range(n):
        if track is not None and track in con.world.targets:
            con.dial = rel(con, track) + random.gauss(0, 0.7)
        con.update(DT, NoKeys())
        if station and i >= n - 30:
            station.draw(screen, con, state, False, False, DT)


def save(name):
    pygame.image.save(screen, str(OUT / f"{name}.png"))
    print("wrote", name)


def place(con, rel_brg, rng, course, kt, kind="MERCHANT", **kw):
    p = con.world.player
    b = math.radians(p.heading + rel_brg)
    ship = Vessel(p.x + rng * math.sin(b), p.y + rng * math.cos(b), course % 360, kt * KNOT, **kw)
    ship.kind = kind
    con.world.targets.append(ship)
    return ship


def quiet_sea(con, rain=0.0):
    o = con.world.ocean
    o.rain = o.front = rain
    o.timer, o.wind = 1e9, 3 + 11 * rain


def hero():
    """The station mid-attack: a convoy on the waterfall, the dial locked on, a wired spread running."""
    random.seed(7)
    st, con = Workstation(), Console("COMMANDER", AUDIO)
    quiet_sea(con)
    run(con, 10)
    merchants = [t for t in con.world.targets if t.kind == "MERCHANT"]
    target = min(merchants, key=con.world.player.range_to)
    con.waterfall.row_interval = 3.0  # F8's slow scale: ten minutes of history shows the bearing drift
    run(con, 600, track=target)
    con.mark()
    con.ping()
    run(con, 14, track=target)
    p = con.world.player
    con.tdc.set("RNG", p.range_to(target) / YARD)
    con.tdc.set("SPD", target.speed / KNOT)
    con.tdc.set("CRS", target.heading)
    con.tdc.set("SPR", 4.0)
    con.fire()
    if con.wire_sel is None:  # a long shot asks for a second press
        con.fire()
    con.wire_sel.wire_aim = (target.x, target.y)
    run(con, 40, st, track=target)
    save("station")
    return st, con


def anatomy(st, con):
    """The hero frame with numbered callouts for the README legend."""
    st.draw(screen, con, "PLAY", False, False, DT)
    font = pygame.font.SysFont("arial", 17, bold=True)
    spots = [(26, 24), (26, 280), (288, 160), (897, 130), (288, 350), (897, 350), (936, 24), (1256, 394),
             (28, 500), (246, 500), (522, 497), (777, 612), (897, 487)]
    for i, (x, y) in enumerate(spots, 1):
        pygame.draw.circle(screen, (20, 18, 14), (x, y), 15)
        pygame.draw.circle(screen, (255, 190, 86), (x, y), 13)
        label = font.render(str(i), True, (20, 18, 14))
        screen.blit(label, label.get_rect(center=(x, y + 1)))
    save("anatomy")


def periscope_scene():
    random.seed(3)
    con = Console("CADET", AUDIO)
    con.world.director = None
    quiet_sea(con)
    p = con.world.player
    p.z = p.ordered_depth = 15.0
    p.speed = p.ordered_speed = 2 * KNOT
    place(con, 18, 2300, p.heading + 110, 8, noise=1.1)
    place(con, 31, 3600, p.heading + 110, 8, noise=1.0)
    place(con, 6, 4700, p.heading + 110, 8, noise=1.0)
    place(con, -8, 3300, p.heading + 120, 14, kind="ESCORT")
    con.update(DT, NoKeys())
    con.toggle_scope()
    run(con, 3)
    con.look()
    return con


def periscope():
    st, con = Workstation(), periscope_scene()
    con.scope_brg = 18.0
    run(con, 2, st)
    save("periscope")
    con.toggle_power()
    con.scope_brg = 18.5
    run(con, 2, st)
    save("periscope_high")


def periscope_gif():
    """High power on the nearest merchant: the hit, the blast column, then her going down by the stern."""
    from PIL import Image
    st, con = Workstation(), periscope_scene()
    con.toggle_power()
    w = con.world
    ship = min(w.targets, key=w.player.range_to)
    frames = []
    for i in range(78):
        if i == 14:  # the fish arrives
            w.targets.remove(ship)
            ship.sunk_at = w.time
            w.sunk.append(ship)
            w.explosion(ship.x, ship.y, True, object())
        con.scope_brg = rel(con, ship)
        for _ in range(3 if i < 48 else 90):  # real time for the blast, then hurry the sinking
            con.update(DT, NoKeys())
        st.draw(screen, con, "PLAY", False, False, DT)
        img = Image.frombytes("RGB", (1280, 720), pygame.image.tobytes(screen, "RGB"))
        frames.append(img.crop((200, 60, 1080, 620)).resize((660, 420), Image.LANCZOS)
                      .quantize(colors=128, method=Image.Quantize.MEDIANCUT))
    frames[0].save(OUT / "periscope_hit.gif", save_all=True, append_images=frames[1:], duration=100, loop=0,
                   optimize=True)
    print("wrote periscope_hit.gif")


def tma():
    """Two legs of bearings on a crossing merchant, a ping for range, then auto-solve."""
    random.seed(5)
    st, con = Workstation(), Console("CADET", AUDIO)
    con.world.director = None
    quiet_sea(con)
    p = con.world.player
    target = place(con, 50, 6500, 210, 9, noise=1.2)
    run(con, 150, track=target)
    p.rudder = -30.0
    while abs(((p.heading - 300) + 180) % 360 - 180) > 3:
        run(con, 1, track=target)
    p.rudder = 0.0
    run(con, 150, track=target)
    con.ping()
    run(con, 12, track=target)
    con.auto_solve()
    con.flip_page()
    run(con, 3, st, track=target)
    save("tma")


def damage():
    random.seed(2)
    st, con = Workstation(), Console("IRON CAPTAIN", AUDIO)
    quiet_sea(con)
    run(con, 4)
    p = con.world.player
    p.break_systems(["PLANES", "HYDROPHONES", "TUBE 2", "BATTERY", "ACTIVE SONAR"])
    p.repair_first("PLANES")
    p.leaks = [35.0, 50.0]
    con.world.hull = 58.0
    con.teletype.print("DAMAGE CONTROL: PLANES, HYDROPHONES, TUBE 2, BATTERY, ACTIVE SONAR DAMAGED. ONE PARTY "
                       "WORKS THE LIST TOP FIRST - F5 TO SET IT.")
    con.teletype.print("DAMAGE CONTROL: FLOODING. 2 LEAK(S). PUMPS ON.")
    con.damage_board()
    run(con, 30, st)
    save("damage")


def pages():
    st = Workstation()
    for _ in range(40):
        st.draw(screen, None, "TITLE", False, False, DT)
    save("title")
    st.menu = settings.SettingsMenu()
    for k in (pygame.K_DOWN,) * 4:
        st.menu.key(k)
    for _ in range(40):
        st.draw(screen, None, "SETTINGS", False, False, DT)
    save("settings")
    car = campaign.Career(Path(tempfile.mkdtemp()) / "career.json")
    car.add_score("COMMANDER", 45500, 6)
    car.add_score("IRON CAPTAIN", 8100, 2)
    con, patrol = campaign.sail(car, AUDIO)
    escort = Vessel(0, 0, 0, 0)
    escort.kind = "ESCORT"
    con.world.sunk += [Vessel(0, 0, 0, 0), Vessel(0, 0, 0, 0), escort]
    con.world.time, con.world.hull = 1834.0, 62.0
    con.actions.add("ENTER")
    patrol.update(con)
    random.seed(1)
    st.debrief = car.record(patrol, con)
    for _ in range(40):
        st.draw(screen, None, "DEBRIEF", False, False, DT)
    save("debrief")
    car.fit(st.debrief["offer"][0])
    st.career = car
    for _ in range(40):
        st.draw(screen, None, "CAREER", False, False, DT)
    save("career")


if __name__ == "__main__":
    settings.reset()
    station, console = hero()
    anatomy(station, console)
    periscope()
    tma()
    damage()
    pages()
    periscope_gif()
