"""Procedural audio: every sound is synthesised from NumPy buffers at start-up."""
import random

import numpy as np
import pygame


SAMPLE_RATE = 44100


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
