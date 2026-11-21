"""Step 2.2: deterministic evals of /gutachten (gate in the engine). Each case is a draft as Claude might return it;
the engine must reject it before it is stored or exported. Synthetic only."""
import copy
import re
from pathlib import Path

import pytest

from schlomo_engine import belege, packages, store, ui_functions as uf
from schlomo_engine.errors import EngineError
from test_step_1_5 import setup  # noqa: F401  (fixture: spf session with input, draft, template)

SKILL = Path(__file__).resolve().parents[2] / "arbeitsordner" / ".claude" / "skills" / "gutachten" / "SKILL.md"


def _problems(draft, gi, cfg) -> set[str]:
    return {p["problem"] for p in belege.pruefe_belege(draft, gi, cfg)}


def _save_code(draft, sid, cfg) -> str:
    with pytest.raises(EngineError) as e:
        packages.check_draft(draft, store.load(sid), cfg)
    return e.value.code


def _sentence(draft, abschnitt_id):
    a = next(a for a in draft["abschnitte"] if a["abschnitt_id"] == abschnitt_id)
    return a["absaetze"][0]["saetze"][0]


def test_baseline_draft_passes(setup):
    assert packages.check_draft(copy.deepcopy(setup["draft"]), store.load(setup["sid"]), setup["cfg"])


def test_category_does_not_match_value(setup):
    draft = copy.deepcopy(setup["draft"])
    next(a for a in draft["abschnitte"] if a["abschnitt_id"] == "testbefunde")["tabellen"][0]["zeilen"][0][
        "kategorie"] = "Kategorie A"
    assert "kategorie_abweichend" in _problems(draft, setup["gi"], setup["cfg"])
    assert _save_code(draft, setup["sid"], setup["cfg"]) == "E_BELEG"


def test_procedure_block_cannot_be_changed(setup):
    """The draft has no place for the block text; a foreign block source is rejected, the export takes the
    catalogue text unchanged."""
    draft = copy.deepcopy(setup["draft"])
    tabelle = next(a for a in draft["abschnitte"] if a["abschnitt_id"] == "testbefunde")["tabellen"][0]
    tabelle["baustein_quelle"] = "lesetest-a"
    assert "baustein_fremd" in _problems(draft, setup["gi"], setup["cfg"])
    sections, _ = belege.render(setup["draft"], setup["gi"], setup["cfg"])
    catalogue = setup["cfg"].test("iq-test-a")["beschreibungsbaustein"]["text"]
    assert catalogue in sections["testbefunde"]


def test_spf_without_performance_samples_blocks_export(setup):
    record = store.load(setup["sid"])
    record["gutachten_input"]["leistungsproben"]["mathematik"] = {"text": " "}
    store.save(record)
    target = setup["tmp"] / "ohne-leistungsproben.docx"
    with pytest.raises(EngineError) as e:
        uf.docx_exportieren({"session_id": setup["sid"], "ziel_pfad": str(target)})
    assert e.value.code == "E_BLOCKIERT" and not target.exists()


@pytest.mark.parametrize("text", ["[synthetisch] Der SPF wird festgestellt.",
                                  "[synthetisch] Wir stellen einen sonderpädagogischen Förderbedarf fest.",
                                  "[synthetisch] Die Feststellung des SPF erfolgt hiermit."])
def test_festgestellt_instead_of_recommended(setup, text):
    draft = copy.deepcopy(setup["draft"])
    _sentence(draft, "empfehlung")["text"] = text
    assert "festgestellt_statt_empfohlen" in _problems(draft, setup["gi"], setup["cfg"])
    assert _save_code(draft, setup["sid"], setup["cfg"]) == "E_BELEG"


def test_recommended_is_fine(setup):
    draft = copy.deepcopy(setup["draft"])
    _sentence(draft, "empfehlung")["text"] = "[synthetisch] Ein sonderpädagogischer Förderbedarf wird empfohlen."
    assert "festgestellt_statt_empfohlen" not in _problems(draft, setup["gi"], setup["cfg"])


def test_diagnosis_in_spf_report(setup):
    draft = copy.deepcopy(setup["draft"])
    draft["abschnitte"].append({"abschnitt_id": "diagnose", "absaetze": [{"absatz_id": "d1", "saetze": [
        {"text": "[synthetisch] Diagnose: F70.", "quellen": ["/empfehlung"]}]}]})
    assert {"diagnose_im_spf", "code_nicht_im_input"} <= _problems(draft, setup["gi"], setup["cfg"])
    # D1 term list on its own: no diagnose section, the term alone triggers (EGM Task 2 E12)
    term_only = copy.deepcopy(setup["draft"])
    _sentence(term_only, "empfehlung")["text"] = "[synthetisch] Es besteht eine Intelligenzminderung."
    problems = belege.pruefe_belege(term_only, setup["gi"], setup["cfg"])
    assert [p["feld"] for p in problems if p["problem"] == "diagnose_im_spf"] == [
        f"/abschnitte/{[a['abschnitt_id'] for a in term_only['abschnitte']].index('empfehlung')}/absaetze/0/saetze/0"]


def test_diagnosis_without_q1(setup):
    gi = copy.deepcopy(setup["gi"]) | {"gutachtentyp": "lrs", "verfasserin": {"qualifikationen": ["schulpsychologin"]}}
    draft = copy.deepcopy(setup["draft"]) | {"gutachtentyp": "lrs"}
    draft["abschnitte"].append({"abschnitt_id": "diagnose", "absaetze": [{"absatz_id": "d1", "saetze": [
        {"text": "[synthetisch] Diagnose folgt.", "quellen": ["/empfehlung"]}]}]})
    assert "diagnose_ohne_q1" in _problems(draft, gi, setup["cfg"])
    gi["verfasserin"]["qualifikationen"].append("klinische_psychologin")
    assert "diagnose_ohne_q1" not in _problems(draft, gi, setup["cfg"])


def test_emotional_social_type_gets_no_input_for_a_draft(setup):
    record = store.load(setup["sid"])
    record["gutachten_input"]["gutachtentyp"] = "emotional_soziale_entwicklung"
    with pytest.raises(EngineError) as e:
        packages.inhalt(record, "gutachten", setup["cfg"], {})
    assert e.value.code == "E_BLOCKIERT"


def test_skill_file():
    """Frontmatter as in code.claude.com/docs/en/skills; only engine tools, every error code it handles exists."""
    text = SKILL.read_text(encoding="utf-8")
    head = text.split("---")[1]
    assert "name: gutachten" in head and "description:" in head
    tools = set(re.findall(r"mcp__engine__[a-z_]+", text))
    assert tools == {"mcp__engine__liste_sitzungen", "mcp__engine__hole_gutachten_input",
                     "mcp__engine__speichere_entwurf", "mcp__engine__pruefe_belege"}
    from schlomo_engine.errors import CODES
    assert {w.strip("`:,.") for w in text.split() if w.strip("`:,.").startswith("E_")} <= CODES
    assert "festgestellt" in text and "empfohlen" in text
