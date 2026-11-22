"""Learning loop (Task 5, ADR 0001 Lernschleife): proposals from learning signals for konfiguration/lernbausteine.json
only, a deterministic eval suite, release only by the psychologist in the app.

Two guards, kept apart (EGM Task 5 B3): the lock list secures the file (a proposal can only target
lernbausteine.json), the eval suite secures the content of a block (no rules, parameters, locked areas, diagnoses,
statements instead of recommendations, suppressed findings, identifying data)."""
import json
import re
import unicodedata
from pathlib import Path

from . import config, recognition, store
from .contracts import validate
from .errors import EngineError
from .ids import new_id

# Locked as a path list (prompts-v2.md, Task 5): a proposal naming any of these is refused, whatever it says.
GESPERRT = ("regelwerk", "kategorienskala", "vorlagen", "testkatalog", "hinweise.json", "icd10-referenz",
            "diagnosevergleich", "supervision")
ERLAUBT = "lernbausteine.json"
# package type -> (target, origin of the blocks it gets): report reviews learn from reports, protocol reviews from
# intervision (EGM Task 5 B7)
ZIELE = {"gutachten": ("entwurf", "gutachten"), "pruefung_stil": ("stil", "gutachten"),
         "pruefung_goldfisch": ("goldfisch", "gutachten"), "pruefung_elefant": ("elefant", "gutachten"),
         "protokoll_goldfisch": ("goldfisch", "intervision"), "protokoll_elefant": ("elefant", "intervision")}
OFFEN = ("offen", "eval_bestanden", "eval_abgelehnt")  # a proposal in these states reserves its signals (EGM B13)


def datei_pruefen(datei) -> None:
    if not isinstance(datei, str) or not datei.strip():
        raise EngineError("E_SCHEMA", "argumente")
    norm = datei.replace(chr(92), "/").strip().casefold()
    if any(g in norm for g in GESPERRT):
        raise EngineError("E_BLOCKIERT", "gesperrt")
    if norm != ERLAUBT:
        raise EngineError("E_SCHEMA", "pfad")


def _dir() -> Path:
    d = (config.config_dir() or store.data_dir().parent / "konfiguration") / "vorschlaege"
    d.mkdir(parents=True, exist_ok=True)
    return d


def aktuell() -> dict | None:
    return config.load().lernbausteine


def _version(doc: dict | None) -> str:
    return doc["version"] if doc else "keine"


def fuer_claude(cfg, art: str) -> list[dict] | None:
    """The released blocks for one package type, as lernbausteine.schema.json#/$defs/fuer_claude."""
    if art not in ZIELE or not cfg.lernbausteine:
        return None
    ziel, herkunft = ZIELE[art]
    out = [{"bereich": b["bereich"], "text": b["text"]} for b in cfg.lernbausteine["bausteine"]
           if b["ziel"] == ziel and b["herkunft"] == herkunft]
    return out or None


# ---------------------------------------------------------------- signals

def signale() -> list[dict]:
    """Learning signals from reports and intervision. Supervision never; the diagnosis comparison is no signal."""
    out = []
    for r in store.all_records():
        if r["session"]["modus"] == "supervision":
            continue
        out += [s for s in r.get("lernsignale", []) if s.get("herkunft") in ("gutachten", "intervision")]
    return out


def reserviert() -> set[str]:
    """Signals carried by a proposal that is not discarded: they can carry no second one (EGM B13)."""
    return {sid for v in alle() if v["status"] in OFFEN for sid in v["signal_ids"]}


def signale_uebersicht() -> dict:
    """For /verbessern: the free signals with their text, used and reserved ones only counted (EGM B12), and the
    active blocks with their IDs, so a change or removal can name them (EGM C10)."""
    gebunden = reserviert()
    keys = ("signal_id", "herkunft", "art", "bereich", "pruefer", "abschnitt_id", "vorher", "nachher")
    frei, gruppen = [], {}
    for s in signale():
        g = gruppen.setdefault(f"{s['herkunft']}/{s['bereich']}/{s.get('pruefer')}",
                               {"herkunft": s["herkunft"], "bereich": s["bereich"], "pruefer": s.get("pruefer"),
                                "frei": 0, "verwendet": 0})
        if s.get("verwendet_in_vorschlag") or s["signal_id"] in gebunden:
            g["verwendet"] += 1
        else:
            g["frei"] += 1
            frei.append({k: s[k] for k in keys if k in s})
    doc = aktuell()
    return {"signale": frei, "gruppen": list(gruppen.values()), "mindestens": 3,
            "bausteine": doc["bausteine"] if doc else [], "version": _version(doc)}


# ---------------------------------------------------------------- proposals

def anwenden(doc: dict | None, v: dict) -> list[dict]:
    bausteine = [dict(b) for b in (doc["bausteine"] if doc else [])]
    a = v["aenderung"]
    if a["art"] == "hinzufuegen":
        bausteine.append({"baustein_id": new_id("lb"), "bereich": v["bereich"], "ziel": a["ziel"], "text": a["text"],
                          "herkunft": v["herkunft"], "vorschlag_id": v["vorschlag_id"]})
        return bausteine
    ziel = next((b for b in bausteine if b["baustein_id"] == a.get("baustein_id")), None)
    if ziel is None or ziel["bereich"] != v["bereich"] or ziel["herkunft"] != v["herkunft"]:
        raise EngineError("E_NICHT_GEFUNDEN")
    if a["art"] == "entfernen":
        return [b for b in bausteine if b is not ziel]
    ziel.update(text=a["text"], vorschlag_id=v["vorschlag_id"], **({"ziel": a["ziel"]} if "ziel" in a else {}))
    return bausteine


def _pfad(vorschlag_id) -> Path:
    if not isinstance(vorschlag_id, str) or not re.fullmatch(r"vs-[0-9a-f]{8}", vorschlag_id):
        raise EngineError("E_SCHEMA", "argumente")
    return _dir() / f"{vorschlag_id}.json"


def laden(vorschlag_id) -> dict:
    """A stored proposal, checked: schema and target again, an edited or broken file is refused (EGM C7)."""
    path = _pfad(vorschlag_id)
    if not path.is_file():
        raise EngineError("E_NICHT_GEFUNDEN")
    try:
        v = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        raise EngineError("E_SCHEMA", "beschaedigt") from None
    validate("aenderungsvorschlag", v)
    datei_pruefen(v["datei"])
    return v


def sperre(vorschlag_id):
    """One writer per proposal at a time: starte_evals (MCP) and release or discard (app) run in two processes."""
    return store._lock(_pfad(vorschlag_id))


def speichern(v: dict) -> None:
    validate("aenderungsvorschlag", v)
    store.write_atomic(_pfad(v["vorschlag_id"]), json.dumps(v, ensure_ascii=False, indent=1).encode("utf-8"))


def alle() -> list[dict]:
    out = []
    for p in sorted(_dir().glob("vs-*.json")):
        try:
            v = json.loads(p.read_text(encoding="utf-8"))
            validate("aenderungsvorschlag", v)
            out.append(v)
        except (ValueError, EngineError):
            continue
    return out


def schlage_vor(v) -> dict:
    """/verbessern: check the target against the lock list first, then schema, signals and the change itself."""
    if not isinstance(v, dict):
        raise EngineError("E_SCHEMA", "argumente")
    datei_pruefen(v.get("datei"))
    doc = aktuell()
    v = {k: x for k, x in v.items() if k not in ("eval", "neue_version")} | {
        "schema_version": "1", "vorschlag_id": new_id("vs"), "status": "offen", "basis_version": _version(doc)}
    validate("aenderungsvorschlag", v)
    # the change itself first: a block that cannot exist (review behaviour for the draft) is a schema error
    validate("lernbausteine", {"schema_version": "1", "version": "pruefung", "bausteine": anwenden(doc, v)})
    bekannt = {s["signal_id"]: s for s in signale()}
    gebunden = reserviert()
    ziel = v["aenderung"].get("ziel") or next((b["ziel"] for b in (doc["bausteine"] if doc else [])
                                               if b["baustein_id"] == v["aenderung"].get("baustein_id")), None)
    for sid in v["signal_ids"]:
        s = bekannt.get(sid)
        # at least three unused signals of the same origin and area (prompts-v2.md, Task 5); for review behaviour
        # also of the reviewer the block is for (EGM B7)
        if (s is None or s["herkunft"] != v["herkunft"] or s["bereich"] != v["bereich"]
                or s.get("verwendet_in_vorschlag") or sid in gebunden
                or (v["bereich"] == "pruefverhalten" and s.get("pruefer") != ziel)):
            raise EngineError("E_BLOCKIERT", "signale")
    store.write_new(_pfad(v["vorschlag_id"]), json.dumps(v, ensure_ascii=False, indent=1).encode("utf-8"))
    return {"vorschlag_id": v["vorschlag_id"], "status": v["status"]}


# ---------------------------------------------------------------- eval suite (deterministic part)

def norm(text: str) -> str:
    """One form for every check: NFKC, no invisible format characters (zero width and the like), lower case, umlauts
    as ae, oe, ue, ss, so "unterdrücken" and "unterdruecken" meet the same pattern (EGM B1, B2)."""
    t = unicodedata.normalize("NFKC", text)
    t = "".join(c for c in t if unicodedata.category(c) != "Cf").casefold()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        t = t.replace(a, b)
    return t


_TEILSATZ = re.compile(r"[.!?;:,]|\bsondern\b|\baber\b")
_VERNEINT = re.compile(r"\b(nie|niemals|nicht|kein\w*|statt|anstatt|anstelle)\W+(\w+\W+){0,2}$")
_FESTSTELLEN = re.compile(r"\bfest(gestellt\w*|stell\w*|zustellen)|\bstell\w*\b(\W+\w+){0,6}\W+fest\b")
_ICD = re.compile(r"\b[a-z]\d{2}(\.\d{1,2})?\b")
_DIAGNOSE = re.compile(r"diagnos\w*")
_ZAHLWORT = r"(\d+|null|eins?|zwei|drei|vier|fuenf|sechs|sieben|acht|neun|zehn|elf|zwoelf|zwanzig|dreissig|vierzig|fuenfzig|hundert)"
_PARAMETER = re.compile(r"grenzwert|schwellenwert|\bschwelle|regelwerk|kategorienskala|testkatalog|normgruppe|wortlaut|"
                        r"icd|diagnosevergleich|supervision|standardabweichung|perzentil|cut-?off|"
                        r"vorlage\w*\W+(\w+\W+){0,4}(aender|ersetz|abweich)|(aender|ersetz|abweich)\w*\W+(\w+\W+){0,4}vorlage")
_ZAHL_WERT = re.compile(_ZAHLWORT + r"\s*(%|prozent|iq|wertpunkt\w*|t-wert\w*|punkte?|prozentrang\w*|sd\b)|"
                        r"(iq|prozentrang|t-wert|wertpunkt\w*)\W+(\w+\W+){0,2}" + _ZAHLWORT)
_UNTERDRUECKEN = re.compile(r"unterdrueck|ignorier|verschweig|weglass|weg\W*lassen|auslass|aus\W*lassen|uebergeh|"
                            r"ueberspring|zurueckhalt|zurueck\W*halten|verzicht")
_NICHT_MELDEN = re.compile(r"\b(nicht|nie|keine?)\W+(mehr\W+)?(\w+\W+){0,3}(melden|berichten|erwaehnen|anzeigen|nennen|"
                           r"aufnehmen|ausweisen)|\bnur\W+(noch\W+)?(\w+\W+){0,3}(melden|berichten|erwaehnen|anzeigen|"
                           r"nennen)\b[^.]*\bwenn\b|\bnur\W+(dann|noch)\W+(melden|berichten|erwaehnen)|"
                           r"\bseltener\W+(melden|anzeigen|berichten)|\bweniger\W+(befunde|hinweise)")
_ABSTUFEN = re.compile(r"hoechstens\W+als|herabstuf|herunterstuf|abstuf|abwert|als\W+(gering|mittel)\W+(einstuf|wert|meld)|"
                       r"\b(gering|mittel)\W+(einstuf|gewicht)")


def _saetze(t: str) -> list[str]:
    return [s for s in _TEILSATZ.split(t) if s.strip()]


def _verneint(satz: str, start: int) -> bool:
    return bool(_VERNEINT.search(satz[:start]))


def _texte(bausteine, ziele=None):
    return [norm(b["text"]) for b in bausteine if ziele is None or b["ziel"] in ziele]


def _empfehlung(bausteine) -> str | None:
    """Task 2 (Nachtrag 1, Sprachregel): the report recommends, it never states. A negation counts only right before
    the stating form in the same clause ("nie festgestellt", "Empfehlung statt Feststellung"), never elsewhere."""
    for t in _texte(bausteine, ("entwurf", "stil")):
        for satz in _saetze(t):
            for m in _FESTSTELLEN.finditer(satz):
                if not _verneint(satz, m.start()):
                    return "verlangt Feststellung statt Empfehlung"
    return None


def _keine_diagnose(bausteine) -> str | None:
    """Task 2 (Regel D1, q1): no ICD code and no diagnosis by a block; the engine alone decides about a diagnosis."""
    for t in _texte(bausteine):
        if _ICD.search(t):
            return "nennt einen ICD-Code"
        for satz in _saetze(t):
            for m in _DIAGNOSE.finditer(satz):
                if not _verneint(satz, m.start()):
                    return "bringt eine Diagnose in Entwurf oder Prüfung"
    return None


def _regel_ids() -> re.Pattern:
    """The IDs of the rule set in force, so a new rule is covered without code change (EGM C17); fixed list as fallback."""
    cfg = config.load()
    ids = {r["regel_id"].casefold() for r in (cfg.regelwerk or {}).get("regeln", [])}
    ids |= {"awmf_a", "awmf_b", "awmf_c", "awmf_d", "awmf_e", "awmf_f", "spf_s1", "spf_s2", "spf_s3", "normen_alter",
            "konfidenz_95", "q1", "d1"}
    kurz = {i.replace("_", " ") for i in ids} | {i.replace("_", "") for i in ids}
    return re.compile(r"\b(" + "|".join(re.escape(i) for i in sorted(ids | kurz, key=len, reverse=True)) + r")\b")


def _keine_parameter(bausteine) -> str | None:
    """Task 5: review behaviour is wording and weight of the reviewers' hints, never rule parameters, limits in figures
    or words, or anything the lock list protects."""
    regel = _regel_ids()
    for t in _texte(bausteine):
        if regel.search(t) or _PARAMETER.search(t) or _ZAHL_WERT.search(t):
            return "berührt Regeln, Grenzwerte oder gesperrte Bereiche"
    return None


def _befunde_bleiben(bausteine) -> str | None:
    """Task 2 and 3: reviewers report every finding and change nothing. A block may change wording and emphasis, never
    tell them to suppress, leave out, report only under conditions, or rate findings down (EGM B2)."""
    for t in _texte(bausteine, ("stil", "goldfisch", "elefant")):
        for satz in _saetze(t):
            if any(not _verneint(satz, m.start()) for m in _UNTERDRUECKEN.finditer(satz)):
                return "weist einen Prüfer an, Befunde wegzulassen"
        # conditions run over the comma ("nur erwähnen, wenn ..."): whole sentences here
        if any(_NICHT_MELDEN.search(satz) or _ABSTUFEN.search(satz) for satz in re.split(r"[.!?]", t)):
            return "schränkt die Meldepflicht oder die Schwere der Befunde ein"
    return None


def _datenminimierung(bausteine) -> str | None:
    """Task 2 (Befundart Datenminimierung) and the privacy limits: no identifying data in a block."""
    for b in bausteine:
        if any(not f.unsicher for f in recognition.detect_text(b["text"], 0, [], None, use_ner=False)):
            return "enthält identifizierende Angaben"
    return None


FAELLE = (("empfehlung_statt_feststellung", _empfehlung), ("keine_diagnose", _keine_diagnose),
          ("keine_regelparameter", _keine_parameter), ("befunde_nicht_unterdruecken", _befunde_bleiben),
          ("datenminimierung", _datenminimierung))


def evals(vorher: list[dict], nachher: list[dict]) -> dict:
    """Every case on the state before and after the change. Stricter than "only no case gets worse" (prompts-v2.md):
    any case that fails afterwards rejects the proposal, also one that failed before (EGM B14)."""
    faelle = []
    for fall_id, check in FAELLE:
        g_nachher = check(nachher)
        eintrag = {"fall_id": fall_id, "vorher": check(vorher) is None, "nachher": g_nachher is None}
        if g_nachher:
            eintrag["grund"] = g_nachher
        faelle.append(eintrag)
    return {"bestanden": all(f["nachher"] for f in faelle), "faelle": faelle, "llm_evals": "offen"}


def starte_evals(vorschlag_id) -> dict:
    with sperre(vorschlag_id):
        v = laden(vorschlag_id)
        if v["status"] not in OFFEN:
            raise EngineError("E_BLOCKIERT")
        doc = aktuell()
        if v["basis_version"] != _version(doc):
            raise EngineError("E_BLOCKIERT", "konflikt")  # the blocks changed since the proposal; propose again
        ergebnis = evals(doc["bausteine"] if doc else [], anwenden(doc, v))
        v.pop("llm_bestaetigt", None)  # a new deterministic result needs a new LLM run
        v |= {"eval": ergebnis, "status": "eval_bestanden" if ergebnis["bestanden"] else "eval_abgelehnt"}
        speichern(v)
    return {"vorschlag_id": v["vorschlag_id"], "status": v["status"], "eval": ergebnis}


def signale_markieren(signal_ids: list[str], vorschlag_id: str) -> None:
    """Signals used by a released proposal are marked so they never count twice; repeatable after a crash."""
    for r in store.all_records():
        if any(s["signal_id"] in signal_ids and s.get("verwendet_in_vorschlag") != vorschlag_id
               for s in r.get("lernsignale", [])):
            record = store.load(r["session"]["session_id"])
            for s in record["lernsignale"]:
                if s["signal_id"] in signal_ids:
                    s["verwendet_in_vorschlag"] = vorschlag_id
            store.save(record)
