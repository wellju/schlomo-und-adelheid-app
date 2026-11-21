"""Technical IDs as in contracts/ (prefix plus 8 hex digits)."""
import secrets


def new_id(prefix: str) -> str:
    if prefix not in ("s", "d", "p", "bf", "f", "ls", "pg"):
        raise ValueError(prefix)
    return f"{prefix}-{secrets.token_hex(4)}"
