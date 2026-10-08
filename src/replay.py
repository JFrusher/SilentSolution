"""After-action recording: the world's truth, sampled through a patrol and saved for the tabletop replay.
World side and read-only: it reads positions and events, and never changes the simulation."""
import datetime
import gzip
import json
from pathlib import Path

import numpy as np

from geometry import angle_diff
from sim import silhouette_class

SAMPLE = 1.0     # s of sim time between samples
KEEP = 10        # replays kept on disk
DIR = Path.home() / ".silent_solution" / "replays"
VERSION = 1
EVENTS = ("HIT", "PLAYER_HIT", "CHARGES", "CHARGE", "DECOY_DROP", "DECOYED", "EXHAUSTED", "WIRE_CUT", "DAMAGE",
          "HOSTILE_LAUNCH", "WAVE", "WAVE_CLEAR", "ESCORT_PING")


def describe(v, t):
    """A body's static description, kept once."""
    surface = v.kind in ("MERCHANT", "ESCORT")
    return dict(kind=v.kind, cls=silhouette_class(v) if surface else v.kind.lower(), born=round(t, 1),
                hostile=bool(getattr(v, "hostile", False)), tube=int(getattr(v, "tube", 0) or 0),
                owner=getattr(v, "owner", None), sunk=None)


class Recorder:
    def __init__(self):
        self.bodies, self.tracks, self.events = {}, {}, []
        self.next_t = 0.0
        self.layer = None

    def sample(self, world, events=()):
        t = world.time
        self.layer = world.ocean.layer_depth
        for kind, a, b in events:
            if kind in EVENTS:
                self._event(t, kind, a, b)
        if t < self.next_t:
            return
        self.next_t = t + SAMPLE
        for v in (world.player, *world.targets, *world.torpedoes, *world.charges):
            self._sample(v, t)

    def _sample(self, v, t):
        if v.uid not in self.bodies:
            self.bodies[v.uid], self.tracks[v.uid] = describe(v, t), []
        self.tracks[v.uid].append((round(t, 1), round(v.x, 1), round(v.y, 1), round(v.z, 1), round(v.heading, 1),
                                   round(v.speed, 2)))

    def _event(self, t, kind, a, b):
        uid = getattr(a, "uid", None)
        row = dict(t=round(t, 1), kind=kind, uid=uid)
        if hasattr(a, "x"):
            row.update(x=round(a.x, 1), y=round(a.y, 1), z=round(a.z, 1))
            self._sample(a, t)  # the moment itself is on the track, not just the nearest second
        if kind == "HIT" and hasattr(b, "uid"):  # b went down here
            row["target"] = b.uid
            self._sample(b, t)
            self.bodies[b.uid]["sunk"] = round(t, 1)
        if kind == "PLAYER_HIT" or (kind == "CHARGE" and isinstance(b, (int, float))):
            row["damage"] = round(float(b), 1)
        if kind == "DAMAGE":
            row["systems"] = list(b)
        self.events.append(row)

    def data(self, meta):
        return dict(version=VERSION, meta=dict(meta, layer=self.layer), events=self.events,
                    bodies={str(k): v for k, v in self.bodies.items()},
                    tracks={str(k): [list(col) for col in zip(*rows)] for k, rows in self.tracks.items() if rows})


def save(recorder, meta, folder=None):
    """Write the replay and keep only the newest KEEP. Returns the path, or None if nothing was recorded."""
    if not recorder.tracks:
        return None
    folder = Path(folder or DIR)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = folder / f"{stamp}-{meta.get('mode', 'patrol').lower().replace(' ', '-')}.json.gz"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(recorder.data(meta), f, separators=(",", ":"))
        for old in sorted(folder.glob("*.json.gz"))[:-KEEP]:
            old.unlink()
    except OSError:
        return None  # a read-only home: the replay is lost, the game carries on
    return path


def listing(folder=None):
    """Saved replays, newest first: [(path, meta or None if unreadable)]."""
    out = []
    for path in sorted(Path(folder or DIR).glob("*.json.gz"), reverse=True):
        r = load(path)
        out.append((path, r.meta if r else None))
    return out


class Replay:
    """A loaded replay: interpolated truth at any time."""

    def __init__(self, data):
        self.meta, self.events = data["meta"], data["events"]
        self.bodies = {int(k): v for k, v in data["bodies"].items()}
        self.tracks = {int(k): np.array(cols, float).T for k, cols in data["tracks"].items()}  # (n, 6)
        self.start = min(tr[0, 0] for tr in self.tracks.values())
        self.end = max(tr[-1, 0] for tr in self.tracks.values())

    def at(self, t):
        """{uid: (x, y, z, heading, speed)} for every body alive at time t (a sunk ship holds its last place)."""
        out = {}
        for uid, tr in self.tracks.items():
            sunk = self.bodies[uid].get("sunk")
            last = sunk if sunk is not None else tr[-1, 0]
            if t < tr[0, 0] or t > last + (240.0 if sunk is not None else SAMPLE):
                continue
            tt = min(t, tr[-1, 0])
            i = int(np.searchsorted(tr[:, 0], tt))
            if i == 0 or tr[i if i < len(tr) else -1, 0] == tt:
                row = tr[min(i, len(tr) - 1)]
                out[uid] = tuple(row[1:])
                continue
            a, b = tr[i - 1], tr[min(i, len(tr) - 1)]
            f = (tt - a[0]) / max(b[0] - a[0], 1e-9)
            heading = (a[4] + angle_diff(b[4], a[4]) * f) % 360  # by the short way round
            out[uid] = (*(a[1:4] + (b[1:4] - a[1:4]) * f), heading, a[5] + (b[5] - a[5]) * f)
        return out

    def path(self, uid, t=None):
        """The track up to time t as an (n, 3) array of x, y, z."""
        tr = self.tracks[uid]
        if t is not None:
            tr = tr[tr[:, 0] <= t]
        return tr[:, 1:4]


def load(path):
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("version") != VERSION or not data.get("tracks"):
            return None
        return Replay(data)
    except (OSError, ValueError, KeyError, TypeError):
        return None


if __name__ == "__main__":  # self-check: round trip, interpolation, retention, junk files, read-only recording
    import os
    import tempfile
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    import sim
    from sim import KNOT, Submarine, Vessel, WorldSimulation
    folder = Path(tempfile.mkdtemp())

    def world():
        sim.seed(4)
        return WorldSimulation(Submarine(0, 0, 0, 5 * KNOT, z=60), [Vessel(2000, 0, 270, 8 * KNOT)])
    w, rec = world(), Recorder()
    for _ in range(600):
        rec.sample(w, w.step(0.1))
    path = save(rec, dict(mode="CADET", result="TEST"), folder)
    r = load(path)
    ship = r.at(30.0)[w.targets[0].uid]
    assert abs(ship[0] - (2000 - 8 * KNOT * 30.0)) < 0.5 and abs(ship[1]) < 0.5, ship  # interpolated, 1 s samples
    assert abs(r.at(30.4)[w.player.uid][1] - 5 * KNOT * 30.4) < 0.5
    w2 = world()  # recording must not change the world: the same seed runs identically without it
    for _ in range(600):
        w2.step(0.1)
    assert (w.targets[0].x, w.player.y) == (w2.targets[0].x, w2.player.y)
    for k in range(KEEP + 3):
        (folder / f"20000101-0000{k:02d}-old.json.gz").write_bytes(b"not a gzip")
    save(rec, dict(mode="CADET"), folder)
    files = listing(folder)
    assert len(files) == KEEP and files[0][1]["mode"] == "CADET" and files[-1][1] is None  # junk listed, unreadable
    print("replay ok")
