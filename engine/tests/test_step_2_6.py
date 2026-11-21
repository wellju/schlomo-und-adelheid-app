"""Step 2.6: fixes after the EGM gate of Task 2 (docs/reviews/egm-task-2.md). Synthetic only."""
import copy
import json
import re
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from schlomo_engine import belege, config, mcp_server as m, packages, rules, store
from schlomo_engine.errors import EngineError
from test_step_1_4 import SYN
from test_step_1_5 import setup  # noqa: F401  (fixture)
from test_step_1_6 import STILPROFIL, _paket, full  # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "arbeitsordner" / ".claude" / "agents"
PACKAGE_TOOLS = {"mcp__engine__hole_goldfisch_paket", "mcp__engine__hole_stil_paket", "mcp__engine__hole_elefant_paket",
                 "mcp__engine__hole_diagnose_paket", "mcp__engine__hole_gutachten_input"}


@pytest.mark.parametrize("name,own", [("goldfisch", "mcp__engine__hole_goldfisch_paket"),
                                      ("stil", "mcp__engine__hole_stil_paket"),
                                      ("elefant", "mcp__engine__hole_elefant_paket"),
                                      ("diagnosevorschlag", "mcp__engine__hole_diagnose_paket")])
def test_each_reviewer_reaches_only_its_own_package(name, own):
    """E01: the role is fixed by the tool, not chosen by the model."""
    head = (AGENTS / f"{name}.md").read_text(encoding="utf-8").split("---")[1]
    tools = {t.strip() for t in re.search(r"tools:(.*)", head)[1].split(",")}
    assert tools & PACKAGE_TOOLS == {own}
    assert "hole_pruefpaket" not in m.mcp._tool_manager._tools  # the tool with a free role is gone


def test_data_minimisation_is_medium_everywhere():
    """E02: Nachtrag 1 sets severity mittel for the data minimisation check of Elefant and Goldfisch."""
    for path in (AGENTS / "elefant.md", AGENTS / "goldfisch.md", ROOT / "plugin" / "skills" / "pruefen-elefant" / "SKILL.md",
                 ROOT / "plugin" / "skills" / "pruefen-goldfisch" / "SKILL.md"):
        text = " ".join(path.read_text(encoding="utf-8").split())
        assert "Datenminimierung" in text and "`gering` (Datenminimierung" not in text
        assert re.search(r"Datenminimierung[^.]{0,60}`mittel`|`mittel`[^.]{0,60}Datenminimierung", text), path.name


def test_goldfish_knows_the_report_type_for_spf_weighting(full):
    """E06: wording that judges weighs more in spf; the package carries only the type for that."""
    assert m.hole_goldfisch_paket(full["sid"])["gutachtentyp"] == "spf"
    text = " ".join((AGENTS / "goldfisch.md").read_text(encoding="utf-8").split())
    assert "besonderem Gewicht" in text and "`spf`" in text


def test_style_profile_reaches_claude_without_quotes(full):
    """E30: quotes come from sample reports of other cases."""
    sid = full["sid"]
    profil = STILPROFIL | {"merkmale": [{"merkmal_id": "m1", "kategorie": "satzbau", "beschreibung": "x",
                                         "belegzitate": [{"text": "SYN-ANDERER-FALL", "probe_id": "pg-00000000"}]}]}
    (packages.stilprofile_dir() / "syn-1.json").write_text(json.dumps(profil), encoding="utf-8")
    for out in (m.hole_stilprofil(), m.hole_stil_paket(sid), _paket(sid, "gutachten")):
        assert "SYN-ANDERER-FALL" not in json.dumps(out) and "belegzitate" not in json.dumps(out)


def test_mcp_evidence_check_validates_a_given_draft(full):
    """E19: a broken draft gives E_SCHEMA; an empty dict is not replaced by the stored draft."""
    for bad in ({}, {"abschnitte": []}):
        with pytest.raises(ToolError) as e:
            m.pruefe_belege(full["sid"], bad)
        assert str(e.value) == "E_SCHEMA"
    assert m.pruefe_belege(full["sid"]) == []


@pytest.mark.parametrize("answer,ok", [
    ('Skill x aktiv\n```json\n{"a": 1}\n```', True),
    ('Skill x aktiv\n```JSON\n{"a": 1}\n```', True),
    ('Skill x aktiv\n````json\n{"a": 1}\n````', True),
    ('{"a": 1}', True),
    ("```json\n{\"a\": 1}\n```\n```json\n{\"b\": 2}\n```", False),
    ("kein json", False),
])
def test_extract_json_edge_cases(answer, ok):
    """E20"""
    if ok:
        assert packages.extract_json(answer) == {"a": 1}
    else:
        with pytest.raises(EngineError):
            packages.extract_json(answer)
    with pytest.raises(EngineError):
        packages.extract_json(None)


def test_d1_without_term_list_still_checks_codes(setup, tmp_path):
    """E18: without the term list D1 is nicht_pruefbar in the rule result (export blocked, Task 1 E30); the evidence
    check still finds ICD codes but cannot find terms."""
    folder = tmp_path / "konf"
    folder.mkdir()
    for f in SYN.glob("*.json"):
        (folder / f.name).write_bytes(f.read_bytes())
    regelwerk = json.loads((folder / "regelwerk.json").read_text(encoding="utf-8"))
    for r in regelwerk["regeln"]:
        if r["regel_id"] == "d1":
            r["parameter"].pop("begriffe")
    (folder / "regelwerk.json").write_text(json.dumps(regelwerk), encoding="utf-8")
    cfg = config.load(folder)
    (d1,) = [e for e in rules.pruefe_fachregeln(setup["gi"], cfg)["ergebnisse"] if e["regel_id"] == "d1"]
    assert d1["ergebnis"] == "nicht_pruefbar"
    draft = copy.deepcopy(setup["draft"])
    empfehlung = next(a for a in draft["abschnitte"] if a["abschnitt_id"] == "empfehlung")
    empfehlung["absaetze"][0]["saetze"][0]["text"] = "[synthetisch] Es besteht eine Intelligenzminderung."
    assert "diagnose_im_spf" not in {p["problem"] for p in belege.pruefe_belege(draft, setup["gi"], cfg)}
    empfehlung["absaetze"][0]["saetze"][0]["text"] = "[synthetisch] Verdacht auf F70."
    assert "diagnose_im_spf" in {p["problem"] for p in belege.pruefe_belege(draft, setup["gi"], cfg)}


@pytest.mark.parametrize("text,hit", [
    ("[synthetisch] Die Feststellung der Testwerte erfolgte im Einzelsetting.", False),  # no SPF in the sentence
    ("[synthetisch] Festgestellt wurde eine gute Ausdauer.", False),
    ("[synthetisch] Ein SPF wird empfohlen.", False),
    ("[synthetisch] Der sonderpädagogische Förderbedarf wird festgestellt.", True),
])
def test_festgestellt_negative_cases(setup, text, hit):
    """E25. Known limit: a sentence naming the SPF and any "Feststellung" triggers, even if it means something else."""
    draft = copy.deepcopy(setup["draft"])
    next(a for a in draft["abschnitte"] if a["abschnitt_id"] == "empfehlung")["absaetze"][0]["saetze"][0]["text"] = text
    found = "festgestellt_statt_empfohlen" in {p["problem"] for p in belege.pruefe_belege(draft, setup["gi"], setup["cfg"])}
    assert found is hit


def test_style_profile_in_skill_format_is_valid():
    """E25: a profile built exactly as the /stil-lernen skill describes passes the schema and the save path."""
    from schlomo_engine.contracts import validate
    profil = {"schema_version": "1", "version": "v1", "vorgaenger_version": None, "status": "entwurf",
              "anzahl_probegutachten": 3,
              "merkmale": [{"merkmal_id": "m1", "kategorie": "satzbau", "beschreibung": "Stichwortstil",
                            "belegzitate": [{"text": "Ruhig, zurückhaltend.", "probe_id": "pg-0000a002"}]}],
              "formulierungsbeispiele": [{"abschnitt_id": "empfehlung", "text": "Empfohlen werden ..."}]}
    validate("stilprofil", profil)
