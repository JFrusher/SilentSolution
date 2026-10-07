# Backlog: ten consolidation and feature items

**Agreed:**
- Git flow by hand (`main` holds releases, `develop` integrates, `feature/*` branches merge in with `--no-ff`, then push).
- Python 3.11+.
- All 10 items without stopping.
- Era: keep the WWII / early Cold War mix.
- Campaign and endless as separate modes.
- System damage with one repair queue (no compartments).
- Single-file Windows `.exe`.
- Wire guidance steered by clicking on the tactical scope.

**Build order:** 1, 2, 3, 4, 5, 6, 8, 9, 7, 10. Small fixes are folded in where they fit.

| # | Branch | Scope |
|---|---|---|
| 1 | `feature/project-cleanup` | Commit existing work; `.gitignore` keeps `CLAUDE.md` + `uv.lock`; drop the template `src/` package and its entry point; `requires-python >= 3.11`; CLAUDE.md commands |
| 2 | `feature/split-main` | `main.py` → `layout`, `sensors`, `fire_control`, `displays`, `audio`, `console`, `workstation` modules (no behaviour change); ship dimensions defined once in `sim.py`; `checks.py` runs every suite |
| 3 | `feature/debug-tuning` | F3 debug overlay (fps, true contacts, AI states); `tuning.py` holds the balance knobs (difficulty, spotting, AI timings, waves); wave time limit |
| 4 | `feature/tma-plot` | CRT page: bearing history (dial locks, marks, scope marks, echoes) against the TDC's predicted bearing curve, a fit-quality readout, and auto-solve on Cadet / Training |
| 5 | `feature/spreads-wire` | SPRD TDC field fans a salvo across the ready tubes; wire-guided fish steered by clicking the tactical scope (select fish, then aim point), `[` `]` nudge, `L` cuts; the wire breaks at speed or at its length |
| 6 | `feature/damage-control` | Systems: hydrophones, active sonar, planes, rudder, tube 1/2, periscope, snorkel, battery, motors; hits damage some of them; one repair party works a priority list on a DAMAGE CRT page |
| 8 | `feature/settings-access` | Settings screen (volumes by category, key rebinding, mouse sensitivity, large text, colour-blind lamps), saved as JSON in the user's home folder |
| 9 | `feature/audio-pass` | Stereo pan by bearing (one-shots and hydrophone), FFT hull reverb on interior sounds, RMS-normalised mix by category |
| 7 | `feature/campaign` | Six patrols with objectives and briefings, debrief, ranks, upgrades, save file, patrol log and high scores (endless included) |
| 10 | `feature/packaging` | PyInstaller one-file `.exe`, crash log, version and credits on the title, tutorial chapter select and skip-drill |

Each item ends with every check suite passing, screenshots for UI items, then commit → merge into `develop` → push.
