"""External programs: Tesseract (OCR, via stdin/stdout, no files) and LibreOffice (DOC and XLS only)."""
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .errors import EngineError

_DEFAULTS = {
    "tesseract": [r"C:\Program Files\Tesseract-OCR\tesseract.exe", "/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract"],
    "soffice": [r"C:\Program Files\LibreOffice\program\soffice.exe",
                "/Applications/LibreOffice.app/Contents/MacOS/soffice"],
}


def find(program: str, env_var: str) -> str | None:
    if os.environ.get(env_var):
        return os.environ[env_var]
    return shutil.which(program) or next((p for p in _DEFAULTS[program] if Path(p).exists()), None)


def ocr_png(png: bytes) -> str:
    exe = find("tesseract", "SCHLOMO_TESSERACT")
    if not exe:
        raise EngineError("E_OCR_FEHLT")
    proc = subprocess.run([exe, "stdin", "stdout", "-l", "deu"], input=png, capture_output=True, timeout=300)
    if proc.returncode != 0:
        raise EngineError("E_INTERN")
    return proc.stdout.decode("utf-8", errors="replace")


_PREFIX = "sua-"


def _remove(path: Path) -> None:
    """Delete a temp folder even while a just-killed soffice still holds a file (Windows); retry, never raise."""
    for _ in range(50):
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return
        time.sleep(0.1)


def _kill_tree(proc: subprocess.Popen) -> None:
    if os.name == "nt":  # soffice.exe starts soffice.bin as child; kill both
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.kill()
    proc.wait()


def cleanup_stale() -> int:
    """Remove conversion folders left behind by a crashed engine (called at start of startart ui, EGM E16)."""
    # older than the conversion timeout, so a second running engine keeps its folder
    stale = [p for p in Path(tempfile.gettempdir()).glob(f"{_PREFIX}*")
             if p.is_dir() and time.time() - p.stat().st_mtime > 600]
    for p in stale:
        _remove(p)
    return len(stale)


def libreoffice_convert(raw: bytes, src_ext: str, target: str) -> bytes:
    """Convert DOC to DOCX or XLS to XLSX.
    shortcut: LibreOffice needs files, so clear text touches the disk for seconds in a private temp folder that is
    deleted in finally, also after a timeout, and swept at the next start after a crash; upgrade to a pipe-based
    converter if one becomes available."""
    exe = find("soffice", "SCHLOMO_SOFFICE")
    if not exe:
        raise EngineError("E_LIBREOFFICE_FEHLT")
    tmp_path = Path(tempfile.mkdtemp(prefix=_PREFIX))
    try:
        src = tmp_path / f"in.{src_ext}"
        src.write_bytes(raw)
        profile = (tmp_path / "profil").as_uri()  # own profile: no clash with a running LibreOffice, no user macros
        proc = subprocess.Popen([exe, f"-env:UserInstallation={profile}", "--headless", "--norestore",
                                 "--convert-to", target, "--outdir", str(tmp_path / "out"), str(src)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            proc.wait(timeout=180)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            raise EngineError("E_INTERN") from None
        out = tmp_path / "out" / f"in.{target}"
        if proc.returncode != 0 or not out.exists():
            raise EngineError("E_INTERN")
        return out.read_bytes()
    finally:
        _remove(tmp_path)
