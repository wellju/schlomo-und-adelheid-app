"""JSON-lines channel of start type ui (docs/ui-api.md): one request per line on stdin, one answer per line on
stdout, progress events in between. Answers never echo request content; errors carry only a code."""
import json
import sys
import time
from dataclasses import dataclass
from typing import Callable

from . import ram
from .errors import EngineError
from .logging_safe import log
from .ui_functions import FUNCTIONS


@dataclass
class Context:
    request_id: str
    _write: Callable[[dict], None]

    def emit(self, event: dict) -> None:
        self._write({**event, "id": self.request_id})


def _fail(req_id, code, reason=None) -> dict:
    return {"id": req_id, "ok": False, "fehler": EngineError(code, reason).as_dict()}


def handle(line: str, write: Callable[[dict], None] = lambda m: None) -> tuple[dict, bool]:
    """Process one input line. Returns (answer, stop). Events go through write before the answer."""
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        log("anfrage_ungueltig", code="E_SCHEMA")
        return _fail(None, "E_SCHEMA", "json"), False
    req_id = msg.get("id") if isinstance(msg, dict) and isinstance(msg.get("id"), str) else None
    fn = msg.get("fn") if isinstance(msg, dict) else None
    args = msg.get("args", {}) if isinstance(msg, dict) else {}
    if req_id is None or not isinstance(args, dict):
        return _fail(req_id, "E_SCHEMA", "argumente"), False
    if fn == "beenden":
        ram.clear()
        log("beenden")
        return {"id": req_id, "ok": True, "result": {}}, True
    func = FUNCTIONS.get(fn)
    if func is None:
        log("funktion_unbekannt", code="E_NICHT_GEFUNDEN")
        return _fail(req_id, "E_NICHT_GEFUNDEN", "unbekannte_funktion"), False
    t0 = time.perf_counter()
    try:
        result = func(args, Context(req_id, write))
    except EngineError as e:
        log("anfrage_fehler", code=e.code)
        return {"id": req_id, "ok": False, "fehler": e.as_dict()}, False
    except Exception:  # never leak exception text, it may contain input
        log("anfrage_fehler", code="E_INTERN")
        return _fail(req_id, "E_INTERN"), False
    log("anfrage_ok", dauer_ms=int((time.perf_counter() - t0) * 1000))
    return {"id": req_id, "ok": True, "result": result}, False


def serve(stdin=None, stdout=None) -> None:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout

    def write(message: dict) -> None:
        stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
        stdout.flush()

    log("start_ui")
    try:
        for line in stdin:
            if not line.strip():
                continue
            answer, stop = handle(line, write)
            write(answer)
            if stop:
                break
    finally:
        ram.clear()
        log("ende_ui")
