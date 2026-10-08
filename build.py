"""Build the single-file Windows executable: uv run --with pyinstaller build.py  ->  dist/SilentSolution.exe
The licence and third-party notices are copied next to it; ship the whole dist/ folder."""
import shutil
import sys
from importlib.metadata import distribution
from pathlib import Path

import PyInstaller.__main__

sys.path.insert(0, "src")
from version import __version__  # noqa: E402

PyInstaller.__main__.run(["src/main.py", "--onefile", "--windowed", "--clean", "--noconfirm",
                          "--name", "SilentSolution", "--exclude-module", "tkinter"])
dist = Path("dist")
for name in ("LICENSE", "THIRD-PARTY-NOTICES.txt"):
    shutil.copy(name, dist / name)
numpy = distribution("numpy")
for f in numpy.files:
    if "/licenses/" in str(f).replace("\\", "/"):
        out = dist / "licenses" / "numpy" / str(f).replace("\\", "/").split("/licenses/", 1)[1]
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(numpy.locate_file(f), out)
print(f"built dist/SilentSolution.exe  v{__version__}, with LICENSE, THIRD-PARTY-NOTICES.txt and licenses/")
