"""Step 2.5: chat variant and plugin (deterministic part). Every skill answer has the form the skill prescribes:
a marker line, then exactly one json code block; the engine must accept it via lies_rueckgabe. Synthetic only."""
import copy
import json
import re
from pathlib import Path

import pytest

from schlomo_engine import packages, ram, store, ui_functions as uf
from schlomo_engine.errors import EngineError
from test_step_1_5 import setup  # noqa: F401  (fixture)
from test_step_1_6 import INTERN, STILPROFIL, _paket, full  # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugin"
CHAT_SKILLS = {"gutachten": ("gutachten", "gutachten-output"), "stil-lernen": ("stil_lernen", "stilprofil"),
               "pruefen-goldfisch": ("pruefung_goldfisch", "befunde"), "pruefen-stil": ("pruefung_stil", "befunde"),
               "pruefen-elefant": ("pruefung_elefant", "befunde"), "diagnosevorschlag": ("diagnosevorschlag", "diagnosevorschlag")}


def _answer(skill: str, block: dict) -> str:
    return f"Skill {skill} aktiv\n\n```json\n{json.dumps(block, ensure_ascii=False, indent=2)}\n```\n"


def _befund(pruefer: str, **kw) -> dict:
    return {"befund_id": "bf-00000001", "stelle": {"zitat": "[synthetisch]"}, "problem": "x", "schwere": "gering",
            "begruendung": "y", "pruefer": pruefer, "entscheidung": {"status": "offen"}} | kw


def test_plugin_holds_only_allowed_files():
    files = sorted(p.relative_to(PLUGIN).as_posix() for p in PLUGIN.rglob("*") if p.is_file())
    assert files == [".claude-plugin/plugin.json"] + sorted(f"skills/{s}/SKILL.md" for s in CHAT_SKILLS)
    assert not (PLUGIN / "bin").exists()
    meta = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert meta["name"] == "schlomo-und-adelheid" and meta["license"] == "Apache-2.0"


@pytest.mark.parametrize("name", ["gutachten", "stil-lernen"])
def test_shared_skills_equal_their_source(name):
    """One skill for Code-Tab and chat (ADR 0002); scripts/build_plugin.py copies it."""
    src = ROOT / "arbeitsordner" / ".claude" / "skills" / name / "SKILL.md"
    assert (PLUGIN / "skills" / name / "SKILL.md").read_bytes() == src.read_bytes()


@pytest.mark.parametrize("name", sorted(CHAT_SKILLS))
def test_chat_skill_text(name):
    art, typ = CHAT_SKILLS[name]
    text = (PLUGIN / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    head = text.split("---")[1]
    assert f"name: {name}" in head and "description:" in head
    assert f"`art` nicht `{art}`" in text and f'"typ": "{typ}"' in text
    assert f"`Skill {name} aktiv`" in text and "genau ein Codeblock" in text
    assert "um das Paket" in " ".join(text.split())  # never works with typed-in case data
    if name not in ("gutachten", "stil-lernen"):
        assert not re.search(r"mcp__engine__", text)  # chat has no engine tools
    for marker in ("SYN-", "Quastberger", "Lenja"):
        assert marker not in text


@pytest.mark.parametrize("skill,art,pruefer", [("pruefen-goldfisch", "pruefung_goldfisch", "goldfisch"),
                                               ("pruefen-stil", "pruefung_stil", "stil"),
                                               ("pruefen-elefant", "pruefung_elefant", "elefant")])
def test_findings_answer_is_accepted(full, skill, art, pruefer):
    sid = full["sid"]
    paket = _paket(sid, art)
    block = {"schema_version": "2", "paket_id": paket["paket_id"], "typ": "befunde", "daten": [_befund(pruefer)]}
    out = uf.lies_rueckgabe({"session_id": sid, "text": _answer(skill, block)})
    assert out["gueltig"] and out["befunde"] == 1


def test_draft_answer_is_accepted(full):
    sid = full["sid"]
    paket = _paket(sid, "gutachten")
    draft = copy.deepcopy(store.load(sid)["entwuerfe"][-1])
    draft["regelergebnis"] = paket["inhalt"]["regelergebnis"]
    block = {"schema_version": "2", "paket_id": paket["paket_id"], "typ": "gutachten-output", "daten": draft}
    assert uf.lies_rueckgabe({"session_id": sid, "text": _answer("gutachten", block)})["entwurf_version"] == 2


def test_diagnosis_answer_is_accepted(full):
    sid = full["sid"]
    paket = _paket(sid, "diagnosevorschlag")
    assert "gutachten_diagnose" not in paket["inhalt"]["gutachten_input"]
    block = {"schema_version": "2", "paket_id": paket["paket_id"], "typ": "diagnosevorschlag", "daten": {
        "schema_version": "1", "session_id": sid, "quelle": "claude", "kriterien": "nicht_pruefbar",
        "begruendung": [{"text": "[synthetisch]", "quellen": ["/testergebnisse/0"]}], "hinweis": "Vorschlag einer KI, keine Diagnose."}}
    assert uf.lies_rueckgabe({"session_id": sid, "text": _answer("diagnosevorschlag", block)})["diagnosevorschlag"] == "gespeichert"
    assert INTERN not in json.dumps(paket, ensure_ascii=False)


def test_style_answer_is_renumbered_when_v1_exists(full):
    """A chat cannot see stored versions and always names v1; the return path picks the next free version."""
    sid = full["sid"]
    record = store.load(sid)
    record["session"]["dokumente"].append({
        "dok_id": "d-0000b001", "format": "docx", "quelle_rolle": packages.PROBEGUTACHTEN,
        "text_anonymisiert": "[synthetisch] Probe.", "freigabe": {"status": "freigegeben", "geprueft_bestaetigt": True,
                                                                   "funde_je_kategorie": uf._funde_counts(ram.ImportedDoc("", "", "", b"", 1))}})
    store.save(record)
    profil = STILPROFIL | {"version": "v1", "status": "entwurf", "anzahl_probegutachten": 1}
    for expected in ("v1", "v2"):
        paket = _paket(sid, "stil_lernen")
        block = {"schema_version": "2", "paket_id": paket["paket_id"], "typ": "stilprofil", "daten": profil}
        assert uf.lies_rueckgabe({"session_id": sid, "text": _answer("stil-lernen", block)})["stilprofil"] == expected
    assert packages.released_stilprofil()["version"] == "syn-1"  # the released profile stays the one in use


def test_two_blocks_are_rejected(full):
    """Exactly one return block per package: an answer with a second json block is not read as a return."""
    sid = full["sid"]
    paket = _paket(sid, "pruefung_goldfisch")
    block = {"schema_version": "2", "paket_id": paket["paket_id"], "typ": "befunde", "daten": [_befund("goldfisch")]}
    answer = _answer("pruefen-goldfisch", block) + "\n```json\n{}\n```\n"
    with pytest.raises(EngineError) as e:
        uf.lies_rueckgabe({"session_id": sid, "text": answer})
    assert (e.value.code, e.value.reason) == ("E_SCHEMA", "json")
    assert packages._open_packages(sid)  # the package stays open for a correct answer
