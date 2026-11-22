"""PyInstaller build of the engine (one program, start types ui, mcp and hook, --onedir), portable instead of the
earlier generated spec with absolute paths. Output: <out>/engine/engine.exe

Usage: python -I scripts/build_pyinstaller.py [out folder, default auslieferung/pyinstaller]
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLLECT_ALL = ("spacy", "de_core_news_md", "thinc", "blis", "srsly", "cymem", "preshed", "murmurhash", "pypdfium2",
               "pypdfium2_raw", "pillow_heif", "pikepdf")


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "auslieferung" / "pyinstaller"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir", "--name", "engine",
           "--paths", str(ROOT / "engine" / "src"),
           "--add-data", f"{ROOT / 'contracts'}{os.pathsep}contracts",
           # template of the Code-Tab working folder for the first start (Task 4.6, engine function einrichten)
           "--add-data", f"{ROOT / 'arbeitsordner'}{os.pathsep}arbeitsordner",
           "--collect-submodules", "mcp",
           "--distpath", str(out), "--workpath", str(out / "build"), "--specpath", str(out / "build")]
    for name in COLLECT_ALL:
        cmd += ["--collect-all", name]
    cmd.append(str(ROOT / "engine" / "pyinstaller_entry.py"))
    return subprocess.run(cmd, cwd=ROOT).returncode


if __name__ == "__main__":
    sys.exit(main())
