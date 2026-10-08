"""Player settings: volumes by category, key bindings, mouse feel, large text, colour-blind lamps.
Saved as JSON in the user's home folder; a missing or broken file just means defaults."""
import copy
import json
import re
from pathlib import Path

import pygame

PATH = Path.home() / ".silent_solution" / "settings.json"
KEYS = {  # action -> pygame key name
    "PING": "space", "FIRE": "f", "FIRE TUBE 1": "1", "FIRE TUBE 2": "2",
    "TDC ROW UP": "w", "TDC ROW DOWN": "s", "TDC VALUE UP": "up", "TDC VALUE DOWN": "down",
    "AUTO-SOLVE": "f4", "MARK": "m", "TRAIN LEFT": "a", "TRAIN RIGHT": "d",
    "RAISE SCOPE": "u", "RAISE SNORKEL": "k", "PERISCOPE DEPTH": "g", "LOOK": "v", "SCOPE POWER": "tab",
    "SHALLOWER": "q", "DEEPER": "e", "HOLD DEPTH": "h", "BLOW": "b",
    "SLOWER": "z", "FASTER": "x", "RUDDER LEFT": "left", "RUDDER RIGHT": "right", "RUDDER AMIDSHIPS": "c",
    "NOISEMAKER": "n", "SCOPE RANGE": "t", "WIRE LEFT": "[", "WIRE RIGHT": "]", "NEXT FISH": "\\", "CUT WIRE": "l",
    "TMA PAGE": "f2", "DAMAGE BOARD": "f5", "DEBUG": "f3", "ACKNOWLEDGE": "return", "SKIP DRILL": "f6",
    "BEARING MODE": "f7", "WATERFALL SCALE": "f8", "SCOPE TO SONAR": "o", "STAND UP": "r",
}
RESERVED = ("escape", "f1", "p")  # quit / back, help card, pause
DEFAULTS = dict(volume=dict(MASTER=0.8, SONAR=1.0, EFFECTS=1.0, AMBIENCE=1.0), mouse=1.0, large_text=False,
                colorblind=False, sound_captions=True, caption_scale=1.0, true_bearings=True, trained=False,
                keys=KEYS)
SETTINGS = copy.deepcopy(DEFAULTS)
CAPTION_SIZES = {1.0: "SMALL", 1.3: "LARGE", 1.7: "HUGE"}  # caption_scale -> its name


def reset():
    SETTINGS.clear()
    SETTINGS.update(copy.deepcopy(DEFAULTS))


def load(path=PATH):
    reset()
    try:
        saved = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(saved, dict):
        return
    for name, value in saved.items():
        cur = SETTINGS.get(name)
        if isinstance(cur, dict) and isinstance(value, dict):
            for k, v in value.items():
                if k in cur and isinstance(v, type(cur[k])) and (name != "keys" or _valid(v)):
                    cur[k] = v
        elif isinstance(cur, bool):
            SETTINGS[name] = value if isinstance(value, bool) else cur
        elif isinstance(cur, float) and isinstance(value, (int, float)):
            SETTINGS[name] = float(value)
    if SETTINGS["caption_scale"] not in CAPTION_SIZES:  # a hand-edited file: only the sizes on offer
        SETTINGS["caption_scale"] = DEFAULTS["caption_scale"]


def save(path=PATH):
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(SETTINGS, indent=2), encoding="utf-8")
    except OSError:
        pass  # read-only home: settings last for this run only


def _valid(name):
    try:
        pygame.key.key_code(name)
        return name not in RESERVED
    except ValueError:
        return False


def code(action):
    try:
        return pygame.key.key_code(SETTINGS["keys"][action])
    except ValueError:  # a name SDL can't resolve: fall back rather than crash the frame
        return pygame.key.key_code(KEYS[action])


def action_for(k):
    if k == pygame.K_KP_ENTER:
        return "ACKNOWLEDGE"
    name = pygame.key.name(k)
    return next((a for a, n in SETTINGS["keys"].items() if n == name), None)


def volume(category):
    v = SETTINGS["volume"]
    return v["MASTER"] * v[category]


SHOWN = {"return": "ENTER", "space": "SPACE"}  # key names as the station prints them
TOKEN = re.compile(r"\{([A-Z0-9 -]+)\}")


def label(*actions):
    """Display name of the key(s) bound to these actions: label("SLOWER", "FASTER") -> "Z / X"."""
    return " / ".join(SHOWN.get(n, n.upper()) for n in (SETTINGS["keys"][a] for a in actions))


def keyed(text):
    """Fill {ACTION} tokens with the bound key: "PRESS {MARK}" -> "PRESS M"."""
    return TOKEN.sub(lambda m: label(m.group(1)) if m.group(1) in KEYS else m.group(0), text)


def bind(action, k):
    """Put `action` on key k; whatever had k takes this action's old key. Returns an error or None."""
    name = pygame.key.name(k)
    if name in RESERVED:
        return f"{name.upper()} IS RESERVED"
    if not _valid(name):  # media / OEM keys SDL can't name
        return "KEY CAN'T BE BOUND"
    keys = SETTINGS["keys"]
    other = next((a for a, n in keys.items() if n == name), None)
    if other:
        keys[other] = keys[action]
    keys[action] = name
    return None


ROW_Y0, ROW_H, VISIBLE = 62, 19, 15  # menu rows on the CRT
BAR_X, BAR_W = 300, 200              # value bars, CRT-local x


class SettingsMenu:
    """The settings page on the monitor. UP/DOWN pick a line, LEFT/RIGHT change it, ENTER toggles or rebinds."""

    def __init__(self):
        self.rows = [*(("VOLUME", c) for c in DEFAULTS["volume"]), ("MOUSE", None), ("LARGE TEXT", None),
                     ("COLOUR-BLIND LAMPS", None), ("SOUND CAPTIONS", None), ("CAPTION SIZE", None),
                     ("TRUE BEARINGS", None),
                     *(("KEY", a) for a in KEYS),
                     ("RESET DEFAULTS", None),
                     ("BACK", None)]
        self.sel = self.top = 0
        self.waiting = False
        self.note = ""

    def label(self, row):
        """(name, bar fill 0..1 or None, value text) for one line."""
        kind, arg = row
        if kind == "VOLUME":
            v = SETTINGS["volume"][arg]
            return f"{arg} VOLUME", v, f"{v:.0%}"
        if kind == "MOUSE":
            m = SETTINGS["mouse"]
            return "MOUSE SENSITIVITY", (m - 0.25) / 2.75, f"x{m:.2f}"
        if kind == "LARGE TEXT":
            return kind, None, "ON" if SETTINGS["large_text"] else "OFF"
        if kind == "COLOUR-BLIND LAMPS":
            return kind, None, "ON" if SETTINGS["colorblind"] else "OFF"
        if kind == "CAPTION SIZE":
            return kind, None, CAPTION_SIZES[SETTINGS["caption_scale"]]
        if kind == "SOUND CAPTIONS":
            return kind, None, "ON" if SETTINGS["sound_captions"] else "OFF"
        if kind == "TRUE BEARINGS":
            return kind, None, "ON (NORTH-STABILISED)" if SETTINGS["true_bearings"] else "OFF (SHIP'S HEAD)"
        if kind == "KEY":
            waiting = self.waiting and row == self.rows[self.sel]
            return arg, None, "PRESS A KEY..." if waiting else SETTINGS["keys"][arg].upper()
        return kind, None, ""

    def _adjust(self, d):
        kind, arg = self.rows[self.sel]
        if kind == "VOLUME":
            SETTINGS["volume"][arg] = round(min(1.0, max(0.0, SETTINGS["volume"][arg] + 0.1 * d)), 2)
        elif kind == "MOUSE":
            SETTINGS["mouse"] = min(3.0, max(0.25, SETTINGS["mouse"] + 0.25 * d))
        elif kind == "LARGE TEXT":
            SETTINGS["large_text"] = not SETTINGS["large_text"]
        elif kind == "COLOUR-BLIND LAMPS":
            SETTINGS["colorblind"] = not SETTINGS["colorblind"]
        elif kind == "CAPTION SIZE":
            sizes = list(CAPTION_SIZES)
            SETTINGS["caption_scale"] = sizes[(sizes.index(SETTINGS["caption_scale"]) + d) % len(sizes)]
        elif kind == "SOUND CAPTIONS":
            SETTINGS["sound_captions"] = not SETTINGS["sound_captions"]
        elif kind == "TRUE BEARINGS":
            SETTINGS["true_bearings"] = not SETTINGS["true_bearings"]

    def _select(self, i):
        self.sel = i % len(self.rows)
        self.top = min(max(self.top, self.sel - VISIBLE + 1), self.sel)

    def _activate(self):
        kind, _ = self.rows[self.sel]
        if kind == "KEY":
            self.waiting, self.note = True, "PRESS THE NEW KEY - ESC CANCELS"
        elif kind == "RESET DEFAULTS":
            trained = SETTINGS["trained"]  # progress, not a preference: restoring defaults keeps it
            reset()
            SETTINGS["trained"] = trained
            self.note = "DEFAULTS RESTORED"
        elif kind == "BACK":
            save()
            return "BACK"
        else:
            self._adjust(1)
        return None

    def key(self, k):
        """Returns "BACK" when the player leaves (settings saved)."""
        self.note = ""
        if self.waiting:
            self.waiting = False
            if k != pygame.K_ESCAPE:
                self.note = bind(self.rows[self.sel][1], k) or "BOUND"
            return None
        if k == pygame.K_ESCAPE:
            save()
            return "BACK"
        if k in (pygame.K_UP, pygame.K_DOWN):
            self._select(self.sel + (1 if k == pygame.K_DOWN else -1))
        elif k in (pygame.K_LEFT, pygame.K_RIGHT):
            self._adjust(1 if k == pygame.K_RIGHT else -1)
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
            return self._activate()
        return None

    def click(self, x, y):
        """CRT-local click: pick a line; on a bar, set the value where clicked; else act on it."""
        i = self.top + (y - ROW_Y0) // ROW_H
        if not (0 <= y - ROW_Y0 < VISIBLE * ROW_H and 0 <= i < len(self.rows)):
            return None
        self._select(i)
        kind, arg = self.rows[i]
        frac = min(1.0, max(0.0, (x - BAR_X) / BAR_W))
        if kind == "VOLUME" and x >= BAR_X - 10:
            SETTINGS["volume"][arg] = round(frac, 1)
        elif kind == "MOUSE" and x >= BAR_X - 10:
            SETTINGS["mouse"] = round((0.25 + 2.75 * frac) * 4) / 4
        elif kind not in ("VOLUME", "MOUSE"):
            return self._activate()
        return None

    def scroll(self, dy):
        self.top = min(max(0, self.top - dy), len(self.rows) - VISIBLE)


if __name__ == "__main__":  # self-check: load/save round trip, rebinding swaps, junk files fall back to defaults
    import tempfile
    pygame.init()
    assert all(_valid(n) and pygame.key.name(pygame.key.key_code(n)) == n for n in KEYS.values())
    tmp = Path(tempfile.mkdtemp()) / "s.json"
    tmp.write_text('{"volume": {"MASTER": 0.3, "BOGUS": 1}, "mouse": 2, "keys": {"FIRE": "no such key"}}')
    load(tmp)
    assert SETTINGS["volume"]["MASTER"] == 0.3 and SETTINGS["mouse"] == 2.0 and SETTINGS["keys"]["FIRE"] == "f"
    assert bind("FIRE", pygame.K_SPACE) is None and SETTINGS["keys"]["PING"] == "f"
    assert action_for(pygame.K_SPACE) == "FIRE" and bind("FIRE", pygame.K_p)
    assert bind("TRAIN LEFT", 0) and SETTINGS["keys"]["TRAIN LEFT"] == "a"  # an unnamed key is refused
    SETTINGS["keys"]["TRAIN LEFT"] = ""
    assert code("TRAIN LEFT") == pygame.K_a  # and a bad stored name never raises
    SETTINGS["keys"]["TRAIN LEFT"] = "a"
    save(tmp)
    load(tmp)
    assert SETTINGS["keys"]["FIRE"] == "space"
    assert keyed("PRESS {FIRE}, THEN {SLOWER} - {NOT AN ACTION}") == "PRESS SPACE, THEN Z - {NOT AN ACTION}"
    assert label("ACKNOWLEDGE", "PING") == "ENTER / F"
    assert keyed("PRESS {FIRE}, THEN {SLOWER} - {NOT AN ACTION}") == "PRESS SPACE, THEN Z - {NOT AN ACTION}"
    assert label("ACKNOWLEDGE", "PING") == "ENTER / F"
    SETTINGS["trained"] = True
    menu = SettingsMenu()
    menu.sel = menu.rows.index(("RESET DEFAULTS", None))
    menu._activate()
    assert SETTINGS["keys"] == DEFAULTS["keys"] and SETTINGS["trained"], "defaults restored, First Watch kept"
    tmp.write_text("not json")
    load(tmp)
    assert SETTINGS == DEFAULTS
    print("settings ok")
