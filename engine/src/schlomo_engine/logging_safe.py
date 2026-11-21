"""Logging per Nachtrag 1: only event type, time, counters, error code and technical IDs (s-, d-, p-, bf-).
Anything else is dropped, so document or input text can never reach a log line."""
import json
import re
import sys
import time

_ID = re.compile(r"^(s|d|p|bf|r)-[0-9a-z]{1,16}$")
_EVENT = re.compile(r"^[a-z_]{1,40}$")
_ALLOWED_KEYS = {"count", "code", "session_id", "dok_id", "paket_id", "befund_id", "request_id", "dauer_ms"}


def _safe(key: str, value) -> bool:
    if key not in _ALLOWED_KEYS:
        return False
    if key in ("count", "dauer_ms"):
        return isinstance(value, int) and not isinstance(value, bool)
    if key == "code":
        from .errors import CODES
        return value in CODES
    return isinstance(value, str) and bool(_ID.match(value))


def log(event: str, stream=None, **fields) -> None:
    """Write one log line to stderr. Unknown keys and values that are not IDs, counts or codes are dropped."""
    if not _EVENT.match(event):
        event = "ungueltiges_ereignis"
    line = {"t": round(time.time(), 3), "event": event}
    line.update({k: v for k, v in fields.items() if _safe(k, v)})
    print(json.dumps(line), file=stream or sys.stderr, flush=True)
