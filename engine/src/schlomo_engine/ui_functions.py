"""App-only functions of start type ui (docs/ui-api.md). Steps 1.1 (status, sessions) and 1.2 (import, OCR).
Every function takes (args, ctx); ctx.emit sends progress events for the running request."""
import json
import re
from datetime import date
from pathlib import Path

from . import (__version__, belege, config, derive, docx_template, external, importer, packages, ram, recognition,
               rubberduck, rules, store)
from .contracts import schema_versions, validate
from .errors import EngineError
from .ids import new_id

# Fields that only the Q1 functions (step 1.6) may return; sitzung_laden never does (docs/ui-api.md).
_DIAGNOSIS_FIELDS = ("interne_diagnose", "diagnosevorschlaege", "vergleich")
NOT_CONFIGURED = "nicht_konfiguriert"


_INITIALEN = re.compile(r"(?<!\w)[A-ZÄÖÜ]\.\s?[A-ZÄÖÜ]\.?(?!\w)")


def _check_label(text, names: list, use_ner: bool = True) -> None:
    """Session label and source role stay neutral ("Fall 7", "Bericht Schule"): known names, every rule hit (also an
    uncertain one such as a year), initials and NER persons block (session.schema.json, EGM E17, E47). NER places and
    organisations are left out: on one to three words they flag ordinary nouns."""
    if not isinstance(text, str):
        return
    hits = recognition.detect_text(text, 0, names, None, use_ner)
    if _INITIALEN.search(text) or any(f.quelle != "ner" or f.kategorie == "direkte_identifikatoren" for f in hits):
        raise EngineError("E_BEZEICHNUNG")


def status(args: dict, ctx=None) -> dict:
    return {"engine_version": __version__, "schema_versionen": schema_versions()}


def sitzung_anlegen(args: dict, ctx=None) -> dict:
    modus = args.get("modus")
    typ = args.get("gutachtentyp")
    # session.schema.json: gutachtentyp only with modus gutachten; there it is required (Nachtrag 1).
    if (modus == "gutachten") != (typ is not None):
        raise EngineError("E_SCHEMA", "argumente")
    session = {
        "schema_version": "1",
        "session_id": new_id("s"),
        "bezeichnung": args.get("bezeichnung"),
        "modus": modus,
        "status": "import",
        "dokumente": [],
        "versionen": {"regelwerk": NOT_CONFIGURED, "testkatalog": NOT_CONFIGURED},
    }
    if typ is not None:
        session["gutachtentyp"] = typ
    validate("session", session)
    _check_label(session["bezeichnung"], [])
    store.save({"schema_version": "1", "session": session})
    return {"session": session}


def sitzung_umbenennen(args: dict, ctx=None) -> dict:
    """New neutral label, e.g. after bekannte_namen_setzen found a name in the old one."""
    record = store.load(str(args.get("session_id", "")))
    record["session"]["bezeichnung"] = args.get("bezeichnung")
    validate("session", record["session"])
    _check_label(record["session"]["bezeichnung"], ram.names(record["session"]["session_id"]))
    store.save(record)
    return {"session": record["session"]}


def sitzungen_auflisten(args: dict, ctx=None) -> dict:
    return {"sessions": [r["session"] for r in store.all_records()]}


def sitzung_laden(args: dict, ctx=None) -> dict:
    record = store.load(str(args.get("session_id", "")))
    return {k: v for k, v in record.items() if k not in _DIAGNOSIS_FIELDS}


def _funde_counts(doc) -> dict:
    """Counts only. Recognition (step 1.3) fills the other categories."""
    return {"direkte_identifikatoren": 0, "datumsangaben": 0, "orte_einrichtungen": 0, "seltene_merkmale": 0,
            "versteckte_inhalte": doc.versteckte_inhalte, "bilder": doc.bilder, "unsicher": 0}


def dokument_importieren(args: dict, ctx=None) -> dict:
    """Read the file once (pfad is used for this call only, never stored or logged), keep clear text in RAM."""
    record = store.load(str(args.get("session_id", "")))
    pfad, rolle = args.get("pfad"), args.get("quelle_rolle")
    if not isinstance(pfad, str) or not isinstance(rolle, str) or not rolle.strip():
        raise EngineError("E_SCHEMA", "argumente")
    # stored in the Fallspeicher (EGM E47); names are known by now, NER would flag role words such as "Foto"
    _check_label(rolle, ram.names(record["session"]["session_id"]), use_ner=False)
    path = Path(pfad)
    if not path.is_file():
        raise EngineError("E_NICHT_GEFUNDEN")
    raw = path.read_bytes()
    doc = importer.import_bytes(raw, path.suffix, record["session"]["session_id"], new_id("d"))
    record["session"]["dokumente"].append({"dok_id": doc.dok_id, "format": doc.format, "quelle_rolle": rolle,
                                           "freigabe": {"status": "offen", "funde_je_kategorie": _funde_counts(doc)}})
    store.save(record)
    ram.put(doc)
    return {"dok_id": doc.dok_id, "format": doc.format, "seiten": doc.seiten, "ocr_noetig": bool(doc.ocr_seiten)}


def ocr_ausfuehren(args: dict, ctx=None) -> dict:
    doc = ram.get(str(args.get("session_id", "")), str(args.get("dok_id", "")))
    if doc is None:
        raise EngineError("E_NICHT_GEFUNDEN")
    pages = list(doc.ocr_seiten)
    for i, (page, png) in enumerate(importer.render_pages_png(doc, pages), 1):
        text = external.ocr_png(png)
        if text.strip():
            doc.parts.append(ram.Part("haupttext", text, page))
        if ctx is not None:
            ctx.emit({"event": "fortschritt", "schritt": "ocr", "anteil": round(i / len(pages), 3)})
    doc.ocr_seiten = []
    return {"seiten_erkannt": len(pages)}


def _doc(args: dict):
    doc = ram.get(str(args.get("session_id", "")), str(args.get("dok_id", "")))
    if doc is None:
        raise EngineError("E_NICHT_GEFUNDEN")
    return doc


def bekannte_namen_setzen(args: dict, ctx=None) -> dict:
    """Names the psychologist knows (child, parents, teacher, school), with the role that replaces them.
    RAM only (stage 1 of recognition); never stored, never logged."""
    record = store.load(str(args.get("session_id", "")))
    namen = args.get("namen")
    if not isinstance(namen, list) or not all(isinstance(n, dict) and isinstance(n.get("text"), str)
                                               and n["text"].strip() and isinstance(n.get("rolle"), str)
                                               and n["rolle"].strip() for n in namen):
        raise EngineError("E_SCHEMA", "argumente")
    known = [recognition.KnownName(n["text"], n["rolle"]) for n in namen]
    ram.set_names(args["session_id"], known)
    # The label was checked before any name was known; a name in it now asks for sitzung_umbenennen (EGM E17).
    label_hit = any(f.quelle == "liste" for f in recognition.detect_text(record["session"]["bezeichnung"], 0, known,
                                                                          None, use_ner=False))
    return {"anzahl": len(namen), "bezeichnung_enthaelt_namen": label_hit}


def erkennung_ausfuehren(args: dict, ctx=None) -> dict:
    doc = _doc(args)
    if doc.ocr_seiten:
        raise EngineError("E_BLOCKIERT")  # OCR must run first, otherwise scanned pages are not checked
    testtag = None
    if args.get("testdatum") is not None:
        try:
            testtag = date.fromisoformat(str(args["testdatum"]))  # transient, never stored
        except ValueError:
            raise EngineError("E_SCHEMA", "argumente")
    doc.funde = recognition.detect_document(doc.parts, ram.names(doc.session_id), testtag)
    doc.erkennung_gelaufen = True
    out = _fund_state(doc)
    hinweise = [] if ram.names_set(doc.session_id) else ["namen_fehlen"]
    if not recognition.rare_terms():
        hinweise.append("seltene_merkmale_ohne_liste")  # first language, country of origin stay unchecked (E13)
    return out | {"hinweise": hinweise}


def _fund_state(doc) -> dict:
    return {"funde": [f.for_ui() for f in doc.funde], "funde_je_kategorie": recognition.counts(doc.funde, doc.bilder)}


def schwaerzung_entscheiden(args: dict, ctx=None) -> dict:
    doc = _doc(args)
    fund = next((f for f in doc.funde if f.fund_id == args.get("fund_id")), None)
    entscheidung = {"uebernehmen": "uebernommen", "verwerfen": "verworfen", "aendern": "geaendert"}.get(
        args.get("entscheidung"))
    if fund is None:
        raise EngineError("E_NICHT_GEFUNDEN")
    if entscheidung is None or (entscheidung == "geaendert" and not isinstance(args.get("ersatz"), str)):
        raise EngineError("E_SCHEMA", "argumente")
    if fund.kategorie == "versteckte_inhalte" and entscheidung == "verworfen":
        raise EngineError("E_BLOCKIERT")  # hidden content is never released (projektrahmen.md, Harte Vorgaben 7)
    if fund.quelle == "liste" and fund.kategorie == "direkte_identifikatoren" and entscheidung == "verworfen":
        raise EngineError("E_BLOCKIERT")  # a known name can be changed, never kept (EGM E08)
    fund.status = entscheidung
    if entscheidung == "geaendert":
        fund.ersatz = args["ersatz"]
    return {"fund": fund.for_ui(), "funde_je_kategorie": recognition.counts(doc.funde, doc.bilder)}


def anonymisierung_freigeben(args: dict, ctx=None) -> dict:
    """Release needs: recognition ran, no open uncertain finding, explicit confirmation, and a clean re-check of the
    released text with names and rules. Then the anonymised text is stored and the clear text is dropped."""
    doc = _doc(args)
    if args.get("geprueft_bestaetigt") is not True:
        raise EngineError("E_SCHEMA", "argumente")
    if not doc.erkennung_gelaufen or any(f.status == "offen" for f in doc.funde):
        raise EngineError("E_ANONYMISIERUNG_OFFEN")
    text, kept = recognition.anonymize(doc.parts, doc.funde, doc.bilder)
    recheck = [f for f in recognition.detect_text(text, 0, ram.names(doc.session_id), None, use_ner=False)
               if not f.unsicher and not any(a <= f.start and f.end <= b for a, b in kept)]
    if recheck:
        raise EngineError("E_ANONYMISIERUNG_OFFEN")
    record = store.load(doc.session_id)
    entry = next(d for d in record["session"]["dokumente"] if d["dok_id"] == doc.dok_id)
    entry["freigabe"] = {"status": "freigegeben", "funde_je_kategorie": recognition.counts(doc.funde, doc.bilder),
                         "geprueft_bestaetigt": True}
    entry["text_anonymisiert"] = text
    store.save(record)
    ram.drop(doc.dok_id)
    return {"freigabe": entry["freigabe"]}


def _iso(args: dict, key: str) -> date:
    try:
        return date.fromisoformat(str(args.get(key)))
    except ValueError:
        raise EngineError("E_SCHEMA", "argumente")


def alter_berechnen(args: dict, ctx=None) -> dict:
    """Age J;M on the test day; both dates are used for this call only (transient)."""
    try:
        return {"alter": derive.age(_iso(args, "geburtsdatum"), _iso(args, "testdatum"))}
    except ValueError:
        raise EngineError("E_SCHEMA", "argumente")


def schulbesuch_berechnen(args: dict, ctx=None) -> dict:
    try:
        return {"schulbesuch_oesterreich_monate": derive.months_between(_iso(args, "schulbeginn_oesterreich"),
                                                                        _iso(args, "testdatum"))}
    except ValueError:
        raise EngineError("E_SCHEMA", "argumente")


def normwerte_ableiten(args: dict, ctx=None) -> dict:
    """Norm group of the child and age of the norms on the test day, from the test catalogue."""
    entry = config.load().test(args.get("testkatalog_id"))
    if entry is None:
        raise EngineError("E_NICHT_GEFUNDEN")
    alter = args.get("alter")
    if not isinstance(alter, dict) or not isinstance(alter.get("jahre"), int) or not isinstance(alter.get("monate"), int):
        raise EngineError("E_SCHEMA", "argumente")
    out = {"normen_alter_jahre": derive.norm_age_years(entry, _iso(args, "testdatum"))}
    if group := derive.norm_group(entry, alter):
        out["normgruppe"] = group
    return out


def fachregeln_pruefen(args: dict, ctx=None) -> dict:
    """Full rule result, local only. Claude only ever receives rules.fuer_claude(...) (step 1.6)."""
    record = store.load(str(args.get("session_id", "")))
    if "gutachten_input" not in record:
        raise EngineError("E_NICHT_GEFUNDEN")
    result = rules.pruefe_fachregeln(record["gutachten_input"], config.load())
    validate("regelergebnis", result)
    return {"regelergebnis": result}


def eingabe_speichern(args: dict, ctx=None) -> dict:
    record = store.load(str(args.get("session_id", "")))
    gi = args.get("gutachten_input")
    session = record["session"]
    if not isinstance(gi, dict) or gi.get("session_id") != session["session_id"] \
            or gi.get("gutachtentyp") != session.get("gutachtentyp"):
        raise EngineError("E_SCHEMA", "argumente")
    from .app_functions import gespeicherte_qualifikationen
    if (quali := gespeicherte_qualifikationen()) is not None:
        gi = gi | {"verfasserin": {"qualifikationen": quali}}  # one source for Q1: the profile of Screen 13 (EGM B5)
    validate("gutachten-input", gi)  # also rejects a diagnosis in SPF and one without Q1
    if funde := _freitext_offen(session["session_id"], gi, args):
        return {"gespeichert": False, "funde": funde}
    cfg = config.load()
    record["gutachten_input"] = gi
    session["versionen"].update(regelwerk=cfg.version("regelwerk"), testkatalog=cfg.version("testkatalog"),
                                konfiguration=cfg.lernbausteine["version"] if cfg.lernbausteine else NOT_CONFIGURED)
    if session["status"] == "import":
        session["status"] = "eingabe"
    store.save(record)
    return {"gespeichert": True, "session": session}


def _signal(record: dict, **fields) -> dict | None:
    """Learning signal (lernsignal.schema.json); supervision never produces one (Nachtrag 1, ADR 0002)."""
    modus = record["session"]["modus"]
    if modus == "supervision":
        return None
    signal = {"schema_version": "1", "signal_id": new_id("ls"),
              "herkunft": "intervision" if modus == "intervision" else "gutachten",
              "konfiguration_version": record["session"]["versionen"].get("konfiguration", NOT_CONFIGURED), **fields}
    validate("lernsignal", signal)
    record.setdefault("lernsignale", []).append(signal)
    return signal


def befund_entscheiden(args: dict, ctx=None) -> dict:
    record = store.load(str(args.get("session_id", "")))
    befund = next((b for b in record.get("befunde", []) if b["befund_id"] == args.get("befund_id")), None)
    status = {"annehmen": "angenommen", "verwerfen": "verworfen"}.get(args.get("entscheidung"))
    if befund is None:
        raise EngineError("E_NICHT_GEFUNDEN")
    if status is None:
        raise EngineError("E_SCHEMA", "argumente")
    befund["entscheidung"] = {"status": status, **({"kommentar": args["kommentar"]}
                                                   if isinstance(args.get("kommentar"), str) else {})}
    signal = _signal(record, art=f"befund_{status}", bereich="sprache" if befund["pruefer"] == "stil" else "pruefverhalten",
                     pruefer=befund["pruefer"], befund_id=befund["befund_id"])
    store.save(record)
    return {"befund": befund, "lernsignal": signal}


def text_aendern(args: dict, ctx=None) -> dict:
    """The psychologist edits one paragraph; a new draft version is stored and a text_geaendert signal created."""
    record = store.load(str(args.get("session_id", "")))
    if not record.get("entwuerfe") or not isinstance(args.get("nachher"), str) or not args["nachher"].strip():
        raise EngineError("E_NICHT_GEFUNDEN" if not record.get("entwuerfe") else "E_SCHEMA")
    draft = json.loads(json.dumps(record["entwuerfe"][-1]))
    abschnitt = next((a for a in draft["abschnitte"] if a["abschnitt_id"] == args.get("abschnitt_id")), None)
    absatz = next((p for p in (abschnitt or {}).get("absaetze", []) if p["absatz_id"] == args.get("absatz_id")), None)
    if absatz is None:
        raise EngineError("E_NICHT_GEFUNDEN")
    if funde := _freitext_offen(record["session"]["session_id"], {"nachher": args["nachher"]}, args):
        return {"gespeichert": False, "funde": funde}
    vorher = " ".join(s.get("text", "") for s in absatz["saetze"]).strip()
    quellen = sorted({q for s in absatz["saetze"] for q in s.get("quellen", [])}
                     | {s["luecke"]["feld"] for s in absatz["saetze"] if "luecke" in s})
    if not quellen:
        raise EngineError("E_BELEG")  # no pointer to keep; "/" is not the whole input under RFC 6901 (EGM E56)
    absatz["saetze"] = [{"text": args["nachher"], "quellen": quellen}]
    draft["entwurf_version"] += 1
    validate("gutachten-output", draft)
    record["entwuerfe"].append(draft)
    signal = _signal(record, art="text_geaendert", bereich="sprache", pruefer=None, abschnitt_id=abschnitt["abschnitt_id"],
                     vorher=vorher[:500], nachher=args["nachher"][:500])
    store.save(record)
    return {"gespeichert": True, "entwurf_version": draft["entwurf_version"], "lernsignal": signal}


def _vorlagen_dir() -> Path:
    return packages.vorlagen_dir()


def vorlage_importieren(args: dict, ctx=None) -> dict:
    """Copy a DOCX template into the local templates folder and return its structure for the mapping dialog."""
    path = Path(str(args.get("pfad", "")))
    if not path.is_file():
        raise EngineError("E_NICHT_GEFUNDEN")
    raw = path.read_bytes()
    if importer.detect_format(raw, path.suffix.lstrip(".")) != "docx":
        raise EngineError("E_DATEITYP", "format")
    info = docx_template.analyze(raw)
    datei = re.sub(r"[^\w.-]", "_", path.stem) + ".docx"
    if (_vorlagen_dir() / datei).exists():
        raise EngineError("E_BLOCKIERT")  # same file name: never overwrite a template silently (EGM E61)
    store.write_new(_vorlagen_dir() / datei, raw)
    return {"datei": datei, "titel": info["titel"], "kopf_beschriftungen": info["kopf_beschriftungen"],
            "felder": info["felder"]}


def vorlage_zuordnen(args: dict, ctx=None) -> dict:
    vorlage = args.get("vorlage")
    if not isinstance(vorlage, dict) or "datei" not in vorlage:
        raise EngineError("E_SCHEMA", "argumente")
    validate("vorlage", vorlage)
    if Path(vorlage["datei"]).name != vorlage["datei"] or re.match(r"^[A-Za-z]:", vorlage["datei"]):
        raise EngineError("E_SCHEMA", "pfad")  # "D:x.docx" passes the schema pattern (EGM E61)
    template = _vorlagen_dir() / vorlage["datei"]
    if not template.is_file():
        raise EngineError("E_NICHT_GEFUNDEN")
    docx_template.check_mapping(template.read_bytes(), vorlage)
    store.write_atomic(_vorlagen_dir() / f"{vorlage['vorlage_id']}.json", json.dumps(vorlage, ensure_ascii=False).encode())
    return {"vorlage_id": vorlage["vorlage_id"]}


def _export_bereit(record: dict):
    """Every export lock in one place (also for the preview of Screen 06). Returns draft, input, template, config."""
    if not record.get("entwuerfe") or "gutachten_input" not in record:
        raise EngineError("E_NICHT_GEFUNDEN")
    draft, gi = record["entwuerfe"][-1], record["gutachten_input"]
    if gi["gutachtentyp"] == "emotional_soziale_entwicklung":
        raise EngineError("E_BLOCKIERT")  # no template yet (Nachtrag 1)
    if not re.fullmatch(r"[a-z0-9-]+", str(draft["vorlage_id"])):
        raise EngineError("E_SCHEMA", "pfad")  # vorlage_id comes from Claude; never a path (EGM E31)
    meta_path = _vorlagen_dir() / f"{draft['vorlage_id']}.json"
    if not meta_path.is_file():
        raise EngineError("E_NICHT_GEFUNDEN")
    vorlage = json.loads(meta_path.read_text(encoding="utf-8"))
    cfg = config.load()
    if cfg.regelwerk is None:
        raise EngineError("E_BLOCKIERT")
    result = rules.pruefe_fachregeln(gi, cfg)
    # nicht_pruefbar blocks as well: a missing input or parameter is listed and stops the export (Nachtrag 1, E30)
    if any(e["wirkung"] == "blockiert_export" and e["ergebnis"] != "erfuellt" for e in result["ergebnisse"]):
        raise EngineError("E_BLOCKIERT")
    if belege.pruefe_belege(draft, gi, cfg):
        raise EngineError("E_BELEG")
    return draft, gi, vorlage, cfg


def docx_exportieren(args: dict, ctx=None) -> dict:
    """Export the latest draft into the template. Blocks on export rules, failed evidence, missing sections, the type
    without template, a missing rule set, and an existing target file (no overwrite)."""
    record = store.load(str(args.get("session_id", "")))
    target = Path(str(args.get("ziel_pfad", "")))
    if target.suffix.lower() != ".docx":
        raise EngineError("E_SCHEMA", "argumente")
    draft, gi, vorlage, cfg = _export_bereit(record)
    sections, tables = belege.render(draft, gi, cfg)
    data = docx_template.fill((_vorlagen_dir() / vorlage["datei"]).read_bytes(), vorlage, sections, tables)
    store.write_new(target, data)
    return {"entwurf_version": draft["entwurf_version"]}


def export_vorschau(args: dict, ctx=None) -> dict:
    """Screen 06: the text as it will stand in the template, the header labels that stay placeholders, and the lock
    (error code) if the export would refuse. Nothing is written."""
    record = store.load(str(args.get("session_id", "")))
    try:
        draft, gi, vorlage, cfg = _export_bereit(record)
        sperre = None
    except EngineError as e:
        if not record.get("entwuerfe") or "gutachten_input" not in record:
            raise
        sperre = e.as_dict()
        draft, gi, cfg, vorlage = record["entwuerfe"][-1], record["gutachten_input"], config.load(), None
    sections, tables = belege.render(draft, gi, cfg)
    return {"entwurf_version": draft["entwurf_version"], "sperre": sperre,
            "abschnitte": [{"abschnitt_id": a["abschnitt_id"], "text": sections.get(a["abschnitt_id"], ""),
                            "tabellen": tables.get(a["abschnitt_id"], [])} for a in draft["abschnitte"]],
            "kopffelder": (vorlage or {}).get("kopffelder", []),
            "ueberschriften": {a["abschnitt_id"]: a["ueberschrift"] for a in (vorlage or {}).get("abschnitte", [])},
            "vorlage_id": draft["vorlage_id"]}


# Fields that hold JSON pointers, IDs or versions, never free text; only these are exempt from the re-check (EGM E02).
_NO_FREE_TEXT = {"quellen", "feld", "felder", "wert_quelle", "baustein_quelle", "schema_version", "regel_version",
                 "regelwerk_version", "testkatalog_version", "regelergebnis_version", "entwurf_version"}
# Enum fields (the schema checks them before the free text check): a value from the enum cannot hold a name. Only
# such a value is exempt, never any text under the same key (Task 4.3: the NER flagged "schulpsychologin"; EGM C21).
_ENUM_WERTE = {
    "qualifikationen": {"schulpsychologin", "klinische_psychologin", "gesundheitspsychologin"},
    "gutachtentyp": {"spf", "lrs", "rechenstoerung", "emotional_soziale_entwicklung"},
    "art": {"gespraech", "bericht", "vorbefund", "fragebogen", "sonstiges", "kindeswohl", "akute_gefaehrdung"},
    "ebene": {"index", "subtest", "fall", "beziehung", "rolle_und_system", "person", "ethik_und_qualitaet"},
    "skala": {"iq", "wertpunkte", "t", "pr"},
    "klinischer_eindruck": {"dokumentiert", "fehlt", "nicht_anwendbar"},
    "intelligenztest": {"dokumentiert", "fehlt", "nicht_anwendbar"},
    "befragung_adaptives_verhalten": {"dokumentiert", "fehlt", "nicht_anwendbar"},
}


def _texts(node, pointer="", key=""):
    if key in _NO_FREE_TEXT or key.endswith("_id"):
        return
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _texts(v, f"{pointer}/{k}", k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _texts(v, f"{pointer}/{i}", key)
    elif isinstance(node, str) and node not in _ENUM_WERTE.get(key, ()):
        yield pointer, node


def _freitext_funde(session_id: str, node, use_ner: bool, names_needed: bool = True) -> list[dict]:
    """Recognition on free text typed in the app or sent out. Needs the known names of this run: after a restart
    they are gone and must be entered again, otherwise stage 1 would silently fall away (EGM E01, E02)."""
    if names_needed and not ram.names_set(session_id):
        raise EngineError("E_BLOCKIERT", "namen_fehlen")
    names = ram.names(session_id) if ram.names_set(session_id) else []
    return [{"feld": p, "text": f.text, "kategorie": f.kategorie, "sicher": not f.unsicher}
            for p, text in _texts(node) for f in recognition.detect_text(text, 0, names, None, use_ner)]


def _freitext_offen(session_id: str, node, args: dict) -> list[dict]:
    """Findings that stop a save: every certain one, and uncertain ones until the psychologist confirms them."""
    funde = _freitext_funde(session_id, node, use_ner=True)
    if any(f["sicher"] for f in funde) or (funde and args.get("unsichere_bestaetigt") is not True):
        return funde
    return []


def erzeuge_paket(args: dict, ctx=None) -> dict:
    """Browser variant (ADR 0002). Recognition runs again right before the export with the known names and the
    rules; any certain hit blocks (fallpaket.schema.json: anonymisierung_geprueft). NER and uncertain hits were
    decided where the text entered: at the release of each document and when free text was saved."""
    record = store.load(str(args.get("session_id", "")))
    paket = packages.make_package(record, str(args.get("art", "")), config.load(), args)
    # Rubberduck packages hold no case data from the app, so no list of names is asked for; the rules still run
    # over the free text the psychologist typed into Claude (EGM Task 3 B14).
    names_needed = record["session"]["modus"] == "gutachten"
    if any(f["sicher"] for f in _freitext_funde(record["session"]["session_id"], paket["inhalt"], use_ner=False,
                                               names_needed=names_needed)):
        raise EngineError("E_ANONYMISIERUNG_OFFEN")
    ziel = args.get("ziel_pfad")
    if ziel is not None and (not isinstance(ziel, str) or Path(ziel).suffix.lower() != ".json"):
        raise EngineError("E_SCHEMA", "argumente")
    if ziel:  # Task 4.3: the app's save dialog; written whole or not at all, never over an existing file. Written
        # before the package is registered, so a refused target leaves no open package behind (EGM C5)
        store.write_new(Path(ziel), json.dumps(paket, ensure_ascii=False, indent=1).encode("utf-8"))
    packages.register(record["session"]["session_id"], paket)
    return {"fallpaket": paket}


def lies_rueckgabe(args: dict, ctx=None) -> dict:
    record = store.load(str(args.get("session_id", "")))
    if not isinstance(args.get("text"), str):
        raise EngineError("E_SCHEMA", "argumente")
    return {"gueltig": True, **packages.read_return(record, args["text"], config.load())}


def protokoll_beenden(args: dict, ctx=None) -> dict:
    """Ends an intervision or supervision protocol in phase abschluss; review findings stored so far go with it."""
    record = store.load(str(args.get("session_id", "")))
    result = rubberduck.beenden(record)
    store.save(record)
    return result


def _q1_record(args: dict) -> dict:
    record = store.load(str(args.get("session_id", "")))
    if not packages.q1(record.get("gutachten_input")):
        raise EngineError("E_Q1")
    return record


def interne_diagnose_speichern(args: dict, ctx=None) -> dict:
    """Blind comparison: the internal diagnosis is entered before any proposal is shown and cannot change after."""
    record = _q1_record(args)
    if "vergleich" in record:
        raise EngineError("E_BLOCKIERT")
    diagnose = args.get("interne_diagnose")
    if not isinstance(diagnose, dict):
        raise EngineError("E_SCHEMA", "argumente")
    if funde := _freitext_offen(record["session"]["session_id"], {"text": diagnose.get("text")}, args):
        return {"gespeichert": False, "funde": funde}  # free text goes through the recognition (EGM B4)
    record["interne_diagnose"] = diagnose | {"erfasst_vor_vorschlaegen": True}
    store.save(record)
    return {"gespeichert": True}


def _vergleich(intern: dict, vorschlag: dict | None) -> str:
    if not vorschlag or not intern.get("icd10_code") or not vorschlag.get("icd10_code"):
        return "nicht_vergleichbar"
    return "gleich" if intern["icd10_code"] == vorschlag["icd10_code"] else "abweichend"


def diagnosevergleich_laden(args: dict, ctx=None) -> dict:
    record = _q1_record(args)
    if "interne_diagnose" not in record:
        raise EngineError("E_BLOCKIERT")
    cfg = config.load()
    gi = record["gutachten_input"]
    vorschlaege = [v for v in record.get("diagnosevorschlaege", []) if v["quelle"] == "claude"]
    engine = rules.engine_diagnosevorschlag(gi, rules.pruefe_fachregeln(gi, cfg), cfg)
    claude = vorschlaege[-1] if vorschlaege else None
    vergleich = {"engine": _vergleich(record["interne_diagnose"], engine),
                 "claude": _vergleich(record["interne_diagnose"], claude),
                 **({"notiz": record["vergleich"]["notiz"]} if record.get("vergleich", {}).get("notiz") else {})}
    if record.get("diagnosevorschlaege") != [engine] + vorschlaege or record.get("vergleich") != vergleich:
        # written only on a change: the app polls this while waiting for Claude (EGM B3)
        record["diagnosevorschlaege"] = [engine] + vorschlaege
        record["vergleich"] = vergleich
        store.save(record)
    return {"interne_diagnose": record["interne_diagnose"], "engine": engine, "claude": claude,
            "vergleich": record["vergleich"]}


def vergleich_notiz_speichern(args: dict, ctx=None) -> dict:
    record = _q1_record(args)
    if "vergleich" not in record or not isinstance(args.get("notiz"), str):
        raise EngineError("E_BLOCKIERT" if "vergleich" not in record else "E_SCHEMA")
    if funde := _freitext_offen(record["session"]["session_id"], {"notiz": args["notiz"]}, args):
        return {"gespeichert": False, "funde": funde}  # EGM B4
    record["vergleich"]["notiz"] = args["notiz"]
    store.save(record)
    return {"gespeichert": True, "vergleich": record["vergleich"]}


FUNCTIONS = {
    "erzeuge_paket": erzeuge_paket,
    "lies_rueckgabe": lies_rueckgabe,
    "protokoll_beenden": protokoll_beenden,
    "interne_diagnose_speichern": interne_diagnose_speichern,
    "diagnosevergleich_laden": diagnosevergleich_laden,
    "vergleich_notiz_speichern": vergleich_notiz_speichern,
    "eingabe_speichern": eingabe_speichern,
    "befund_entscheiden": befund_entscheiden,
    "text_aendern": text_aendern,
    "vorlage_importieren": vorlage_importieren,
    "vorlage_zuordnen": vorlage_zuordnen,
    "docx_exportieren": docx_exportieren,
    "export_vorschau": export_vorschau,
    "alter_berechnen": alter_berechnen,
    "schulbesuch_berechnen": schulbesuch_berechnen,
    "normwerte_ableiten": normwerte_ableiten,
    "fachregeln_pruefen": fachregeln_pruefen,
    "bekannte_namen_setzen": bekannte_namen_setzen,
    "erkennung_ausfuehren": erkennung_ausfuehren,
    "schwaerzung_entscheiden": schwaerzung_entscheiden,
    "anonymisierung_freigeben": anonymisierung_freigeben,
    "status": status,
    "sitzung_anlegen": sitzung_anlegen,
    "sitzungen_auflisten": sitzungen_auflisten,
    "sitzung_laden": sitzung_laden,
    "sitzung_umbenennen": sitzung_umbenennen,
    "dokument_importieren": dokument_importieren,
    "ocr_ausfuehren": ocr_ausfuehren,
}

from .app_functions import FUNCTIONS as _APP_FUNCTIONS  # noqa: E402  (Task 4; imports no function of this module)

FUNCTIONS.update(_APP_FUNCTIONS)
