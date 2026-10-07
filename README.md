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
uv run checks.py          # every suite, headless
```

Or one at a time: `test_sim.py` (world, AI, masts, spotting, optics), `test_tutorial.py` (a scripted trainee
plays the whole training patrol), `test_periscope.py` (eyepiece renderer).

## Layout

World side (truth, never drawn directly):

| Path | What |
|---|---|
| `sim.py` | vessels, torpedoes, ocean and weather, masts, ship classes, the world step |
| `ai.py` | ship behaviour (merchants, escorts, submarines), convoys, the wave director |

Operator side (only sees the world through sensors):

| Path | What |
|---|---|
| `sensors.py` | passive and active sonar, periscope optics |
| `fire_control.py` | Torpedo Data Computer |
| `displays.py` | waterfall, acoustic profile analyser, teleprinter |
| `audio.py` | procedural sound |
| `console.py` | operator state, input and event reporting |
| `layout.py` | screen geometry |
| `workstation.py` | draws the station, CRTs and periscope eyepiece |
| `graphics/` | CRT post-processing, 1970s/80s control-room art kit, periscope renderer |
| `tutorial.py` | the training patrol |
| `main.py` | game loop and screen states |
