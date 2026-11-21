"""Fallspeicher: one JSON file per session (fallspeicher.schema.json) in the app data folder, never inside the
working folder (ADR 0001, Durchsetzung im Code)."""
import hashlib
import json
import os
import re
import secrets
import time
from contextlib import contextmanager
from pathlib import Path

from platformdirs import user_data_dir

from .contracts import validate
from .errors import EngineError

_SESSION_ID = re.compile(r"^s-[0-9a-f]{8}$")


def data_dir() -> Path:
    base = Path(os.environ["SCHLOMO_DATA_DIR"]) if os.environ.get("SCHLOMO_DATA_DIR") \
        else Path(user_data_dir("SchlomoUndAdelheid", appauthor=False)) / "fallspeicher"
    base = base.resolve()
    working = [Path.cwd().resolve()]
    if os.environ.get("SCHLOMO_ARBEITSORDNER"):
        working.append(Path(os.environ["SCHLOMO_ARBEITSORDNER"]).resolve())
    if any(base == w or w in base.parents for w in working):
        raise EngineError("E_BLOCKIERT", "datenordner")
    base.mkdir(parents=True, exist_ok=True)
    return base


def _path(session_id: str) -> Path:
    if not _SESSION_ID.match(session_id):
        raise EngineError("E_SCHEMA", "argumente")
    return data_dir() / f"{session_id}.json"


class Record(dict):
    """A loaded record remembers the digest of the file it came from; save refuses if the file changed meanwhile,
    so ui and mcp (separate processes) never overwrite each other's newer state (EGM E09)."""
    digest: str | None = None


def _digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


@contextmanager
def _lock(target: Path, timeout: float = 5.0):
    lock = target.with_suffix(".lock")
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > 30:  # stale lock of a crashed process
                    lock.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() > deadline:
                raise EngineError("E_BLOCKIERT", "konflikt")
            time.sleep(0.02)
    try:
        yield
    finally:
        os.close(fd)
        lock.unlink(missing_ok=True)


def save(record: dict) -> None:
    validate("fallspeicher", record)
    target = _path(record["session"]["session_id"])
    data = json.dumps(record, ensure_ascii=False)
    with _lock(target):
        if isinstance(record, Record) and _digest(target) != record.digest:
            raise EngineError("E_BLOCKIERT", "konflikt")
        tmp = target.with_suffix(".tmp")
        tmp.write_text(data, encoding="utf-8")
        os.replace(tmp, target)  # atomic, so a crash never leaves a half-written record
    if isinstance(record, Record):
        record.digest = hashlib.sha256(data.encode("utf-8")).hexdigest()


def load(session_id: str) -> Record:
    path = _path(session_id)
    if not path.exists():
        raise EngineError("E_NICHT_GEFUNDEN")
    raw = path.read_bytes()
    record = Record(json.loads(raw.decode("utf-8")))
    record.digest = hashlib.sha256(raw).hexdigest()
    return record


def all_records() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(data_dir().glob("s-*.json"))]  # pakete-s-*.json excluded


def write_atomic(target: Path, data: bytes) -> None:
    tmp = target.with_name(f".{target.name}.{secrets.token_hex(4)}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, target)


def write_new(target: Path, data: bytes) -> None:
    """Write a file that must not exist yet: complete or not at all, never overwriting (EGM E60)."""
    tmp = target.with_name(f".{target.name}.{secrets.token_hex(4)}.tmp")
    tmp.write_bytes(data)
    try:
        os.link(tmp, target)  # fails if target exists; no window between check and write
    except FileExistsError:
        raise EngineError("E_BLOCKIERT") from None
    except OSError:  # file systems without hard links
        try:
            with open(target, "xb") as f:
                f.write(data)
        except FileExistsError:
            raise EngineError("E_BLOCKIERT") from None
    finally:
        tmp.unlink(missing_ok=True)
