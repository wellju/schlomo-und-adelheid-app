"""Build the engine for delivery without an own .exe (replaces the PyInstaller build).

Windows Smart App Control blocks an unsigned program it does not know, such as the PyInstaller engine.exe (Task 1,
EGM E28). The official embeddable Python is signed by the Python Software Foundation; the engine's own code is .py
files, and the wheels' libraries ran on a machine with Smart App Control on. So the bundle is:

    <out>/python/   official embeddable Python (unchanged, plus Lib/site-packages and a python314._pth)
    <out>/app/      schlomo_engine and contracts/

Start: <out>/python/python.exe -m schlomo_engine ui|mcp|hook

Packages are copied from engine/.venv, file by file from each distribution's RECORD, for exactly the runtime
dependencies of engine/pyproject.toml and their dependencies, plus the NER model de_core_news_md. Test and build
tools stay out. Nothing is downloaded.

Usage: python -I scripts/build_engine.py <python-3.14.x-embed-amd64.zip> [out folder, default auslieferung/engine]
"""
import re
import shutil
import sys
import tomllib
import zipfile
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = "de_core_news_md"


def runtime_distributions() -> list[metadata.Distribution]:
    """Runtime dependencies of the engine and everything they require, evaluated for this interpreter, including
    the dependencies of requested extras (mcp needs PyJWT[crypto], so cryptography)."""
    from packaging.requirements import Requirement
    deps = tomllib.loads((ROOT / "engine" / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    todo = [(Requirement(d).name, frozenset(Requirement(d).extras)) for d in deps] + [(MODEL, frozenset())]
    seen, out = set(), {}
    while todo:
        raw_name, extras = todo.pop()
        name = re.sub(r"[-_.]+", "-", raw_name).lower()
        if (name, extras) in seen:
            continue
        seen.add((name, extras))
        dist = out.setdefault(name, metadata.distribution(name))
        for raw in dist.requires or []:
            req = Requirement(raw)
            wanted = req.marker is None or any(req.marker.evaluate({"extra": e}) for e in ("", *extras))
            if wanted:
                todo.append((req.name, frozenset(req.extras)))
    return list(out.values())


def copy_distribution(dist: metadata.Distribution, site: Path) -> int:
    count = 0
    for f in dist.files or []:
        src = Path(dist.locate_file(f))
        rel = Path(f)
        if ".." in rel.parts or not src.is_file() or "__pycache__" in rel.parts:
            continue  # scripts outside site-packages (bin/) and caches are not needed
        dst = site / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        count += 1
    return count


def main() -> int:
    embed = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "auslieferung" / "engine"
    shutil.rmtree(out, ignore_errors=True)
    py = out / "python"
    with zipfile.ZipFile(embed) as z:
        z.extractall(py)
    pth = next(py.glob("python3*._pth"))
    zipname = next(py.glob("python3*.zip")).name
    # "import site" processes the .pth files in Lib/site-packages (pywin32 needs them); with a ._pth file Python
    # still ignores PYTHONPATH and the user's site-packages (checked by tests/smoke_frozen.py)
    pth.write_text(f"{zipname}\n.\nLib\\site-packages\n..\\app\nimport site\n", encoding="utf-8")
    site = py / "Lib" / "site-packages"
    site.mkdir(parents=True)
    dists = runtime_distributions()
    files = sum(copy_distribution(d, site) for d in dists)
    app = out / "app"
    shutil.copytree(ROOT / "engine" / "src" / "schlomo_engine", app / "schlomo_engine",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "contracts", app / "contracts", ignore=shutil.ignore_patterns("tests"))
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    names = sorted(d.metadata["Name"] for d in dists)
    print(f"{out}: {len(dists)} Pakete, {files} Dateien, {size / 1e6:.0f} MB")
    print("Pakete:", ", ".join(names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
