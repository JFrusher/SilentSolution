"""Run every check suite headlessly. Run: uv run checks.py"""
import os
import subprocess
import sys
import time

SUITES = ("test_sim.py", "test_tutorial.py", "test_periscope.py", "settings.py", "audio.py")

if __name__ == "__main__":
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    failed = []
    for suite in SUITES:
        t0 = time.perf_counter()
        result = subprocess.run([sys.executable, suite], env=env, capture_output=True, text=True)
        status = "ok" if result.returncode == 0 else "FAILED"
        print(f"{suite:20s} {status:6s} {time.perf_counter() - t0:5.1f} s")
        if result.returncode:
            failed.append(suite)
            print(result.stdout[-2000:], result.stderr[-2000:], sep="\n")
    sys.exit(1 if failed else 0)
