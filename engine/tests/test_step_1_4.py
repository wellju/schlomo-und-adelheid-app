"""Step 1.4: configuration, derivations, rules per ID, regelergebnis and fuer_claude, engine diagnosis proposal.
Synthetic configuration under tests/konfiguration_synthetisch (herkunft synthetisch, never shipped)."""
import copy
import json
from datetime import date
from pathlib import Path

import pytest

from schlomo_engine import config, derive, rules, store, ui_functions as uf
from schlomo_engine.contracts import validate
from schlomo_engine.errors import EngineError

SYN = Path(__file__).parent / "konfiguration_synthetisch"
T = {"text": "synthetisch"}
GI = {"schema_version": "3", "session_id": "s-0000abcd", "gutachtentyp": "spf",
      "verfasserin": {"qualifikationen": ["schulpsychologin", "klinische_psychologin"]},
      "vorstellungsgrund": T, "schullaufbahn": {"schulstufe": 2, "jahr_der_schulpflicht": 2},
      "vorbefunde": [], "verhaltensbeobachtung": T, "anamnese": [],
      "testergebnisse": [{"testergebnis_id": "t1", "verfahren": "Synthetischer Intelligenztest A",
                          "testkatalog_id": "iq-test-a", "einzeltestung": True, "gesamt_iq": 62, "ki_untergrenze": 57,
                          "ki_obergrenze": 68, "ki_niveau": 0.95, "normen_alter_jahre": 12,
                          "werte": [{"ebene": "index", "kennung": "I1", "wert": 62, "skala": "iq"}]}],
      "leistungsproben": {"deutsch": {"lesen": T, "schreiben": T}, "mathematik": T},
      "foerderung_und_umfeld": T,
      "adaptives_verhalten": {"befragte_rollen": ["die Klassenlehrerin"], "text": "synthetisch"},
      "drei_quellen": {"klinischer_eindruck": "dokumentiert", "intelligenztest": "dokumentiert",
                       "befragung_adaptives_verhalten": "dokumentiert"},
      "erstsprache_deutsch": True, "alter": {"jahre": 8, "monate": 4, "abgeleitet": True},
      "empfehlung": {"text": "synthetisch", "spf_empfohlen": True}}


@pytest.fixture
def cfg():
    return config.load(SYN)


def _by_id(result):
    out = {}
    for e in result["ergebnisse"]:
        out.setdefault(e["regel_id"], []).append(e["ergebnis"])
    return out


def test_synthetic_configuration_is_valid_and_marked(cfg):
    assert cfg.regelwerk and cfg.testkatalog and cfg.kategorienskala and cfg.icd10
    assert all(e["herkunft"] == "synthetisch" for e in cfg.kategorienskala["eintraege"])
    assert cfg.icd10["herkunft"] == "synthetisch"


def test_overlapping_scale_rejected(cfg, tmp_path):
    for name in config.FILES.values():
        if (SYN / name).exists():  # lernbausteine.json (Task 5) has no synthetic file: nothing learned yet
            (tmp_path / name).write_text((SYN / name).read_text(encoding="utf-8"), encoding="utf-8")
    skala = json.loads((tmp_path / "kategorienskala.json").read_text(encoding="utf-8"))
    skala["eintraege"][1]["von"] = 60  # overlaps 40..69
    (tmp_path / "kategorienskala.json").write_text(json.dumps(skala), encoding="utf-8")
    with pytest.raises(EngineError):
        config.load(tmp_path)


def test_derivations(cfg):
    assert derive.age(date(2018, 1, 20), date(2026, 6, 10)) == {"jahre": 8, "monate": 4, "abgeleitet": True}
    assert derive.months_between(date(2024, 9, 2), date(2026, 6, 1)) == 20
    entry = cfg.test("iq-test-a")
    assert derive.norm_group(entry, {"jahre": 8, "monate": 4})["von"] == {"jahre": 8, "monate": 0}
    assert derive.norm_group(entry, {"jahre": 12, "monate": 0}) is None
    assert derive.norm_age_years(entry, date(2026, 6, 10)) == 12


def test_category_derivation(cfg):
    assert derive.category(cfg, 75, "iq", None)["kategorie"] == "Kategorie B"
    assert derive.category(cfg, 55, "iq", "iq-test-a")["kategorie"] == "Kategorie A-spezifisch"  # specific wins
    assert "kategorie_luecke" in derive.category(cfg, 10, "iq", None)
    assert "kategorie_luecke" in derive.category(cfg, 50, "pr", None)  # no scale for PR: gap, not a guess
    assert "kategorie_luecke" in derive.category(config.Config(None, None, None, None), 75, "iq", None)


def test_all_rules_on_complete_spf_input(cfg):
    result = rules.pruefe_fachregeln(GI, cfg)
    validate("regelergebnis", result)
    r = _by_id(result)
    assert r["awmf_a"] == r["awmf_b"] == r["awmf_d"] == r["awmf_e"] == ["erfuellt"]
    assert r["spf_s1"] == r["spf_s2"] == r["spf_s3"] == r["q1"] == ["erfuellt"]
    assert r["normen_alter"] == ["nicht_erfuellt"]  # 12 years > 10: hint only
    assert r["konfidenz_95"] == ["erfuellt"] and r["d1"] == ["erfuellt"]
    assert result["gesamt"] == "erfuellt"  # hints never change gesamt
    assert result["schweregrad_vorschlag"]["stufe"] == "leicht"


@pytest.mark.parametrize("change,rule_id,expected", [
    (lambda g: g["drei_quellen"].update(befragung_adaptives_verhalten="fehlt"), "awmf_a", "nicht_erfuellt"),
    (lambda g: g["testergebnisse"][0].update(ki_obergrenze=72), "awmf_b", "nicht_erfuellt"),
    (lambda g: g["testergebnisse"][0].pop("ki_niveau") and g["testergebnisse"][0].pop("gesamt_iq"), "awmf_b",
     "nicht_pruefbar"),
    (lambda g: g["testergebnisse"][0].update(einzeltestung=False), "awmf_e", "nicht_erfuellt"),
    (lambda g: g["testergebnisse"][0].update(testkatalog_id=None), "awmf_d", "nicht_pruefbar"),
    (lambda g: g["testergebnisse"][0].update(ki_niveau=0.90), "konfidenz_95", "nicht_erfuellt"),
    (lambda g: g["testergebnisse"].clear(), "spf_s1", "nicht_erfuellt"),
    (lambda g: g["leistungsproben"]["mathematik"].update(text=" "), "spf_s2", "nicht_erfuellt"),
    (lambda g: g["foerderung_und_umfeld"].update(text=""), "spf_s3", "nicht_erfuellt"),
    (lambda g: g["empfehlung"].update(text="Verdacht auf F70"), "d1", "nicht_erfuellt"),
    (lambda g: g["empfehlung"].update(text="Hinweis auf Intelligenzminderung"), "d1", "nicht_erfuellt"),
])
def test_rule_failures(cfg, change, rule_id, expected):
    gi = copy.deepcopy(GI)
    change(gi)
    result = rules.pruefe_fachregeln(gi, cfg)
    assert expected in _by_id(result)[rule_id]


def test_q1_on_lrs(cfg):
    gi = copy.deepcopy(GI) | {"gutachtentyp": "lrs", "gutachten_diagnose": {"text": "synthetisch"}}
    assert _by_id(rules.pruefe_fachregeln(gi, cfg))["q1"] == ["erfuellt"]
    gi["verfasserin"]["qualifikationen"] = ["schulpsychologin"]
    result = rules.pruefe_fachregeln(gi, cfg)
    assert _by_id(result)["q1"] == ["nicht_erfuellt"] and result["gesamt"] == "nicht_erfuellt"
    assert "spf_s1" not in _by_id(result)  # SPF rules only for spf


def test_missing_parameter_never_passes(cfg):
    rule = next(r for r in cfg.regelwerk["regeln"] if r["regel_id"] == "awmf_b")
    rule["parameter"] = {}
    assert _by_id(rules.pruefe_fachregeln(GI, cfg))["awmf_b"] == ["nicht_pruefbar"]


def test_without_configuration_everything_is_not_checkable():
    result = rules.pruefe_fachregeln(GI, config.Config(None, None, None, None))
    # required export rules missing from the regelwerk are listed as nicht_pruefbar, never silently dropped (E30)
    assert {e["regel_id"]: e["ergebnis"] for e in result["ergebnisse"]} == dict.fromkeys(
        ("spf_s1", "spf_s2", "spf_s3", "q1", "d1"), "nicht_pruefbar")
    assert all(e["wirkung"] == "blockiert_export" for e in result["ergebnisse"])
    assert result["gesamt"] == "nicht_pruefbar" and result["regelwerk_version"] == "nicht_konfiguriert"


def test_d1_without_term_list_is_not_checkable(cfg):
    rule = next(r for r in cfg.regelwerk["regeln"] if r["regel_id"] == "d1")
    rule["parameter"] = {}
    assert _by_id(rules.pruefe_fachregeln(GI, cfg))["d1"] == ["nicht_pruefbar"]


def test_fuer_claude_hides_diagnosis_rules(cfg):
    gi = copy.deepcopy(GI)
    gi["drei_quellen"]["befragung_adaptives_verhalten"] = "fehlt"  # blocks diagnosis only
    full = rules.pruefe_fachregeln(gi, cfg)
    assert full["gesamt"] == "nicht_erfuellt"
    claude = rules.fuer_claude(full)
    validate("regelergebnis", claude)
    from schlomo_engine.contracts import _registry
    from jsonschema import Draft202012Validator
    schemas, registry = _registry()
    Draft202012Validator({"$ref": "regelergebnis.schema.json#/$defs/fuer_claude"}, registry=registry).validate(claude)
    assert not any(e["regel_id"].startswith("awmf_") for e in claude["ergebnisse"])
    assert "schweregrad_vorschlag" not in claude
    assert claude["gesamt"] == "erfuellt"  # the diagnosis-only failure does not leak through gesamt


def test_engine_diagnosis_proposal(cfg):
    result = rules.pruefe_fachregeln(GI, cfg)
    proposal = rules.engine_diagnosevorschlag(GI, result, cfg)
    validate("diagnosevorschlag", proposal)
    assert proposal["kriterien"] == "erfuellt" and proposal["icd10_code"] == "F70"
    assert proposal["schweregrad_vorschlag"] == "leicht" and "[synthetisch]" in proposal["hinweis"]

    gi = copy.deepcopy(GI)
    gi["testergebnisse"][0].update(gesamt_iq=30, ki_untergrenze=25, ki_obergrenze=35)  # F72: not in reference
    proposal = rules.engine_diagnosevorschlag(gi, rules.pruefe_fachregeln(gi, cfg), cfg)
    validate("diagnosevorschlag", proposal)
    assert "icd10_code" not in proposal and "nicht in den lokalen Referenzdaten" in proposal["hinweis"]


def test_ui_functions(env, monkeypatch):
    monkeypatch.setenv("SCHLOMO_KONFIGURATION", str(SYN))
    assert uf.alter_berechnen({"geburtsdatum": "2018-01-20", "testdatum": "2026-06-10"})["alter"]["monate"] == 4
    with pytest.raises(EngineError):
        uf.alter_berechnen({"geburtsdatum": "2027-01-01", "testdatum": "2026-06-10"})
    assert uf.schulbesuch_berechnen({"schulbeginn_oesterreich": "2024-09-02", "testdatum": "2026-06-01"}) == \
        {"schulbesuch_oesterreich_monate": 20}
    out = uf.normwerte_ableiten({"testkatalog_id": "iq-test-a", "alter": {"jahre": 8, "monate": 4},
                                 "testdatum": "2026-06-10"})
    assert out["normen_alter_jahre"] == 12 and out["normgruppe"]["abgeleitet"] is True
    session = uf.sitzung_anlegen({"bezeichnung": "Fall 6", "modus": "gutachten", "gutachtentyp": "spf"})["session"]
    record = store.load(session["session_id"])
    record["gutachten_input"] = copy.deepcopy(GI) | {"session_id": session["session_id"]}
    store.save(record)
    result = uf.fachregeln_pruefen({"session_id": session["session_id"]})["regelergebnis"]
    assert result["regelwerk_version"] == "syn-1" and result["gesamt"] == "erfuellt"
