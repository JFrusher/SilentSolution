"""Golden run: one seeded, scripted patrol through the real console must play out exactly the same every time.
Run: uv run checks.py, or with PYTHONPATH=src: uv run tests/test_golden.py [--update]
--update regenerates golden/<platform>.json after a change that is meant to alter play; commit the new file.
Float maths can differ in the last bit between platforms, so each platform keeps its own file."""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

import settings  # noqa: E402
import sim  # noqa: E402
from audio import AudioSynthesizer  # noqa: E402
from console import Console  # noqa: E402

SEED = 1
STEP = 1 / 60  # main.SIM_DT
STEPS = 4 * 60 * 60  # four minutes of patrol
SCRIPT = {60: "DEEPER", 120: "DEEPER", 600: "FASTER", 1200: "PING", 1800: "MARK", 2400: "FIRE", 2410: "FIRE",
          3000: "NOISEMAKER", 3600: "RUDDER AMIDSHIPS", 4000: "SLOWER", 5000: "PERISCOPE DEPTH", 9000: "RAISE SCOPE",
          9100: "LOOK", 9200: "MARK", 9300: "LOOK", 9400: "AUTO-SOLVE", 11000: "RAISE SNORKEL", 13000: "DEEPER"}
GOLDEN = Path(__file__).parent / "golden" / f"{sys.platform}.json"


class NoKeys(dict):
    def __getitem__(self, k):
        return 0


def patrol(audio):
    """The digest of one scripted patrol: every world event, every log line, and where it all ended up."""
    con = Console("COMMANDER", audio, seed=SEED)
    events, keys = [], NoKeys()
    for step in range(STEPS):
        if step in SCRIPT:
            con.key(settings.code(SCRIPT[step]))
        con.update(STEP, keys)
        events += [[step, kind, getattr(a, "uid", None)] for kind, a, _ in con.frame_events]
    w, p = con.world, con.world.player
    end = dict(x=round(p.x, 3), y=round(p.y, 3), z=round(p.z, 3), heading=round(p.heading, 3), hull=round(w.hull, 3),
               score=con.score, wave=con.wave, targets=len(w.targets), torpedoes=len(w.torpedoes),
               dial=round(con.dial_true, 3), dice=sim.DICE.random())
    return dict(events=events, log=list(con.log), teletype=list(con.teletype.lines), end=end)


if __name__ == "__main__":
    pygame.init()
    audio = AudioSynthesizer()
    first, second = patrol(audio), patrol(audio)
    assert first == second, "the same seed played out differently in one process: something rolls outside sim.DICE"
    if "--update" in sys.argv:
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(first, indent=1))
        print(f"wrote {GOLDEN}")
        sys.exit(0)
    assert GOLDEN.exists(), f"no golden file for {sys.platform}: run test_golden.py --update and commit it"
    golden = json.loads(GOLDEN.read_text())
    for part in ("end", "events", "log", "teletype"):
        assert first[part] == golden[part], f"{part} differs from {GOLDEN.name}:\n{first[part]}\n!=\n{golden[part]}"
    print(f"golden run matches {GOLDEN.name}: {len(first['events'])} events")
