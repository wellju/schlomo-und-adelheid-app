"""Transient derivations (Nachtrag 1): age J;M, norm group, age of the norms on the test day, months of school in
Austria, and the category of a value. Dates are used for the call only and never stored."""
from datetime import date

from .config import Config


def age(birth: date, test_day: date) -> dict:
    if test_day < birth:
        raise ValueError("test day before birth")
    months = (test_day.year - birth.year) * 12 + (test_day.month - birth.month) - (test_day.day < birth.day)
    return {"jahre": months // 12, "monate": months % 12, "abgeleitet": True}


def months_between(start: date, end: date) -> int:
    if end < start:
        raise ValueError("end before start")
    return (end.year - start.year) * 12 + (end.month - start.month) - (end.day < start.day)


def _months(a: dict) -> int:
    return a["jahre"] * 12 + a["monate"]


def norm_group(entry: dict, child_age: dict) -> dict | None:
    """The child's norm group from the catalogue (Nachtrag 1: norm group of the child). None if not covered."""
    for g in entry.get("normgruppen", []):
        if _months(g["von"]) <= _months(child_age) <= _months(g["bis"]):
            return {"von": g["von"], "bis": g["bis"], "abgeleitet": True}
    return None


def norm_age_years(entry: dict, test_day: date) -> int:
    """Age of the norms on the test day from the norming year in the manual (not the publication year)."""
    return test_day.year - entry["normjahr"]


def category(cfg: Config, value: float, skala: str, testkatalog_id: str | None) -> dict:
    """Category from kategorienskala; the LLM never chooses one. Missing scale or range: a gap, never a guess."""
    if not cfg.kategorienskala:
        return {"kategorie_luecke": "Kategorienskala fehlt"}
    matches = [e for e in cfg.kategorienskala["eintraege"]
               if e["skala"] == skala and e["von"] <= value <= e["bis"]
               and (not e.get("verfahren") or testkatalog_id in e["verfahren"])]
    if not matches:
        return {"kategorie_luecke": "kein Bereich der Kategorienskala passt"}
    # A procedure-specific entry wins over a general one for the same scale.
    best = sorted(matches, key=lambda e: not e.get("verfahren"))[0]
    return {"kategorie": best["bezeichnung"], "status": best["status"]}
