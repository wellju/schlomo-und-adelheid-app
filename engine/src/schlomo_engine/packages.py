"""Case packages (fallpaket.schema.json) and their returns (rueckgabe.schema.json), ADR 0002. The same package
contents feed the MCP tools of start type mcp. Never contained: internal diagnosis, awmf_* results, severity,
file names, clear text. This module must not import recognition (start type mcp)."""
import json
import os
import re
from pathlib import Path

from . import belege, derive, rules, store
from .config import Config
from .contracts import validate
from .errors import EngineError
from .ids import new_id

ARTEN = {"gutachten": "gutachten-output", "pruefung_stil": "befunde", "pruefung_goldfisch": "befunde",
         "pruefung_elefant": "befunde", "diagnosevorschlag": "diagnosevorschlag", "stil_lernen": "stilprofil",
         "hypothese": "befunde"}
PRUEFER = {"pruefung_stil": "stil", "pruefung_goldfisch": "goldfisch", "pruefung_elefant": "elefant",
           "hypothese": "goldfisch"}


def q1(gi: dict | None) -> bool:
    return bool(gi) and "klinische_psychologin" in gi.get("verfasserin", {}).get("qualifikationen", [])


# ---------------------------------------------------------------- local folders

def _dir(env: str, default: Path) -> Path:
    path = Path(os.environ[env]) if os.environ.get(env) else default
    path.mkdir(parents=True, exist_ok=True)
    return path


def vorlagen_dir() -> Path:
    return _dir("SCHLOMO_VORLAGEN", store.data_dir().parent / "wissensbasis" / "vorlagen")


def wissensbasis_dir() -> Path:
    return _dir("SCHLOMO_WISSENSBASIS", store.data_dir().parent / "wissensbasis")


def stilprofile_dir() -> Path:
    return _dir("SCHLOMO_STILPROFILE", store.data_dir().parent / "stilprofile")


def wissen(name: str) -> str:
    """haltung.md, goldfisch-kriterien.md or a file from the guidelines; only names, never paths."""
    if not re.fullmatch(r"[\w-]+\.md", name or ""):
        raise EngineError("E_SCHEMA", "argumente")
    path = wissensbasis_dir() / name
    if not path.is_file():
        raise EngineError("E_NICHT_GEFUNDEN")
    return path.read_text(encoding="utf-8")


def _version_key(version: str) -> list:
    """Natural order, so "10" comes after "9" (EGM E36)."""
    return [(0, int(x), "") if x.isdigit() else (1, 0, x) for x in re.findall(r"\d+|\D+", version)]


def released_stilprofil() -> dict | None:
    profiles = [json.loads(p.read_text(encoding="utf-8")) for p in stilprofile_dir().glob("*.json")]
    released = [p for p in profiles if p["status"] == "freigegeben"]
    return max(released, key=lambda p: _version_key(p["version"])) if released else None


def stilprofil_fuer_claude(profil: dict) -> dict:
    """Features and phrasing examples without the sample quotes: they come from reports of other cases and are not
    needed to write or review a draft (stilprofil.schema.json#/$defs/fuer_claude, EGM Task 2 E30)."""
    return {"schema_version": profil["schema_version"], "version": profil["version"],
            "merkmale": [{k: m[k] for k in ("merkmal_id", "kategorie", "beschreibung")} for m in profil["merkmale"]],
            "formulierungsbeispiele": profil["formulierungsbeispiele"]}


def free_version(wanted: str) -> str:
    """The wanted version if no profile has it, else the next free "v<n>". A chat cannot see the stored versions,
    so its return names "v1" (Task 2.5); the MCP path keeps refusing an existing version instead."""
    taken = {p.stem for p in stilprofile_dir().glob("*.json")}
    if re.sub(r"[^\w.-]", "_", wanted) not in taken:
        return wanted
    numbers = [int(m[1]) for name in taken if (m := re.fullmatch(r"v(\d+)", name))]
    return f"v{max(numbers, default=0) + 1}"


def save_stilprofil(profil: dict) -> dict:
    """A returned profile is always a new draft: status entwurf, never over an existing version, written whole
    (listen.md: release only in the app; EGM E36)."""
    profil = profil | {"status": "entwurf"}
    validate("stilprofil", profil)
    store.write_new(stilprofile_dir() / f"{re.sub(r'[^\w.-]', '_', profil['version'])}.json",
                    json.dumps(profil, ensure_ascii=False).encode("utf-8"))
    return profil


# ---------------------------------------------------------------- contents

PROBEGUTACHTEN = "Probegutachten"  # quelle_rolle of sample reports for /stil-lernen (docs/ui-api.md)

def _vorlage_for(gi: dict) -> dict:
    metas = [json.loads(p.read_text(encoding="utf-8")) for p in vorlagen_dir().glob("*.json")]
    wanted = [m for m in metas if (m["vorlage_id"] == gi.get("vorlage_id")) or
              (not gi.get("vorlage_id") and m["gutachtentyp"] == gi["gutachtentyp"])]
    if len(wanted) != 1:
        raise EngineError("E_NICHT_GEFUNDEN")
    return {k: v for k, v in wanted[0].items() if k != "datei"}  # vorlage fuer_claude: never the file name


def kategorien(gi: dict, cfg: Config) -> list[dict]:
    out = []
    for i, t in enumerate(gi.get("testergebnisse", [])):
        for j, w in enumerate(t.get("werte", [])):
            c = derive.category(cfg, w["wert"], w["skala"], t.get("testkatalog_id"))
            out.append({"wert_quelle": f"/testergebnisse/{i}/werte/{j}",
                        **({"kategorie": c["kategorie"]} if "kategorie" in c else {"kategorie_luecke": c["kategorie_luecke"]})})
    return out


def bausteine(gi: dict, cfg: Config) -> list[dict]:
    out = []
    for t in gi.get("testergebnisse", []):
        entry = cfg.test(t.get("testkatalog_id"))
        if entry and not any(b["testkatalog_id"] == entry["id"] for b in out):
            out.append({"testkatalog_id": entry["id"], **entry["beschreibungsbaustein"]})
    return out


def _record_parts(record: dict):
    gi = record.get("gutachten_input")
    if gi is None:
        raise EngineError("E_NICHT_GEFUNDEN")
    return gi, (record.get("entwuerfe") or [None])[-1]


def draft_text(draft: dict, gi: dict, cfg: Config) -> str:
    sections, tables = belege.render(draft, gi, cfg)
    lines = []
    for a in draft["abschnitte"]:
        lines.append(sections.get(a["abschnitt_id"], ""))
        for rows in tables.get(a["abschnitt_id"], []):
            lines += [" | ".join(r) for r in rows]
    return "\n".join(l for l in lines if l)


def inhalt(record: dict, art: str, cfg: Config, args: dict) -> dict:
    """Contents per package type exactly as allowed by fallpaket.schema.json."""
    if art == "hypothese":
        return {"vignette": str(args.get("vignette", "")), "schlussfolgerung": str(args.get("schlussfolgerung", ""))}
    if art == "stil_lernen":
        # only documents imported as sample reports, never the other documents of a case (EGM E49)
        docs = [d for d in record["session"]["dokumente"]
                if "text_anonymisiert" in d and d["quelle_rolle"] == PROBEGUTACHTEN]
        if not docs:
            raise EngineError("E_NICHT_GEFUNDEN")
        # probe_id stable per document (pg- plus the neutral dok_id suffix), so a quote can be traced back later
        return {"probetexte": [{"probe_id": "pg-" + d["dok_id"][2:], "text": d["text_anonymisiert"][:100000]}
                               for d in docs[:10]]}
    gi, draft = _record_parts(record)
    fresh = rules.fuer_claude(rules.pruefe_fachregeln(gi, cfg))
    if art == "gutachten":
        if gi["gutachtentyp"] == "emotional_soziale_entwicklung":
            raise EngineError("E_BLOCKIERT")  # no template, no draft (Nachtrag 1)
        out = {"gutachten_input": gi, "regelergebnis": fresh, "vorlage": _vorlage_for(gi),
               "kategorien": kategorien(gi, cfg), "bausteine": bausteine(gi, cfg)}
        if profil := released_stilprofil():
            out["stilprofil"] = stilprofil_fuer_claude(profil)
        return out
    if art == "diagnosevorschlag":
        if not q1(gi):
            raise EngineError("E_Q1")
        # blind: Claude never sees the psychologist's own diagnosis (Nachtrag 1, EGM E10)
        return {"gutachten_input": {k: v for k, v in gi.items() if k != "gutachten_diagnose"},
                "kategorien": kategorien(gi, cfg)}
    if draft is None:
        raise EngineError("E_NICHT_GEFUNDEN")
    if art == "pruefung_stil":
        profil = released_stilprofil()
        if profil is None:
            raise EngineError("E_NICHT_GEFUNDEN")
        return {"entwurf": draft, "stilprofil": stilprofil_fuer_claude(profil)}
    if art == "pruefung_goldfisch":
        return {"fragestellung": gi["vorstellungsgrund"]["text"][:20000], "ergebnis_text": draft_text(draft, gi, cfg)[:100000],
                "kriterien": wissen("goldfisch-kriterien.md")[:20000],
                "gutachtentyp": gi["gutachtentyp"]}  # spf: weigh judging language more (Nachtrag 1)
    if art == "pruefung_elefant":
        return {"gutachten_input": gi, "entwurf": draft, "regelergebnis": fresh, "kategorien": kategorien(gi, cfg),
                "bausteine": bausteine(gi, cfg)}
    raise EngineError("E_SCHEMA", "argumente")


# ---------------------------------------------------------------- packages and returns

def _pakete_path(session_id: str) -> Path:
    store.load(session_id)  # validates the ID and that the session exists
    return store.data_dir() / f"pakete-{session_id}.json"


def _open_packages(session_id: str) -> dict:
    path = _pakete_path(session_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def register(session_id: str, paket: dict) -> None:
    pakete = _open_packages(session_id)
    pakete[paket["paket_id"]] = {"art": paket["art"], "erwartete_rueckgabe": paket["erwartete_rueckgabe"]}
    store.write_atomic(_pakete_path(session_id), json.dumps(pakete).encode("utf-8"))


def make_package(record: dict, art: str, cfg: Config, args: dict) -> dict:
    if art not in ARTEN:
        raise EngineError("E_SCHEMA", "argumente")
    paket = {"schema_version": "2", "paket_id": new_id("p"), "art": art,
             "session_id": record["session"]["session_id"], "erwartete_rueckgabe": ARTEN[art],
             "anonymisierung_geprueft": True, "inhalt": inhalt(record, art, cfg, args)}
    if v := record["session"]["versionen"].get("konfiguration"):
        paket["konfiguration_version"] = v
    validate("fallpaket", paket)
    return paket


def extract_json(text: str) -> dict:
    """Accept the bare JSON or the one fenced code block of a chat answer. Two or more blocks are refused: each
    package takes exactly one return block (Nachtrag 1, Abläufe), and the app must not guess which one is meant."""
    if not isinstance(text, str):
        raise EngineError("E_SCHEMA", "json")
    # fences of three or more backticks, language tag in any case (EGM Task 2 E20)
    blocks = [m[1] for m in re.findall(r"(`{3,})[ \t]*(?:json)?[ \t]*\r?\n(.*?)\1", text, re.S | re.I)]
    if len(blocks) > 1:
        raise EngineError("E_SCHEMA", "json")
    try:
        data = json.loads(blocks[0] if blocks else text)
    except (json.JSONDecodeError, TypeError):
        raise EngineError("E_SCHEMA", "json")
    if not isinstance(data, dict):
        raise EngineError("E_SCHEMA", "schema")
    return data


def check_befunde(befunde: list, pruefer: str, gi: dict, cfg: Config) -> list[dict]:
    """IDs new, decisions open; Elefant findings must agree with a fresh rule run and never cite awmf_* rules."""
    fresh = {}
    for e in rules.pruefe_fachregeln(gi, cfg)["ergebnisse"] if gi else []:
        fresh.setdefault(e["regel_id"], set()).add(e["ergebnis"])
    out = []
    for b in befunde:
        if b["pruefer"] != pruefer:
            raise EngineError("E_PAKET_FREMD")
        if rid := b.get("regel_id"):
            if pruefer != "elefant" or rid.startswith("awmf_") or not (fresh.get(rid, set()) - {"erfuellt"}):
                raise EngineError("E_REGELABWEICHUNG")
        out.append(b | {"befund_id": new_id("bf"), "entscheidung": {"status": "offen"}})
    return out


def check_draft(draft: dict, record: dict, cfg: Config) -> dict:
    """Shared by lies_rueckgabe and the MCP tool speichere_entwurf."""
    gi = record.get("gutachten_input")
    if gi is None or draft.get("session_id") != record["session"]["session_id"] or draft.get("gutachtentyp") != gi["gutachtentyp"]:
        raise EngineError("E_PAKET_FREMD")
    draft = draft | {"entwurf_version": len(record.get("entwuerfe", [])) + 1}
    validate("gutachten-output", draft)
    if belege.pruefe_belege(draft, gi, cfg):  # order as in ui-api.md, ADR 0002 step 4 (EGM E54)
        raise EngineError("E_BELEG")
    if draft["regelergebnis"] != rules.fuer_claude(rules.pruefe_fachregeln(gi, cfg)):
        raise EngineError("E_REGELABWEICHUNG")
    return draft


def check_claude_proposal(vorschlag: dict, record: dict, cfg: Config) -> dict:
    gi = record.get("gutachten_input")
    if not q1(gi):
        raise EngineError("E_Q1")
    if vorschlag.get("session_id") != record["session"]["session_id"] or vorschlag.get("quelle") != "claude":
        raise EngineError("E_PAKET_FREMD")
    validate("diagnosevorschlag", vorschlag)
    if code := vorschlag.get("icd10_code"):
        if not cfg.icd_exists(code):  # Nachtrag 1: only codes from the local reference data
            vorschlag = {k: v for k, v in vorschlag.items() if k != "icd10_code"}
            vorschlag["hinweis"] = vorschlag.get("hinweis", "") + " ICD-Code nicht in den lokalen Referenzdaten, daher nicht übernommen."
    return vorschlag


def read_return(record: dict, text: str, cfg: Config) -> dict:
    """ADR 0002, step 4: schema, own open package, evidence, rule result against a fresh run; IDs new, decisions open."""
    data = extract_json(text)
    validate("rueckgabe", data)
    session_id = record["session"]["session_id"]
    pakete = _open_packages(session_id)
    paket = pakete.get(data["paket_id"])
    if paket is None or paket["erwartete_rueckgabe"] != data["typ"]:
        raise EngineError("E_PAKET_FREMD")
    typ, gi = data["typ"], record.get("gutachten_input")
    if typ == "gutachten-output":
        record.setdefault("entwuerfe", []).append(check_draft(data["daten"], record, cfg))
        result = {"entwurf_version": record["entwuerfe"][-1]["entwurf_version"]}
    elif typ == "befunde":
        neue = check_befunde(data["daten"], PRUEFER[paket["art"]], gi, cfg)
        record.setdefault("befunde", []).extend(neue)
        result = {"befunde": len(neue)}
    elif typ == "diagnosevorschlag":
        record.setdefault("diagnosevorschlaege", []).append(check_claude_proposal(data["daten"], record, cfg))
        result = {"diagnosevorschlag": "gespeichert"}
    elif typ == "stilprofil":
        result = {"stilprofil": save_stilprofil(data["daten"] | {"version": free_version(data["daten"]["version"])})["version"]}
    else:
        raise EngineError("E_PAKET_FREMD")
    # The package is closed first: a crash in between loses this return but never allows a second one (EGM E55).
    del pakete[data["paket_id"]]
    store.write_atomic(_pakete_path(session_id), json.dumps(pakete).encode("utf-8"))
    store.save(record)
    return result
