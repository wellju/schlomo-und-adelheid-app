"""Step 1.6: packages and returns (ADR 0002), Q1 diagnosis comparison, MCP tools, privacy tests. Synthetic only."""
import copy
import json
import subprocess
import sys

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from conftest import read_json_line
from schlomo_engine import mcp_server as m, packages, ram, store, ui_functions as uf
from schlomo_engine.contracts import validate
from schlomo_engine.errors import EngineError
from test_step_1_5 import setup  # noqa: F401  (fixture: session with input, draft, finding and template)

INTERN = "SYN-INTERN-9911"
STILPROFIL = {"schema_version": "1", "version": "syn-1", "status": "freigegeben", "anzahl_probegutachten": 3,
              "merkmale": [], "formulierungsbeispiele": []}


@pytest.fixture
def full(setup, monkeypatch, tmp_path):
    wb = tmp_path / "wissensbasis"
    wb.mkdir()
    (wb / "goldfisch-kriterien.md").write_text("[synthetisch] Nachvollziehbarkeit, Jargon, Wertung.", encoding="utf-8")
    monkeypatch.setenv("SCHLOMO_WISSENSBASIS", str(wb))
    monkeypatch.setenv("SCHLOMO_STILPROFILE", str(tmp_path / "stil"))
    validate("stilprofil", STILPROFIL)
    (packages.stilprofile_dir() / "syn-1.json").write_text(json.dumps(STILPROFIL), encoding="utf-8")
    record = store.load(setup["sid"])
    record["interne_diagnose"] = {"text": INTERN, "icd10_code": "F70", "erfasst_vor_vorschlaegen": True}
    store.save(record)
    ram.clear()
    uf.bekannte_namen_setzen({"session_id": setup["sid"], "namen": []})
    return setup


def _paket(sid, art, **extra):
    return uf.erzeuge_paket({"session_id": sid, "art": art, **extra})["fallpaket"]


@pytest.mark.parametrize("art", ["gutachten", "pruefung_elefant", "pruefung_goldfisch", "pruefung_stil",
                                 "diagnosevorschlag", "hypothese"])
def test_packages_are_valid_and_never_leak(full, art):
    extra = {"vignette": "[synthetisch] Ein Kind zeigt Unruhe.", "schlussfolgerung": "[synthetisch] Hypothese."} \
        if art == "hypothese" else {}
    paket = _paket(full["sid"], art, **extra)
    validate("fallpaket", paket)
    raw = json.dumps(paket, ensure_ascii=False)
    assert INTERN not in raw and "interne_diagnose" not in raw and "awmf_" not in raw
    assert "schweregrad" not in raw and ".docx" not in raw and "Vorlage SPF" not in raw
    if art == "pruefung_goldfisch":
        assert set(paket["inhalt"]) == {"fragestellung", "ergebnis_text", "kriterien", "gutachtentyp"}


def test_package_blocked_when_recognition_hits(full):
    uf.bekannte_namen_setzen({"session_id": full["sid"], "namen": [{"text": "Lenja Quastberger", "rolle": "das Kind"}]})
    with pytest.raises(EngineError) as e:
        _paket(full["sid"], "hypothese", vignette="Lenja Quastberger zeigt Unruhe.", schlussfolgerung="x")
    assert e.value.code == "E_ANONYMISIERUNG_OFFEN"
    with pytest.raises(EngineError) as e:
        _paket(full["sid"], "hypothese", vignette="Termin am 03.04.2026.", schlussfolgerung="x")
    assert e.value.code == "E_ANONYMISIERUNG_OFFEN"


def test_full_size_package(full):
    record = store.load(full["sid"])
    gi = record["gutachten_input"]
    filler = ("[synthetisch] Das Kind arbeitet konzentriert und fragt nach. " * 400)[:20000]
    for key in ("vorstellungsgrund", "verhaltensbeobachtung", "foerderung_und_umfeld"):
        gi[key]["text"] = filler
    gi["empfehlung"].update(text=filler, staerken=filler, foerdermassnahmen=filler)
    gi["anamnese"] = [{"quelle_id": f"q{i}", "erhoben_mit": "die Mutter", "art": "gespraech",
                       "uebersetzungshilfe": False, "text": filler} for i in range(5)]
    assert uf.eingabe_speichern({"session_id": full["sid"], "gutachten_input": gi, "unsichere_bestaetigt": True})["gespeichert"]
    paket = _paket(full["sid"], "gutachten")
    assert len(json.dumps(paket, ensure_ascii=False)) > 200_000
    validate("fallpaket", paket)


def _rueckgabe(paket_id, typ, daten):
    return {"schema_version": "2", "paket_id": paket_id, "typ": typ, "daten": daten}


def test_draft_return_checks(full):
    sid = full["sid"]
    paket = _paket(sid, "gutachten")
    draft = copy.deepcopy(full["draft"]) | {"entwurf_version": 99}
    bad = copy.deepcopy(draft)
    bad["abschnitte"][0]["absaetze"][0]["saetze"][0]["text"] = "Seit 7 Jahren."
    with pytest.raises(EngineError) as e:
        uf.lies_rueckgabe({"session_id": sid, "text": json.dumps(_rueckgabe(paket["paket_id"], "gutachten-output", bad))})
    assert e.value.code == "E_BELEG"
    bad = copy.deepcopy(draft)
    bad["regelergebnis"]["gesamt"] = "nicht_erfuellt"
    with pytest.raises(EngineError) as e:
        uf.lies_rueckgabe({"session_id": sid, "text": json.dumps(_rueckgabe(paket["paket_id"], "gutachten-output", bad))})
    assert e.value.code == "E_REGELABWEICHUNG"
    with pytest.raises(EngineError) as e:  # foreign package
        uf.lies_rueckgabe({"session_id": sid, "text": json.dumps(_rueckgabe("p-00000000", "gutachten-output", draft))})
    assert e.value.code == "E_PAKET_FREMD"
    chat = "Hier der Entwurf:\n```json\n" + json.dumps(_rueckgabe(paket["paket_id"], "gutachten-output", draft)) + "\n```"
    assert uf.lies_rueckgabe({"session_id": sid, "text": chat})["entwurf_version"] == 2  # version set by engine
    with pytest.raises(EngineError) as e:  # package is closed after one return
        uf.lies_rueckgabe({"session_id": sid, "text": chat})
    assert e.value.code == "E_PAKET_FREMD"


def _befund(**kw):
    return {"befund_id": "bf-11111111", "stelle": {"abschnitt_id": "empfehlung"}, "problem": "x", "schwere": "mittel",
            "begruendung": "y", "pruefer": "elefant", "entscheidung": {"status": "offen"}} | kw


def test_findings_return_checks(full):
    sid = full["sid"]
    paket = _paket(sid, "pruefung_elefant")
    for b, code in ((_befund(regel_id="awmf_b"), "E_REGELABWEICHUNG"), (_befund(regel_id="spf_s1"), "E_REGELABWEICHUNG"),
                    (_befund(pruefer="goldfisch"), "E_PAKET_FREMD")):
        with pytest.raises(EngineError) as e:
            uf.lies_rueckgabe({"session_id": sid, "text": json.dumps(_rueckgabe(paket["paket_id"], "befunde", [b]))})
        assert e.value.code == code
    assert uf.lies_rueckgabe({"session_id": sid, "text": json.dumps(
        _rueckgabe(paket["paket_id"], "befunde", [_befund(regel_id="normen_alter")]))})["befunde"] == 1
    stored = store.load(sid)["befunde"][-1]
    assert stored["befund_id"] != "bf-11111111" and stored["entscheidung"] == {"status": "offen"}


def test_q1_and_blind_comparison(full):
    sid = full["sid"]
    paket = _paket(sid, "diagnosevorschlag")
    vorschlag = {"schema_version": "1", "session_id": sid, "quelle": "claude", "kriterien": "erfuellt",
                 "icd10_code": "F72", "begruendung": [{"text": "x", "quellen": ["/testergebnisse/0"]}], "hinweis": "KI"}
    uf.lies_rueckgabe({"session_id": sid, "text": json.dumps(_rueckgabe(paket["paket_id"], "diagnosevorschlag", vorschlag))})
    stored = store.load(sid)["diagnosevorschlaege"][-1]
    assert "icd10_code" not in stored and "nicht in den lokalen Referenzdaten" in stored["hinweis"]
    record = store.load(sid)
    del record["interne_diagnose"]
    store.save(record)
    with pytest.raises(EngineError) as e:  # blind: no comparison before the internal diagnosis
        uf.diagnosevergleich_laden({"session_id": sid})
    assert e.value.code == "E_BLOCKIERT"
    uf.interne_diagnose_speichern({"session_id": sid, "interne_diagnose": {"text": INTERN, "icd10_code": "F70"}})
    out = uf.diagnosevergleich_laden({"session_id": sid})
    assert out["vergleich"] == {"engine": "gleich", "claude": "nicht_vergleichbar"}
    with pytest.raises(EngineError) as e:  # internal diagnosis cannot change after proposals were shown
        uf.interne_diagnose_speichern({"session_id": sid, "interne_diagnose": {"text": "anders"}})
    assert e.value.code == "E_BLOCKIERT"
    assert uf.vergleich_notiz_speichern({"session_id": sid, "notiz": "[synthetisch]"})["vergleich"]["notiz"]
    validate("fallspeicher", store.load(sid))

    record = store.load(sid)
    record["gutachten_input"]["verfasserin"]["qualifikationen"] = ["schulpsychologin"]
    store.save(record)
    for func in (uf.diagnosevergleich_laden, uf.vergleich_notiz_speichern):
        with pytest.raises(EngineError) as e:
            func({"session_id": sid, "notiz": "x"})
        assert e.value.code == "E_Q1"
    with pytest.raises(EngineError) as e:
        _paket(sid, "diagnosevorschlag")
    assert e.value.code == "E_Q1"


def test_mcp_tools_never_return_internal_diagnosis(full):
    sid = full["sid"]
    outputs = [m.liste_sitzungen(), m.hole_gutachten_input(sid), m.hole_elefant_paket(sid),
               m.hole_goldfisch_paket(sid), m.hole_stil_paket(sid), m.pruefe_fachregeln(sid),
               m.pruefe_belege(sid), m.hole_entwurf(sid), m.hole_stilprofil(), m.hole_wissensbasis("goldfisch-kriterien.md")]
    raw = json.dumps(outputs, ensure_ascii=False)
    assert INTERN not in raw and "interne_diagnose" not in raw and "awmf_" not in raw and "schweregrad" not in raw
    with pytest.raises(ToolError) as e:
        m.hole_wissensbasis("../geheim.md")
    assert str(e.value) == "E_SCHEMA"
    assert m.speichere_stilprofil(STILPROFIL | {"version": "syn-2"})["status"] == "entwurf"  # always draft
    with pytest.raises(ToolError) as e:  # never over an existing, here the released, profile (E36)
        m.speichere_stilprofil(STILPROFIL)
    assert str(e.value) == "E_BLOCKIERT" and m.hole_stilprofil()["version"] == "syn-1"


def test_mcp_draft_and_findings(full):
    sid = full["sid"]
    assert m.speichere_entwurf(sid, full["draft"])["entwurf_version"] == 2
    assert m.speichere_befunde(sid, "goldfisch", [_befund(pruefer="goldfisch")])["befunde"] == 1
    with pytest.raises(ToolError) as e:
        m.speichere_befunde(sid, "elefant", [_befund(regel_id="awmf_a")])
    assert str(e.value) == "E_REGELABWEICHUNG"


def test_mcp_subprocess_error_is_code_only(full):
    import os
    from conftest import SRC
    proc = subprocess.Popen([sys.executable, "-m", "schlomo_engine", "mcp"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            env=dict(os.environ, PYTHONPATH=str(SRC)))
    try:
        def send(msg):
            proc.stdin.write((json.dumps(msg) + "\n").encode())
            proc.stdin.flush()

        def receive(i):
            while True:
                msg = read_json_line(proc)
                if msg.get("id") == i:
                    return msg
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}})
        receive(1)
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
              "params": {"name": "hole_entwurf", "arguments": {"session_id": "s-00000000"}}})
        result = receive(2)["result"]
        assert result["isError"] and result["content"][0]["text"].strip().endswith("E_NICHT_GEFUNDEN")
    finally:
        proc.kill()


# The log test of a corpus run moved to test_step_1_7.py (all functions, all 33 documents; EGM E07).
