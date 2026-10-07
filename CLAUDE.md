# Silent Solution - Development Context

## Project Constraints
- **Language:** Python 3.11+
- **Primary Libraries:** Pygame-ce, NumPy
- **Execution:** Always use `uv run main.py` for testing (on this machine `uv` lives at `.venv/Scripts/uv.exe`)
- **Checks:** `uv run test_sim.py`, `uv run test_tutorial.py`, `uv run test_periscope.py` (headless; set `SDL_VIDEODRIVER=dummy` for ad-hoc scripts)
- **Git:** git flow — `main` releases, `develop` integration, `feature/*` merged into `develop` with `--no-ff`

## Core Architecture
- Keep **World Simulation** state decoupled from **Operator UI Rendering**.
- Use delta time (`dt`) for all positional/kinematic updates.
- All CRT vector rendering must route through `graphics/crt_renderer.py`.

## Audio Guidelines
- Synthesize sonar pings procedurally via `NumPy` audio buffers before falling back to external `.wav` assets.