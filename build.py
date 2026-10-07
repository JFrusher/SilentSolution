"""Build the single-file Windows executable: uv run --with pyinstaller build.py  ->  dist/SilentSolution.exe"""
import PyInstaller.__main__

from version import __version__

PyInstaller.__main__.run(["main.py", "--onefile", "--windowed", "--clean", "--noconfirm",
                          "--name", "SilentSolution", "--exclude-module", "tkinter"])
print(f"built dist/SilentSolution.exe  v{__version__}")
