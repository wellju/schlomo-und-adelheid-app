"""Step 4.3: input context, package written to a chosen path, export preview with locks. Synthetic."""
import copy
import json
from pathlib import Path

import pytest

import synth_template as st
from schlomo_engine import config, rules, store, ui_functions as uf
from schlomo_engine.errors import EngineError
from test_step_1_4 import GI

KONF = Path(__file__).resolve().parent / "konfiguration_synthetisch"


@pytest.fixture
def sid(env, monkeypatch, tmp_path):
    monkeypatch.setenv("SCHLOMO_KONFIGURATION", str(KONF))
    monkeypatch.setenv("SCHLOMO_VORLAGEN", str(tmp_path / "vorlagen"))
    sid = uf.sitzung_anlegen({"bezeichnung": "Fall 31", "modus": "gutachten", "gutachtentyp": "spf"})["session"]["session_id"]
    uf.bekannte_namen_setzen({"session_id": sid, "namen": []})
    return sid


def test_eingabe_kontext_before_and_after_input(sid):
    k = uf.FUNCTIONS["eingabe_kontext"]({"session_id": sid})
    assert k["testkatalog"][0]["id"] == "iq-test-a" and k["kategorien"] == [] and k["regelergebnis"] is None
    assert "spf_s1" in k["regeln"] and "quelle" in k["regeln"]["spf_s1"]
    assert not any("quelle" in e for e in k["testkatalog"])  # only what the input screen needs
    gi = copy.deepcopy(GI) | {"session_id": sid}
    assert uf.eingabe_speichern({"session_id": sid, "gutachten_input": gi, "unsichere_bestaetigt": True})["gespeichert"]
    k = uf.FUNCTIONS["eingabe_kontext"]({"session_id": sid})
    assert k["kategorien"][0]["wert_quelle"] == "/testergebnisse/0/werte/0"
    assert k["bausteine"][0]["testkatalog_id"] == "iq-test-a" and k["regelergebnis"]["ergebnisse"]


def test_package_written_once(sid, tmp_path):
    gi = copy.deepcopy(GI) | {"session_id": sid}
    uf.eingabe_speichern({"session_id": sid, "gutachten_input": gi, "unsichere_bestaetigt": True})
    template = tmp_path / "Vorlage SPF.docx"
    st.build(template)
    uf.vorlage_zuordnen({"vorlage": st.vorlage(uf.vorlage_importieren({"pfad": str(template)})["datei"])})
    ziel = tmp_path / "paket.json"
    p = uf.erzeuge_paket({"session_id": sid, "art": "gutachten", "ziel_pfad": str(ziel)})["fallpaket"]
    assert json.loads(ziel.read_text(encoding="utf-8"))["paket_id"] == p["paket_id"]
    with pytest.raises(EngineError) as e:  # never over an existing file
        uf.erzeuge_paket({"session_id": sid, "art": "gutachten", "ziel_pfad": str(ziel)})
    assert e.value.code == "E_BLOCKIERT"
    with pytest.raises(EngineError):
        uf.erzeuge_paket({"session_id": sid, "art": "gutachten", "ziel_pfad": str(tmp_path / "paket.exe")})


def test_export_preview_reports_lock(sid, tmp_path):
    with pytest.raises(EngineError) as e:
        uf.export_vorschau({"session_id": sid})
    assert e.value.code == "E_NICHT_GEFUNDEN"
    gi = copy.deepcopy(GI) | {"session_id": sid}
    uf.eingabe_speichern({"session_id": sid, "gutachten_input": gi, "unsichere_bestaetigt": True})
    record = store.load(sid)
    record["entwuerfe"] = [{"schema_version": "3", "session_id": sid, "gutachtentyp": "spf", "vorlage_id": "spf-syn",
                            "entwurf_version": 1, "regelergebnis": rules.fuer_claude(rules.pruefe_fachregeln(gi, config.load())),
                            "platzhalter": [], "abschnitte": [
                                {"abschnitt_id": "empfehlung", "absaetze": [{"absatz_id": "a1", "saetze": [
                                    {"text": "[synthetisch] Empfohlen.", "quellen": ["/empfehlung"]}]}]}]}]
    store.save(record)
    v = uf.export_vorschau({"session_id": sid})
    assert v["sperre"]["code"] == "E_NICHT_GEFUNDEN"  # template not imported yet
    assert v["abschnitte"][0]["text"].startswith("[synthetisch] Empfohlen")


def test_enum_fields_are_no_free_text(sid):
    """The qualification "schulpsychologin" came back as an uncertain NER person and blocked saving (Task 4.3)."""
    gi = copy.deepcopy(GI) | {"session_id": sid}
    gi["verfasserin"] = {"qualifikationen": ["schulpsychologin"]}
    gi["anamnese"] = [{"quelle_id": "q1", "erhoben_mit": "die Mutter", "art": "gespraech", "uebersetzungshilfe": False,
                       "text": "[synthetisch] Sprachentwicklung verzögert."}]
    out = uf.eingabe_speichern({"session_id": sid, "gutachten_input": gi})
    assert out["gespeichert"], out
    gi["vorstellungsgrund"] = {"text": "[synthetisch] Bartholomäus Wendelin meldet das Kind an."}
    out = uf.eingabe_speichern({"session_id": sid, "gutachten_input": gi})
    assert not out["gespeichert"] and out["funde"][0]["feld"] == "/vorstellungsgrund/text"  # real free text still checked


def test_enum_exemption_only_for_enum_values(sid):
    """EGM C21: only a value from the enum is exempt; other text under such a key is still checked."""
    out = uf._freitext_funde(sid, {"art": "Bartholomäus Wendelin", "skala": "iq"}, use_ner=True)
    assert [f["feld"] for f in out] == ["/art"]


def test_refused_package_file_leaves_no_open_package(sid, tmp_path):
    """EGM C5: the file is written before the package is registered."""
    from schlomo_engine import packages
    gi = copy.deepcopy(GI) | {"session_id": sid}
    uf.eingabe_speichern({"session_id": sid, "gutachten_input": gi, "unsichere_bestaetigt": True})
    template = tmp_path / "Vorlage SPF.docx"
    st.build(template)
    uf.vorlage_zuordnen({"vorlage": st.vorlage(uf.vorlage_importieren({"pfad": str(template)})["datei"])})
    (tmp_path / "da.json").write_text("{}", encoding="utf-8")
    with pytest.raises(EngineError):
        uf.erzeuge_paket({"session_id": sid, "art": "gutachten", "ziel_pfad": str(tmp_path / "da.json")})
    assert packages._open_packages(sid) == {}


def test_qualifications_come_from_the_profile(sid, env):
    """EGM B5: once the profile of Screen 13 is saved, it is the one source of the qualifications in the input."""
    uf.FUNCTIONS["einstellungen_speichern"]({"einstellungen": {"schema_version": "1", "verbindung": "desktop",
                                                             "qualifikationen": ["schulpsychologin"], "darstellung": "system"}})
    gi = copy.deepcopy(GI) | {"session_id": sid}  # says klinische_psychologin as well
    assert uf.eingabe_speichern({"session_id": sid, "gutachten_input": gi, "unsichere_bestaetigt": True})["gespeichert"]
    assert store.load(sid)["gutachten_input"]["verfasserin"]["qualifikationen"] == ["schulpsychologin"]
