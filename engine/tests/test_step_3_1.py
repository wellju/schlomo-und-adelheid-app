"""Step 3.1: intervision protocol with checked phase transitions (speichere_protokoll, EGM Task 1 E57). Synthetic."""
import copy
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from schlomo_engine import mcp_server as m, store, ui_functions as uf

KONF = Path(__file__).resolve().parent / "konfiguration_synthetisch"
HINT = "[synthetisch] Hinweis der KI: Nach meiner Einschätzung könnte eine Gefährdungsmeldung an die MA 11 nötig sein. Die Entscheidung triffst du."


@pytest.fixture
def sid(env, monkeypatch):
    monkeypatch.setenv("SCHLOMO_KONFIGURATION", str(KONF))
    monkeypatch.setenv("SCHLOMO_WISSENSBASIS", str(env["data"].parent / "wissen"))
    return uf.sitzung_anlegen({"bezeichnung": "Intervision 1", "modus": "intervision"})["session"]["session_id"]


def proto(sid, phase="rollen", **extra):
    return {"schema_version": "1", "session_id": sid, "phase": phase,
            "rollen": {"fallerzaehlerin": "psychologin", "moderation": "ki",
                       "berater": [{"berater_id": "b1", "perspektive": "Mehrsprachigkeit und DaZ"},
                                   {"berater_id": "b2", "perspektive": "Lehrkraft"}]}, **extra}


SF = {"schluesselfrage": {"vorschlaege": ["[synthetisch] Wie gewinne ich die Eltern?"],
                          "endgueltig": "[synthetisch] Wie gewinne ich die Eltern?", "bestaetigt": True}}
SP = {"spontanerzaehlung": {"zusammenfassung": "[synthetisch] Ein Kind der zweiten Stufe zieht sich zurück."}}
BER = {"beratung": [{"runde": 1, "berater_id": "b1", "beitrag": "[synthetisch] Ich würde die Erstsprache ansprechen."}]}


def walk(sid, upto):
    """Save the phases in order up to and including upto."""
    steps = [("rollen", {}), ("spontanerzaehlung", SP), ("schluesselfrage", SP | SF),
             ("methodenwahl", SP | SF | {"methode": "resonanzrunde"}),
             ("beratung", SP | SF | {"methode": "resonanzrunde"} | BER),
             ("abschluss", SP | SF | {"methode": "resonanzrunde"} | BER | {"abschluss": {"mitnahme": "[synthetisch] x"}})]
    for phase, extra in steps:
        m.speichere_protokoll(sid, proto(sid, phase, **extra))
        if phase == upto:
            return proto(sid, phase, **extra)


def code(call):
    with pytest.raises(ToolError) as e:
        call()
    return str(e.value)


def test_full_session_and_review_findings_go_into_the_protocol(sid):
    last = walk(sid, "abschluss")
    befund = {"stelle": {"protokoll_phase": "beratung"}, "problem": "[synthetisch] Bestätigung ohne Gegenfrage",
              "schwere": "mittel", "begruendung": "[synthetisch] Anker", "pruefer": "goldfisch"}
    assert m.speichere_befunde(sid, "goldfisch", [befund]) == {"befunde": 1}
    assert code(lambda: m.speichere_protokoll(sid, last | {"phase": "beendet"})) == "E_BLOCKIERT"  # Elefant missing
    assert m.speichere_befunde(sid, "elefant", []) == {"befunde": 0}  # a review without findings still counts
    assert m.speichere_protokoll(sid, last | {"phase": "beendet", "pruefbefunde": []})["phase"] == "beendet"
    p = m.hole_protokoll(sid)
    assert p["phase"] == "beendet" and [b["problem"] for b in p["pruefbefunde"]] == [befund["problem"]]
    assert "lernsignale" not in store.load(sid)  # the protocol itself writes no learning signal
    assert code(lambda: m.speichere_protokoll(sid, last)) == "E_PHASENFOLGE"  # finished is fixed


def test_advice_before_the_method_choice_is_rejected(sid):
    """Eval 'Ratschlag vor Phase 4 wird verhindert', deterministic part."""
    walk(sid, "spontanerzaehlung")
    assert code(lambda: m.speichere_protokoll(sid, proto(sid, "spontanerzaehlung", **SP, **BER))) == "E_PHASENFOLGE"
    walk_sf = proto(sid, "schluesselfrage", **SP, **SF)
    m.speichere_protokoll(sid, walk_sf)
    assert code(lambda: m.speichere_protokoll(sid, walk_sf | BER)) == "E_PHASENFOLGE"
    assert code(lambda: m.speichere_protokoll(sid, walk_sf | {"phase": "methodenwahl", "methode": "brainstorming"} | BER)) \
        == "E_PHASENFOLGE"
    assert len(store.load(sid)["protokolle"]) == 3


@pytest.mark.parametrize("bad", ["skip", "back", "first_not_rollen"])
def test_phase_order(sid, bad):
    if bad == "first_not_rollen":
        assert code(lambda: m.speichere_protokoll(sid, proto(sid, "spontanerzaehlung", **SP))) == "E_PHASENFOLGE"
        return
    walk(sid, "schluesselfrage")
    p = proto(sid, "beratung", **SP, **SF, methode="brainstorming") if bad == "skip" else proto(sid, "spontanerzaehlung", **SP)
    assert code(lambda: m.speichere_protokoll(sid, p)) == "E_PHASENFOLGE"


def test_key_question_needs_confirmation_and_is_fixed_later(sid):
    walk(sid, "spontanerzaehlung")
    unbestaetigt = copy.deepcopy(SF)
    unbestaetigt["schluesselfrage"]["bestaetigt"] = False
    assert code(lambda: m.speichere_protokoll(sid, proto(sid, "schluesselfrage", **SP, **unbestaetigt))) == "E_SCHEMA"
    m.speichere_protokoll(sid, proto(sid, "schluesselfrage", **SP, **SF))
    m.speichere_protokoll(sid, proto(sid, "methodenwahl", **SP, **SF, methode="resonanzrunde"))
    other = copy.deepcopy(SF)
    other["schluesselfrage"]["endgueltig"] = "[synthetisch] Andere Frage"
    assert code(lambda: m.speichere_protokoll(sid, proto(sid, "methodenwahl", **SP, **other, methode="resonanzrunde"))) \
        == "E_PHASENFOLGE"


def test_hint_only_with_stored_wording_and_session_continues(sid):
    """Eval 'Kindeswohl-Hinweis ... Sitzung läuft weiter', deterministic part: a hint never ends the session."""
    walk(sid, "spontanerzaehlung")
    hint = {"hinweise": [{"art": "kindeswohl", "text": HINT}]}
    assert code(lambda: m.speichere_protokoll(sid, proto(sid, "spontanerzaehlung", **SP,
                hinweise=[{"art": "kindeswohl", "text": "eigener Wortlaut"}]))) == "E_SCHEMA"
    m.speichere_protokoll(sid, proto(sid, "spontanerzaehlung", **SP, **hint))
    assert m.speichere_protokoll(sid, proto(sid, "schluesselfrage", **SP, **SF, **hint))["phase"] == "schluesselfrage"
    # hints are only added, never removed
    assert code(lambda: m.speichere_protokoll(sid, proto(sid, "schluesselfrage", **SP, **SF))) == "E_PHASENFOLGE"


def test_adviser_perspective_from_configuration(sid):
    p = proto(sid)
    p["rollen"]["berater"][0]["perspektive"] = "Erfundene Perspektive"
    assert code(lambda: m.speichere_protokoll(sid, p)) == "E_SCHEMA"
    v = m.hole_rubberduck_vorgaben()
    assert "Mehrsprachigkeit und DaZ" in {x["name"] for x in v["berater_perspektiven"]}
    assert v["hinweise"]["kindeswohl"] == HINT and v["haltung_version"] == "nicht_konfiguriert"


def test_without_hint_wordings_no_session(sid, monkeypatch, tmp_path):
    """EGM Task 3 B2: the wording comes from the psychologist, never from the prompt; without it no session."""
    monkeypatch.setenv("SCHLOMO_KONFIGURATION", str(tmp_path / "leer"))
    v = m.hole_rubberduck_vorgaben()
    assert v["hinweise"] is None and v["berater_perspektiven"] is None and v["herkunft"]["hinweise"] is None
    assert code(lambda: m.speichere_protokoll(sid, proto(sid))) == "E_BLOCKIERT"


def test_cancel_keeps_hints_and_content(sid):
    """EGM Task 3 B1: cancelling changes only phase and reason."""
    walk(sid, "spontanerzaehlung")
    hint = {"hinweise": [{"art": "kindeswohl", "text": HINT}]}
    m.speichere_protokoll(sid, proto(sid, "spontanerzaehlung", **SP, **hint))
    ab = {"abbruch": {"grund": "durch_psychologin", "hinweis": "[synthetisch]"}}
    assert code(lambda: m.speichere_protokoll(sid, proto(sid, "abgebrochen", **SP, **ab))) == "E_PHASENFOLGE"
    other = {"spontanerzaehlung": {"zusammenfassung": "[synthetisch] umgeschrieben"}}
    assert code(lambda: m.speichere_protokoll(sid, proto(sid, "abgebrochen", **other, **hint, **ab))) == "E_PHASENFOLGE"
    assert m.speichere_protokoll(sid, proto(sid, "abgebrochen", **SP, **hint, **ab))["phase"] == "abgebrochen"


def test_leaving_a_phase_needs_its_field(sid):
    """EGM Task 3, code 3: otherwise the end could never be reached."""
    walk(sid, "methodenwahl")
    assert code(lambda: m.speichere_protokoll(sid, proto(sid, "beratung", **SP, **SF, **BER))) == "E_PHASENFOLGE"


def test_changed_configuration_does_not_block_a_running_session(sid, monkeypatch, tmp_path):
    """EGM Task 3 B10: only hints added now are checked, perspectives only while roles are chosen."""
    walk(sid, "spontanerzaehlung")
    m.speichere_protokoll(sid, proto(sid, "spontanerzaehlung", **SP, hinweise=[{"art": "kindeswohl", "text": HINT}]))
    neu = tmp_path / "konf"
    neu.mkdir()
    import json, shutil
    shutil.copy(KONF / "berater.json", neu / "berater.json")
    h = json.loads((KONF / "hinweise.json").read_text(encoding="utf-8"))
    h["kindeswohl"]["text"] = "[synthetisch] neuer Wortlaut"
    (neu / "hinweise.json").write_text(json.dumps(h), encoding="utf-8")
    monkeypatch.setenv("SCHLOMO_KONFIGURATION", str(neu))
    hints = [{"art": "kindeswohl", "text": HINT}]
    assert m.speichere_protokoll(sid, proto(sid, "schluesselfrage", **SP, **SF, hinweise=hints))["phase"] == "schluesselfrage"


def test_cancel_and_foreign_session(sid):
    walk(sid, "spontanerzaehlung")
    other = uf.sitzung_anlegen({"bezeichnung": "Intervision 2", "modus": "intervision"})["session"]["session_id"]
    assert code(lambda: m.speichere_protokoll(other, proto(sid))) == "E_PAKET_FREMD"
    cancel = proto(sid, "abgebrochen", **SP, abbruch={"grund": "durch_psychologin", "hinweis": "[synthetisch]"})
    assert m.speichere_protokoll(sid, cancel)["phase"] == "abgebrochen"
    assert code(lambda: m.speichere_protokoll(sid, cancel)) == "E_PHASENFOLGE"


def test_report_sessions_have_no_protocol(env):
    gid = uf.sitzung_anlegen({"bezeichnung": "Fall 93", "modus": "gutachten", "gutachtentyp": "lrs"})["session"]["session_id"]
    assert code(lambda: m.speichere_protokoll(gid, proto(gid))) == "E_PAKET_FREMD"


def test_review_findings_need_a_phase_and_a_reviewer_of_the_mode(sid):
    walk(sid, "beratung")
    b = {"stelle": {"zitat": "x"}, "problem": "x", "schwere": "gering", "begruendung": "x", "pruefer": "elefant"}
    ok = b | {"stelle": {"protokoll_phase": "spontanerzaehlung"}}
    assert code(lambda: m.speichere_befunde(sid, "elefant", [ok])) == "E_PHASENFOLGE"  # review only in abschluss
    m.speichere_protokoll(sid, proto(sid, "abschluss", **SP, **SF, methode="resonanzrunde", **BER,
                                     abschluss={"mitnahme": "[synthetisch] x"}))
    assert code(lambda: m.speichere_befunde(sid, "elefant", [b])) == "E_SCHEMA"
    for bad in ("person", "beendet"):  # levels belong to supervision; beendet is no phase to report on
        assert code(lambda: m.speichere_befunde(sid, "elefant", [b | {"stelle": {"protokoll_phase": bad}}])) == "E_SCHEMA"
    assert code(lambda: m.speichere_befunde(sid, "stil", [b | {"pruefer": "stil"}])) == "E_PAKET_FREMD"
    assert m.speichere_befunde(sid, "elefant", [ok]) == {"befunde": 1}


def test_goldfish_view_has_no_narrative_or_roles(sid):
    walk(sid, "abschluss")
    view = m.hole_protokoll_goldfisch(sid)
    assert set(view) == {"modus", "schluesselfrage", "methode", "beitraege", "mitnahme"}
    assert "zieht sich zurück" not in str(view) and "Lehrkraft" not in str(view)
