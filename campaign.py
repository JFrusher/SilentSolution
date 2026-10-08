"""Campaign: six patrols with objectives and briefings, a debrief after each, ranks and refits, and a career
save with the patrol log and high scores (endless patrols included). Saved as JSON in the user's home folder."""
import copy
import datetime
import json
import random
from pathlib import Path

from console import Console
from settings import keyed
from tuning import DIFFICULTY

PATH = Path.home() / ".silent_solution" / "career.json"
RANKS = ("SUB-LIEUTENANT", "LIEUTENANT", "LIEUTENANT COMMANDER", "COMMANDER", "CAPTAIN", "COMMODORE", "REAR ADMIRAL")
PATROLS = (  # rules = difficulty preset; boost = how many waves' worth of escalation it starts with
    dict(name="SHAKEDOWN", rules="CADET", waves=2, boost=0, grt=6500, sink=None, storm=False,
         brief="WORK UP THE NEW BOAT ON A QUIET LANE. A SMALL CONVOY, ONE ESCORT. SINK ONE MERCHANT AND BRING "
               "HER HOME."),
    dict(name="CONVOY LANE", rules="COMMANDER", waves=2, boost=1, grt=13000, sink=None, storm=False,
         brief="CONVOYS ARE RUNNING THE LANE WITH A PROPER SCREEN. BATTERY IS REAL NOW: SNORKEL TO CHARGE. "
               "13,000 GRT."),
    dict(name="THE NARROWS", rules="COMMANDER", waves=3, boost=2, grt=19500, sink=None, storm=True,
         brief="WEATHER IS FOUL IN THE NARROWS. RAIN WILL DROWN WEAK CONTACTS; SO WILL IT DROWN YOU. 19,500 GRT."),
    dict(name="WOLF IN THE FOLD", rules="COMMANDER", waves=3, boost=3, grt=6500, sink="SUB", storm=False,
         brief="A HOSTILE BOAT IS SHADOWING OUR CONVOYS. FIND HER BY HER FAINT NARROW LINE AND SINK HER. "
               "ANY MERCHANTS ARE A BONUS."),
    dict(name="HEAVY SCREEN", rules="IRON CAPTAIN", waves=3, boost=4, grt=20000, sink=None, storm=False,
         brief="THE ENEMY HAS LEARNED. SHARP LOOKOUTS, HOMING FISH, OXYGEN TO WATCH. 20,000 GRT."),
    dict(name="LAST PATROL", rules="IRON CAPTAIN", waves=4, boost=5, grt=32500, sink="ESCORT", storm=True,
         brief="ONE MORE. THE BIG CONVOY, IN A GALE, WITH EVERYTHING THEY HAVE. 32,500 GRT AND AN ESCORT SUNK."),
)
UPGRADES = {  # refit -> what it does (applied in sail)
    "QUIET SCREWS": "SELF-NOISE -20%",
    "EXTRA RACKS": "+2 TORPEDO RELOADS",
    "MORE DECOYS": "+2 NOISEMAKERS",
    "FAST RELOAD": "TUBE RELOAD -30%",
    "SHARP EARS": "NARROWER HYDROPHONE BEAM",
    "THICK HULL": "DAMAGE TAKEN -25%",
}


def today():
    return datetime.date.today().isoformat()


class Career:
    def __init__(self, path=PATH):
        self.path = Path(path)
        self.patrol, self.upgrades, self.log, self.scores = 0, [], [], []
        self.note = ""  # career page prompt (new-career confirmation); not saved
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            self.patrol = min(int(saved["patrol"]), len(PATROLS))
            self.upgrades = [u for u in saved["upgrades"] if u in UPGRADES]
            self.log, self.scores = list(saved["log"]), list(saved["scores"])
        except (OSError, ValueError, KeyError, TypeError):
            pass  # no career yet, or an unreadable one: start fresh

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(dict(patrol=self.patrol, upgrades=self.upgrades, log=self.log,
                                                 scores=self.scores), indent=2), encoding="utf-8")
        except OSError:
            pass  # read-only home: the career lasts this run only

    def new(self):
        """A new commission: progress and refits go; the high-score table stays."""
        self.patrol, self.upgrades, self.log = 0, [], []
        self.save()

    @property
    def rank(self):
        return RANKS[self.patrol]

    @property
    def finished(self):
        return self.patrol >= len(PATROLS)

    def add_score(self, mode, grt, waves):
        self.scores.append(dict(mode=mode, grt=grt, waves=waves, rank=self.rank, date=today()))
        self.scores = sorted(self.scores, key=lambda s: -s["grt"])[:10]
        self.save()

    def offer(self):
        """Two refits not yet fitted, for the debrief."""
        spare = [u for u in UPGRADES if u not in self.upgrades]
        return random.sample(spare, min(2, len(spare)))

    def record(self, run, con):
        """File the patrol: log, high score, and promotion on success. Returns the debrief."""
        p = run.patrol
        grt, sunk = con.score, [s.kind for s in con.world.sunk]
        self.log.append(dict(patrol=p["name"], result=run.result, grt=grt, date=today()))
        self.log = self.log[-20:]
        promoted = run.result == "SUCCESS"
        if promoted:
            self.patrol += 1
        self.add_score(f"P{PATROLS.index(p) + 1} {p['name']}", grt, con.wave)  # also saves
        return dict(patrol=p, result=run.result, grt=grt, sunk=sunk, hull=con.world.hull, time=con.world.time,
                    promoted=self.rank if promoted else None,
                    offer=self.offer() if promoted and not self.finished else [])

    def fit(self, upgrade):
        if upgrade in UPGRADES and upgrade not in self.upgrades:
            self.upgrades.append(upgrade)
            self.save()


class PatrolRun:
    """Watches a campaign patrol for its end: boat lost, objectives met and ENTER (return to base),
    or the last wave cleared."""

    def __init__(self, patrol):
        self.patrol, self.result, self.announced = patrol, None, False

    def met(self, con):
        p = self.patrol
        return con.score >= p["grt"] and (p["sink"] is None or any(s.kind == p["sink"] for s in con.world.sunk))

    def update(self, con):
        if con.dead:
            self.result = "LOST"
        elif self.met(con):
            if not self.announced:
                self.announced = True
                con.teletype.print(keyed("FROM FLAG OFFICER SUBMARINES: OBJECTIVES MET. RETURN TO BASE WHEN READY "
                                         "({ACKNOWLEDGE}), OR STAY AND HUNT."))
            if "ENTER" in con.actions or con.world.director.done:
                self.result = "SUCCESS"
        elif con.world.director.done:
            self.result = "FAILED"
        con.actions.discard("ENTER")
        return self.result


def objective(p):
    goal = f"{p['grt']:,} GRT"
    return goal + (f" AND A{'N' if p['sink'] == 'ESCORT' else ''} {p['sink']} SUNK" if p["sink"] else "")


def sail(career, audio):
    """Commission the boat for the career's next patrol: rules, refits, weather, briefing."""
    p = PATROLS[career.patrol]
    diff = copy.deepcopy(DIFFICULTY[p["rules"]])
    fitted = set(career.upgrades)
    if "FAST RELOAD" in fitted:
        diff["reload"] *= 0.7
    if "SHARP EARS" in fitted:
        diff["beam_width"] *= 0.6
    con = Console(p["rules"], audio, diff)
    w = con.world
    w.director.boost, w.director.waves = p["boost"], p["waves"]
    sub = w.player
    sub.quiet = 0.8 if "QUIET SCREWS" in fitted else 1.0
    sub.torpedoes += 2 * ("EXTRA RACKS" in fitted)
    sub.noisemakers += 2 * ("MORE DECOYS" in fitted)
    w.armour = 0.75 if "THICK HULL" in fitted else 1.0
    if p["storm"]:
        w.ocean.rain = w.ocean.front = 0.8
        w.ocean.wind = 12.0
    con.teletype.print(f"FROM FLAG OFFICER SUBMARINES TO {career.rank}: PATROL {career.patrol + 1} - {p['name']}. "
                       f"{p['brief']} OBJECTIVE: {objective(p)} IN {p['waves']} WAVES.")
    return con, PatrolRun(p)


if __name__ == "__main__":  # self-check: save round trip, ranks, objectives, refits, patrol outcomes
    import os
    import tempfile
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    import pygame
    from audio import AudioSynthesizer
    from sim import Vessel
    pygame.init()
    tmp = Path(tempfile.mkdtemp()) / "career.json"
    car = Career(tmp)
    assert car.rank == "SUB-LIEUTENANT" and not car.finished
    car.fit("THICK HULL")
    car.fit("QUIET SCREWS")
    con, run = sail(car, AudioSynthesizer())
    assert con.world.armour == 0.75 and con.world.player.quiet == 0.8 and con.world.director.waves == 2
    assert run.update(con) is None
    con.world.sunk.append(Vessel(0, 0, 0, 0))  # one merchant: 6,500 GRT meets SHAKEDOWN
    assert run.update(con) is None and run.announced  # met, but still out hunting
    con.actions.add("ENTER")
    assert run.update(con) == "SUCCESS"
    debrief = car.record(run, con)
    assert debrief["promoted"] == "LIEUTENANT" and len(debrief["offer"]) == 2
    assert not set(debrief["offer"]) & {"THICK HULL", "QUIET SCREWS"}
    again = Career(tmp)
    assert again.patrol == 1 and again.upgrades == ["THICK HULL", "QUIET SCREWS"] and again.log[0]["result"] == "SUCCESS"
    con, run = sail(again, AudioSynthesizer())
    con.world.director.done = True
    assert run.update(con) == "FAILED" and again.record(run, con)["promoted"] is None and again.patrol == 1
    for g in (500, 90000, 20):
        again.add_score("COMMANDER", g, 3)
    assert [s["grt"] for s in Career(tmp).scores][:2] == [90000, 6500]
    tmp.write_text("{broken")
    assert Career(tmp).patrol == 0
    print("campaign ok")
