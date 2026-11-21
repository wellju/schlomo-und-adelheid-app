"""Build the chat plugin: copy the dual-mode skills from arbeitsordner/ into plugin/skills/, then zip plugin/ to
auslieferung/schlomo-und-adelheid-plugin.zip (local only, gitignored). Refuses a top-level bin/ (the chat rejects
it, ADR 0002) and any file that is not plugin.json or a SKILL.md.

Usage: python -I scripts/build_plugin.py
"""
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin"
SHARED = ("gutachten", "stil-lernen")  # same skill in Code-Tab and chat; the source lives in arbeitsordner/


def sync() -> None:
    for name in SHARED:
        target = PLUGIN / "skills" / name
        target.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "arbeitsordner" / ".claude" / "skills" / name / "SKILL.md", target / "SKILL.md")


def files() -> list[Path]:
    found = sorted(p for p in PLUGIN.rglob("*") if p.is_file())
    bad = [p for p in found if p.relative_to(PLUGIN).parts[0] == "bin"
           or (p.name != "SKILL.md" and p.relative_to(PLUGIN).as_posix() != ".claude-plugin/plugin.json")]
    if bad:
        raise SystemExit(f"Abbruch, nicht erlaubt im Plugin: {[str(p.relative_to(PLUGIN)) for p in bad]}")
    return found


def main() -> int:
    sync()
    out = ROOT / "auslieferung" / "schlomo-und-adelheid-plugin.zip"
    out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files():
            z.write(p, p.relative_to(PLUGIN).as_posix())
    print(f"{out.relative_to(ROOT)}: {len(files())} Dateien")
    return 0


if __name__ == "__main__":
    sys.exit(main())
