"""App-only functions added with the desktop app (Task 4, docs/ui-api.md). No new domain logic. Imports nothing from
ui_functions at module level (ui_functions imports this module)."""
import json
import os
import re
import shutil
import sys
from pathlib import Path

from . import config, packages, ram, recognition, rules, store
from .errors import EngineError
from .ids import new_id
from .contracts import validate

DEFAULT_SETTINGS = {"schema_version": "1", "verbindung": "desktop", "qualifikationen": [], "darstellung": "system"}


def _settings_path():
    return store.data_dir() / "einstellungen.json"


def _settings_or_none() -> dict | None:
    """The stored settings, or None if there is no file or it is broken (EGM C17: a broken file never stops the app)."""
    path = _settings_path()
    if not path.exists():
        return None
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
        validate("einstellungen", settings)
        return settings
    except (ValueError, EngineError):
        return None


def gespeicherte_qualifikationen() -> list | None:
    """Q1 has one source: the profile of Screen 13, once it is saved (EGM B5). eingabe_speichern takes it from here."""
    settings = _settings_or_none()
    return settings["qualifikationen"] if settings else None


def einstellungen_laden(args: dict, ctx=None) -> dict:
    settings = _settings_or_none()
    return {"einstellungen": settings or dict(DEFAULT_SETTINGS), "vorhanden": settings is not None,
            "beschaedigt": settings is None and _settings_path().exists()}


def einstellungen_speichern(args: dict, ctx=None) -> dict:
    settings = args.get("einstellungen")
    validate("einstellungen", settings)
    store.write_atomic(_settings_path(), json.dumps(settings, ensure_ascii=False).encode("utf-8"))
    return {"einstellungen": settings}


def dokument_text(args: dict, ctx=None) -> dict:
    """Clear text of an imported, not yet released document for the redaction view (Screen 03). RAM only: it goes to
    the app over the channel and stays in the app's memory (docs/ui-api.md, Datenschutz); gone after the release."""
    doc = ram.get(str(args.get("session_id", "")), str(args.get("dok_id", "")))
    if doc is None:
        raise EngineError("E_NICHT_GEFUNDEN")
    return {"teile": [{"teil": i, "art": p.art, "seite": p.seite, "text": p.text} for i, p in enumerate(doc.parts)],
            "ocr_offen": len(doc.ocr_seiten), "erkennung_gelaufen": doc.erkennung_gelaufen,
            "funde": [f.for_ui() for f in doc.funde]}


_MANUELL = ("direkte_identifikatoren", "datumsangaben", "orte_einrichtungen", "seltene_merkmale")


def fund_hinzufuegen(args: dict, ctx=None) -> dict:
    """Manual redaction (RedactionViewer, also by keyboard): marks every occurrence of the given text in the visible
    parts, after the recognition ran (it would replace the findings). Overlaps with existing findings are skipped."""
    doc = ram.get(str(args.get("session_id", "")), str(args.get("dok_id", "")))
    if doc is None:
        raise EngineError("E_NICHT_GEFUNDEN")
    text, kategorie, ersatz = args.get("text"), args.get("kategorie"), args.get("ersatz")
    if not (isinstance(text, str) and 2 <= len(text.strip()) <= 200 and kategorie in _MANUELL
            and isinstance(ersatz, str) and ersatz.strip() and len(ersatz) <= 100):
        raise EngineError("E_SCHEMA", "argumente")
    if not doc.erkennung_gelaufen:
        raise EngineError("E_BLOCKIERT")
    text = text.strip()
    neu = []
    for i, part in enumerate(doc.parts):
        if part.art not in recognition.VISIBLE_ARTS:
            continue
        start = part.text.find(text)
        while start >= 0:
            end = start + len(text)
            if not any(f.teil == i and f.start < end and start < f.end for f in doc.funde + neu):
                neu.append(recognition.Fund(new_id("f"), kategorie, i, start, end, text, "manuell", 1.0, ersatz,
                                            "uebernommen"))
            start = part.text.find(text, end)
    if not neu:
        raise EngineError("E_NICHT_GEFUNDEN")
    doc.funde.extend(neu)
    return {"neu": len(neu), "funde": [f.for_ui() for f in doc.funde],
            "funde_je_kategorie": recognition.counts(doc.funde, doc.bilder)}


def _katalog_auszug(entry: dict) -> dict:
    keys = ("id", "name", "art", "normart", "normjahr", "normgruppen", "konfidenzniveaus", "einzeltestung", "indizes",
            "beschreibungsbaustein", "status")
    return {k: entry[k] for k in keys if k in entry}


def eingabe_kontext(args: dict, ctx=None) -> dict:
    """What Screen 04 shows next to the input (Task 4.3): procedures of the test catalogue, the rule titles and sources,
    and, for the stored input, the derived categories and locked text blocks. Read only; nothing is derived in the app."""
    record = store.load(str(args.get("session_id", "")))
    cfg = config.load()
    gi = record.get("gutachten_input")
    try:
        vorlage = packages._vorlage_for(gi or {"gutachtentyp": record["session"].get("gutachtentyp")})
    except EngineError:
        vorlage = None
    regeln = cfg.rules_for(record["session"].get("gutachtentyp", "")) if record["session"].get("gutachtentyp") else []
    return {
        "testkatalog": [_katalog_auszug(e) for e in (cfg.testkatalog or {}).get("eintraege", [])],
        "testkatalog_version": cfg.version("testkatalog"), "regelwerk_version": cfg.version("regelwerk"),
        "regeln": {r["regel_id"]: {"titel": r["titel"], "quelle": r["quelle"], "status": r["status"]} for r in regeln},
        "kategorien": packages.kategorien(gi, cfg) if gi else [],
        "bausteine": packages.bausteine(gi, cfg) if gi else [],
        "regelergebnis": rules.pruefe_fachregeln(gi, cfg) if gi and cfg.regelwerk else None,
        "vorlage": vorlage,
        # every mapped template of this report type: with more than one, the input names its vorlage_id
        "vorlagen": sorted(({"vorlage_id": m["vorlage_id"], "version": m["version"], "status": m["status"]}
                            for m in _gueltige("vorlage", packages.vorlagen_dir())
                            if m["gutachtentyp"] == record["session"].get("gutachtentyp")), key=lambda v: v["vorlage_id"]),
    }


# ---------------------------------------------------------------- catalogue (Screen 10, Task 4.4)

_PFLEGBAR = ("testkatalog", "kategorienskala")  # the rule set and hint wordings are not edited in the app
_VERSIONIERT = ("testkatalog", "kategorienskala", "regelwerk", "lernbausteine")  # lernbausteine: Task 5


def _konf_dir():
    """The configuration folder; created on first use next to the case store, so the browser variant (no working
    folder, no einrichten) can maintain the catalogue as well (EGM B2)."""
    d = config.config_dir() or store.data_dir().parent / "konfiguration"
    d.mkdir(parents=True, exist_ok=True)
    return d


_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")


def _version_ok(v) -> bool:
    """A version label becomes a file name: no path parts, no Windows-reserved characters (EGM C4)."""
    return isinstance(v, str) and bool(_VERSION.match(v)) and ".." not in v


def _verlauf(name: str):
    d = _konf_dir() / "versionen" / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _versionen(name: str) -> list[str]:
    return sorted((p.stem for p in _verlauf(name).glob("*.json")), key=packages._version_key)  # syn-10 after syn-2


def _gueltige(schema: str, ordner) -> list[dict]:
    """JSON files of a folder that satisfy their schema; a broken file is skipped, never shown half (EGM C17)."""
    out = []
    for p in sorted(ordner.glob("*.json")):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            validate(schema, doc)
            out.append(doc)
        except (ValueError, UnicodeDecodeError, EngineError):
            continue
    return out


def konfiguration_laden(args: dict, ctx=None) -> dict:
    """Screen 10: the current state of every configuration file, earlier versions, and the imported templates."""
    cfg = config.load()
    vorlagen = sorted(_gueltige("vorlage", packages.vorlagen_dir()), key=lambda v: v["vorlage_id"])
    return {"testkatalog": cfg.testkatalog, "regelwerk": cfg.regelwerk, "kategorienskala": cfg.kategorienskala,
            "lernbausteine": cfg.lernbausteine,
            "versionen": {n: _versionen(n) for n in _VERSIONIERT},
            "vorlagen": [{k: v for k, v in m.items() if k != "datei"} for m in vorlagen]}


def _archivieren(name: str) -> None:
    path = _konf_dir() / config.FILES[name]
    if path.exists():
        alt = json.loads(path.read_text(encoding="utf-8"))
        ziel = _verlauf(name) / f"{alt['version']}.json"
        if not ziel.exists():
            store.write_new(ziel, path.read_bytes())


def _quellen_leer(node) -> bool:
    """Every source must say something: the schema allows empty strings in quelle.manual and quelle.seite."""
    if isinstance(node, dict):
        return any((k == "quelle" and (not v or (isinstance(v, str) and not v.strip()) or
                                       (isinstance(v, dict) and not all(isinstance(x, str) and x.strip() for x in v.values()))))
                   or _quellen_leer(v) for k, v in node.items())
    return isinstance(node, list) and any(_quellen_leer(v) for v in node)


def _schreiben(name: str, doc: dict) -> dict:
    if not isinstance(doc, dict) or not _version_ok(doc.get("version")):
        raise EngineError("E_SCHEMA", "argumente")
    validate(name, doc)  # the schema demands a source for every entry (Quellenpflicht) ...
    if _quellen_leer(doc):  # ... and here it must not be empty
        raise EngineError("E_SCHEMA", "schema")
    if name == "kategorienskala":
        config.check_scale(doc)
    path = _konf_dir() / config.FILES[name]
    aktuell = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if aktuell and aktuell["version"] == doc["version"] or doc["version"] in _versionen(name):
        raise EngineError("E_BLOCKIERT")  # a version is written once; a change is a new version
    _archivieren(name)
    store.write_atomic(path, json.dumps(doc, ensure_ascii=False, indent=1).encode("utf-8"))
    return {"version": doc["version"], "versionen": _versionen(name)}


def katalog_speichern(args: dict, ctx=None) -> dict:
    """Test catalogue or category scale as a new version; the earlier one stays in konfiguration/versionen/."""
    name, doc = args.get("name"), args.get("dokument")
    if name not in _PFLEGBAR or not isinstance(doc, dict):
        raise EngineError("E_SCHEMA", "argumente")
    return _schreiben(name, doc)


_IMPORTIERBAR = ("regelwerk", "testkatalog", "kategorienskala", "icd10-referenz", "hinweise", "berater")


def konfiguration_importieren(args: dict, ctx=None) -> dict:
    """A configuration file the psychologist received or maintains outside the app (the rule set, hint wordings,
    ICD-10 reference) comes in as a new state, checked like every other write (EGM C3). pfad is used for this call
    only."""
    name, pfad = args.get("name"), args.get("pfad")
    if name not in _IMPORTIERBAR or not isinstance(pfad, str):
        raise EngineError("E_SCHEMA", "argumente")
    path = Path(pfad)
    if not path.is_file():
        raise EngineError("E_NICHT_GEFUNDEN")
    if path.stat().st_size > 2 * 1024 * 1024:
        raise EngineError("E_SCHEMA", "groesse")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise EngineError("E_SCHEMA", "json") from None
    if name in _VERSIONIERT:
        return _schreiben(name, doc)
    if not isinstance(doc, dict):
        raise EngineError("E_SCHEMA", "argumente")
    validate(name, doc)
    if name == "icd10-referenz" and _quellen_leer(doc):
        raise EngineError("E_SCHEMA", "schema")
    store.write_atomic(_konf_dir() / config.FILES[name], json.dumps(doc, ensure_ascii=False, indent=1).encode("utf-8"))
    return {"version": doc["version"], "versionen": []}


def rollback(args: dict, ctx=None) -> dict:
    """Back to an earlier version as a new version (VersionList): nothing is deleted."""
    name, alt, neu = args.get("name"), args.get("version"), args.get("neue_version")
    if name not in _VERSIONIERT or not _version_ok(alt) or not _version_ok(neu):
        raise EngineError("E_SCHEMA", "argumente")
    if alt not in _versionen(name):
        raise EngineError("E_NICHT_GEFUNDEN")
    doc = json.loads((_verlauf(name) / f"{alt}.json").read_text(encoding="utf-8"))
    out = _schreiben(name, doc | {"version": neu})
    if name == "lernbausteine":
        from . import lernschleife
        out["eval"] = lernschleife.evals(doc["bausteine"], doc["bausteine"])  # shown, not blocking (EGM Task 5 B9)
    return out


def diagnosevergleich_uebersicht(args: dict, ctx=None) -> dict:
    """Screen 12, agreement over all cases: counts only, from comparisons already made (reading changes nothing);
    only cases whose input carries Q1. Never part of a learning signal (Nachtrag 1)."""
    zaehler = {q: {"gleich": 0, "abweichend": 0, "nicht_vergleichbar": 0} for q in ("engine", "claude")}
    for r in store.all_records():
        if "vergleich" in r and packages.q1(r.get("gutachten_input")):
            for q in zaehler:
                if r["vergleich"].get(q) in zaehler[q]:  # the schema allows nothing else; never a KeyError (EGM C19)
                    zaehler[q][r["vergleich"][q]] += 1
    return {"uebersicht": zaehler}


# ---------------------------------------------------------------- Rubberduck, style, quality (Task 4.5)

def rubberduck_vorgaben(args: dict, ctx=None) -> dict:
    """Screens 07 and 08: hint wordings (or null, then no session starts), adviser perspectives, origin."""
    from . import rubberduck  # imports packages, which imports this module's neighbours
    return rubberduck.vorgaben()


def stilprofile_laden(args: dict, ctx=None) -> dict:
    """Screen 09: every stored style profile, newest first; the active one is the highest released version."""
    profile = _gueltige("stilprofil", packages.stilprofile_dir())
    profile.sort(key=lambda p: packages._version_key(p["version"]), reverse=True)
    aktiv = packages.released_stilprofil()
    return {"stilprofile": profile, "aktiv": aktiv["version"] if aktiv else None}


def stilprofil_freigeben(args: dict, ctx=None) -> dict:
    """Release a draft profile: only its status changes, the content stays as Claude wrote it and she reviewed it."""
    version = args.get("version")
    if not isinstance(version, str):
        raise EngineError("E_SCHEMA", "argumente")
    path = packages.stilprofile_dir() / f"{re.sub(r'[^\w.-]', '_', version)}.json"
    if not path.is_file():
        raise EngineError("E_NICHT_GEFUNDEN")
    profil = json.loads(path.read_text(encoding="utf-8"))
    if profil["status"] == "freigegeben":
        raise EngineError("E_BLOCKIERT")
    profil["status"] = "freigegeben"
    validate("stilprofil", profil)
    store.write_atomic(path, json.dumps(profil, ensure_ascii=False).encode("utf-8"))
    return {"version": profil["version"], "status": profil["status"]}


def lernsignale_uebersicht(args: dict, ctx=None) -> dict:
    """Screen 11: counts of the learning signals over all report and intervision sessions. Supervision gives none,
    the diagnosis comparison is never counted (Nachtrag 1)."""
    out = {"gutachten": 0, "signale": 0, "je_art": {}, "je_pruefer": {}, "offene_luecken": 0}
    for r in store.all_records():
        if r["session"]["modus"] == "gutachten" and r.get("entwuerfe"):
            out["gutachten"] += 1
            out["offene_luecken"] += sum(1 for a in r["entwuerfe"][-1]["abschnitte"] for p in a.get("absaetze", [])
                                         for satz in p["saetze"] if "luecke" in satz)
        if r["session"]["modus"] == "supervision":
            continue  # never from supervision, even if a signal got there (ADR 0002, EGM B14)
        for sig in r.get("lernsignale", []):
            out["signale"] += 1
            out["je_art"][sig["art"]] = out["je_art"].get(sig["art"], 0) + 1
            if sig.get("pruefer"):
                pr = out["je_pruefer"].setdefault(sig["pruefer"], {"befund_angenommen": 0, "befund_verworfen": 0})
                if sig["art"] in pr:
                    pr[sig["art"]] += 1
    return out


# ---------------------------------------------------------------- first start (Task 4.6)

def _arbeitsordner_vorlage() -> Path:
    if env := os.environ.get("SCHLOMO_ARBEITSORDNER_VORLAGE"):
        return Path(env)
    if getattr(sys, "frozen", False):  # PyInstaller bundle ships the template as data (scripts/build_pyinstaller.py)
        return Path(sys._MEIPASS) / "arbeitsordner"
    return Path(__file__).resolve().parents[3] / "arbeitsordner"


def _befehl(startart: str) -> dict:
    """How the Code-Tab starts this very engine: the bundled program, or in development the venv Python with a small
    entry script next to the case store (hooks take no environment, so PYTHONPATH cannot be passed)."""
    if getattr(sys, "frozen", False):
        return {"command": sys.executable, "args": [startart]}
    entry = store.data_dir().parent / "engine_entry.py"
    if not entry.exists():
        src = str(Path(__file__).resolve().parents[1])
        lines = ["import sys", f"sys.path.insert(0, {src!r})", "from schlomo_engine.__main__ import main", "sys.exit(main())", ""]
        entry.write_text(chr(10).join(lines), encoding="utf-8")
    return {"command": sys.executable, "args": [str(entry), startart]}


def _einrichtung_path() -> Path:
    return store.data_dir() / "einrichtung.json"


def einrichten_status(args: dict, ctx=None) -> dict:
    path = _einrichtung_path()
    info = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    ok = bool(info) and (Path(info["arbeitsordner"]) / ".mcp.json").is_file()
    return {"eingerichtet": ok, "arbeitsordner": info["arbeitsordner"] if info else None,
            "konfiguration": str(config.config_dir() or store.data_dir().parent / "konfiguration")}


def einrichten(args: dict, ctx=None) -> dict:
    """First start: the working folder for the Code-Tab from the template with this engine in .mcp.json and as hook,
    and konfiguration/ and wissensbasis/vorlagen/ next to the case store. The working folder must be new or empty and
    lie apart from the case store; nothing existing is overwritten."""
    ziel = args.get("arbeitsordner")
    if not isinstance(ziel, str) or not ziel.strip():
        raise EngineError("E_SCHEMA", "argumente")
    ziel_p = Path(ziel).resolve()
    daten = store.data_dir()
    if ziel_p == daten or daten in ziel_p.parents or ziel_p in daten.parents:
        raise EngineError("E_BLOCKIERT", "datenordner")
    if ziel_p.exists() and any(ziel_p.iterdir()):
        raise EngineError("E_BLOCKIERT")
    vorlage = _arbeitsordner_vorlage()
    if not (vorlage / ".mcp.json").is_file():
        raise EngineError("E_NICHT_GEFUNDEN")
    shutil.copytree(vorlage, ziel_p, dirs_exist_ok=True)
    (ziel_p / "benutzer-einstellungen.json").unlink(missing_ok=True)  # user settings belong to Claude, see the guide
    mcp = {"mcpServers": {"engine": _befehl("mcp")}}
    store.write_atomic(ziel_p / ".mcp.json", json.dumps(mcp, ensure_ascii=False, indent=2).encode("utf-8"))
    settings_path = ziel_p / ".claude" / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    hook = settings["hooks"]["PreToolUse"][0]["hooks"][0]
    hook.update({k: v for k, v in _befehl("hook").items() if k in ("command", "args")})
    store.write_atomic(settings_path, json.dumps(settings, ensure_ascii=False, indent=2).encode("utf-8"))
    (daten.parent / "konfiguration").mkdir(parents=True, exist_ok=True)
    packages.vorlagen_dir()  # creates wissensbasis/vorlagen/
    store.write_atomic(_einrichtung_path(), json.dumps({"arbeitsordner": str(ziel_p)}, ensure_ascii=False).encode("utf-8"))
    return einrichten_status({})


# ---------------------------------------------------------------- learning loop (Task 5)

def vorschlaege_laden(args: dict, ctx=None) -> dict:
    """Screen 11: proposals of /verbessern with their signals' origin and area, eval result and status."""
    from . import lernschleife
    return {"vorschlaege": lernschleife.alle(), "lernbausteine": config.load().lernbausteine,
            "signale": lernschleife.signale_uebersicht()["gruppen"]}


def llm_evals_bestaetigen(args: dict, ctx=None) -> dict:
    """The psychologist confirms that the LLM part of the evals of Task 2 and 3 ran with this proposal and passed
    (evals/lernschleife/mit_vorschlag.py builds the configuration for that run). Stored with the date; a new
    deterministic eval clears it (EGM Task 5 C1)."""
    from datetime import date

    from . import lernschleife
    with lernschleife.sperre(args.get("vorschlag_id")):
        v = lernschleife.laden(args.get("vorschlag_id"))
        if v["status"] != "eval_bestanden" or args.get("bestaetigt") is not True:
            raise EngineError("E_BLOCKIERT")
        v["llm_bestaetigt"] = {"bestaetigt": True, "am": date.today().isoformat()}
        lernschleife.speichern(v)
    return {"vorschlag_id": v["vorschlag_id"], "llm_bestaetigt": v["llm_bestaetigt"]}


def konfiguration_freigeben(args: dict, ctx=None) -> dict:
    """Release by the psychologist: only a checked proposal (schema, target, eval computed again now, LLM part
    confirmed) on the version it was checked against. The blocks become a new version (the old one stays for the
    rollback), the signals are marked as used. Repeatable after a crash between these steps (EGM Task 5 B5, C7, C8)."""
    from . import lernschleife
    with lernschleife.sperre(args.get("vorschlag_id")):
        v = lernschleife.laden(args.get("vorschlag_id"))
        if v["status"] != "eval_bestanden" or not v.get("llm_bestaetigt"):
            raise EngineError("E_BLOCKIERT")
        doc = lernschleife.aktuell()
        schon = v["aenderung"]["art"] != "entfernen" and doc and any(
            b["vorschlag_id"] == v["vorschlag_id"] for b in doc["bausteine"])
        if schon:  # written before a crash: finish the remaining steps, never a second version
            neu = doc["version"]
        else:
            if v["basis_version"] != (doc["version"] if doc else "keine"):
                raise EngineError("E_BLOCKIERT", "konflikt")
            nachher = lernschleife.anwenden(doc, v)
            if not lernschleife.evals(doc["bausteine"] if doc else [], nachher)["bestanden"]:
                raise EngineError("E_BLOCKIERT")  # the suite of today decides, not a stored result
            versionen = _versionen("lernbausteine") + ([doc["version"]] if doc else [])
            neu = str(max([int(x) for x in versionen if x.isdigit()], default=0) + 1)
            _schreiben("lernbausteine", {"schema_version": "1", "version": neu, "bausteine": nachher})
        lernschleife.signale_markieren(v["signal_ids"], v["vorschlag_id"])
        v |= {"status": "freigegeben", "neue_version": neu}
        lernschleife.speichern(v)
    return {"vorschlag_id": v["vorschlag_id"], "status": v["status"], "version": neu}


def vorschlag_verwerfen(args: dict, ctx=None) -> dict:
    """Discarded proposals give their signals free again (they no longer reserve them)."""
    from . import lernschleife
    with lernschleife.sperre(args.get("vorschlag_id")):
        v = lernschleife.laden(args.get("vorschlag_id"))
        if v["status"] in ("freigegeben", "verworfen"):
            raise EngineError("E_BLOCKIERT")
        v["status"] = "verworfen"
        lernschleife.speichern(v)
    return {"vorschlag_id": v["vorschlag_id"], "status": v["status"]}


FUNCTIONS = {
    "vorschlaege_laden": vorschlaege_laden,
    "konfiguration_freigeben": konfiguration_freigeben,
    "vorschlag_verwerfen": vorschlag_verwerfen,
    "llm_evals_bestaetigen": llm_evals_bestaetigen,
    "einrichten_status": einrichten_status,
    "einrichten": einrichten,
    "rubberduck_vorgaben": rubberduck_vorgaben,
    "stilprofile_laden": stilprofile_laden,
    "stilprofil_freigeben": stilprofil_freigeben,
    "lernsignale_uebersicht": lernsignale_uebersicht,
    "diagnosevergleich_uebersicht": diagnosevergleich_uebersicht,
    "konfiguration_laden": konfiguration_laden,
    "katalog_speichern": katalog_speichern,
    "rollback": rollback,
    "konfiguration_importieren": konfiguration_importieren,
    "eingabe_kontext": eingabe_kontext,
    "fund_hinzufuegen": fund_hinzufuegen,
    "dokument_text": dokument_text,
    "einstellungen_laden": einstellungen_laden,
    "einstellungen_speichern": einstellungen_speichern,
}
