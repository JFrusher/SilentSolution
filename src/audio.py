"""Procedural audio: every sound is synthesised from NumPy buffers at start-up.
Sounds from the sea are panned by bearing; sounds inside the boat ring through a convolved steel hull;
every buffer is normalised to its category's RMS so the volume sliders mix like with like."""
import math
import random

import numpy as np
import pygame

from settings import volume

SAMPLE_RATE = 44100
MIX_RMS = {"SONAR": 0.16, "EFFECTS": 0.2, "AMBIENCE": 0.14}  # buffer loudness per category before play strength
HULL_WET = 0.4   # reverb share on interior sounds
PAN_WIDTH = 0.8  # how hard a beam bearing pans (1 = one ear only)


# ---------- procedural audio ----------
def sweep_phase(f0, f1, dur, t):
    """Phase of an exponential frequency sweep f0 -> f1 over dur seconds."""
    k = f1 / f0
    return 2 * np.pi * f0 * dur / np.log(k) * (k ** (t / dur) - 1)


def lowpass(wave, taps):
    return np.convolve(wave, np.ones(taps) / taps, "same")


def rms(wave):
    return max(float(np.sqrt(np.mean(wave ** 2))), 1e-9)


def normalise(wave, target):
    """Scale to a target RMS, then pull the peak back under full scale."""
    wave = wave * target / rms(wave)
    return wave / max(1.0, np.abs(wave).max() / 0.98)


def pan_gains(rel_brg):
    """(left, right) gains for a relative bearing: ahead and astern centre, the beams to one side."""
    p = PAN_WIDTH * math.sin(math.radians(rel_brg))
    return min(1.0, 1 - p), min(1.0, 1 + p)


def hull_ir(rate, dur=0.9):
    """Impulse response of the pressure hull: a few ringing steel modes over a diffuse low tail."""
    t = np.arange(int(rate * dur)) / rate
    ring = ((96, 0.35), (151, 0.28), (233, 0.2), (347, 0.14))  # Hz, decay s
    modes = sum(np.sin(2 * np.pi * f * t) * np.exp(-t / d) for f, d in ring)
    ir = 0.5 * modes + lowpass(np.random.uniform(-1, 1, t.size), 8) * np.exp(-t / 0.2)
    return ir / np.sqrt(np.sum(ir ** 2))


def reverb(wave, ir, wet=HULL_WET, loop=False):
    """FFT convolution. A loop wraps its tail round (circular convolution) so it still loops without a seam."""
    n = wave.size if loop else wave.size + ir.size - 1
    size = n if loop else 1 << (n - 1).bit_length()
    tail = np.fft.irfft(np.fft.rfft(wave, size) * np.fft.rfft(ir[:size], size), size)[:n]
    dry = np.pad(wave, (0, n - wave.size))
    return (1 - wet) * dry + wet * tail * rms(wave) / rms(tail)


class AudioSynthesizer:
    def __init__(self):
        try:
            pygame.mixer.init(SAMPLE_RATE, -16, 2, 512)
        except pygame.error:
            self.enabled = False  # no audio device: run silent; every cue also has a visual
            return
        self.enabled = True
        pygame.mixer.set_num_channels(32)
        pygame.mixer.set_reserved(3)  # channels 0-2 belong to the loops: one-shots can't steal them
        self.rate, _, self.channels = pygame.mixer.get_init()
        self.ir = hull_ir(self.rate)
        ping = self._ping_wave()
        self.ping = self._sound(ping, "SONAR")
        self.echo = self._sound(ping, "SONAR", 0.5)
        self.enemy_ping = self._sound(self._ping_wave(950.0, 900.0, 0.9), "SONAR")  # flat ASDIC tone, not our sweep
        self.explosion = self._sound(self._explosion_wave())
        self.hiss = self._sound(self._hiss_wave())
        rush = lowpass(np.random.uniform(-1, 1, int(self.rate * 3)), 30) * np.exp(-0.5 * self._t(3))
        self.blow = self._sound(reverb(rush, self.ir))
        self.clack = self._sound(np.random.uniform(-1, 1, int(self.rate * 0.02)) * np.exp(-300 * self._t(0.02)) * 0.5)
        self.creaks = [self._sound(reverb(self._creak_wave(f), self.ir)) for f in (38.0, 52.0, 67.0, 85.0)]
        self.thrum_channel = self._loop(0, self._sound(self._thrum_wave(), "SONAR"))
        self.thrum_channel.set_volume(0.0)
        t = self._t(1.2)  # hydraulic mast ram: a rising whine over a hiss
        self.mast = self._sound(reverb((np.sin(sweep_phase(180.0, 320.0, 1.2, t)) * 0.6
                                        + lowpass(np.random.uniform(-1, 1, t.size), 6) * 0.5)
                                       * np.minimum(1.0, t / 0.1) * np.minimum(1.0, (1.2 - t) / 0.2), self.ir))
        t = self._t(0.4)
        thunk = (0.9 * np.sin(2 * np.pi * 55 * t) * np.exp(-14 * t)
                 + 0.3 * lowpass(np.random.uniform(-1, 1, t.size), 40) * np.exp(-20 * t))
        self.thunk = self._sound(reverb(thunk, self.ir))
        t = self._t(1.6)  # klaxon: a raw square-ish horn sliding down, twice ("aa-oo-ga")
        horn = np.tanh(4 * np.sin(sweep_phase(520.0, 380.0, 0.8, t % 0.8))) * (np.sin(np.pi * (t % 0.8) / 0.8) ** 0.3)
        self.klaxon = self._sound(reverb(horn * 0.5, self.ir))
        t = self._t(2.0)  # diesel: 25 Hz firing pulses (whole cycles in 2 s -> seamless) through the hull
        chug = np.maximum(0, np.sin(2 * np.pi * 25 * t)) ** 4 - 0.25
        diesel = reverb(lowpass(chug + 0.3 * np.random.uniform(-1, 1, t.size), 12), self.ir, loop=True)
        self.diesel_channel = self._loop(1, self._sound(diesel, "AMBIENCE"))
        self.diesel_channel.set_volume(0.0)
        t = self._t(4.0)  # surface: wind hiss with slow wave slaps
        slap = 0.5 + 0.5 * np.sin(2 * np.pi * 0.5 * t) ** 8
        surface = lowpass(np.random.uniform(-1, 1, t.size), 8) * slap
        self.surface_channel = self._loop(2, self._sound(surface, "AMBIENCE"))
        self.surface_channel.set_volume(0.0)

    @staticmethod
    def _loop(index, sound):
        ch = pygame.mixer.Channel(index)
        ch.play(sound, loops=-1)
        return ch

    def _sound(self, wave, category="EFFECTS", level=1.0):
        pcm = (np.clip(normalise(wave, MIX_RMS[category] * level), -1, 1) * 32767).astype(np.int16)
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

    def _play(self, name, strength, category="EFFECTS", rel_brg=None):
        """name: the sound's attribute, looked up only with audio on (silent, none are made); a list plays one at
        random. rel_brg: where it is outside the hull, for the pan; None plays it centred (inside the boat)."""
        if self.enabled:
            sound = getattr(self, name)
            ch = (random.choice(sound) if isinstance(sound, list) else sound).play()
            if ch:
                v = float(np.clip(strength, 0.05, 1.0)) * volume(category)
                left, right = pan_gains(rel_brg) if rel_brg is not None else (1.0, 1.0)
                ch.set_volume(v * left, v * right)

    def play_ping(self):
        self._play("ping", 1.0, "SONAR")

    def play_echo(self, strength, rel_brg=None):
        self._play("echo", strength, "SONAR", rel_brg)

    def play_enemy_ping(self, strength, rel_brg=None):
        self._play("enemy_ping", strength, "SONAR", rel_brg)

    def play_explosion(self, strength, rel_brg=None):
        self._play("explosion", strength, rel_brg=rel_brg)

    def play_hiss(self, strength, rel_brg=None):
        self._play("hiss", strength, rel_brg=rel_brg)

    def play_blow(self):
        self._play("blow", 0.8)

    def play_clack(self):
        self._play("clack", 0.06)

    def play_creak(self, strength):
        self._play("creaks", strength)

    def set_hydrophone(self, signal, rel_brg=0.0):
        """The trained hydrophone in the headphones: louder on a contact, panned to where the dial points."""
        if self.enabled:
            v = float(np.clip(0.03 + signal, 0.0, 1.0)) * volume("SONAR")
            left, right = pan_gains(rel_brg)
            self.thrum_channel.set_volume(v * left, v * right)

    def play_mast(self):
        self._play("mast", 0.6)

    def play_klaxon(self):
        self._play("klaxon", 0.8)

    def play_thunk(self):
        self._play("thunk", 0.8)

    def set_diesel(self, running):
        if self.enabled:
            self.diesel_channel.set_volume((0.55 if running else 0.0) * volume("AMBIENCE"))

    def set_surface(self, looking, sea_state):
        if self.enabled:
            self.surface_channel.set_volume((0.15 + 0.08 * sea_state if looking else 0.0) * volume("AMBIENCE"))


if __name__ == "__main__":  # self-check: mix levels, pan law, reverb lengths and seamless loops
    w = np.random.uniform(-1, 1, 4000)
    assert abs(rms(normalise(w, 0.2)) - 0.2) < 1e-6 and np.abs(normalise(w * 50, 0.9)).max() <= 0.98 + 1e-9
    assert pan_gains(0) == (1.0, 1.0) and pan_gains(90)[0] < 0.3 < pan_gains(90)[1] == 1.0
    ir = hull_ir(SAMPLE_RATE)
    assert reverb(w, ir).size == w.size + ir.size - 1
    hum = np.sin(2 * np.pi * 50 * np.arange(8820) / SAMPLE_RATE)  # whole cycles: a seamless loop
    out = reverb(hum, ir, loop=True)
    assert out.size == hum.size and abs(out[0] - out[-1]) < 0.1, (out[0], out[-1])
    silent = AudioSynthesizer.__new__(AudioSynthesizer)  # as made with no audio device: no sounds at all
    silent.enabled = False
    silent.play_klaxon(), silent.play_creak(0.5), silent.play_echo(0.5, 30.0)
    print("audio ok")
