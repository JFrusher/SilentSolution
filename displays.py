"""Console displays with state: passive waterfall, acoustic profile analyser, teleprinter."""
import math
import textwrap
from collections import deque

import numpy as np
import pygame

from layout import WF_H, WF_W
from settings import SETTINGS

ROW_INTERVAL = 0.1        # sim seconds per waterfall row


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
    _template((50, 1.0, .03), (300, .3, .03), floor=.05, slope=.5),                              # one faint narrow line
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

    def __init__(self, audio, cps=34.0):
        self.audio, self.cps = audio, cps
        self.lines = deque(maxlen=40)
        self.queue = deque()
        self.typing = ""
        self.acc = 0.0
        self.fed = 0  # lines fed through, for the paper's perforations

    def print(self, text):
        self.queue.extend(textwrap.wrap(text, 30 if SETTINGS["large_text"] else 38) + [""])

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
            b, lv, w = np.array(self.blips).T
            bearings, levels, widths = (np.concatenate(p) for p in ((bearings, b), (levels, lv), (widths, w)))
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
