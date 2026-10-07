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

Start with **[T] TRAINING** on the title screen: four chapters that walk through every station (F6 skips a
drill). **[C] CAMPAIGN** is six patrols with briefings, ranks and refits; **[1]-[3]** are endless patrols.
**[S] SETTINGS** sets volumes, keys, mouse feel, large text and colour-blind lamps. **F1** shows the key card in
game. The game can be played entirely with the sound off: every audio cue has a lamp, a log line or a picture.

Settings, the career and high scores live in `~/.silent_solution/`. If the game crashes, the traceback is
appended to `~/.silent_solution/crash.log`.

## Build

```
uv run --with pyinstaller build.py   # -> dist/SilentSolution.exe, one file, no console
```

## Checks

```
uv run checks.py          # every suite, headless
```

Or one at a time: `test_sim.py` (world, AI, masts, spotting, optics, damage, wire), `test_tutorial.py` (a
scripted trainee plays the whole training patrol, each chapter alone, and a skip-everything run),
`test_periscope.py` (eyepiece renderer); `settings.py`, `audio.py` and `campaign.py` self-check when run.

## Layout

World side (truth, never drawn directly):

| Path | What |
|---|---|
| `sim.py` | vessels, torpedoes, ocean and weather, masts, damage and repairs, ship classes, the world step |
| `ai.py` | ship behaviour (merchants, escorts, submarines), convoys, the wave director |

Operator side (only sees the world through sensors):

| Path | What |
|---|---|
| `sensors.py` | passive and active sonar, periscope optics |
| `fire_control.py` | Torpedo Data Computer |
| `tma.py` | bearing history, TMA fit and auto-solve |
| `displays.py` | waterfall, acoustic profile analyser, teleprinter |
| `audio.py` | procedural sound |
| `console.py` | operator state, input and event reporting |
| `layout.py` | screen geometry |
| `settings.py` | volumes, key bindings, mouse, large text, colour-blind lamps (`~/.silent_solution/settings.json`) |
| `workstation.py` | draws the station, CRTs and periscope eyepiece |
| `graphics/` | CRT post-processing, 1970s/80s control-room art kit, periscope renderer |
| `tutorial.py` | the training patrol |
| `campaign.py` | six patrols, debriefs, ranks, refits, career save, patrol log and high scores (`~/.silent_solution/career.json`) |
| `main.py` | game loop and screen states, crash log |
| `version.py` | version shown on the title |
| `build.py` | PyInstaller one-file build |
