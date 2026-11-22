"""Step 3.2: supervision, /hypothese-pruefen and the chat variant of both skills (deterministic part). Synthetic."""
import json
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from schlomo_engine import mcp_server as m, store, ui_functions as uf
from schlomo_engine.errors import EngineError
from test_step_3_1 import KONF, proto, walk, SP, SF, BER

ROOT = Path(__file__).resolve().parents[2]
CLAUDE = ROOT / "arbeitsordner" / ".claude"
HALTUNG = "# Haltung\n[synthetisch] Fragend, wertschätzend, widersprechend, wo nötig.\n"
ABSCHLUSS = {"abschluss": {"mitnahme": "[synthetisch] x"}}


@pytest.fixture
def konf(env, monkeypatch):
    monkeypatch.setenv("SCHLOMO_KONFIGURATION", str(KONF))
    wissen = env["data"].parent / "wissen"
    wissen.mkdir()
    (wissen / "haltung.md").write_text(HALTUNG, encoding="utf-8")
    monkeypatch.setenv("SCHLOMO_WISSENSBASIS", str(wissen))
    return env


def session(modus: str) -> str:
    """No list of names: rubberduck packages hold no case data (EGM Task 3 B14)."""
    return uf.sitzung_anlegen({"bezeichnung": f"{modus.capitalize()} 1", "modus": modus})["session"]["session_id"]


def sup(sid, phase="anliegen", status="laufend", **extra):
    return {"schema_version": "1", "session_id": sid, "status": status, "phase": phase, "ki_kennzeichnung": True,
            "haltung_version": "von Claude", "anliegen": "[synthetisch] Ich fühle mich von einer Lehrerin unter Druck gesetzt.",
            **extra}


EBENE = {"ebenen": [{"ebene": "beziehung", "balint_schwerpunkt": "[synthetisch] Druck", "hypothesen": ["[synthetisch] h1"],
                     "widerspruch": ["[synthetisch] w1"]}]}
B = {"stelle": {"protokoll_phase": "bearbeitung", "zitat": "h1"}, "problem": "[synthetisch] nur Bestätigung",
     "schwere": "mittel", "begruendung": "[synthetisch] Gefälligkeit", "pruefer": "goldfisch"}


def code(call):
    with pytest.raises((ToolError, EngineError)) as e:
        call()
    return str(e.value)


def supervision_to_abschluss(sid):
    m.speichere_protokoll(sid, sup(sid, "anliegen"))
    for phase in ("klaerung", "bearbeitung", "integration"):
        m.speichere_protokoll(sid, sup(sid, phase, **EBENE))
    m.speichere_protokoll(sid, sup(sid, "abschluss", **EBENE, **ABSCHLUSS))


def test_supervision_phases_goldfish_only_and_no_learning_signal(konf):
    """Eval 'Supervision erzeugt kein Lernsignal', deterministic part."""
    sid = session("supervision")
    m.speichere_protokoll(sid, sup(sid, "anliegen"))
    assert code(lambda: m.speichere_protokoll(sid, sup(sid, "anliegen", **EBENE))) == "E_PHASENFOLGE"  # levels from klaerung
    for phase in ("klaerung", "bearbeitung", "integration"):
        m.speichere_protokoll(sid, sup(sid, phase, **EBENE))
    assert code(lambda: m.speichere_protokoll(sid, sup(sid, "abschluss", "beendet", **EBENE, **ABSCHLUSS))) \
        == "E_PHASENFOLGE"  # integration -> beendet in one step would skip abschluss
    m.speichere_protokoll(sid, sup(sid, "abschluss", **EBENE, **ABSCHLUSS))
    assert code(lambda: m.speichere_protokoll(sid, sup(sid, "abschluss", **ABSCHLUSS))) == "E_PHASENFOLGE"  # levels fixed
    assert code(lambda: m.speichere_befunde(sid, "elefant", [B | {"pruefer": "elefant"}])) == "E_PAKET_FREMD"
    assert code(lambda: m.speichere_protokoll(sid, sup(sid, "abschluss", "beendet", **EBENE, **ABSCHLUSS))) == "E_BLOCKIERT"
    m.speichere_befunde(sid, "goldfisch", [B])
    m.speichere_protokoll(sid, sup(sid, "abschluss", "beendet", **EBENE, **ABSCHLUSS))
    p = m.hole_protokoll(sid)
    assert p["status"] == "beendet" and len(p["goldfisch_befunde"]) == 1
    assert p["haltung_version"].startswith("sha256-")  # set by the engine from haltung.md, not by Claude
    befund_id = store.load(sid)["befunde"][0]["befund_id"]
    out = uf.befund_entscheiden({"session_id": sid, "befund_id": befund_id, "entscheidung": "annehmen"})
    assert out.get("lernsignal") is None and "lernsignale" not in store.load(sid)


def test_haltung_version_is_fixed_with_the_first_state(konf):
    sid = session("supervision")
    m.speichere_protokoll(sid, sup(sid, "anliegen"))
    first = m.hole_protokoll(sid)["haltung_version"]
    (konf["data"].parent / "wissen" / "haltung.md").write_text(HALTUNG + "geändert\n", encoding="utf-8")
    m.speichere_protokoll(sid, sup(sid, "klaerung", **EBENE))
    assert m.hole_protokoll(sid)["haltung_version"] == first


def test_hypothesis_check_goes_into_the_running_protocol_and_can_be_decided(konf):
    sid = session("intervision")
    assert code(lambda: m.speichere_hypothesenpruefung(sid, "v", "s", [])) == "E_PHASENFOLGE"  # no protocol yet
    walk(sid, "spontanerzaehlung")
    befund = {"stelle": {"protokoll_phase": "hypothese", "zitat": "[synthetisch] faul"},
              "problem": "[synthetisch] Anker auf ein Detail", "schwere": "mittel",
              "begruendung": "[synthetisch] andere Erklärung: Sehschwäche", "pruefer": "goldfisch"}
    assert m.speichere_hypothesenpruefung(sid, "[synthetisch] Kind schaut oft weg.", "[synthetisch] Es ist faul.",
                                          [befund]) == {"befunde": 1}
    assert m.speichere_hypothesenpruefung(sid, "[synthetisch] v", "[synthetisch] s", []) == {"befunde": 0}
    p = m.hole_protokoll(sid)
    assert [len(h["befunde"]) for h in p["hypothesenpruefungen"]] == [1, 0]
    # also a finding of the session, so the psychologist can decide it in the app
    bid = p["hypothesenpruefungen"][0]["befunde"][0]["befund_id"]
    assert uf.befund_entscheiden({"session_id": sid, "befund_id": bid, "entscheidung": "verwerfen"})
    # Claude's next protocol state cannot drop or rewrite them
    m.speichere_protokoll(sid, proto(sid, "schluesselfrage", **SP, **SF, hypothesenpruefungen=[]))
    assert len(m.hole_protokoll(sid)["hypothesenpruefungen"]) == 2
    for bad in (befund | {"pruefer": "stil"}, befund | {"regel_id": "konfidenz_95"},
                befund | {"stelle": {"protokoll_phase": "beratung", "zitat": "x"}}):
        assert code(lambda: m.speichere_hypothesenpruefung(sid, "v", "s", [bad])) in ("E_PAKET_FREMD", "E_REGELABWEICHUNG",
                                                                                     "E_SCHEMA")
    assert code(lambda: m.speichere_hypothesenpruefung(sid, "", "s", [])) == "E_SCHEMA"
    assert code(lambda: m.speichere_hypothesenpruefung(sid, "v", "s", [{"problem": "ohne Pruefer"}])) == "E_SCHEMA"


def _answer(skill, paket, typ, daten):
    block = {"schema_version": "2", "paket_id": paket["paket_id"], "typ": typ, "daten": daten}
    return f"Skill {skill} aktiv\n\n```json\n{json.dumps(block, ensure_ascii=False)}\n```\n"


def _bf(pruefer, phase="beratung"):
    return {"befund_id": "bf-00000001", "stelle": {"protokoll_phase": phase, "zitat": "x"}, "problem": "x",
            "schwere": "gering", "begruendung": "y", "pruefer": pruefer, "entscheidung": {"status": "offen"}}


FINAL = dict(**SP, **SF, methode="resonanzrunde", **BER, **ABSCHLUSS)


def test_chat_intervision_return_then_both_reviewers_then_app_ends_it(konf):
    """EGM Task 3 B3, B5: in the chat too, Elefant and Goldfisch review the returned protocol, in packages the
    engine builds from it."""
    sid = session("intervision")
    paket = uf.erzeuge_paket({"session_id": sid, "art": "intervision"})["fallpaket"]
    assert paket["erwartete_rueckgabe"] == "protokoll-intervision"
    assert "Mehrsprachigkeit und DaZ" in {p["name"] for p in paket["inhalt"]["berater_perspektiven"]}
    assert code(lambda: uf.erzeuge_paket({"session_id": sid, "art": "protokoll_elefant"})) == "E_PHASENFOLGE"
    uf.lies_rueckgabe({"session_id": sid, "text": _answer("intervision", paket, "protokoll-intervision", proto(sid, "abschluss", **FINAL))})
    assert code(lambda: uf.protokoll_beenden({"session_id": sid})) == "E_BLOCKIERT"  # no review yet
    el = uf.erzeuge_paket({"session_id": sid, "art": "protokoll_elefant"})["fallpaket"]
    gf = uf.erzeuge_paket({"session_id": sid, "art": "protokoll_goldfisch"})["fallpaket"]
    assert el["inhalt"]["protokoll"]["phase"] == "abschluss"
    assert set(gf["inhalt"]) == {"modus", "schluesselfrage", "methode", "beitraege", "mitnahme"}
    uf.lies_rueckgabe({"session_id": sid, "text": _answer("pruefen-elefant", el, "befunde", [])})
    uf.lies_rueckgabe({"session_id": sid, "text": _answer("pruefen-goldfisch", gf, "befunde", [_bf("goldfisch")])})
    hyp = uf.erzeuge_paket({"session_id": sid, "art": "hypothese", "vignette": "[synthetisch] v",
                            "schlussfolgerung": "[synthetisch] s"})["fallpaket"]
    uf.lies_rueckgabe({"session_id": sid, "text": _answer("pruefen-goldfisch", hyp, "befunde", [_bf("goldfisch", "hypothese")])})
    assert uf.protokoll_beenden({"session_id": sid})["phase"] == "beendet"
    p = m.hole_protokoll(sid)
    assert len(p["pruefbefunde"]) == 1 and p["hypothesenpruefungen"][0]["vignette"] == "[synthetisch] v"
    assert code(lambda: uf.protokoll_beenden({"session_id": sid})) == "E_PHASENFOLGE"


def test_chat_supervision_return_and_end(konf):
    sid = session("supervision")
    paket = uf.erzeuge_paket({"session_id": sid, "art": "supervision"})["fallpaket"]
    assert paket["inhalt"]["haltung"] == HALTUNG and paket["inhalt"]["hinweise"]["kindeswohl"].startswith("[synthetisch]")
    final = sup(sid, "abschluss", **EBENE, **ABSCHLUSS)
    uf.lies_rueckgabe({"session_id": sid, "text": _answer("supervision", paket, "protokoll-supervision", final)})
    assert code(lambda: uf.erzeuge_paket({"session_id": sid, "art": "protokoll_elefant"})) == "E_PHASENFOLGE"
    gf = uf.erzeuge_paket({"session_id": sid, "art": "protokoll_goldfisch"})["fallpaket"]
    uf.lies_rueckgabe({"session_id": sid, "text": _answer("pruefen-goldfisch", gf, "befunde", [_bf("goldfisch", "bearbeitung")])})
    assert uf.protokoll_beenden({"session_id": sid})["status"] == "beendet"
    assert "lernsignale" not in store.load(sid)


def test_chat_return_must_be_a_whole_session_and_only_once(konf):
    sid = session("intervision")
    paket = uf.erzeuge_paket({"session_id": sid, "art": "intervision"})["fallpaket"]
    mid = proto(sid, "spontanerzaehlung", **SP)
    assert code(lambda: uf.lies_rueckgabe({"session_id": sid, "text": _answer("intervision", paket, "protokoll-intervision", mid)})) \
        == "E_PHASENFOLGE"
    no_method = proto(sid, "abschluss", **SP, **SF, **BER, **ABSCHLUSS)  # EGM Task 3 B9: could never be ended
    paket = uf.erzeuge_paket({"session_id": sid, "art": "intervision"})["fallpaket"]
    assert code(lambda: uf.lies_rueckgabe({"session_id": sid, "text": _answer("intervision", paket, "protokoll-intervision", no_method)})) \
        == "E_SCHEMA"
    paket = uf.erzeuge_paket({"session_id": sid, "art": "intervision"})["fallpaket"]
    uf.lies_rueckgabe({"session_id": sid, "text": _answer("intervision", paket, "protokoll-intervision", proto(sid, "abschluss", **FINAL))})
    paket2 = uf.erzeuge_paket({"session_id": sid, "art": "intervision"})["fallpaket"]
    assert code(lambda: uf.lies_rueckgabe({"session_id": sid, "text": _answer("intervision", paket2, "protokoll-intervision",
                                                                              proto(sid, "abschluss", **FINAL))})) == "E_PHASENFOLGE"


def test_goldfish_finding_without_phase_is_rejected_in_chat(konf):
    sid = session("supervision")
    m.speichere_protokoll(sid, sup(sid, "anliegen"))
    hyp = uf.erzeuge_paket({"session_id": sid, "art": "hypothese", "vignette": "[synthetisch] v",
                            "schlussfolgerung": "[synthetisch] s"})["fallpaket"]
    b = _bf("goldfisch") | {"stelle": {"zitat": "x"}}
    assert code(lambda: uf.lies_rueckgabe({"session_id": sid, "text": _answer("pruefen-goldfisch", hyp, "befunde", [b])})) \
        == "E_SCHEMA"


def test_wrong_mode_and_missing_wordings(konf, monkeypatch, tmp_path):
    sid = session("supervision")
    assert code(lambda: uf.erzeuge_paket({"session_id": sid, "art": "intervision"})) == "E_PAKET_FREMD"
    monkeypatch.setenv("SCHLOMO_KONFIGURATION", str(tmp_path / "leer"))
    assert code(lambda: uf.erzeuge_paket({"session_id": sid, "art": "supervision"})) == "E_BLOCKIERT"


def test_command_skills_and_goldfish_wiring():
    cmd = (CLAUDE / "commands" / "hypothese-pruefen.md").read_text(encoding="utf-8")
    assert "Subagent `goldfisch`" in cmd and "Hypothese, session_id:" in cmd
    gold = (CLAUDE / "agents" / "goldfisch.md").read_text(encoding="utf-8")
    assert "## Hypothese prüfen" in gold and "mcp__engine__speichere_hypothesenpruefung" in gold
    for skill in ("intervision", "supervision"):
        text = (CLAUDE / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
        assert "Bitte nur anonymisiert erzählen." in text and "entscheidung trifft die psychologin" in text.lower()
        assert "Wortlaut noch nicht hinterlegt" not in text  # no wording of our own (EGM Task 3 B2)
        assert (ROOT / "plugin" / "skills" / skill / "SKILL.md").read_bytes() == text.encode("utf-8") or \
            (ROOT / "plugin" / "skills" / skill / "SKILL.md").read_text(encoding="utf-8") == text
