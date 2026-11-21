"""Step 1.1: channel, sessions, store, logging, MCP start. Synthetic data only."""
import json
import subprocess
import sys

import pytest

from conftest import read_json_line, run_ui
from schlomo_engine import store, ui_functions
from schlomo_engine.contracts import validate
from schlomo_engine.errors import EngineError
from schlomo_engine.logging_safe import log

SYNTH_TEXT = "SYNTHETISCH-KONTROLLTEXT-5521"


def test_status_and_unknown_function_and_broken_json(env):
    answers, _ = run_ui(env, [{"id": "r-1", "fn": "status"}, {"id": "r-2", "fn": "gibt_es_nicht"}, "{kaputt",
                              {"id": "r-3", "fn": "beenden"}, {"id": "r-4", "fn": "status"}])
    assert answers[0]["ok"] and answers[0]["result"]["schema_versionen"]["session"] == "1"
    assert answers[1]["fehler"]["code"] == "E_NICHT_GEFUNDEN"
    assert answers[2]["fehler"] == {"code": "E_SCHEMA", "grund": "json"}
    assert answers[3] == {"id": "r-3", "ok": True, "result": {}}
    assert len(answers) == 4  # nothing is processed after beenden


def test_create_list_load_session(env):
    answers, _ = run_ui(env, [
        {"id": "r-1", "fn": "sitzung_anlegen", "args": {"bezeichnung": "Fall 7", "modus": "gutachten",
                                                       "gutachtentyp": "spf"}},
        {"id": "r-2", "fn": "sitzungen_auflisten"},
    ])
    session = answers[0]["result"]["session"]
    assert session["session_id"].startswith("s-") and session["status"] == "import"
    assert [s["session_id"] for s in answers[1]["result"]["sessions"]] == [session["session_id"]]
    stored = json.loads((env["data"] / f"{session['session_id']}.json").read_text(encoding="utf-8"))
    validate("fallspeicher", stored)
    loaded, _ = run_ui(env, [{"id": "r-3", "fn": "sitzung_laden", "args": {"session_id": session["session_id"]}}])
    assert loaded[0]["result"]["session"] == session


@pytest.mark.parametrize("args", [
    {"bezeichnung": "Fall 1", "modus": "unbekannt"},
    {"bezeichnung": "Fall 1", "modus": "gutachten"},                       # gutachtentyp missing
    {"bezeichnung": "Fall 1", "modus": "intervision", "gutachtentyp": "spf"},  # gutachtentyp not allowed
    {"bezeichnung": "x" * 41, "modus": "supervision"},                    # longer than schema allows
])
def test_invalid_session_rejected(env, args):
    with pytest.raises(EngineError) as e:
        ui_functions.sitzung_anlegen(args)
    assert e.value.code == "E_SCHEMA"
    assert not list(env["data"].glob("*.json")) if env["data"].exists() else True


def test_load_never_returns_diagnosis(env):
    session = ui_functions.sitzung_anlegen({"bezeichnung": "Fall 2", "modus": "gutachten",
                                            "gutachtentyp": "lrs"})["session"]
    record = store.load(session["session_id"])
    record["interne_diagnose"] = {"text": "[synthetisch]", "erfasst_vor_vorschlaegen": True}
    store.save(record)
    loaded = ui_functions.sitzung_laden({"session_id": session["session_id"]})
    assert "interne_diagnose" not in loaded and "diagnosevorschlaege" not in loaded and "vergleich" not in loaded


def test_unknown_session_and_bad_id(env):
    for sid, code in (("s-00000000", "E_NICHT_GEFUNDEN"), ("../etc/passwd", "E_SCHEMA")):
        with pytest.raises(EngineError) as e:
            ui_functions.sitzung_laden({"session_id": sid})
        assert e.value.code == code


def test_data_dir_inside_working_folder_rejected(env, monkeypatch):
    monkeypatch.setenv("SCHLOMO_DATA_DIR", str(env["work"] / "fallspeicher"))
    with pytest.raises(EngineError) as e:
        store.data_dir()
    assert e.value.code == "E_BLOCKIERT"


def test_logs_never_contain_input_text(env):
    _, stderr = run_ui(env, [
        {"id": "r-1", "fn": "sitzung_anlegen", "args": {"bezeichnung": SYNTH_TEXT[:40], "modus": "supervision"}},
        {"id": "r-2", "fn": "sitzung_laden", "args": {"session_id": SYNTH_TEXT}},
        {"id": "r-3", "fn": SYNTH_TEXT},
        SYNTH_TEXT,
    ])
    assert stderr.strip() and "SYNTHETISCH" not in stderr
    for line in stderr.splitlines():
        assert set(json.loads(line)) <= {"t", "event", "count", "code", "session_id", "dok_id", "paket_id",
                                         "befund_id", "request_id", "dauer_ms"}


def test_logger_drops_free_text(capsys):
    import io
    buf = io.StringIO()
    log("test", stream=buf, code=SYNTH_TEXT, session_id=SYNTH_TEXT, text=SYNTH_TEXT, count="3")
    log(SYNTH_TEXT, stream=buf)
    assert SYNTH_TEXT not in buf.getvalue()


def test_mcp_start_lists_tool_and_loads_no_recognition(env):
    probe = (
        "import sys, schlomo_engine.mcp_server as m; "
        "bad = [n for n in sys.modules if n.split('.')[0] in ('spacy', 'pytesseract', 'pypdfium2', 'docx')]; "
        "print(bad)"
    )
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, env=env["env"], cwd=env["work"],
                         timeout=60)
    assert out.stdout.decode().strip() == "[]"

    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}}
    proc = subprocess.Popen([sys.executable, "-m", "schlomo_engine", "mcp"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env["env"], cwd=env["work"])
    try:
        def send(m):
            proc.stdin.write((json.dumps(m) + "\n").encode())
            proc.stdin.flush()

        def receive(i):
            while True:
                m = read_json_line(proc)
                if m.get("id") == i:
                    return m
        send(init)
        receive(1)
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        # docs/listen.md minus speichere_protokoll (Task 3) and the Task-5 tools
        assert sorted(t["name"] for t in receive(2)["result"]["tools"]) == sorted([
            "liste_sitzungen", "hole_gutachten_input", "hole_goldfisch_paket", "hole_stil_paket",
            "hole_elefant_paket", "hole_diagnose_paket", "pruefe_fachregeln", "pruefe_belege",
            "speichere_entwurf", "hole_entwurf", "speichere_befunde", "hole_stilprofil", "hole_probetexte",
            "speichere_stilprofil", "speichere_diagnosevorschlag", "hole_wissensbasis"])
    finally:
        proc.kill()
