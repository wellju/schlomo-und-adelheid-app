"""Rubberduck (Task 3): protocols of intervision and supervision with checked phase transitions (EGM Task 1 E57).
The psychologist types anonymised free text directly into Claude (Nachtrag 1, approved exception); the engine only
stores the protocol and enforces the order of the phases, so advice before the method choice cannot be stored.
Supervision never produces a learning signal: nothing here writes one."""
import hashlib

from . import config, packages
from .contracts import validate
from .errors import EngineError

ORDER = {"intervision": ("rollen", "spontanerzaehlung", "schluesselfrage", "methodenwahl", "beratung", "abschluss",
                         "beendet"),
         "supervision": ("anliegen", "klaerung", "bearbeitung", "integration", "abschluss")}
# field -> (first phase in which it may be filled, last phase in which it may still change)
FELDER = {"intervision": {"rollen": ("rollen", "rollen"), "spontanerzaehlung": ("spontanerzaehlung", "spontanerzaehlung"),
                          "schluesselfrage": ("schluesselfrage", "schluesselfrage"),
                          "methode": ("methodenwahl", "methodenwahl"), "beratung": ("beratung", "beratung"),
                          "abschluss": ("abschluss", "abschluss")},
          "supervision": {"anliegen": ("anliegen", "anliegen"), "ebenen": ("klaerung", "integration"),
                          "abschluss": ("abschluss", "abschluss")}}
# leaving this phase needs this field, so the end can always be reached (schema: required at beendet)
VERLASSEN = {"intervision": {"spontanerzaehlung": "spontanerzaehlung", "methodenwahl": "methode",
                             "beratung": "beratung", "abschluss": "abschluss"},
             "supervision": {"klaerung": "ebenen"}}
ENGINE_FELDER = {"intervision": ("pruefbefunde", "hypothesenpruefungen"),
                 "supervision": ("goldfisch_befunde", "hypothesenpruefungen", "haltung_version", "ki_kennzeichnung")}
ENDE_FELD = {"intervision": "pruefbefunde", "supervision": "goldfisch_befunde"}
PRUEFER = {"intervision": ("elefant", "goldfisch"), "supervision": ("goldfisch",)}
EBENEN = ("fall", "beziehung", "rolle_und_system", "person", "ethik_und_qualitaet")
BEFUND_STELLEN = {"intervision": set(ORDER["intervision"][:-1]) | {"hypothese"},
                  "supervision": set(ORDER["supervision"]) | set(EBENEN) | {"hypothese"}}


def haltung_version() -> str:
    try:
        return "sha256-" + hashlib.sha256(packages.wissen("haltung.md").encode("utf-8")).hexdigest()[:12]
    except EngineError:
        return "nicht_konfiguriert"


def vorgaben() -> dict:
    """What the skills need besides the free text: hint wordings and adviser perspectives, or null if missing.
    herkunft shows a synthetic placeholder as such (EGM Task 3 B6)."""
    cfg = config.load()
    h, b = cfg.hinweise, cfg.berater
    return {"hinweise": {k: h[k]["text"] for k in ("kindeswohl", "akute_gefaehrdung")} if h else None,
            "berater_perspektiven": b["perspektiven"] if b else None,
            "herkunft": {"hinweise": h["herkunft"] if h else None, "berater": b["herkunft"] if b else None},
            "haltung_version": haltung_version()}


def _need_hints(vorg: dict) -> None:
    """Without stored wordings no session: the hint text must come from the psychologist, never from a prompt
    (Nachtrag 1; EGM Task 3 B2)."""
    if vorg["hinweise"] is None:
        raise EngineError("E_BLOCKIERT", "hinweise_fehlen")


def modus(record: dict) -> str:
    m = record["session"]["modus"]
    if m not in PRUEFER:
        raise EngineError("E_PAKET_FREMD")
    return m


def current(record: dict) -> dict | None:
    return (record.get("protokolle") or [None])[-1]


def _final(m: str, p: dict) -> bool:
    return p["phase"] in ("beendet", "abgebrochen") if m == "intervision" else p["status"] != "laufend"


def _cancelled(m: str, p: dict) -> bool:
    return p["phase"] == "abgebrochen" if m == "intervision" else p["status"] == "abgebrochen"


def _content(m: str, p: dict) -> dict:
    """What Claude wrote, without engine fields, hints, phase, status and cancellation."""
    return {k: v for k, v in p.items() if k not in ENGINE_FELDER[m] + ("hinweise", "phase", "status", "abbruch")}


def _step(m: str, old: dict | None, new: dict) -> None:
    """Each save stays in the phase or moves exactly one on; a finished protocol is fixed. Fields of a phase may only
    be filled from that phase on and are fixed once it is over; leaving a phase needs its field. Cancelling changes
    nothing but phase or status and the reason (EGM Task 3 B1). Hints are only ever added."""
    order = ORDER[m]
    if old is not None and _final(m, old):
        raise EngineError("E_PHASENFOLGE")
    old_hints = (old or {}).get("hinweise", [])
    if new.get("hinweise", [])[:len(old_hints)] != old_hints:
        raise EngineError("E_PHASENFOLGE")
    if _cancelled(m, new):
        if old is not None and (_content(m, new) != _content(m, old) or new.get("phase") != old.get("phase")
                                and m == "supervision"):
            raise EngineError("E_PHASENFOLGE")
        return
    if new.get("phase") is None:
        raise EngineError("E_PHASENFOLGE")
    i = order.index(new["phase"])
    if old is None:
        if i != 0 or m == "supervision" and new["status"] != "laufend":
            raise EngineError("E_PHASENFOLGE")
        j = 0
    else:
        j = order.index(old["phase"])
        if i - j not in (0, 1):
            raise EngineError("E_PHASENFOLGE")
        if i == j + 1 and (feld := VERLASSEN[m].get(old["phase"])) and feld not in new:
            raise EngineError("E_PHASENFOLGE")
    if m == "supervision" and new["status"] == "beendet" and (old is None or old["phase"] != "abschluss"
                                                              or new["phase"] != "abschluss"):
        raise EngineError("E_PHASENFOLGE")  # the end is its own step after abschluss, like beendet in intervision
    for feld, (ab, bis) in FELDER[m].items():
        if feld in new and i < order.index(ab):
            raise EngineError("E_PHASENFOLGE")  # e.g. advice (beratung) before the method choice
        if old is not None and j > order.index(bis) and new.get(feld) != old.get(feld):
            raise EngineError("E_PHASENFOLGE")


def _check_content(m: str, old: dict | None, new: dict, vorg: dict) -> None:
    """Only hints added now are checked against the stored wording, and perspectives only while roles are chosen,
    so a later change of the configuration never blocks a running session (EGM Task 3 B10)."""
    for h in new.get("hinweise", [])[len((old or {}).get("hinweise", [])):]:
        if h["text"] != vorg["hinweise"][h["art"]]:
            raise EngineError("E_SCHEMA", "argumente")
    if m == "intervision" and new.get("phase") == "rollen" and vorg["berater_perspektiven"] is not None:
        names = {p["name"] for p in vorg["berater_perspektiven"]}
        if any(b["perspektive"] not in names for b in new["rollen"]["berater"]):
            raise EngineError("E_SCHEMA", "argumente")


def _ending(m: str, p: dict) -> bool:
    return p.get("phase") == "beendet" if m == "intervision" else p.get("status") == "beendet"


def speichere(record: dict, protokoll: dict, browser: bool = False) -> dict:
    """Check and append a new protocol state. Review findings, hypothesis checks and haltung_version belong to the
    engine: they come from the stored findings and earlier states, never from Claude's protocol."""
    m = modus(record)
    if not isinstance(protokoll, dict) or protokoll.get("session_id") != record["session"]["session_id"]:
        raise EngineError("E_PAKET_FREMD")
    vorg = vorgaben()
    _need_hints(vorg)
    old = current(record)
    new = {k: v for k, v in protokoll.items() if k not in ENGINE_FELDER[m]}
    if old is not None and "hypothesenpruefungen" in old:
        new["hypothesenpruefungen"] = old["hypothesenpruefungen"]
    if m == "supervision":
        # fixed with the first state: the protocol names the stance the session was held with (EGM Task 3, 10)
        new["haltung_version"] = old["haltung_version"] if old else vorg["haltung_version"]
        new["ki_kennzeichnung"] = True
    if _ending(m, new):
        new[ENDE_FELD[m]] = [b for b in record.get("befunde", []) if b["pruefer"] in PRUEFER[m]
                             and b["stelle"].get("protokoll_phase") not in (None, "hypothese")]
    validate(f"protokoll-{m}", new)
    if not browser:
        _step(m, old, new)  # order before reviews, so a skipped phase is E_PHASENFOLGE, not a missing review
    if _ending(m, new) and set(PRUEFER[m]) - set(record.get("protokoll_pruefungen", [])):
        raise EngineError("E_BLOCKIERT", "pruefung_fehlt")  # every reviewer of the mode reported, even with none
    if browser:
        # one return per chat: only the result can be checked, not each step (ADR 0002, Abweichungen Rubberduck)
        ende = new["phase"] == "abschluss" if m == "intervision" else new["status"] == "laufend" and new.get("phase") == "abschluss"
        if old is not None or not (ende or _cancelled(m, new)):
            raise EngineError("E_PHASENFOLGE")
        if ende:  # it must be possible to end it later: every field the end needs is there (EGM Task 3 B9)
            validate(f"protokoll-{m}", new | ({"phase": "beendet"} if m == "intervision" else {"status": "beendet"})
                     | {ENDE_FELD[m]: []})
    _check_content(m, None if browser else old, new, vorg)
    record.setdefault("protokolle", []).append(new)
    return {"stand": len(record["protokolle"]), "phase": new.get("phase"), **({"status": new["status"]} if m == "supervision" else {})}


def importiere(record: dict, protokoll: dict) -> dict:
    """Browser variant: the protocol of a whole chat comes back once, in phase abschluss or cancelled; the reviews
    follow in their own chats, then the app ends it with protokoll_beenden."""
    return speichere(record, protokoll, browser=True)


def beenden(record: dict) -> dict:
    """protokoll_beenden (app): the next state after abschluss, with the review findings stored so far."""
    m, p = modus(record), current(record)
    if p is None:
        raise EngineError("E_NICHT_GEFUNDEN")
    if _final(m, p) or p.get("phase") != "abschluss":
        raise EngineError("E_PHASENFOLGE")
    return speichere(record, p | ({"phase": "beendet"} if m == "intervision" else {"status": "beendet"}))


def paket_inhalt(record: dict, art: str) -> dict:
    """Packages for the chat variant: what the engine tools give in the Code-Tab."""
    m = modus(record)
    if art in ("protokoll_elefant", "protokoll_goldfisch"):
        p = current(record)
        if p is None or _final(m, p) or p.get("phase") != "abschluss" or (art == "protokoll_elefant" and m != "intervision"):
            raise EngineError("E_PHASENFOLGE")
        return {"protokoll": p} if art == "protokoll_elefant" else goldfisch_sicht(record)
    if m != art:
        raise EngineError("E_PAKET_FREMD")
    v = vorgaben()
    _need_hints(v)
    if art == "intervision":
        return {"hinweise": v["hinweise"], "berater_perspektiven": v["berater_perspektiven"]}
    try:
        haltung = packages.wissen("haltung.md")
    except EngineError:
        haltung = None
    if haltung is not None and len(haltung) > 20000:
        raise EngineError("E_SCHEMA", "groesse")  # never cut: the version names the whole file
    return {"hinweise": v["hinweise"], "haltung": haltung, "haltung_version": v["haltung_version"]}


def check_protokoll_befunde(record: dict, rolle: str, befunde: list) -> None:
    """Findings on a protocol name the phase or level they refer to; supervision is reviewed only by the Goldfisch
    (Nachtrag 1, Abläufe). A review of the protocol runs on its final content, in phase abschluss."""
    m = modus(record)
    if rolle not in PRUEFER[m]:
        raise EngineError("E_PAKET_FREMD")
    if any(b.get("stelle", {}).get("protokoll_phase") not in BEFUND_STELLEN[m] for b in befunde):
        raise EngineError("E_SCHEMA", "argumente")


def pruefung_vermerken(record: dict, rolle: str) -> None:
    """A reviewer reported on the protocol (with or without findings); the end needs every reviewer of the mode."""
    m, p = modus(record), current(record)
    if p is None or _final(m, p) or p.get("phase") != "abschluss":
        raise EngineError("E_PHASENFOLGE")
    if rolle not in record.setdefault("protokoll_pruefungen", []):
        record["protokoll_pruefungen"].append(rolle)


def goldfisch_sicht(record: dict) -> dict:
    """Only question and result of the session, like the Goldfisch package of a report: no narrative, no roles."""
    m, p = modus(record), current(record)
    if p is None:
        raise EngineError("E_NICHT_GEFUNDEN")
    if m == "intervision":
        return {"modus": m, "schluesselfrage": p.get("schluesselfrage", {}).get("endgueltig"),
                "methode": p.get("methode"), "beitraege": [b["beitrag"] for b in p.get("beratung", [])],
                "mitnahme": p.get("abschluss", {}).get("mitnahme")}
    return {"modus": m, "anliegen": p["anliegen"],
            "hypothesen": [h for e in p.get("ebenen", []) for h in e.get("hypothesen", [])],
            "mitnahme": p.get("abschluss", {}).get("mitnahme")}


def speichere_hypothese(record: dict, vignette: str, schlussfolgerung: str, befunde: list) -> dict:
    """/hypothese-pruefen, Code-Tab and chat: the Goldfisch's findings on a vignette and conclusion, as a new protocol
    state and as findings the psychologist decides in the app (EGM Task 3 B11)."""
    m, old = modus(record), current(record)
    if old is None or _final(m, old):
        raise EngineError("E_PHASENFOLGE")
    if not all(isinstance(t, str) and 0 < len(t) <= 20000 for t in (vignette, schlussfolgerung)):
        raise EngineError("E_SCHEMA", "argumente")  # same limits as the package hypothese
    if not isinstance(befunde, list):
        raise EngineError("E_SCHEMA", "argumente")
    for b in befunde:  # schema first, like speichere_befunde, so a broken finding is E_SCHEMA and never E_INTERN
        validate("befund", b | {"befund_id": "bf-00000000", "entscheidung": {"status": "offen"}}
                 if isinstance(b, dict) else b)
    check_protokoll_befunde(record, "goldfisch", befunde)
    if any(b.get("stelle", {}).get("protokoll_phase") != "hypothese" for b in befunde):
        raise EngineError("E_SCHEMA", "argumente")
    neue = packages.check_befunde(befunde, "goldfisch", None, config.load())
    new = old | {"hypothesenpruefungen": old.get("hypothesenpruefungen", []) + [
        {"vignette": vignette, "schlussfolgerung": schlussfolgerung, "befunde": neue}]}
    validate(f"protokoll-{m}", new)
    record["protokolle"].append(new)
    record.setdefault("befunde", []).extend(neue)
    return {"befunde": len(neue)}
