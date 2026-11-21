"""Configuration the psychologist maintains (regelwerk, testkatalog, kategorienskala, icd10-referenz), validated against
contracts/. The engine ships none: a missing file means the related rules yield "nicht_pruefbar", nothing is guessed."""
import json
import os
from dataclasses import dataclass
from pathlib import Path

from .contracts import validate
from .errors import EngineError

FILES = {"regelwerk": "regelwerk.json", "testkatalog": "testkatalog.json",
         "kategorienskala": "kategorienskala.json", "icd10-referenz": "icd10-referenz.json"}


@dataclass
class Config:
    regelwerk: dict | None
    testkatalog: dict | None
    kategorienskala: dict | None
    icd10: dict | None

    def version(self, name: str) -> str:
        doc = {"regelwerk": self.regelwerk, "testkatalog": self.testkatalog}[name]
        return doc["version"] if doc else "nicht_konfiguriert"

    def test(self, testkatalog_id: str | None) -> dict | None:
        if not testkatalog_id or not self.testkatalog:
            return None
        return next((e for e in self.testkatalog["eintraege"] if e["id"] == testkatalog_id), None)

    def rules_for(self, gutachtentyp: str) -> list[dict]:
        if not self.regelwerk:
            return []
        return [r for r in self.regelwerk["regeln"] if gutachtentyp in r["gutachtentyp"] and r["status"] != "ausser_kraft"]

    def icd_exists(self, code: str) -> bool:
        return bool(self.icd10) and any(c["code"] == code for c in self.icd10["codes"])


def config_dir() -> Path | None:
    return Path(os.environ["SCHLOMO_KONFIGURATION"]) if os.environ.get("SCHLOMO_KONFIGURATION") else None


def check_scale(skala: dict) -> None:
    """Scale entries of the same scale and procedure set must neither overlap nor be reversed (kategorienskala.schema)."""
    groups: dict[tuple, list] = {}
    for e in skala["eintraege"]:
        if e["von"] > e["bis"]:
            raise EngineError("E_SCHEMA", "schema")
        groups.setdefault((e["skala"], tuple(sorted(e.get("verfahren", [])))), []).append(e)
    for entries in groups.values():
        entries.sort(key=lambda e: e["von"])
        for a, b in zip(entries, entries[1:]):
            if b["von"] <= a["bis"]:
                raise EngineError("E_SCHEMA", "schema")


def load(directory: Path | None = None) -> Config:
    directory = directory or config_dir()
    docs = {}
    for name, filename in FILES.items():
        path = directory / filename if directory else None
        if path is None or not path.exists():
            docs[name] = None
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        validate(name, doc)
        docs[name] = doc
    if docs["kategorienskala"]:
        check_scale(docs["kategorienskala"])
    return Config(docs["regelwerk"], docs["testkatalog"], docs["kategorienskala"], docs["icd10-referenz"])
