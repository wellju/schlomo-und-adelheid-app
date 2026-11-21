"""Step 2.4: /stil-lernen (deterministic part). Synthetic only."""
import re
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from schlomo_engine import mcp_server as m, packages, ram, store, ui_functions as uf
from test_step_1_5 import setup  # noqa: F401  (fixture)
from test_step_1_6 import STILPROFIL, full  # noqa: F401  (fixture)

SKILL = Path(__file__).resolve().parents[2] / "arbeitsordner" / ".claude" / "skills" / "stil-lernen" / "SKILL.md"


def _add_sample(sid: str, dok_id: str, text: str) -> None:
    record = store.load(sid)
    record["session"]["dokumente"].append({
        "dok_id": dok_id, "format": "docx", "quelle_rolle": packages.PROBEGUTACHTEN, "text_anonymisiert": text,
        "freigabe": {"status": "freigegeben", "funde_je_kategorie": uf._funde_counts(ram.ImportedDoc("", "", "", b"", 1)),
                     "geprueft_bestaetigt": True}})
    store.save(record)


def test_probe_ids_are_stable_and_valid(full):
    sid = full["sid"]
    _add_sample(sid, "d-0000abcd", "[synthetisch] Probe eins.")
    first, second = m.hole_probetexte(sid), m.hole_probetexte(sid)
    assert first == second and first["probetexte"][0]["probe_id"] == "pg-0000abcd"
    assert re.fullmatch(r"pg-[0-9a-f]{8}", first["probetexte"][0]["probe_id"])


def test_session_without_sample_reports(full):
    with pytest.raises(ToolError) as e:
        m.hole_probetexte(full["sid"])
    assert str(e.value) == "E_NICHT_GEFUNDEN"


def test_profile_is_always_a_draft_and_never_overwrites(full):
    assert m.speichere_stilprofil(STILPROFIL | {"version": "v7", "status": "freigegeben"})["status"] == "entwurf"
    with pytest.raises(ToolError) as e:
        m.speichere_stilprofil(STILPROFIL | {"version": "v7"})
    assert str(e.value) == "E_BLOCKIERT"
    with pytest.raises(ToolError) as e:  # quote over 300 characters breaks stilprofil.schema.json
        m.speichere_stilprofil(STILPROFIL | {"version": "v8", "merkmale": [
            {"merkmal_id": "m1", "kategorie": "satzbau", "beschreibung": "x",
             "belegzitate": [{"text": "x" * 301, "probe_id": "pg-00000000"}]}]})
    assert str(e.value) == "E_SCHEMA"


def test_skill_file():
    text = SKILL.read_text(encoding="utf-8")
    head = text.split("---")[1]
    assert "name: stil-lernen" in head
    tools = set(re.findall(r"mcp__engine__[a-z_]+", text))
    assert tools == {"mcp__engine__liste_sitzungen", "mcp__engine__hole_probetexte", "mcp__engine__hole_stilprofil",
                     "mcp__engine__speichere_stilprofil"}
    assert tools <= {f"mcp__engine__{t}" for t in m.mcp._tool_manager._tools}
    for feature in ("Stichwortstil", "Konjunktiv", "Aufbau der Empfehlung"):  # three extra features (prompts-v2.md)
        assert feature in text
