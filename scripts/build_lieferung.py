"""Assemble the delivery in auslieferung/ (gitignored): guide, plugin ZIP, user settings template, licences, and the
installers if given. Also writes the licences into app/src-tauri/resources/Lizenzen/ so the app bundle ships them.

Usage: python -I scripts/build_lieferung.py [folder with installers, e.g. the CI artifacts]
"""
import json
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "auslieferung"
INSTALLER = (".exe", ".dmg", ".msi")


def python_lizenzen() -> list[str]:
    """Licence of every package in the engine's virtual environment (the PyInstaller build bundles these)."""
    venv = ROOT / "engine" / ".venv"
    py = venv / "Scripts" / "python.exe" if (venv / "Scripts").is_dir() else venv / "bin" / "python"
    if not py.exists():  # CI: the engine packages are installed into the running interpreter (EGM B1)
        py = Path(sys.executable)
    code = ("import json;from importlib import metadata as m;print(json.dumps(sorted({(d.metadata['Name'], d.version, "
            "d.metadata.get('License-Expression') or d.metadata.get('License') or '') for d in m.distributions()})))")
    rows = json.loads(subprocess.run([str(py), "-I", "-c", code], capture_output=True, text=True, check=True).stdout)
    return [f"{n} {v}: {(l or 'siehe Paket').splitlines()[0][:120]}" for n, v, l in rows]


def npm_lizenzen() -> list[str]:
    lock = json.loads((ROOT / "app" / "package-lock.json").read_text(encoding="utf-8"))
    out = []
    for name, info in sorted(lock["packages"].items()):
        if name.startswith("node_modules/") and not info.get("dev"):
            out.append(f"{name.removeprefix('node_modules/')} {info.get('version', '')}: {info.get('license', 'siehe Paket')}")
    return out


def lizenzen(ziel: Path) -> None:
    ziel.mkdir(parents=True, exist_ok=True)
    for font in ("inter", "source-serif-4"):  # SIL Open Font License, shipped with the fonts
        src = ROOT / "app" / "node_modules" / "@fontsource" / font / "LICENSE"
        if not src.is_file():  # the fonts are bundled, so their licence must be too (EGM B1): npm ci first
            raise SystemExit(f"Lizenz der Schrift {font} fehlt: zuerst npm ci in app/")
        shutil.copyfile(src, ziel / f"Schrift-{font}-OFL.txt")
    (ziel / "Python-Pakete.txt").write_text("\n".join(python_lizenzen()) + "\n", encoding="utf-8")
    (ziel / "App-Pakete.txt").write_text("\n".join(npm_lizenzen()) + "\n", encoding="utf-8")
    (ziel / "LIESMICH.txt").write_text(
        "Schlomo und Adelheid steht unter Apache-2.0. Gebündelte Programme behalten ihre Lizenzen: Tauri (MIT oder "
        "Apache-2.0), PDFium (BSD-3-Clause, über pypdfium2), Tesseract (Apache-2.0), NSIS (zlib), spaCy und das "
        "Sprachmodell (MIT). Die Listen in diesem Ordner nennen jedes Paket mit Version und Lizenz.\n", encoding="utf-8")


def main() -> int:
    OUT.mkdir(exist_ok=True)
    lizenzen(OUT / "Lizenzen")
    lizenzen(ROOT / "app" / "src-tauri" / "resources" / "Lizenzen")
    shutil.copyfile(ROOT / "docs" / "anleitung.md", OUT / "Anleitung.md")
    shutil.copyfile(ROOT / "arbeitsordner" / "benutzer-einstellungen.json", OUT / "benutzer-einstellungen.json")
    subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "build_plugin.py")], check=True)
    if len(sys.argv) > 1:
        for f in Path(sys.argv[1]).rglob("*"):
            if f.suffix.lower() in INSTALLER:
                shutil.copyfile(f, OUT / f.name)
    found = sorted(p.name for p in OUT.iterdir() if p.suffix.lower() in INSTALLER)
    print("Lieferung in", OUT)
    print("Installer:", ", ".join(found) if found else "keine (Build nur im CI des öffentlichen Repos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
