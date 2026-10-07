"""Silent Solution - Phase 5: steampunk operator workstation, acoustic profiling, hostile submarines,
counter-fire, countermeasures, difficulty presets and an endless wave patrol."""
import math
import random
import textwrap
from collections import deque, namedtuple

import numpy as np
import pygame

from ai import ThreatDirector
from graphics import brass
from graphics.crt_renderer import DIM, PHOSPHOR, RED, CRTRenderer
from graphics.periscope import EYE, PeriscopeRenderer, View
from sim import (CRUSH_DEPTH, DIFFICULTY, FEATHER_KT, KNOT, MAST_DEPTH, MAX_DEPTH, MAX_RUDDER, MIN_ORDER_DEPTH,
                 PERISCOPE_DEPTH, R_EFF,
                 SCOPE_TOP, SOUND_SPEED, TELEGRAPH, TORP_MAX_RUN, TORP_SPEED, YARD, Decoy, Submarine, Torpedo,
                 WorldSimulation, angle_diff, bearing, clamp, horizon_distance, intercept, ping_delay,
                 range_from_delay, spot_probability)
from tutorial import TRAINING, Tutorial

W, H = 1280, 720
FPS = 60
SAMPLE_RATE = 44100
DIAL_RATE = 60.0          # hydrophone dial deg/s
RUDDER_RATE = 20.0        # deg/s while LEFT/RIGHT held
MAX_ECHO_RANGE = 12000.0  # m; beyond this the return is lost in noise
DECOY_WIDTH = 14.0        # noisemaker cloud smears across ~30 deg of waterfall
HOSTILE_WIDTH = 0.8       # hostile fish: bright, narrow
HOLD_DELAY = 0.35         # s of holding UP/DOWN before the TDC value starts to run
ROW_INTERVAL = 0.1        # sim seconds per waterfall row
DIESEL_DEAFNESS = 3.0     # contacts sound this many times quieter while our diesels run
DIESEL_FLOOR = 40.0       # waterfall noise our diesels add
MAST_MESSAGES = {  # own mast events: (sonar log line, teleprinter line or "")
    "MASTS_LOWERED": ("MASTS HOUSED FOR DEPTH", ""),
    "HEAD_VALVE": ("HEAD VALVE SHUT - WAVE OVER SNORKEL", ""),
    "SNORKEL_FLOODED": ("SNORKEL FLOODED - DIESELS TRIPPED", "ENGINE ROOM: SNORKEL HEAD FLOODED AT SPEED. DIESELS "
                        "STOPPED FOR TEN SECONDS. KEEP UNDER EIGHT KNOTS WHILE SNORKELLING."),
    "SCOPE_DAMAGED": ("PERISCOPE BENT", "CONTROL ROOM: PERISCOPE BENT BY SPEED. FREEING IT - TWO MINUTES."),
}
ECHO_FADE = 40.0          # s an echo blip glows on the scope
SCOPE_RANGES = (5000.0, 10000.0, 20000.0)  # yd

# ---------- workstation layout (logical 1280x720, scaled to the window) ----------
MONITOR = pygame.Rect(272, 10, 640, 456)
CRT_RECT = pygame.Rect(302, 38, 580, 400)
SCOPE_PANEL = pygame.Rect(10, 10, 254, 250)
SCOPE_C, SCOPE_R = (137, 132), 104
TDC_PANEL = pygame.Rect(10, 266, 254, 200)
CONSOLE = pygame.Rect(10, 472, 902, 238)
GAUGES = pygame.Rect(920, 10, 350, 364)
TELETYPE = pygame.Rect(920, 380, 350, 330)
PAPER_RECT = pygame.Rect(938, 418, 314, 280)
ORDER_SLIP = pygame.Rect(950, 424, 290, 62)  # tutorial: current order pinned to the paper
GAUGE_R = 76
GAUGE_POS = {"DEPTH": (1008, 104), "BATTERY": (1182, 104), "NOISE": (1008, 282), "HULL": (1182, 282)}
GAUGE_SPECS = {
    "DEPTH": dict(title="DEPTH", lo=0, hi=300, major=50, minor=10, red=(CRUSH_DEPTH, 300), units="METRES"),
    "BATTERY": dict(title="BATTERY", lo=0, hi=100, major=20, minor=5, red=(0, 15), units="% CHARGE"),
    "NOISE": dict(title="SELF NOISE", lo=0, hi=3, major=0.5, minor=0.1, red=(1.2, 3), units="CAVITATION"),
    "HULL": dict(title="HULL", lo=0, hi=100, major=20, minor=5, red=(0, 30), units="% INTEGRITY"),
}
TELEGRAPH_C, TELEGRAPH_R = (118, 650), 94
WHEEL_C, WHEEL_R = (330, 578), 56
RUDDER_BAR = pygame.Rect(250, 656, 160, 9)
DEPTH_C, DEPTH_R = (530, 566), 60
HOLD_BTN, BLOW_BTN, PD_BTN = pygame.Rect(440, 638, 56, 24), pygame.Rect(502, 638, 56, 24), pygame.Rect(564, 638, 56, 24)
SCOPE_LEVER, SNORT_LEVER = (446, 528), (614, 528)  # mast levers either side of the depth-order dial
LOOK_BTN = pygame.Rect(422, 562, 48, 22)
TUBE_SW = ((672, 540), (752, 540))
NMKR_BTN, PING_BTN = pygame.Rect(642, 640, 140, 24), pygame.Rect(642, 674, 140, 24)
LAMPS = ("ENEMY SONAR", "TORPEDO", "CAVITATION", "DIESEL", "MASTS UP", "BROACH", "LEAK", "HULL STRESS", "BELOW LAYER")
LAMP_X, LAMP_Y0, LAMP_DY = 814, 506, 22
TDC_ROW_Y0, TDC_ROW_H = 296, 21

# inside the CRT (local coordinates)
WF_POS = (20, 30)
WF_W, WF_H = 360, 214
SPEC_RECT = pygame.Rect(392, 30, 172, 146)
LIB_RECT = pygame.Rect(392, 198, 172, 46)
LOG_POS = (20, 266)
HYD_POS = (392, 262)

HIGHLIGHTS = {  # tutorial rings: screen rect, or (centre, radius)
    "waterfall": pygame.Rect(CRT_RECT.x + WF_POS[0] - 4, CRT_RECT.y + WF_POS[1] - 4, WF_W + 8, WF_H + 8),
    "spectrum": SPEC_RECT.union(LIB_RECT).move(CRT_RECT.topleft).inflate(10, 22),
    "scope": (SCOPE_C, SCOPE_R + 4),
    "tdc": TDC_PANEL.inflate(-4, -4),
    "gauges": GAUGES.inflate(-4, -4),
    "noise": (GAUGE_POS["NOISE"], GAUGE_R + 4),
    "battery": (GAUGE_POS["BATTERY"], GAUGE_R + 4),
    "telegraph": pygame.Rect(TELEGRAPH_C[0] - TELEGRAPH_R - 6, TELEGRAPH_C[1] - TELEGRAPH_R - 6, 2 * TELEGRAPH_R + 12, TELEGRAPH_R + 36),
    "wheel": pygame.Rect(WHEEL_C[0] - 90, WHEEL_C[1] - 78, 180, 168),
    "depth": pygame.Rect(DEPTH_C[0] - 86, DEPTH_C[1] - DEPTH_R - 8, 172, 140),
    "tubes": pygame.Rect(636, 494, 156, 136),
    "nmkr": NMKR_BTN.inflate(10, 10),
    "ping": PING_BTN.inflate(10, 10),
    "lamps": pygame.Rect(798, 496, 112, 204),
    "masts": pygame.Rect(416, 492, 228, 96),
}

# periscope screen (look mode): the eyepiece and the instruments you can glimpse around it
EYEPIECE_C = (640, 340)
STRIP = pygame.Rect(40, 676, 1200, 36)


def cone_gain(dial, bearings, cone=25.0):
    """0..1 hydrophone sensitivity per contact; 1 dead ahead of the dial, 0 past the cone."""
    delta = np.abs((bearings - dial + 180) % 360 - 180)
    return np.clip(1 - delta / cone, 0, 1) ** 2


# ---------- operator sensors: the only path from world truth to the console ----------
KIND_INDEX = {"MERCHANT": 0, "ESCORT": 1, "SUB": 2, "TORPEDO": 3, "DECOY": 4}


class PassiveSonar:
    """Relative bearings with noise, 0.5 deg resolution, 1/r spreading loss and thermocline loss."""

    def __init__(self, world, beam_width=1.5, noise_deg=0.8, resolution=0.5):
        self.world, self.beam_width, self.noise_deg, self.resolution = world, beam_width, noise_deg, resolution

    def listen(self):
        """Returns (rel_bearings, levels, waterfall widths, spectral family index, hostile-fish flags)."""
        p, ocean = self.world.player, self.world.ocean
        sources = [*self.world.targets, *self.world.torpedoes]
        if not sources:
            return np.empty(0), np.empty(0), np.empty(0), np.empty(0, int), np.empty(0, bool)
        src = np.array([(s.x, s.y, s.noise * ocean.transmission(p, s) * (1.5 if getattr(s, "hostile", False) else 1.0),
                         DECOY_WIDTH if isinstance(s, Decoy) else HOSTILE_WIDTH if getattr(s, "hostile", False)
                         else self.beam_width, KIND_INDEX.get(s.kind, 0), getattr(s, "hostile", False))
                        for s in sources])
        dx, dy = src[:, 0] - p.x, src[:, 1] - p.y
        rel = np.degrees(np.arctan2(dx, dy)) - p.heading + np.random.normal(0, self.noise_deg, len(src))
        rel = (np.round(rel / self.resolution) * self.resolution) % 360
        rng = np.maximum(np.hypot(dx, dy), 1.0)
        level = 160 * src[:, 2] * np.minimum(1.0, 3000 / rng) * np.random.uniform(0.75, 1.0, len(src))
        return rel, level, src[:, 3], src[:, 4].astype(int), src[:, 5].astype(bool)

    def bearing_of(self, source):
        """Noisy relative bearing of a transient (detonation, splash, ping)."""
        p = self.world.player
        return (bearing(p.x, p.y, source.x, source.y) - p.heading + random.gauss(0, self.noise_deg)) % 360

    def loudness(self, source, ref=3000.0):
        """0..1 how loud a transient at source sounds here."""
        p = self.world.player
        return min(1.0, ref / max(p.range_to(source), 1.0)) * self.world.ocean.transmission(p, source)


class ActiveSonar:
    """Ping now, echoes arrive after 2d/c. Operator only ever sees bearing + delay-derived range.
    Contacts across the layer sit in its shadow and return nothing; the layer itself returns reverb."""

    def __init__(self, world, noise_deg=1.5, timing_jitter=0.01):
        self.world, self.noise_deg, self.timing_jitter = world, noise_deg, timing_jitter
        self.clock = 0.0
        self.pending = []  # (arrival_time, rel_bearing or None for layer reverb, measured_delay)

    def ping(self):
        self.world.emit_ping()
        p, ocean = self.world.player, self.world.ocean
        for t in self.world.targets:
            r = p.range_to(t)
            if r <= MAX_ECHO_RANGE and not ocean.crosses_layer(p, t):
                rel = (bearing(p.x, p.y, t.x, t.y) - p.heading + random.gauss(0, self.noise_deg)) % 360
                delay = ping_delay(r)
                self.pending.append((self.clock + delay, rel, delay + random.gauss(0, self.timing_jitter)))
        layer = ping_delay(abs(ocean.layer_depth - p.z))
        self.pending.append((self.clock + layer, None, layer))

    def update(self, dt):
        """Returns [(rel_bearing or None, range_m)] for echoes arriving this frame."""
        self.clock += dt
        arrived = [(b, range_from_delay(d)) for at, b, d in self.pending if at <= self.clock]
        self.pending = [e for e in self.pending if e[0] > self.clock]
        return arrived


# ---------- fire control ----------
Solution = namedtuple("Solution", "gyro lead time run intercept")

# name: (label, units, format, tap step, hold rate per s, min, max, wraps)
FIELDS = {
    "BRG": ("TGT BRG", "REL", "{:05.1f}", 1.0, 20.0, 0, 360, True),
    "RNG": ("TGT RNG", "YD", "{:6,.0f}", 100.0, 1500.0, 200, 20000, False),
    "SPD": ("TGT SPD", "KT", "{:4.1f}", 0.5, 4.0, 0, 35, False),
    "CRS": ("TGT CRS", "TRUE", "{:05.1f}", 1.0, 20.0, 0, 360, True),
    "ARM": ("SKR ARM", "YD", "{:5,.0f}", 100.0, 1500.0, 0, 6000, False),
    "DEP": ("RUN DEP", "M", "{:03.0f}", 5.0, 40.0, 5, 250, False),
}


class TargetDataComputer:
    """Holds only the operator's estimates, as a north-up position relative to own ship.
    Acts as a position keeper: dead-reckons the estimate along estimated course/speed, so
    BRG/RNG drift the way the real contact would if the estimates are right."""

    def __init__(self, own):
        self.own = own
        self.x, self.y = 0.0, 3000 * YARD
        self.values = {"SPD": 10.0, "CRS": 90.0, "ARM": 1000.0, "DEP": 10.0}
        self.selected = 0

    @property
    def field(self):
        return list(FIELDS)[self.selected]

    def get(self, name):
        if name == "BRG":
            return (bearing(0, 0, self.x, self.y) - self.own.heading) % 360
        if name == "RNG":
            return math.hypot(self.x, self.y) / YARD
        return self.values[name]

    def set(self, name, v):
        *_, lo, hi, wraps = FIELDS[name]
        v = v % hi if wraps else clamp(v, lo, hi)
        if name in ("BRG", "RNG"):
            brg = v if name == "BRG" else self.get("BRG")
            rng = (v if name == "RNG" else self.get("RNG")) * YARD
            b = math.radians(brg + self.own.heading)
            self.x, self.y = rng * math.sin(b), rng * math.cos(b)
        else:
            self.values[name] = v

    def cycle(self, d):
        self.selected = (self.selected + d) % len(FIELDS)

    def nudge(self, d):
        self.set(self.field, self.get(self.field) + d * FIELDS[self.field][3])

    def hold(self, d, dt):
        self.set(self.field, self.get(self.field) + d * FIELDS[self.field][4] * dt)

    def target_velocity(self):
        c, s = math.radians(self.values["CRS"]), self.values["SPD"] * KNOT
        return s * math.sin(c), s * math.cos(c)

    def update(self, dt):
        (vx, vy), (ox, oy) = self.target_velocity(), self.own.velocity()
        self.x += (vx - ox) * dt
        self.y += (vy - oy) * dt

    def solve(self):
        sol = intercept(bearing(0, 0, self.x, self.y), math.hypot(self.x, self.y), self.values["CRS"],
                        self.values["SPD"] * KNOT, TORP_SPEED)
        if sol is None:
            return None
        gyro, lead, t = sol
        run, g = TORP_SPEED * t, math.radians(gyro)
        return Solution(gyro, lead, t, run, (run * math.sin(g), run * math.cos(g)))


# ---------- acoustic profile analysis (the deaf/mute-playable ear) ----------
SPEC_BINS = 92
FREQS = np.geomspace(20, 2000, SPEC_BINS)
CLASSES = ("MERCHANT", "WARSHIP", "SUBMARINE", "TORPEDO", "NOISEMAKER")
CLASS_TAGS = ("MER", "WAR", "SUB", "TORP", "NOIS")


def _template(*peaks, floor=0.0, slope=0.0):
    """Spectral lines (Hz, amplitude, width in octaves) over a sloped broadband floor, peak-normalised."""
    lf = np.log2(FREQS)
    t = floor * (FREQS / 20.0) ** -slope
    for f, a, w in peaks:
        t = t + a * np.exp(-0.5 * ((lf - np.log2(f)) / w) ** 2)
    return t / t.max()


TEMPLATES = np.array([
    _template((30, 1.0, .06), (60, .8, .06), (90, .55, .06), (120, .35, .06), floor=.25, slope=.6),  # 2-blade shaft hum
    _template((60, .5, .08), (120, .45, .08), (450, .9, .05), (900, 1.0, .04), (1350, .6, .04), floor=.45, slope=.1),
    _template((50, 1.0, .03), (300, .3, .03), floor=.05, slope=.5),                                 # one faint narrow line
    _template((1500, 1.0, .03), (750, .35, .04), floor=.1, slope=-.3),                              # high-speed screw
    _template(floor=1.0),                                                                           # broadband bubbles
])
TEMPLATES_N = TEMPLATES / np.linalg.norm(TEMPLATES, axis=1, keepdims=True)


class SpectrumAnalyzer:
    """Frequency vs amplitude of whatever the hydrophone dial is pointed at, plus library matching."""

    def __init__(self):
        self.curve = np.zeros(SPEC_BINS)
        self.best, self.confidence = None, 0.0

    def update(self, dt, t, gains, levels, kinds, rain):
        w = gains * levels / 160
        w = np.where(kinds == 0, w * (0.7 + 0.3 * math.sin(2 * math.pi * 0.9 * t)), w)  # merchant shaft beat
        target = (w[:, None] * TEMPLATES[kinds]).sum(axis=0) if len(w) else np.zeros(SPEC_BINS)
        floor = 0.06 + 0.25 * rain
        noise = np.abs(np.random.normal(floor, 0.03 + 0.08 * rain, SPEC_BINS))
        self.curve += (target + noise - self.curve) * min(1.0, dt * 8)
        signal = np.clip(self.curve - floor - 0.04, 0, None)
        if signal.max() < 0.1:
            self.best, self.confidence = None, 0.0
            return
        sims = TEMPLATES_N @ (signal / np.linalg.norm(signal))
        self.best, self.confidence = int(np.argmax(sims)), float(sims.max())


# ---------- teleprinter ----------
class Teletype:
    WIDTH = 38

    def __init__(self, audio, cps=34.0):
        self.audio, self.cps = audio, cps
        self.lines = deque(maxlen=40)
        self.queue = deque()
        self.typing = ""
        self.acc = 0.0
        self.fed = 0  # lines fed through, for the paper's perforations

    def print(self, text):
        self.queue.extend(textwrap.wrap(text, self.WIDTH) + [""])

    def update(self, dt):
        if not self.queue:
            self.acc = 0.0
            return
        self.acc += dt * self.cps
        while self.acc >= 1 and self.queue:
            self.acc -= 1
            line = self.queue[0]
            if len(self.typing) < len(line):
                self.typing += line[len(self.typing)]
                if self.typing[-1] != " ":
                    self.audio.play_clack()
            if len(self.typing) >= len(line):
                self.lines.append(self.typing)
                self.typing = ""
                self.queue.popleft()
                self.fed += 1


# ---------- procedural audio ----------
def sweep_phase(f0, f1, dur, t):
    """Phase of an exponential frequency sweep f0 -> f1 over dur seconds."""
    k = f1 / f0
    return 2 * np.pi * f0 * dur / np.log(k) * (k ** (t / dur) - 1)


def lowpass(wave, taps):
    return np.convolve(wave, np.ones(taps) / taps, "same")


class AudioSynthesizer:
    def __init__(self):
        try:
            pygame.mixer.init(SAMPLE_RATE, -16, 2, 512)
        except pygame.error:
            self.enabled = False  # no audio device: run silent; every cue also has a visual
            return
        self.enabled = True
        pygame.mixer.set_num_channels(32)
        self.rate, _, self.channels = pygame.mixer.get_init()
        ping = self._ping_wave()
        self.ping = self._sound(ping)
        self.echo = self._sound(ping * 0.5)
        self.enemy_ping = self._sound(self._ping_wave(950.0, 900.0, 0.9))  # flat ASDIC tone, not our sweep
        self.explosion = self._sound(self._explosion_wave())
        self.hiss = self._sound(self._hiss_wave())
        self.blow = self._sound(lowpass(np.random.uniform(-1, 1, int(self.rate * 3)), 30) * 4 * np.exp(-0.5 * self._t(3)))
        self.clack = self._sound(np.random.uniform(-1, 1, int(self.rate * 0.02)) * np.exp(-300 * self._t(0.02)) * 0.5)
        self.creaks = [self._sound(self._creak_wave(f)) for f in (38.0, 52.0, 67.0, 85.0)]
        self.thrum_channel = self._sound(self._thrum_wave()).play(loops=-1)
        self.thrum_channel.set_volume(0.0)
        t = self._t(1.2)  # hydraulic mast ram: a rising whine over a hiss
        self.mast = self._sound(0.35 * (np.sin(sweep_phase(180.0, 320.0, 1.2, t)) * 0.6
                                        + lowpass(np.random.uniform(-1, 1, t.size), 6) * 0.5)
                                * np.minimum(1.0, t / 0.1) * np.minimum(1.0, (1.2 - t) / 0.2))
        t = self._t(0.4)
        self.thunk = self._sound(0.9 * np.sin(2 * np.pi * 55 * t) * np.exp(-14 * t)
                                 + 0.3 * lowpass(np.random.uniform(-1, 1, t.size), 40) * np.exp(-20 * t))
        t = self._t(2.0)  # diesel: 25 Hz firing pulses (whole cycles in 2 s -> seamless) through the hull
        chug = np.maximum(0, np.sin(2 * np.pi * 25 * t)) ** 4 - 0.25
        self.diesel_channel = self._sound(0.6 * lowpass(chug + 0.3 * np.random.uniform(-1, 1, t.size), 12)).play(loops=-1)
        self.diesel_channel.set_volume(0.0)
        t = self._t(4.0)  # surface: wind hiss with slow wave slaps
        slap = 0.5 + 0.5 * np.sin(2 * np.pi * 0.5 * t) ** 8
        self.surface_channel = self._sound(0.5 * lowpass(np.random.uniform(-1, 1, t.size), 8) * slap).play(loops=-1)
        self.surface_channel.set_volume(0.0)

    def _sound(self, wave):
        pcm = (np.clip(wave, -1, 1) * 32767).astype(np.int16)
        if self.channels > 1:
            pcm = np.repeat(pcm[:, None], self.channels, axis=1)
        return pygame.sndarray.make_sound(np.ascontiguousarray(pcm))

    def _t(self, dur):
        return np.arange(int(self.rate * dur)) / self.rate

    def _ping_wave(self, f0=1200.0, f1=800.0, dur=0.6):
        t = self._t(dur)
        phase = sweep_phase(f0, f1, dur, t)
        env = np.exp(-5.0 * t) * np.minimum(1.0, t / 0.004)  # 4 ms attack kills the click
        wave = (np.sin(phase) + 0.25 * np.sin(2 * phase)) * env
        return 0.8 * wave / np.abs(wave).max()

    def _thrum_wave(self, dur=2.0):
        t = self._t(dur)  # 80/160 Hz complete whole cycles -> seamless loop
        hum = 0.6 * np.sin(2 * np.pi * 80 * t) + 0.4 * np.sin(2 * np.pi * 160 * t)
        return 0.7 * (hum + np.random.uniform(-1, 1, t.size) * 0.18)

    def _explosion_wave(self, dur=4.0):
        t = self._t(dur)
        sub = np.sin(sweep_phase(40.0, 15.0, dur, t)) * np.exp(-0.9 * t)       # 40 -> 15 Hz sub-bass sweep
        boom = lowpass(np.random.uniform(-1, 1, t.size), 220) * np.exp(-1.8 * t)  # ~200 Hz low-passed noise
        shock = np.random.uniform(-1, 1, t.size) * np.exp(-40 * t)              # initial pressure front
        wave = (sub + 10 * boom + 0.5 * shock) * np.minimum(1.0, t / 0.008)
        return 0.95 * wave / np.abs(wave).max()

    def _hiss_wave(self, dur=3.5):
        t = self._t(dur)
        env = np.minimum(1.0, t / 0.05) * np.exp(-0.7 * t) * (0.8 + 0.2 * np.sin(2 * np.pi * 7 * t))  # bubbling
        return 0.8 * np.random.uniform(-1, 1, t.size) * env

    def _creak_wave(self, f0):
        dur = random.uniform(1.2, 2.2)
        t = self._t(dur)
        f = f0 * (1 - 0.15 * t / dur) * (1 + 0.03 * np.sin(2 * np.pi * 5.5 * t))  # sagging, wobbling pitch
        square = np.sign(np.sin(2 * np.pi * np.cumsum(f) / self.rate))
        metal = square * (0.6 + 0.4 * np.sin(2 * np.pi * f0 * 4.3 * t))           # ring-mod partial: steel, not wood
        return 0.6 * lowpass(metal, 24) * np.sin(np.pi * t / dur) ** 3

    def _play(self, sound, strength):
        if self.enabled:
            ch = sound.play()
            if ch:
                ch.set_volume(float(np.clip(strength, 0.05, 1.0)))

    def play_ping(self):
        self._play(self.ping, 1.0)

    def play_echo(self, strength):
        self._play(self.echo, strength)

    def play_enemy_ping(self, strength):
        self._play(self.enemy_ping, strength)

    def play_explosion(self, strength):
        self._play(self.explosion, strength)

    def play_hiss(self, strength):
        self._play(self.hiss, strength)

    def play_blow(self):
        self._play(self.blow, 0.8)

    def play_clack(self):
        self._play(self.clack, 0.12)

    def play_creak(self, strength):
        if self.enabled:
            self._play(random.choice(self.creaks), strength)

    def set_hydrophone(self, signal):
        if self.enabled:
            self.thrum_channel.set_volume(float(np.clip(0.03 + signal, 0.0, 1.0)))

    def play_mast(self):
        self._play(self.mast, 0.6)

    def play_thunk(self):
        self._play(self.thunk, 0.8)

    def set_diesel(self, running):
        if self.enabled:
            self.diesel_channel.set_volume(0.55 if running else 0.0)

    def set_surface(self, looking, sea_state):
        if self.enabled:
            self.surface_channel.set_volume(0.15 + 0.08 * sea_state if looking else 0.0)


# ---------- passive waterfall ----------
class WaterfallDisplay:
    def __init__(self):
        self.buffer = np.zeros((WF_H, WF_W), np.float32)
        self.surface = pygame.Surface((WF_W, WF_H))
        self.cols = np.arange(WF_W, dtype=np.float32)
        self.acc = 0.0
        self.blips = []  # (rel_bearing, intensity, width) painted onto the next row: echoes, transients

    def blip(self, rel_bearing, intensity, width=1.5):
        self.blips.append((rel_bearing, intensity, width))

    def update(self, dt, bearings, levels, widths=None, rain=0.0, floor=0.0):
        self.acc += dt
        if self.acc < ROW_INTERVAL:
            return
        self.acc %= ROW_INTERVAL
        if widths is None:
            widths = np.full(len(levels), 1.5)
        if self.blips:
            b, l, w = np.array(self.blips).T
            bearings, levels, widths = (np.concatenate(p) for p in ((bearings, b), (levels, l), (widths, w)))
            self.blips.clear()
        self.buffer = np.roll(self.buffer, shift=1, axis=0)
        row = np.clip(np.random.normal(22.5, 6.0, WF_W), 10, 35)                                 # thermal / self noise
        row += rain * (np.random.uniform(20, 70, WF_W) + (np.random.random(WF_W) < 0.03) * 90)  # rain hiss + drops
        row += floor * np.random.uniform(0.6, 1.4, WF_W)                                        # own diesels
        centre = bearings / 360.0 * WF_W
        off = (self.cols[None, :] - centre[:, None] + WF_W / 2) % WF_W - WF_W / 2  # wraps 359 -> 0
        row += (levels[:, None] * np.exp(-0.5 * (off / widths[:, None]) ** 2)).sum(axis=0)
        self.buffer[0] = row

    def draw(self):
        g = np.clip(self.buffer, 0, 255).T  # surfarray is (x, y)
        pygame.surfarray.blit_array(self.surface, np.stack((g / 6, g, g / 4), axis=-1).astype(np.uint8))
        return self.surface


# ---------- periscope optics: the only path from the surface picture to the eyepiece ----------
SHIP_CLASSES = {  # silhouette family: (length, beam, mast top, freeboard) m - the recognition manual's numbers
    "merchant": (130.0, 17.0, 30.0, 8.0),
    "tanker": (150.0, 20.0, 26.0, 6.0),
    "escort": (95.0, 11.0, 24.0, 5.0),
}
SCOPE_FOV = {False: 32.0, True: 8.0}  # deg across the eyepiece: low power 1.5x, high power 6x
SCOPE_TRAIN_RATE = {False: 40.0, True: 12.0}  # deg/s on A/D
WAKE_SEEN = 2500.0                    # m, a torpedo's bubble track is visible this far
WRECK_TIME = 240.0                    # s a sinking ship stays on the surface picture

Sighting = namedtuple("Sighting", "uid cls brg rng aspect speed height drop sinking lamp")
Wake = namedtuple("Wake", "brg rng heading")
Burst = namedtuple("Burst", "kind brg rng age")


def silhouette_class(ship):
    if ship.kind == "ESCORT":
        return "escort"
    return "tanker" if id(ship) % 3 == 0 else "merchant"


class PeriscopeOptics:
    """What an eye ~1.5 m above the waves can see: limited by weather, the horizon (hull-down) and the lens
    being under a wave. Bearings are far better than sonar's; range comes from the rangefinder."""

    def __init__(self, world):
        self.world = world

    def eye_height(self):
        p = self.world.player
        return max(0.3, SCOPE_TOP - p.z - p.wave)

    def look(self):
        """(sightings, wakes, bursts), or None when the scope is down or the lens is under a wave."""
        w, p = self.world, self.world.player
        if not (getattr(p, "scope_up", False) and p.scope_clear):
            return None
        vis, d_h = w.ocean.visibility, horizon_distance(self.eye_height())
        sightings = []
        wrecks = [t for t in w.sunk if w.time - t.sunk_at < WRECK_TIME]
        for t in [s for s in w.targets if s.kind in ("MERCHANT", "ESCORT")] + wrecks:
            r = p.range_to(t)
            cls = silhouette_class(t)
            height = SHIP_CLASSES[cls][2]
            drop = max(0.0, r - d_h) ** 2 / (2 * R_EFF)  # hull-down: this much of her is below our horizon
            if r > vis or drop >= height:
                continue
            brg = bearing(p.x, p.y, t.x, t.y)
            sightings.append(Sighting(id(t), cls, (brg + random.gauss(0, 0.1)) % 360, r,
                                      angle_diff(t.heading, (brg + 180) % 360), t.speed, height, drop,
                                      w.time - t.sunk_at if t.sunk_at >= 0 else -1.0, t.signal_until > w.time))
        wakes = [Wake(bearing(p.x, p.y, t.x, t.y), p.range_to(t), t.heading) for t in w.torpedoes
                 if t.z < 25 and p.range_to(t) < min(WAKE_SEEN, vis)]
        bursts = [Burst(k, bearing(p.x, p.y, x, y), math.hypot(x - p.x, y - p.y), w.time - t0)
                  for k, x, y, t0 in w.effects if math.hypot(x - p.x, y - p.y) < vis]
        return sightings, wakes, bursts

    @staticmethod
    def rangefinder(sighting, high_power):
        """Known mast height over its angular height: good at high power, rough at low."""
        return sighting.rng * (1 + random.gauss(0, 0.03 if high_power else 0.08))


# ---------- game state behind the workstation ----------
def build_world(d):
    world = WorldSimulation(Submarine(0, 0, 0, 4 * KNOT, z=60, uses_battery=d["battery"], uses_oxygen=d["oxygen"],
                                      mast_damage=d["mast_damage"], lower_delay=d["lower_delay"]), [])
    world.ocean.layer_loss = d["layer_loss"]
    world.leaks_enabled, world.torp_damage, world.spot_mult = d["leaks"], d["torp_damage"], d["spot_mult"]
    world.director = ThreatDirector(d)
    return world


def stamp(t):
    return f"{int(t // 60):02d}:{int(t % 60):02d}"


class Console:
    """Operator-side state and logic: input, sensors, events -> what the crew sees and hears."""

    def __init__(self, level, audio, diff=None):
        self.level, self.diff = level, diff or DIFFICULTY[level]
        self.world = build_world(self.diff)
        self.audio = audio
        self.passive = PassiveSonar(self.world, self.diff["beam_width"])
        self.active = ActiveSonar(self.world)
        self.waterfall, self.spectrum = WaterfallDisplay(), SpectrumAnalyzer()
        self.tdc = TargetDataComputer(self.world.player)
        self.teletype = Teletype(audio)
        self.dial = self.signal = self.held = 0.0
        self.tubes = [0.0, 0.0]  # reload s remaining; 0 = ready; inf = empty, waiting on the racks
        self.log = deque(maxlen=7)
        self.echoes = []         # (x, y, time) absolute fixes for the scope
        self.enemy_pings = []    # (true bearing, time)
        self.ping_time = -99.0
        self.lamp_enemy = self.flash = self.shake = 0.0
        self.banner = ("", 0.0)
        self.torpedo_warning = False
        self.scope_range = SCOPE_RANGES[1]
        self.dead, self.cause = False, ""
        self.dragging = None
        self.actions = set()     # orders given since last asked (the tutorial grades these)
        self.frame_events = []   # world events from the last tick
        self.last_echo = None    # (rel bearing, range yd)
        self.tutorial = None     # set by tutorial.Tutorial
        self.optics = PeriscopeOptics(self.world)
        self.looking = False     # at the eyepiece (the station is out of sight)
        self.scope_brg = 0.0     # relative bearing the scope is trained on
        self.high_power = False
        self.view = None         # last optics.look(): (sightings, wakes, bursts) or None
        self.scope_fix = None    # (true bearing, range m, time) from the last scope mark
        self.exposure = 0.0      # estimated chance of being spotted per minute, 0..1
        self.last_valve = -99.0
        self.say("SONAR ONLINE. PASSIVE ARRAY NOMINAL")
        if diff is None:
            self.teletype.print(f"FROM FLAG OFFICER SUBMARINES: {level} PATROL. INTERCEPT CONVOYS IN YOUR SECTOR. "
                                "STAY DEEP, STAY QUIET. F1 FOR STATION DRILL.")

    @property
    def score(self):
        return ThreatDirector.score(self.world)

    @property
    def wave(self):
        return self.world.director.wave if self.world.director else 0

    @property
    def classification(self):
        return CLASSES[self.spectrum.best] if self.spectrum.best is not None else None

    def say(self, msg):
        self.log.append(f"{stamp(self.world.time)} {msg}")

    # --- orders ---
    def telegraph_index(self):
        p = self.world.player
        return min(range(len(TELEGRAPH)), key=lambda i: abs(TELEGRAPH[i][1] * KNOT - p.ordered_speed))

    def telegraph(self, index):
        index = int(clamp(index, 0, len(TELEGRAPH) - 1))
        self.world.player.ordered_speed = TELEGRAPH[index][1] * KNOT
        self.say(f"ENGINES {TELEGRAPH[index][0]}")

    def order_depth(self, depth):
        p = self.world.player
        p.ordered_depth = clamp(depth, MIN_ORDER_DEPTH, MAX_DEPTH)
        p.blowing = False  # a new depth order takes the boat back from the blow

    # --- masts ---
    def periscope_depth(self):
        self.order_depth(PERISCOPE_DEPTH)
        self.actions.add("PD")
        self.say("MAKE YOUR DEPTH ONE FIVE METRES")

    def toggle_scope(self):
        p = self.world.player
        if p.scope_up:
            p.scope_up, self.looking = False, False
            self.actions.add("SCOPE_DOWN")
            self.say("DOWN SCOPE")
        else:
            why = p.raise_mast("scope")
            if why:
                return self.say(why)
            self.actions.add("SCOPE_UP")
            self.say("UP SCOPE")
        self.audio.play_mast()

    def toggle_snorkel(self):
        p = self.world.player
        if p.snorkel_up:
            p.snorkel_up = False
            self.actions.add("SNORKEL_DOWN")
            self.say("SECURE SNORKELLING")
        else:
            why = p.raise_mast("snorkel")
            if why:
                return self.say(why)
            self.actions.add("SNORKEL_UP")
            self.say("RAISE SNORKEL. START DIESELS")
        self.audio.play_mast()

    def look(self):
        if self.looking:
            self.looking = False
        elif not self.world.player.scope_up:
            self.say("SCOPE IS DOWN  (U TO RAISE)")
        else:
            self.looking = True
            self.actions.add("LOOK")

    def toggle_power(self):
        self.high_power = not self.high_power
        self.actions.add("POWER")

    def scope_mark(self):
        """Exact bearing - and rangefinder range if a ship is in the wires - straight into the TDC."""
        p = self.world.player
        fov = SCOPE_FOV[self.high_power]
        true_brg = (self.scope_brg + p.heading) % 360
        sightings = self.view[0] if self.view else []
        target = min((s for s in sightings if abs(angle_diff(s.brg, true_brg)) < fov * 0.06),
                     key=lambda s: abs(angle_diff(s.brg, true_brg)), default=None)
        self.actions.add("SCOPE_MARK")
        if target is None:
            self.tdc.set("BRG", self.scope_brg)
            return self.say(f"MARK {self.scope_brg:05.1f}R. NOTHING IN THE WIRES")
        rel = (target.brg - p.heading) % 360
        rng = self.optics.rangefinder(target, self.high_power)
        self.tdc.set("BRG", rel)
        self.tdc.set("RNG", rng / YARD)
        self.scope_fix = (target.brg, rng, self.world.time)
        self.say(f"MARK! {rel:05.1f}R RANGE {rng / YARD:,.0f} YD")

    def estimate_exposure(self):
        """Chance per minute of being spotted. Cadet sees the truth; otherwise it's our own estimate from
        what we know: masts, speed, sea, and the nearest ship we have actually seen through the scope."""
        p, o = self.world.player, self.world.ocean
        exposed = getattr(p, "exposed", None)
        if not exposed:
            return 0.0
        mult = self.world.spot_mult
        if self.diff["ping_warning"]:  # cadet: the honest number
            per_s = max((spot_probability(exposed, p.speed / KNOT, ai.ship.range_to(p), o.visibility, o.sea_state,
                                          ai._alertness()) for ai in self.world.ais if ai.lookouts), default=0.0)
        else:
            seen = [s.rng for s in self.view[0]] if self.view else []
            near = min(seen, default=3000.0)
            alert = 2.5 if self.lamp_enemy > 0 else 1.5
            per_s = spot_probability(exposed, p.speed / KNOT, near, o.visibility, o.sea_state, alert)
        return 1 - (1 - min(1.0, per_s * mult)) ** 60

    def ping(self):
        self.active.ping()
        self.audio.play_ping()
        self.ping_time = self.world.time
        self.actions.add("PING")
        self.say("PING OUT. POSITION EXPOSED")

    def fire(self, tube=None):
        if tube is None:
            tube = next((i for i, r in enumerate(self.tubes) if r == 0), None)
        if tube is None or self.tubes[tube] != 0:
            return self.say("NO TUBE READY")
        sol = self.tdc.solve()
        if sol is None:
            return self.say("NO FIRING SOLUTION")
        self.world.fire(sol.gyro, arm_distance=self.tdc.values["ARM"] * YARD, run_depth=self.tdc.values["DEP"],
                        tube=tube + 1)
        self.tubes[tube] = math.inf
        self.actions.add("FIRE")
        self.say(f"T{tube + 1} AWAY. GYRO {sol.gyro:05.1f}")

    def noisemaker(self):
        p = self.world.player
        if not p.noisemakers:
            return self.say("NO NOISEMAKERS LEFT")
        p.noisemakers -= 1
        self.world.drop_noisemaker()
        self.audio.play_hiss(0.5)
        self.actions.add("NOISEMAKER")
        self.say("NOISEMAKER AWAY")

    def blow(self):
        self.world.player.blowing = True
        self.audio.play_blow()
        self.actions.add("BLOW")
        self.say("BLOW ALL MAIN BALLAST!")

    def hold_depth(self):
        self.order_depth(round(self.world.player.z))
        self.actions.add("HOLD")

    def mark(self):
        self.tdc.set("BRG", self.dial)
        self.actions.add("MARK")
        self.say(f"MARK BEARING {self.dial:05.1f}R")

    # --- input ---
    def key(self, k):
        if self.dead:
            return
        p = self.world.player
        actions = {
            pygame.K_SPACE: self.ping,
            pygame.K_f: self.fire,
            pygame.K_1: lambda: self.fire(0),
            pygame.K_2: lambda: self.fire(1),
            pygame.K_w: lambda: self.tdc.cycle(-1),
            pygame.K_s: lambda: self.tdc.cycle(1),
            pygame.K_UP: lambda: self.tdc.nudge(1),
            pygame.K_DOWN: lambda: self.tdc.nudge(-1),
            pygame.K_m: self.scope_mark if self.looking else self.mark,
            pygame.K_u: self.toggle_scope,
            pygame.K_k: self.toggle_snorkel,
            pygame.K_g: self.periscope_depth,
            pygame.K_v: self.look,
            pygame.K_TAB: self.toggle_power,
            pygame.K_q: lambda: self.order_depth(p.ordered_depth - 10),
            pygame.K_e: lambda: self.order_depth(p.ordered_depth + 10),
            pygame.K_h: self.hold_depth,
            pygame.K_b: self.blow,
            pygame.K_z: lambda: self.telegraph(self.telegraph_index() - 1),
            pygame.K_x: lambda: self.telegraph(self.telegraph_index() + 1),
            pygame.K_c: lambda: setattr(p, "rudder", 0.0),
            pygame.K_n: self.noisemaker,
            pygame.K_t: self.cycle_scope,
            pygame.K_RETURN: lambda: self.actions.add("ENTER"),
            pygame.K_KP_ENTER: lambda: self.actions.add("ENTER"),
        }
        if k in actions:
            actions[k]()

    def cycle_scope(self):
        self.scope_range = SCOPE_RANGES[(SCOPE_RANGES.index(self.scope_range) + 1) % len(SCOPE_RANGES)]
        self.actions.add("SCOPE")

    def click(self, pos):
        if self.dead:
            return
        x, y = pos
        p = self.world.player
        wf = pygame.Rect(CRT_RECT.x + WF_POS[0], CRT_RECT.y + WF_POS[1], WF_W, WF_H)
        buttons = ((HOLD_BTN, self.hold_depth), (BLOW_BTN, self.blow), (PD_BTN, self.periscope_depth),
                   (LOOK_BTN, self.look), (NMKR_BTN, self.noisemaker), (PING_BTN, self.ping))
        if self.looking:  # at the eyepiece: grab the training handles
            self.dragging = ("scope", x)
            return
        if math.hypot(x - SCOPE_LEVER[0], y - SCOPE_LEVER[1]) <= 24:
            return self.toggle_scope()
        if math.hypot(x - SNORT_LEVER[0], y - SNORT_LEVER[1]) <= 24:
            return self.toggle_snorkel()
        if self.tutorial and ORDER_SLIP.collidepoint(pos):
            self.actions.add("ENTER")
        elif wf.collidepoint(pos):
            self.dial = (x - wf.x) / WF_W * 360
        elif math.hypot(x - SCOPE_C[0], y - SCOPE_C[1]) <= SCOPE_R:
            self.cycle_scope()
        elif math.hypot(x - TELEGRAPH_C[0], y - TELEGRAPH_C[1]) <= TELEGRAPH_R and y <= TELEGRAPH_C[1]:
            a = math.degrees(math.atan2(TELEGRAPH_C[1] - y, x - TELEGRAPH_C[0]))
            self.telegraph(int((180 - a) / (180 / len(TELEGRAPH))))
        elif math.hypot(x - WHEEL_C[0], y - WHEEL_C[1]) <= WHEEL_R + 18 or RUDDER_BAR.inflate(0, 16).collidepoint(pos):
            self.dragging = "wheel"
            self.drag(pos)
        elif math.hypot(x - DEPTH_C[0], y - DEPTH_C[1]) <= DEPTH_R:
            a = math.degrees(math.atan2(DEPTH_C[1] - y, x - DEPTH_C[0]))
            self.order_depth(round(brass.angle_value(a, 0, 300) / 5) * 5)
        elif TDC_PANEL.collidepoint(pos) and 0 <= (y - TDC_ROW_Y0) // TDC_ROW_H < len(FIELDS):
            self.tdc.selected = int((y - TDC_ROW_Y0) // TDC_ROW_H)
        else:
            for i, (sx, sy) in enumerate(TUBE_SW):
                if math.hypot(x - sx, y - sy) <= 26:
                    return self.fire(i)
            for rect, action in buttons:
                if rect.collidepoint(pos):
                    return action()

    def drag(self, pos):
        if isinstance(self.dragging, tuple):  # training the scope: the scene follows the hand
            dx = pos[0] - self.dragging[1]
            self.scope_brg = (self.scope_brg - dx * SCOPE_FOV[self.high_power] / EYE) % 360
            self.dragging = ("scope", pos[0])
        elif self.dragging == "wheel":
            self.world.player.rudder = round(clamp((pos[0] - WHEEL_C[0]) / (WHEEL_R + 16) * MAX_RUDDER, -MAX_RUDDER, MAX_RUDDER))

    def scroll(self, pos, dy):
        x, y = pos
        p = self.world.player
        if self.looking:
            if (dy > 0) != self.high_power:
                self.toggle_power()
        elif TDC_PANEL.collidepoint(pos):
            self.tdc.nudge(dy)
        elif math.hypot(x - DEPTH_C[0], y - DEPTH_C[1]) <= DEPTH_R:
            self.order_depth(p.ordered_depth - 10 * dy)
        elif math.hypot(x - WHEEL_C[0], y - WHEEL_C[1]) <= WHEEL_R + 18:
            p.rudder = clamp(p.rudder + 5 * dy, -MAX_RUDDER, MAX_RUDDER)
        elif math.hypot(x - TELEGRAPH_C[0], y - TELEGRAPH_C[1]) <= TELEGRAPH_R:
            self.telegraph(self.telegraph_index() + dy)
        elif CRT_RECT.collidepoint(pos):
            self.dial = (self.dial + dy) % 360

    # --- simulation tick ---
    def update(self, dt, keys):
        self.teletype.update(dt)
        if self.dead:
            return
        p, world = self.world.player, self.world
        train = keys[pygame.K_d] - keys[pygame.K_a]
        if self.looking:  # A/D train the scope; the hydrophone dial stays where it was
            self.scope_brg = (self.scope_brg + train * SCOPE_TRAIN_RATE[self.high_power] * dt) % 360
        else:
            self.dial = (self.dial + train * DIAL_RATE * dt) % 360
        rudder = keys[pygame.K_RIGHT] - keys[pygame.K_LEFT]
        if rudder:
            p.rudder = clamp(p.rudder + rudder * RUDDER_RATE * dt, -MAX_RUDDER, MAX_RUDDER)
        adj = keys[pygame.K_UP] - keys[pygame.K_DOWN]
        self.held = self.held + dt if adj else 0.0
        if self.held > HOLD_DELAY:
            self.tdc.hold(adj, dt)

        for i, r in enumerate(self.tubes):
            if r == math.inf and p.torpedoes > 0:
                p.torpedoes -= 1
                self.tubes[i] = self.diff["reload"]
            elif 0 < r <= dt:
                self.say(f"TUBE {i + 1} LOADED")
        self.tubes = [r if r == math.inf else max(0.0, r - dt) for r in self.tubes]

        self.frame_events = world.step(dt)
        for kind, a, b in self.frame_events:
            self.report(kind, a, b)
        self.tdc.update(dt)
        self.view = self.optics.look() if p.scope_up else None
        self.looking = self.looking and p.scope_up
        self.exposure = self.estimate_exposure()
        self.audio.set_diesel(p.snorkeling)
        self.audio.set_surface(self.looking, world.ocean.sea_state)

        strain = max(0.0, (p.z - 80) / 170) + max(0.0, (p.speed / KNOT - 12) / 8) + (p.z > CRUSH_DEPTH)
        if random.random() < 0.3 * strain * dt:
            self.audio.play_creak(0.3 + 0.5 * min(strain, 1.0))

        bearings, levels, widths, kinds, hostile = self.passive.listen()
        for brg, rng in self.active.update(dt):
            if brg is None:
                self.waterfall.blip(0.0, 60, WF_W)  # layer reverb smears every bearing
                self.say(f"LAYER RETURN {rng:.0f} M")
                continue
            self.audio.play_echo(2500 / rng)
            self.waterfall.blip(brg, 230)
            b = math.radians(brg + p.heading)
            self.echoes.append((p.x + rng * math.sin(b), p.y + rng * math.cos(b), world.time))
            self.last_echo = (brg, rng / YARD)
            self.say(f"ECHO {brg:05.1f}R {rng / YARD:,.0f} YD")
        self.echoes = [e for e in self.echoes if world.time - e[2] < ECHO_FADE]
        rain = world.ocean.rain
        diesel = getattr(p, "snorkeling", False)
        if diesel:  # our own diesels thunder through the hull: the hydrophones are nearly deaf while we charge
            levels = levels / DIESEL_DEAFNESS
        self.waterfall.update(dt, bearings, levels, widths, rain, floor=DIESEL_FLOOR if diesel else 0.0)
        gains = cone_gain(self.dial, bearings, self.diff["cone"])
        self.signal = float((gains * levels / 160).max(initial=0.0)) / (1 + 2 * rain)
        self.spectrum.update(dt, world.time, gains, levels, kinds, rain + (0.35 if diesel else 0.0))
        self.audio.set_hydrophone(self.signal)
        self.torpedo_warning = bool(np.any(hostile & (levels > 30)))

        self.flash = max(0.0, self.flash - dt * 2.5)
        self.shake = max(0.0, self.shake - dt * 1.5)
        self.lamp_enemy = max(0.0, self.lamp_enemy - dt)
        self.banner = (self.banner[0], max(0.0, self.banner[1] - dt))
        self.enemy_pings = [e for e in self.enemy_pings if world.time - e[1] < 1.5]

        if world.hull <= 0 or (p.uses_oxygen and p.o2 <= 0):
            self.dead = True
            self.cause = "HULL BREACHED" if world.hull <= 0 else "OXYGEN EXHAUSTED"
            self.audio.set_hydrophone(0.0)
            self.teletype.print(f"{self.cause}. CONTACT LOST WITH BOAT AT {stamp(world.time)}. "
                                f"WAVE {self.wave}. {self.score:,} GRT SUNK.")

    def jolt(self, strength):
        self.shake = max(self.shake, strength)
        self.flash = max(self.flash, strength * 0.8)

    def report(self, kind, a, b):
        """Turn world events into what the operator sees, reads and hears."""
        tt, world = self.teletype.print, self.world
        if kind == "WAVE":
            m, e, s, brg = b
            fuzz = 0 if self.diff["ping_warning"] else random.uniform(-25, 25)
            tt(f"DISPATCH WAVE {a}: CONVOY OF {m} MERCHANTS, {e} ESCORT(S) REPORTED NEAR {(brg + fuzz) % 360:03.0f} TRUE, "
               f"8 KM." + (f" {s} HOSTILE SUBMARINE(S) SUSPECTED." if s else "") + " ATTACK AT DISCRETION.")
            return
        if kind == "WAVE_CLEAR":
            tt(f"WAVE {a} DISPERSED. TENDER RESUPPLY: +4 TORPEDOES, +2 NOISEMAKERS. TOTAL {self.score:,} GRT.")
            return
        if kind == "ESCAPED":
            if a.kind == "MERCHANT":
                tt("CONVOY STRAGGLER HAS SLIPPED OUT OF RANGE.")
            return
        if kind == "LEAK":
            tt(f"DAMAGE CONTROL: FLOODING. {b} LEAK(S). PUMPS ON.")
            return
        if kind in MAST_MESSAGES:  # own-ship mast trouble
            log, teletype = MAST_MESSAGES[kind]
            if kind == "HEAD_VALVE" and world.time - self.last_valve < 6:
                return  # in a seaway it slams every few seconds; don't spam the log
            self.last_valve = world.time if kind == "HEAD_VALVE" else self.last_valve
            self.say(log)
            if teletype:
                tt(teletype)
            if kind in ("HEAD_VALVE", "SNORKEL_FLOODED"):
                self.audio.play_thunk()
            if kind == "MASTS_LOWERED":
                self.looking = False
            return
        if kind == "SPOTTED":  # truth: only cadets are told; everyone else may see a signal lamp in the scope
            if self.diff["ping_warning"]:
                brg = self.passive.bearing_of(a)
                self.banner = (f"SPOTTED BY {a.kind} {brg:03.0f}R!", 4.0)
                tt(f"INSTRUCTOR: LOOKOUTS ON THE {a.kind} AT {brg:03.0f}R HAVE SEEN YOUR "
                   f"{'MASTS' if b == 'both' else b.upper()}. GET DOWN.")
            return
        if kind == "PLAYER_HIT":
            self.audio.play_explosion(1.0)
            self.audio.play_creak(1.0)
            self.jolt(1.0)
            self.say("WE'RE HIT!")
            tt(f"TORPEDO HIT! HULL {world.hull:.0f}%.")
            return
        if kind == "CHARGE":
            loud = self.passive.loudness(a, ref=400.0)
            self.audio.play_explosion(loud)
            self.jolt(loud * 0.7)
            if b >= 1:
                self.audio.play_creak(1.0)
                self.say(f"CHARGE CLOSE. HULL {world.hull:.0f}%")
            return
        brg = self.passive.bearing_of(a)
        if isinstance(a, Torpedo) and a.hostile:
            if kind == "DECOYED":
                self.audio.play_explosion(self.passive.loudness(a))
                self.jolt(0.3)
                self.say(f"DETONATION {brg:05.1f}R. DECOY TOOK IT")
            return  # nothing else about their fish is observable
        if kind == "HOSTILE_LAUNCH":
            if self.passive.loudness(a, ref=6000.0) > 0.05:
                self.say(f"LAUNCH TRANSIENT {brg:05.1f}R!")
                tt(f"CONN, SONAR: TORPEDO IN THE WATER, BEARING {brg:03.0f} RELATIVE.")
        elif kind == "ESCORT_PING":
            self.audio.play_enemy_ping(self.passive.loudness(a, ref=5000.0))
            self.waterfall.blip(brg, 200)
            self.enemy_pings.append(((brg + world.player.heading) % 360, world.time))
            self.lamp_enemy = 1.5
            if self.diff["ping_warning"]:
                self.banner = (f"ENEMY SONAR {brg:03.0f}R - " + ("WE ARE HELD" if b else "NOT HELD"), 3.0)
        elif kind.startswith("AI_"):  # what a sonarman hears: revs, pinging, bearings drawing apart
            msg = {("ESCORT", "AI_ALERT"): "REVS UP, CLOSING" if b in ("PATROL", "SEARCH") else None,
                   ("ESCORT", "AI_ATTACK"): "FAST SCREWS CLOSING",
                   ("ESCORT", "AI_SEARCH"): "SEARCHING, ACTIVE SONAR",
                   ("ESCORT", "AI_PATROL"): "REVS DOWN",
                   ("MERCHANT", "AI_ALARMED"): "REVS UP, ZIG-ZAGGING",
                   ("MERCHANT", "AI_SCATTER"): "FULL REVS, TURNING AWAY",
                   ("MERCHANT", "AI_CRUISE"): "REVS DOWN, STEADY"}.get((a.kind, kind))
            if msg:
                self.say(f"CONTACT {brg:05.1f}R {msg}")
        elif kind == "CONVOY_ALARM":
            self.say(f"CONVOY {brg:05.1f}R REVS UP. ZIG-ZAG")
            tt("CONN, SONAR: CONVOY HAS WOKEN UP - REVS INCREASING, STARTING A ZIG-ZAG.")
        elif kind == "CONVOY_CALM":
            self.say(f"CONVOY {brg:05.1f}R REVS DOWN")
        elif kind == "CONVOY_SCATTER":
            self.say("CONVOY SCATTERING")
            tt("CONN, SONAR: CONVOY IS SCATTERING - CONTACTS FANNING OUT AT FULL REVS. ESCORTS WILL HUNT THE "
               "TORPEDO TRACK BACK TO US.")
        elif kind == "CHARGES":
            self.say(f"SPLASHES {brg:05.1f}R. CHARGES")
            tt("CONN, SONAR: DEPTH CHARGES IN THE WATER.")
        elif kind == "DECOY_DROP":
            self.audio.play_hiss(max(0.4, self.passive.loudness(a)))
            self.say(f"HISS {brg:05.1f}R. COUNTERMEASURE")
        elif kind in ("ARMED", "HOMING", "LOST"):
            self.say(f"T{a.tube} " + {"ARMED": "SEEKER ACTIVE", "HOMING": "HOMING", "LOST": "LOST LOCK"}[kind])
        elif kind == "EXHAUSTED":
            self.say(f"T{a.tube} FUEL OUT. " + ("DECOYED" if isinstance(b, Decoy) else "MISS"))
        elif kind in ("HIT", "DECOYED"):
            self.audio.play_explosion(self.passive.loudness(a, ref=4000.0))
            self.waterfall.blip(brg, 255)
            self.jolt(0.25)
            self.say(f"T{a.tube} DETONATION {brg:05.1f}R")
            if kind == "HIT":
                self.say("BREAKUP NOISES. SUNK")
                tt(f"CONFIRMED: {b.kind} SUNK. {self.score:,} GRT TOTAL.")
            else:
                self.say("NO BREAKUP. DECOYED")


# ---------- the physical workstation ----------
class Workstation:
    """Renders the brass-and-iron operator station around the console state."""

    def __init__(self):
        self.frame = pygame.Surface((W, H))
        self.crt_surf = pygame.Surface(CRT_RECT.size)
        self.crt = CRTRenderer(CRT_RECT.size)
        self.scope_surf = pygame.Surface((SCOPE_R * 2, SCOPE_R * 2))
        self.scope_crt = CRTRenderer(self.scope_surf.get_size(), ghost_decay=200)  # long-persistence PPI phosphor
        self.background = self._background()
        self.overlay = self._overlay()
        self.wheel = brass.ship_wheel(WHEEL_R)
        self.wheel_cache = {}
        self.paper = brass.texture(PAPER_RECT.size, brass.PAPER, grain=5, light=(1.05, 0.9))
        self.needles = {k: brass.Needle() for k in ("DEPTH", "BATTERY", "NOISE", "HULL", "O2", "ORDER")}
        self.title_buttons = []  # (screen rect, difficulty)
        self.periscope = PeriscopeRenderer()
        self.scope_bg = self._periscope_background()
        self.scope_surround = self.scope_bg.convert_alpha()  # same art with a round hole: hides the square corners
        x, y = np.ogrid[:W, :H]
        hole = np.hypot(x - EYEPIECE_C[0], y - EYEPIECE_C[1]) < EYE // 2 - 2
        alpha = pygame.surfarray.pixels_alpha(self.scope_surround)
        alpha[hole] = 0
        del alpha

    def _periscope_background(self):
        """The view from the eyepiece: dark trunk, brass eyepiece ring, training handles, engraved plates."""
        bg = brass.texture((W, H), (34, 34, 33), grain=4, light=(1.0, 0.8))
        cx, cy = EYEPIECE_C
        r = EYE // 2
        pygame.draw.circle(bg, brass.IRON_DARK, EYEPIECE_C, r + 34)
        pygame.draw.circle(bg, brass.BRASS_DARK, EYEPIECE_C, r + 26, 14)
        pygame.draw.circle(bg, brass.BRASS, EYEPIECE_C, r + 22, 6)
        pygame.draw.circle(bg, brass.BRASS_LIGHT, (cx - 3, cy - 3), r + 24, 2)
        for k in range(12):
            brass.rivet(bg, brass.polar(EYEPIECE_C, r + 26, k * 30 + 15), 4)
        for side in (-1, 1):  # training handles
            hx = cx + side * (r + 70)
            pygame.draw.rect(bg, brass.IRON_DARK, (hx - 22, cy - 20, 44, 40), border_radius=6)
            pygame.draw.rect(bg, brass.BRASS, (hx - 18 + side * 10, cy - 70, 26, 140), border_radius=10)
            pygame.draw.line(bg, brass.BRASS_LIGHT, (hx - 12 + side * 10, cy - 64), (hx - 12 + side * 10, cy + 64), 2)
        for rect in (pygame.Rect(30, 120, 230, 300), pygame.Rect(W - 260, 120, 230, 300)):
            brass.plate(bg, rect, brass.BRASS, spacing=200)
        brass.plaque(bg, (145, 136), "ATTACK PERISCOPE", 12)
        brass.plaque(bg, (W - 145, 136), "CONTROL ROOM", 12)
        keys = ("A / D  or drag   TRAIN", "TAB  or wheel   POWER", "M     MARK INTO TDC", "V     BACK TO STATION",
                "U     DOWN SCOPE")
        for i, line in enumerate(keys):
            brass.engrave(bg, line, (40, 440 + i * 20), 12, brass.BRASS_LIGHT, bold=False)
        return bg.convert()

    def draw_periscope(self, f, con, paused):
        p, w = con.world.player, con.world
        sightings, wakes, bursts = con.view if con.view else ([], [], [])
        fov = SCOPE_FOV[con.high_power]
        true_brg = (con.scope_brg + p.heading) % 360
        kt = p.speed / KNOT
        shake = max(0.0, kt - FEATHER_KT) * 0.8 + (1.0 if p.snorkeling else 0.0)
        view = View(true_brg, fov, con.optics.eye_height(), p.x, p.y, w.time, w.ocean, sightings, wakes, bursts,
                    under=con.view is None, shake=shake)
        f.blit(self.periscope.render(view), (EYEPIECE_C[0] - EYE // 2, EYEPIECE_C[1] - EYE // 2))
        f.blit(self.scope_surround, (0, 0))

        # left plate: where the scope points and what it last measured
        x, y = 48, 160
        rows = [("TRUE BRG", f"{true_brg:05.1f}"), ("REL BRG", f"{con.scope_brg:05.1f}"),
                ("POWER", "6 X" if con.high_power else "1.5X")]
        if con.scope_fix:
            brg, rng, t = con.scope_fix
            rows += [("LAST MARK", f"{(brg - p.heading) % 360:05.1f}"), ("RANGE YD", f"{rng / YARD:6,.0f}"),
                     ("AGE S", f"{w.time - t:4.0f}")]
        for i, (k, v) in enumerate(rows):
            brass.engrave(f, k, (x, y + i * 42), 12)
            brass.counter(f, (x + 100, y - 2 + i * 42), v, 14)
        # right plate: the boat, and how visible we are
        x = W - 248
        rows = [("DEPTH M", f"{p.z:5.1f}"), ("LENS  M", f"{max(0.0, SCOPE_TOP - p.z - p.wave):4.1f}"),
                ("SPEED KT", f"{kt:4.1f}"), ("BATTERY", f"{p.battery:4.0f}")]
        for i, (k, v) in enumerate(rows):
            brass.engrave(f, k, (x, y + i * 42), 12)
            brass.counter(f, (x + 110, y - 2 + i * 42), v, 14)
        risk = con.exposure
        brass.engrave(f, "EXPOSURE / MIN", (x, y + 4 * 42), 12, brass.INK_RED if risk > 0.25 else brass.INK)
        bar = pygame.Rect(x, y + 4 * 42 + 20, 150, 14)
        pygame.draw.rect(f, brass.IRON_DARK, bar)
        pygame.draw.rect(f, (200, 60, 30) if risk > 0.25 else (80, 170, 80), (bar.x, bar.y, int(bar.w * min(risk, 1.0)), bar.h))
        brass.engrave(f, f"{risk * 100:3.0f} %", (bar.right + 8, bar.y - 1), 12)
        if kt > FEATHER_KT:
            brass.engrave(f, "FEATHER! SLOW DOWN", (x, bar.bottom + 8), 12, brass.INK_RED)
        if p.snorkeling:
            brass.engrave(f, "DIESELS RUNNING - DEAF", (x, bar.bottom + 26), 12, brass.INK_RED)

        # warning strip: lamps you can still see from the scope, and the last thing sonar said
        pygame.draw.rect(f, brass.IRON_DARK, STRIP, border_radius=6)
        blink = int(w.time * 4) % 2 == 0
        lamps = (("TORPEDO", con.torpedo_warning and blink, (240, 50, 30)),
                 ("ENEMY SONAR", con.lamp_enemy > 0 and blink, (240, 170, 40)),
                 ("EXPOSED", risk > 0.25 and blink, (240, 50, 30)),
                 ("BROACH", p.broached and blink, (240, 50, 30)),
                 ("DIESEL", p.snorkeling, (80, 220, 90)))
        for i, (name, on, color) in enumerate(lamps):
            lx = STRIP.x + 20 + i * 132
            brass.lamp(f, (lx, STRIP.centery), on, color, 6)
            brass.engrave(f, name, (lx + 12, STRIP.y + 10), 11, brass.BRASS_LIGHT)
        line = con.log[-1] if con.log else ""
        if con.tutorial and not con.tutorial.finished:
            line = f"ORDER {con.tutorial.progress}: {con.tutorial.goal}"
        if con.banner[1] > 0:
            line = con.banner[0]
        brass.engrave(f, line, (STRIP.x + 690, STRIP.y + 10), 12, (236, 226, 200), bold=False)
        if paused:
            brass.plaque(f, EYEPIECE_C, "PAUSED  -  P TO RESUME", 16)

    def _background(self):
        bg = brass.texture((W, H), brass.WALL, grain=4)
        for rect, base in ((TDC_PANEL, brass.BRASS), (CONSOLE, brass.BRASS), (GAUGES, brass.BRASS),
                           (TELETYPE, brass.IRON)):
            brass.plate(bg, rect, base)
        for name, c in GAUGE_POS.items():
            face, fc = brass.gauge_face(GAUGE_R, **GAUGE_SPECS[name])
            bg.blit(face, (c[0] - fc[0], c[1] - fc[1]))
        face, fc = brass.telegraph_face(TELEGRAPH_R, [n for n, _ in TELEGRAPH])
        bg.blit(face, (TELEGRAPH_C[0] - fc[0], TELEGRAPH_C[1] - fc[1]))
        face, fc = brass.gauge_face(DEPTH_R, "", 0, 300, 50, 10, red=(CRUSH_DEPTH, 300))
        bg.blit(face, (DEPTH_C[0] - fc[0], DEPTH_C[1] - fc[1]))

        bottom = CONSOLE.bottom - 16
        brass.plaque(bg, (TELEGRAPH_C[0], bottom), "ENGINE TELEGRAPH")
        brass.plaque(bg, (WHEEL_C[0], bottom), "HELM")
        brass.plaque(bg, (DEPTH_C[0], bottom), "DIVING STATION")
        brass.plaque(bg, (712, CONSOLE.top + 14), "TORPEDO ROOM")
        brass.plaque(bg, (858, CONSOLE.top + 14), "WARNINGS")
        brass.plaque(bg, (TDC_PANEL.centerx, TDC_PANEL.top + 14), "TORPEDO DATA COMPUTER")
        brass.plaque(bg, (GAUGES.centerx, GAUGES.bottom - 14), "ENGINEERING")
        brass.plaque(bg, (TELETYPE.x + 70, TELETYPE.y + 18), "TELEPRINTER")
        for i, name in enumerate(LAMPS):
            brass.engrave(bg, name, (LAMP_X + 16, LAMP_Y0 + i * LAMP_DY - 7), 10)
        for i, (label, units, *_) in enumerate(FIELDS.values()):
            y = TDC_ROW_Y0 + i * TDC_ROW_H
            brass.engrave(bg, label, (30, y + 2), 12)
            brass.engrave(bg, units, (214, y + 3), 10, brass.INK_RED)
        brass.engrave(bg, "GYRO", (30, 430), 12)
        brass.engrave(bg, "RUN", (30, 448), 12)
        for i, (sx, sy) in enumerate(TUBE_SW):
            brass.engrave(bg, f"TUBE {i + 1}", (sx, sy - 34), 11, center=True)
        brass.engrave(bg, "TORPS", (650, 590), 10)
        brass.engrave(bg, "DECOYS", (718, 590), 10)
        brass.engrave(bg, "SCOPE", (SCOPE_LEVER[0], SCOPE_LEVER[1] - 36), 10, center=True)
        brass.engrave(bg, "SNORT", (SNORT_LEVER[0], SNORT_LEVER[1] - 36), 10, center=True)
        brass.engrave(bg, "L30", (RUDDER_BAR.left - 26, RUDDER_BAR.top - 2), 9)
        brass.engrave(bg, "R30", (RUDDER_BAR.right + 4, RUDDER_BAR.top - 2), 9)
        brass.engrave(bg, "WAVE", (TELETYPE.x + 150, TELETYPE.y + 10), 10, brass.BRASS_LIGHT)
        brass.engrave(bg, "GRT", (TELETYPE.x + 232, TELETYPE.y + 10), 10, brass.BRASS_LIGHT)
        return bg.convert()

    def _overlay(self):
        hole = pygame.Rect(0, 0, SCOPE_R * 2, SCOPE_R * 2)
        hole.center = SCOPE_C
        ov = brass.bezel_overlay((W, H), [(MONITOR, CRT_RECT, 26), (SCOPE_PANEL, hole, None)])
        for c in [*GAUGE_POS.values()]:
            g = brass.glint(GAUGE_R)
            ov.blit(g, (c[0] - g.get_width() / 2, c[1] - g.get_height() / 2))
        g = brass.glint(DEPTH_R)
        ov.blit(g, (DEPTH_C[0] - g.get_width() / 2, DEPTH_C[1] - g.get_height() / 2))
        brass.plaque(ov, (MONITOR.centerx, MONITOR.bottom - 13), "SONAR STATION No.1  -  HYDROPHONE ARRAY", 11)
        brass.plaque(ov, (SCOPE_C[0], SCOPE_PANEL.bottom - 12), "ACTIVE / TACTICAL", 10)
        return ov

    # --- frame ---
    def draw(self, screen, con, state, paused, show_help, dt):
        f = self.frame
        if con and con.looking and state == "PLAY":
            self.draw_periscope(f, con, paused)
        else:
            f.blit(self.background, (0, 0))
            self.draw_crt(con, state, paused)
            f.blit(self.crt_surf, CRT_RECT.topleft)
            self.draw_scope(con)
            f.blit(self.scope_surf, (SCOPE_C[0] - SCOPE_R, SCOPE_C[1] - SCOPE_R))
            if con:
                self.draw_needles(f, con, dt)
            f.blit(self.overlay, (0, 0))
            if con:
                self.draw_controls(f, con)
            self.draw_teletype(f, con)
            if con and con.tutorial and not con.tutorial.finished:
                self.draw_tutorial(f, con.tutorial)
        if show_help:
            self.draw_help(f)
        jitter = con.shake * 6 if con else 0
        screen.fill((0, 0, 0))
        screen.blit(f, (random.uniform(-jitter, jitter), random.uniform(-jitter, jitter)))

    # --- centre monitor ---
    def draw_crt(self, con, state, paused):
        s, crt = self.crt_surf, self.crt
        s.fill((0, 0, 0))
        if state == "TITLE" or con is None:
            self._crt_title(s, crt)
        else:
            self._crt_sonar(s, crt, con)
            if state == "OVER":
                self._crt_box(s, crt, ["LOST WITH ALL HANDS" if con.cause == "HULL BREACHED" else "CREW UNCONSCIOUS",
                                       con.cause, f"WAVE {con.wave}   {con.score:,} GRT SUNK", "",
                                       "[R] NEW PATROL     [ESC] QUIT"])
            elif paused:
                self._crt_box(s, crt, ["PATROL PAUSED", "", "[P] RESUME"])
            if con.flash > 0:
                v = int(140 * con.flash)
                s.fill((v, v, v), special_flags=pygame.BLEND_RGB_ADD)
        crt.apply_post_processing(s)

    def _crt_box(self, s, crt, lines):
        box = pygame.Rect(0, 0, 420, 40 + 26 * len(lines))
        box.center = (s.get_width() // 2, s.get_height() // 2)
        crt.rect(s, box, (0, 0, 0))
        crt.frame(s, box, color=PHOSPHOR)
        for i, line in enumerate(lines):
            crt.text(s, line, (box.centerx, box.y + 30 + i * 26), RED if i == 0 else PHOSPHOR, big=i == 0, center=True)

    def _crt_title(self, s, crt):
        cx = s.get_width() // 2
        crt.text(s, "SILENT SOLUTION", (cx, 62), PHOSPHOR, huge=True, center=True)
        crt.text(s, "SUBMARINE OPERATOR WORKSTATION", (cx, 98), DIM, center=True)
        options = (("TRAINING", "GUIDED DRILL: EVERY STATION, THEN LIVE EXERCISES"),
                   ("CADET", "CLEAR WARNINGS - SLOW ENEMY FISH - SHORE POWER"),
                   ("COMMANDER", "REAL ACOUSTICS - ZIG-ZAGS - DECOYS - BATTERY"),
                   ("IRON CAPTAIN", "CAVITATION HEARD - HOMING COUNTER-FIRE - LEAKS - O2"))
        self.title_buttons = []
        for i, (name, blurb) in enumerate(options):
            box = pygame.Rect(70, 124 + i * 58, 440, 50)
            crt.frame(s, box, color=PHOSPHOR)
            crt.text(s, f"[{i or 'T'}]  {name}", (box.x + 16, box.y + 6), PHOSPHOR, big=True)
            crt.text(s, blurb, (box.x + 16, box.y + 31), DIM, small=True)
            self.title_buttons.append((box.move(CRT_RECT.topleft), name))
        crt.text(s, "NEW? START WITH [T]  -  F1 STATION DRILL  -  ESC QUIT", (cx, 372), DIM, small=True, center=True)

    def _crt_sonar(self, s, crt, con):
        x0, y0 = WF_POS
        crt.text(s, "PASSIVE WATERFALL  BRG REL", (x0 + 14, 12), DIM, small=True)
        s.blit(con.waterfall.draw(), WF_POS)
        crt.frame(s, (x0 - 1, y0 - 1, WF_W + 2, WF_H + 2))
        for b in (0, 90, 180, 270, 359):
            crt.text(s, f"{b:03d}", (x0 + b / 360 * WF_W - 10, y0 + WF_H + 3), DIM, small=True)
        dx = x0 + con.dial / 360 * WF_W
        crt.line(s, (dx, y0), (dx, y0 + WF_H - 1), RED)
        tx = x0 + con.tdc.get("BRG") / 360 * WF_W  # TDC estimate tick: stays on the trace if TMA is right
        crt.line(s, (tx, y0 - 5), (tx, y0 + 8), PHOSPHOR, 2)
        crt.line(s, (tx, y0 + WF_H - 8), (tx, y0 + WF_H + 1), PHOSPHOR, 2)
        self._spectrum(s, crt, con)

        for i, msg in enumerate(con.log):
            crt.text(s, msg, (LOG_POS[0], LOG_POS[1] + i * 15), PHOSPHOR if i == len(con.log) - 1 else DIM, small=True)

        p, ocean, sp = con.world.player, con.world.ocean, con.spectrum
        lock = "LOCK" if con.signal > 0.5 else "WEAK" if con.signal > 0.15 else "NONE"
        cls = f"{CLASSES[sp.best]} {sp.confidence * 100:.0f}%" if sp.best is not None else "NO SIGNAL"
        sea = "STORM" if ocean.rain > 0.5 else "RAIN" if ocean.rain > 0.15 else "CALM"
        sol = con.tdc.solve()
        rows = [("HYD", f"{con.dial:05.1f} R", PHOSPHOR), ("SIG", lock, RED if lock == "LOCK" else PHOSPHOR),
                ("CLASS", cls, PHOSPHOR if sp.best is not None else DIM),
                ("LAYER", ("BELOW" if p.z >= ocean.layer_depth else "ABOVE") + f" {ocean.layer_depth:.0f}M", PHOSPHOR),
                ("SEA", sea + (f"  EXP {con.exposure * 100:.0f}%" if p.scope_up or p.snorkel_up else ""),
                 RED if sea == "STORM" or con.exposure > 0.25 else PHOSPHOR),
                ("SOLN", f"GYRO {sol.gyro:05.1f}" if sol else "NONE", PHOSPHOR if sol else RED)]
        hx, hy = HYD_POS
        for i, (k, v, color) in enumerate(rows):
            crt.text(s, k, (hx, hy + i * 19), DIM, small=True)
            crt.text(s, v, (hx + 52, hy + i * 19 - 1), color)
        crt.rect(s, (hx + 104, hy + 24, int(min(con.signal, 1.0) * 64), 5))

        text, left = con.banner
        if left > 0 and int(left * 4) % 2 == 0:  # cadet: clear visual ping warning
            crt.rect(s, (x0 + 10, y0 + 90, WF_W - 20, 34), (0, 0, 0))
            crt.frame(s, (x0 + 10, y0 + 90, WF_W - 20, 34), color=RED)
            crt.text(s, text, (x0 + WF_W / 2, y0 + 107), RED, big=True, center=True)

    def _spectrum(self, s, crt, con):
        r, sp = SPEC_RECT, con.spectrum
        crt.text(s, "ACOUSTIC PROFILE", (r.x, 12), DIM, small=True)
        crt.frame(s, r)
        for f, label in ((50, "50"), (200, "200"), (1000, "1K")):
            gx = r.x + math.log(f / 20) / math.log(100) * r.w
            crt.line(s, (gx, r.y + 1), (gx, r.bottom - 2), (12, 50, 24))
            crt.text(s, label, (gx - 8, r.bottom + 2), DIM, small=True)
        crt.text(s, "HZ", (r.right - 16, r.bottom + 2), DIM, small=True)
        ys = r.bottom - 2 - np.clip(sp.curve / 1.6, 0, 1) * (r.h - 6)
        xs = r.x + np.arange(SPEC_BINS) * (r.w - 1) / (SPEC_BINS - 1)
        crt.lines(s, list(zip(xs, ys)), PHOSPHOR, 2)
        cw = LIB_RECT.w // len(CLASSES)
        for i, name in enumerate(CLASSES):
            cell = pygame.Rect(LIB_RECT.x + i * cw, LIB_RECT.y, cw - 3, LIB_RECT.h - 14)
            hot = sp.best == i
            crt.frame(s, cell, color=PHOSPHOR if hot else DIM)
            tx = cell.x + 2 + np.arange(0, SPEC_BINS, 4) * (cell.w - 4) / SPEC_BINS
            ty = cell.bottom - 3 - TEMPLATES[i, ::4] * (cell.h - 6)
            crt.lines(s, list(zip(tx, ty)), PHOSPHOR if hot else DIM, 1)
            crt.text(s, CLASS_TAGS[i], (cell.centerx, cell.bottom + 7), PHOSPHOR if hot else DIM, small=True, center=True)

    # --- tactical scope ---
    def draw_scope(self, con):
        s, crt, R = self.scope_surf, self.scope_crt, SCOPE_R
        s.fill((0, 0, 0))
        c = (R, R)
        for k in (1, 2, 3, 4):
            crt.circle(s, c, (R - 6) * k / 4, (14, 60, 30))
        crt.line(s, (R, 6), (R, 2 * R - 6), (14, 60, 30))
        crt.line(s, (6, R), (2 * R - 6, R), (14, 60, 30))
        crt.text(s, "N", (R - 4, 8), DIM, small=True)
        if con:
            self._scope_contents(s, crt, con, c)
        crt.apply_post_processing(s)

    def _scope_contents(self, s, crt, con, c):
        R, world = SCOPE_R, con.world
        own = world.player
        scale = (R - 6) / (con.scope_range * YARD)

        def P(x, y):
            return c[0] + x * scale, c[1] - y * scale

        age = world.time - con.ping_time
        ring = SOUND_SPEED * age / 2 * scale  # echo arrives when the ring reaches the reflector
        if 0 < ring < R:
            crt.circle(s, c, ring, PHOSPHOR, 2)
        for ex, ey, t in con.echoes:
            fade = 1 - (world.time - t) / ECHO_FADE
            crt.circle(s, P(ex - own.x, ey - own.y), 3, (int(70 * fade), int(255 * fade), int(120 * fade)), 0)
        for brg, _ in con.enemy_pings:
            crt.line(s, c, P(math.sin(math.radians(brg)) * 1e6, math.cos(math.radians(brg)) * 1e6), RED, 2)
        tdc, sol = con.tdc, con.tdc.solve()
        vx, vy = tdc.target_velocity()
        ahead = sol.time * 1.3 if sol else 300.0
        crt.line(s, P(tdc.x - vx * 60, tdc.y - vy * 60), P(tdc.x + vx * ahead, tdc.y + vy * ahead), DIM)
        px, py = P(tdc.x, tdc.y)
        crt.rect(s, (px - 3, py - 3, 7, 7), PHOSPHOR, 1)
        if sol:
            ix, iy = sol.intercept
            crt.line(s, c, P(ix, iy), PHOSPHOR)
            qx, qy = P(ix, iy)
            crt.line(s, (qx - 3, qy - 3), (qx + 3, qy + 3), RED, 2)
            crt.line(s, (qx - 3, qy + 3), (qx + 3, qy - 3), RED, 2)
        for t in world.torpedoes:
            if not t.hostile:  # own fish only: wire telemetry
                crt.circle(s, P(t.x - own.x, t.y - own.y), 2, RED, 0)
        h = math.radians(own.heading)
        crt.circle(s, c, 3, PHOSPHOR)
        crt.line(s, c, (c[0] + 12 * math.sin(h), c[1] - 12 * math.cos(h)), PHOSPHOR, 2)
        crt.text(s, f"{con.scope_range:,.0f} YD", (R, 2 * R - 30), PHOSPHOR, small=True, center=True)

    # --- brass instruments ---
    def draw_needles(self, f, con, dt):
        p, world, nd = con.world.player, con.world, self.needles
        stress = 0.6 if p.z > CRUSH_DEPTH else 0.05
        values = {"DEPTH": (p.z, stress), "BATTERY": (p.battery, 0.15), "NOISE": (p.noise, 0.02 + 0.04 * p.cavitating),
                  "HULL": (world.hull, 0.1 + 0.2 * (world.hull < 50))}
        for name, (v, jitter) in values.items():
            spec, c = GAUGE_SPECS[name], GAUGE_POS[name]
            shown = nd[name].update(v, dt, jitter * (spec["hi"] - spec["lo"]) / 100)
            brass.needle(f, c, brass.value_angle(shown, spec["lo"], spec["hi"]), GAUGE_R - 20)
        if p.uses_oxygen:
            c = GAUGE_POS["BATTERY"]
            brass.needle(f, c, brass.value_angle(nd["O2"].update(p.o2, dt), 0, 100), GAUGE_R - 30, brass.INK_RED, 2)
            brass.engrave(f, "RED: O2", (c[0], c[1] - 26), 9, brass.INK_RED, center=True)
        dc = GAUGE_POS["DEPTH"]
        brass.counter(f, (dc[0] - 24, dc[1] + 46), f"{14.7 + p.z * 1.4228:4.0f}", 11)
        brass.engrave(f, "PSI", (dc[0] + 28, dc[1] + 49), 9, brass.INK_RED)
        brass.needle(f, DEPTH_C, brass.value_angle(nd["ORDER"].update(p.ordered_depth, dt), 0, 300), DEPTH_R - 16,
                     brass.INK_RED, 3)
        brass.needle(f, DEPTH_C, brass.value_angle(p.z, 0, 300), DEPTH_R - 22, brass.INK, 1, tail=6)

    def draw_controls(self, f, con):
        p, world = con.world.player, con.world
        blink = int(world.time * 4) % 2 == 0
        # telegraph handle
        idx = con.telegraph_index()
        tip = brass.polar(TELEGRAPH_C, TELEGRAPH_R - 16, brass.telegraph_angle(idx, len(TELEGRAPH)))
        pygame.draw.line(f, brass.BRASS_DARK, TELEGRAPH_C, tip, 9)
        pygame.draw.line(f, brass.BRASS_LIGHT, TELEGRAPH_C, tip, 3)
        pygame.draw.circle(f, brass.IRON_DARK, [int(v) for v in tip], 9)
        pygame.draw.circle(f, brass.BRASS, [int(v) for v in tip], 7)
        pygame.draw.circle(f, brass.BRASS, TELEGRAPH_C, 12)
        brass.engrave(f, f"{p.speed / KNOT:4.1f} KT", (TELEGRAPH_C[0], TELEGRAPH_C[1] + 22), 12, center=True)
        # helm
        angle = int(p.rudder * 4)
        if angle not in self.wheel_cache:
            self.wheel_cache[angle] = pygame.transform.rotate(self.wheel, -angle)
        w = self.wheel_cache[angle]
        f.blit(w, w.get_rect(center=WHEEL_C))
        pygame.draw.rect(f, brass.IRON_DARK, RUDDER_BAR)
        px = RUDDER_BAR.centerx + p.rudder / MAX_RUDDER * (RUDDER_BAR.w / 2 - 3)
        pygame.draw.line(f, brass.BRASS_LIGHT, (RUDDER_BAR.centerx, RUDDER_BAR.top), (RUDDER_BAR.centerx, RUDDER_BAR.bottom))
        pygame.draw.polygon(f, brass.INK_RED, [(px, RUDDER_BAR.top - 1), (px - 5, RUDDER_BAR.top - 8), (px + 5, RUDDER_BAR.top - 8)])
        side = "AMIDSHIPS" if abs(p.rudder) < 0.5 else f"{abs(p.rudder):.0f} {'RIGHT' if p.rudder > 0 else 'LEFT'}"
        brass.engrave(f, f"RUDDER {side}  HDG {p.heading:05.1f}", (WHEEL_C[0], RUDDER_BAR.bottom + 10), 11, center=True)
        # diving station
        holding = abs(p.ordered_depth - p.z) < 1 and not p.blowing
        brass.button(f, HOLD_BTN, "HOLD", lit=holding, color=(60, 140, 70))
        brass.button(f, BLOW_BTN, "BLOW", lit=p.blowing and blink)
        brass.button(f, PD_BTN, "P.D.", lit=abs(p.ordered_depth - PERISCOPE_DEPTH) < 0.5, color=(60, 110, 160))
        for (lx, ly), up, ready, color in ((SCOPE_LEVER, p.scope_up, p.z <= MAST_DEPTH, (240, 170, 40)),
                                           (SNORT_LEVER, p.snorkel_up, p.z <= MAST_DEPTH, (80, 220, 90))):
            brass.toggle(f, (lx, ly), up)
            brass.lamp(f, (lx, ly + 24), up or (ready and blink and con.tutorial is not None), color, 5)
        brass.button(f, LOOK_BTN, "LOOK", lit=p.scope_up, color=(160, 120, 40))
        if p.scope_damage > 0:
            brass.engrave(f, "JAMMED", (SCOPE_LEVER[0], SCOPE_LEVER[1] + 22), 9, brass.INK_RED, center=True)
        planes = "BLOWING" if p.blowing else "LEVEL" if holding else "DIVE" if p.ordered_depth > p.z else "RISE"
        brass.engrave(f, f"PLANES {planes}  ORD {p.ordered_depth:.0f} M", (DEPTH_C[0], HOLD_BTN.bottom + 10), 11, center=True)
        # torpedo room
        for i, (sx, sy) in enumerate(TUBE_SW):
            r = con.tubes[i]
            ready, empty = r == 0, r == math.inf
            brass.toggle(f, (sx, sy), ready)
            brass.lamp(f, (sx + 26, sy - 16), ready or (not empty and blink),
                       (80, 220, 90) if ready else (230, 160, 40), 6)
            state = "READY" if ready else "EMPTY" if empty else f"{r:2.0f} S"
            brass.engrave(f, state, (sx, sy + 34), 11, brass.INK_RED if empty else brass.INK, center=True)
        brass.counter(f, (650, 604), f"{p.torpedoes:02d}", 14)
        brass.counter(f, (718, 604), f"{p.noisemakers:02d}", 14)
        brass.button(f, NMKR_BTN, "NOISEMAKER  [N]")
        brass.button(f, PING_BTN, "ACTIVE PING  [SPACE]", lit=world.time - con.ping_time < 0.6)
        # warning lamps
        exposed = con.exposure > 0.25
        masts = p.scope_up or p.snorkel_up
        states = (con.lamp_enemy > 0 and blink, con.torpedo_warning and blink, p.cavitating, p.snorkeling,
                  masts and (blink or not exposed), p.broached and blink, bool(p.leaks),
                  p.z > CRUSH_DEPTH - 20 and blink, p.z >= world.ocean.layer_depth)
        colors = ((240, 170, 40), (240, 50, 30), (240, 170, 40), (80, 220, 90),
                  (240, 50, 30) if exposed else (240, 170, 40), (240, 50, 30), (240, 50, 30), (240, 50, 30),
                  (90, 170, 240))
        for i, (on, color) in enumerate(zip(states, colors)):
            brass.lamp(f, (LAMP_X, LAMP_Y0 + i * LAMP_DY), on, color, 6)
        # TDC
        for i, (name, (_, _, fmt, *_)) in enumerate(FIELDS.items()):
            y = TDC_ROW_Y0 + i * TDC_ROW_H
            if i == con.tdc.selected:
                pygame.draw.polygon(f, brass.INK_RED, [(16, y + 3), (16, y + 15), (25, y + 9)])
            brass.counter(f, (112, y), fmt.format(con.tdc.get(name)), 13)
        sol = con.tdc.solve()
        far = sol is not None and sol.run > TORP_MAX_RUN
        brass.counter(f, (112, 428), f"{sol.gyro:05.1f}" if sol else "---.-", 13)
        brass.counter(f, (112, 446), f"{sol.run / YARD:6,.0f}" if sol else "------", 13)
        brass.lamp(f, (238, 446), sol is not None, (240, 50, 30) if far else (80, 220, 90), 6)

    def draw_teletype(self, f, con):
        r = PAPER_RECT
        f.blit(self.paper, r.topleft)
        tt = con.teletype if con else None
        fed = tt.fed if tt else 0
        for k in range(0, r.h + 14, 14):  # tractor-feed perforations creep up as paper feeds
            y = r.bottom - ((k + fed * 7) % (r.h + 14))
            for x in (r.x + 9, r.right - 9):
                pygame.draw.circle(f, (150, 138, 108), (x, int(y)), 3)
        if tt:
            font = brass.mono(12)
            rows = (r.h - 16 - (ORDER_SLIP.h + 8 if con.tutorial else 0)) // 15
            lines = [*list(tt.lines)[-(rows - 1):], tt.typing]
            for i, line in enumerate(lines):
                f.blit(font.render(line, True, brass.INK), (r.x + 20, r.bottom - 12 - (len(lines) - i) * 15))
            if tt.queue and int(pygame.time.get_ticks() / 150) % 2:
                cx = r.x + 20 + font.size(tt.typing)[0]
                pygame.draw.rect(f, brass.INK, (cx, r.bottom - 27, 7, 12))
            brass.counter(f, (TELETYPE.x + 184, TELETYPE.y + 8), f"{con.wave:02d}", 13)
            brass.counter(f, (TELETYPE.x + 258, TELETYPE.y + 8), f"{con.score:6d}", 13)
        pygame.draw.rect(f, brass.IRON_DARK, r, 2)

    def draw_tutorial(self, f, tut):
        pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 160)
        color = (255, int(150 + 90 * pulse), 40)
        for name in tut.step.highlight:
            shape = HIGHLIGHTS[name]
            if isinstance(shape, pygame.Rect):
                pygame.draw.rect(f, color, shape, 3, border_radius=8)
            else:
                pygame.draw.circle(f, color, shape[0], shape[1], 3)
        slip = ORDER_SLIP
        pygame.draw.rect(f, (246, 238, 214), slip)
        pygame.draw.rect(f, brass.INK_RED, slip, 2)
        brass.engrave(f, f"ORDER {tut.progress}", (slip.x + 8, slip.y + 4), 11, brass.INK_RED)
        font = brass.mono(13, True)
        for i, line in enumerate(textwrap.wrap(tut.goal, 34)[:2]):
            f.blit(font.render(line, True, brass.INK), (slip.x + 8, slip.y + 22 + i * 17))

    def draw_help(self, f):
        card = pygame.Rect(0, 0, 600, 562)
        card.center = (W // 2, H // 2)
        f.blit(brass.texture(card.size, brass.PAPER, grain=5), card.topleft)
        pygame.draw.rect(f, brass.BRASS_DARK, card, 4)
        brass.engrave(f, "STATION DRILL", (card.centerx, card.y + 26), 20, center=True)
        rows = (("A / D", "hydrophone dial", "click waterfall / wheel"), ("M", "mark dial bearing into TDC", ""),
                ("W / S", "select TDC field", "click row"), ("UP / DOWN", "adjust TDC field", "mouse wheel"),
                ("LEFT / RIGHT", "rudder   (C amidships)", "drag the wheel"), ("Z / X", "engine telegraph", "click sector"),
                ("Q / E", "depth order -/+ 10 m", "click order dial"), ("H / B", "hold depth / blow ballast", "buttons"),
                ("SPACE", "active ping - reveals you", "button"), ("F  1  2", "fire next / tube 1 / tube 2", "tube switch"),
                ("N", "noisemaker decoy astern", "button"), ("T", "tactical scope range", "click scope"),
                ("G", "periscope depth (15 m)", "P.D. button"), ("U / K", "periscope / snorkel up-down", "levers"),
                ("V", "look through the periscope", "LOOK button"),
                ("A/D TAB M", "scope: train / power / mark", "drag / wheel"),
                ("P / F1 / ESC", "pause / this card / quit", ""))
        for i, (keys, what, mouse) in enumerate(rows):
            y = card.y + 58 + i * 26
            brass.engrave(f, keys, (card.x + 30, y), 13)
            brass.engrave(f, what, (card.x + 180, y), 13, bold=False)
            brass.engrave(f, mouse, (card.x + 420, y), 12, brass.INK_RED, bold=False)


def main():
    pygame.init()
    screen = pygame.display.set_mode((W, H), pygame.SCALED | pygame.RESIZABLE)
    pygame.display.set_caption("SILENT SOLUTION")
    clock = pygame.time.Clock()
    audio = AudioSynthesizer()
    station = Workstation()
    console, state, paused, show_help = None, "TITLE", False, False

    while True:
        dt = min(clock.tick(FPS) / 1000.0, 0.1)
        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                pygame.quit()
                return
            if e.type == pygame.KEYDOWN and e.key == pygame.K_F1:
                show_help = not show_help
            elif state == "TITLE":
                choice = None
                if e.type == pygame.KEYDOWN and e.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                    choice = list(DIFFICULTY)[e.key - pygame.K_1]
                elif e.type == pygame.KEYDOWN and e.key == pygame.K_t:
                    choice = "TRAINING"
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    choice = next((name for rect, name in station.title_buttons if rect.collidepoint(e.pos)), None)
                if choice == "TRAINING":
                    console, state = Console(choice, audio, TRAINING), "PLAY"
                    Tutorial(console)
                elif choice:
                    console, state = Console(choice, audio), "PLAY"
            elif state == "OVER":
                if e.type == pygame.KEYDOWN and e.key == pygame.K_r:
                    console, state = None, "TITLE"
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_p:
                paused = not paused
            elif not paused:
                if e.type == pygame.KEYDOWN:
                    console.key(e.key)
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    console.click(e.pos)
                elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                    console.dragging = None
                elif e.type == pygame.MOUSEMOTION and console.dragging:
                    console.drag(e.pos)
                elif e.type == pygame.MOUSEWHEEL:
                    console.scroll(pygame.mouse.get_pos(), e.y)
        if console and not paused:
            console.update(dt, pygame.key.get_pressed())
            if console.tutorial:
                console.tutorial.update(dt)
                if console.tutorial.finished:
                    console, state = None, "TITLE"
            elif console.dead and state == "PLAY":
                state = "OVER"
        station.draw(screen, console, state, paused, show_help, dt)
        pygame.display.flip()


if __name__ == "__main__":
    main()
