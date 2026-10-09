"""Run every check suite headlessly. Run: uv run checks.py"""
import os
import subprocess
import sys
import tempfile
import time

SUITES = ("tests/test_sim.py", "tests/test_geometry.py", "tests/test_tutorial.py", "tests/test_periscope.py",
          "tests/test_ui.py", "tests/test_golden.py", "tests/test_room.py", "tests/test_crew.py", "tests/test_board.py",
          # and these modules self-check:
          "src/geometry.py", "src/settings.py", "src/audio.py", "src/campaign.py", "src/replay.py",
          "src/control_room.py", "src/stations.py",
          "-m graphics.tabletop", "-m graphics.gltf")
LINT = ("-m", "ruff", "check", ".")  # ruff is a dev dependency: uv run installs it

if __name__ == "__main__":
    home = tempfile.mkdtemp(prefix="silent-checks-")  # suites save settings, careers and replays: never the player's
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy", PYTHONPATH="src",  # flat game imports
               HOME=home, USERPROFILE=home)
    failed = []
    for suite in (*SUITES, "lint"):
        t0 = time.perf_counter()
        args = LINT if suite == "lint" else suite.split()
        result = subprocess.run([sys.executable, *args], env=env, capture_output=True, text=True)
        status = "ok" if result.returncode == 0 else "FAILED"
        print(f"{suite:26s} {status:6s} {time.perf_counter() - t0:5.1f} s")
        if result.returncode:
            failed.append(suite)
            print(result.stdout[-2000:], result.stderr[-2000:], sep="\n")
    sys.exit(1 if failed else 0)
