# Silent Solution

A submarine sonar and fire-control simulator. You never see the ocean, only the instruments: a passive
waterfall, an acoustic profiler, active sonar, a torpedo data computer, brass gauges and a teleprinter.
Raise the periscope and you can look, but every second the mast is up you can be seen.

## Run

```
uv run main.py
```

Requires Python 3.11+. Dependencies (`pygame-ce`, `numpy`) are installed by uv. Every sound and every image is
generated in code; there are no asset files.

Start with **[T] TRAINING** on the title screen, which walks through every station. **F1** shows the full key
card in game. The game can be played entirely with the sound off: every audio cue has a lamp, a log line or a
picture.

## Checks

```
uv run test_sim.py        # world, AI, masts, spotting, optics
uv run test_tutorial.py   # a scripted trainee plays the whole training patrol
uv run test_periscope.py  # eyepiece renderer
```

## Layout

| Path | What |
|---|---|
| `sim.py` | hidden world: vessels, torpedoes, ocean, masts, the world step |
| `ai.py` | ship behaviour (merchants, escorts, submarines), convoys, the wave director |
| `main.py` | operator console, sensors, TDC, audio, workstation rendering, game loop |
| `tutorial.py` | the training patrol |
| `graphics/` | CRT post-processing, procedural brass/paper art, periscope renderer |
| `docs/plans/` | design plans |
