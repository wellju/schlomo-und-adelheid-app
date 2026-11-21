"""Schema registry over contracts/*.schema.json (draft 2020-12, cross references by $id)."""
import json
import os
import sys
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from .errors import EngineError


def contracts_dir() -> Path:
    if env := os.environ.get("SCHLOMO_CONTRACTS"):
        return Path(env)
    if getattr(sys, "frozen", False):  # PyInstaller bundle: contracts are shipped as data
        return Path(sys._MEIPASS) / "contracts"
    # src/schlomo_engine/contracts.py -> repo root is three levels above src/
    return Path(__file__).resolve().parents[3] / "contracts"


@lru_cache(maxsize=1)
def _registry() -> tuple[dict, Registry]:
    schemas = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in contracts_dir().glob("*.schema.json")}
    if not schemas:
        raise RuntimeError("no contract schemas found")
    return schemas, Registry().with_resources([(n, Resource.from_contents(s)) for n, s in schemas.items()])


def validate(name: str, instance, definition: str | None = None) -> None:
    """Raise EngineError(E_SCHEMA) if instance does not satisfy contracts/<name>.schema.json, or its $defs entry."""
    schemas, registry = _registry()
    schema = {"$ref": f"{name}.schema.json#/$defs/{definition}"} if definition else schemas[f"{name}.schema.json"]
    validator = Draft202012Validator(schema, registry=registry)
    if next(validator.iter_errors(instance), None) is not None:
        raise EngineError("E_SCHEMA", "schema")


def schema_versions() -> dict[str, str]:
    schemas, _ = _registry()
    return {n.removesuffix(".schema.json"): s.get("properties", {}).get("schema_version", {}).get("const", "")
            for n, s in sorted(schemas.items())}
