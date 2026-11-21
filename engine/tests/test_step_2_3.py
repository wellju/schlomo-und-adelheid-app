"""Step 2.3: reviewer subagents and /pruefen-goldfisch (deterministic part). Synthetic only."""
import copy
import json
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from schlomo_engine import mcp_server as m, store
from test_step_1_5 import setup  # noqa: F401  (fixture)
from test_step_1_6 import full  # noqa: F401  (fixture)

CLAUDE = Path(__file__).resolve().parents[2] / "arbeitsordner" / ".claude"
EXPECTED_TOOLS = {
    "elefant": {"mcp__engine__hole_elefant_paket", "mcp__engine__pruefe_fachregeln", "mcp__engine__pruefe_belege",
                "mcp__engine__speichere_befunde"},
    "goldfisch": {"mcp__engine__hole_goldfisch_paket", "mcp__engine__speichere_befunde"},
    "stil": {"mcp__engine__hole_stil_paket", "mcp__engine__speichere_befunde"},
    "diagnosevorschlag": {"mcp__engine__hole_diagnose_paket", "mcp__engine__speichere_diagnosevorschlag"},
}


def _frontmatter(path: Path) -> dict:
    head = path.read_text(encoding="utf-8").split("---")[1]
    return {k.strip(): v.strip() for k, v in (line.split(":", 1) for line in head.strip().splitlines())}


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_agent_tool_lists(name):
    """tools is an allowlist (code.claude.com/docs/en/sub-agents, spike point 1): exactly the engine tools of the role."""
    meta = _frontmatter(CLAUDE / "agents" / f"{name}.md")
    assert meta["name"] == name and meta["description"]
    tools = {t.strip() for t in meta["tools"].split(",")}
    assert tools == EXPECTED_TOOLS[name]
    registered = {f"mcp__engine__{t}" for t in m.mcp._tool_manager._tools}
    assert tools <= registered  # every listed tool exists in the engine


def test_goldfish_cannot_reach_the_input():
    tools = {t.strip() for t in _frontmatter(CLAUDE / "agents" / "goldfisch.md")["tools"].split(",")}
    assert not tools & {"mcp__engine__hole_elefant_paket", "mcp__engine__hole_diagnose_paket", "mcp__engine__hole_stil_paket",
                        "mcp__engine__hole_gutachten_input", "mcp__engine__hole_entwurf", "mcp__engine__pruefe_belege",
                        "mcp__engine__pruefe_fachregeln"}


def test_pruefpaket_for_each_role_holds_only_its_fields(full):
    sid = full["sid"]
    assert set(m.hole_goldfisch_paket(sid)) == {"fragestellung", "ergebnis_text", "kriterien", "gutachtentyp"}
    assert set(m.hole_stil_paket(sid)) == {"entwurf", "stilprofil"}
    assert "gutachten_input" in m.hole_elefant_paket(sid)


def test_diagnosis_package_is_blind_and_needs_q1(full):
    sid = full["sid"]
    record = store.load(sid)
    record["gutachten_input"] = copy.deepcopy(record["gutachten_input"]) | {
        "gutachtentyp": "lrs", "gutachten_diagnose": {"text": "[synthetisch] SYN-EIGENE-DIAGNOSE"}}
    record["session"]["gutachtentyp"] = "lrs"
    store.save(record)
    inhalt = m.hole_diagnose_paket(sid)
    raw = json.dumps(inhalt, ensure_ascii=False)
    assert "SYN-EIGENE-DIAGNOSE" not in raw and "entwurf" not in inhalt and "interne_diagnose" not in raw
    record = store.load(sid)
    record["gutachten_input"]["verfasserin"]["qualifikationen"] = ["schulpsychologin"]
    record["gutachten_input"].pop("gutachten_diagnose")
    store.save(record)
    with pytest.raises(ToolError) as e:
        m.hole_diagnose_paket(sid)
    assert str(e.value) == "E_Q1"


def test_command_passes_only_the_session_id():
    text = (CLAUDE / "commands" / "pruefen-goldfisch.md").read_text(encoding="utf-8")
    assert "goldfisch" in text and "session_id: $ARGUMENTS" in text
    assert _frontmatter(CLAUDE / "commands" / "pruefen-goldfisch.md")["description"]


def test_gutachten_skill_starts_reviewers_in_order():
    text = (CLAUDE / "skills" / "gutachten" / "SKILL.md").read_text(encoding="utf-8")
    assert text.index("`stil`") < text.index("`goldfisch`") < text.index("`elefant` zuletzt")
    assert "nur\n   `session_id: <id>`" in text or "nur `session_id: <id>`" in text


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_agent_files_hold_no_case_data(name):
    text = (CLAUDE / "agents" / f"{name}.md").read_text(encoding="utf-8")
    for marker in ("SYN-", "Quastberger", "Lenja", "KOLIBRI"):
        assert marker not in text
