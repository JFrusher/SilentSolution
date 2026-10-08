# Silent Solution - Development Context

## Project Constraints
- **Language:** Python 3.11+
- **Primary Libraries:** Pygame-ce, NumPy
- **Execution:** Always use `uv run src/main.py` for testing (on this machine `uv` lives at `.venv/Scripts/uv.exe`)
- **Checks:** `uv run checks.py` runs every suite headless plus `ruff check` (lint only, line length 120; set `SDL_VIDEODRIVER=dummy` for ad-hoc scripts)
- **Layout:** game modules live flat in `src/` (they import each other by bare name); suites in `tests/`; `checks.py` sets `PYTHONPATH=src`
- **Determinism:** the patrol tick rolls only `sim.DICE` / `sim.NP_DICE` (seeded per patrol); drawing and audio use their own generators. `tests/test_golden.py` replays a seeded patrol against `tests/golden/<platform>.json`; regenerate with `uv run tests/test_golden.py --update` (with `PYTHONPATH=src`) only when a change is meant to alter play
- **3D control room:** `src/control_room.py` (layout, walking, camera moves; no GL) and `src/graphics/room3d.py` (moderngl, procedural meshes, offscreen then read back into pygame). Needs OpenGL: on a headless box run checks under `xvfb-run -a`
- **Models:** the control room's consoles (and crew) are `.glb` files under `assets/`, built in code by `src/graphics/models.py`, not kept in git (built when missing at start; force all with `uv run src/graphics/models.py`, `PYTHONPATH=src`) and read by `src/graphics/gltf.py`; `assets/README.md` says how to drop in a better model
- **Git:** git flow — `main` releases, `develop` integration, `feature/*` merged into `develop` with `--no-ff`

## Core Architecture
- Keep **World Simulation** state decoupled from **Operator UI Rendering**.
- Use delta time (`dt`) for all positional/kinematic updates.
- All CRT vector rendering must route through `src/graphics/crt_renderer.py`.

## Audio Guidelines
- Synthesize sonar pings procedurally via `NumPy` audio buffers before falling back to external `.wav` assets.