"""Step 4.4: catalogue care with mandatory sources, versions and rollback, never in the synthetic test fixtures."""
import copy
import json
import shutil
from pathlib import Path

import pytest

from schlomo_engine import ui_functions as uf
from schlomo_engine.errors import EngineError

KONF = Path(__file__).resolve().parent / "konfiguration_synthetisch"


@pytest.fixture
def konf(env, monkeypatch, tmp_path):
    d = tmp_path / "konfiguration"
    shutil.copytree(KONF, d)
    monkeypatch.setenv("SCHLOMO_KONFIGURATION", str(d))
    monkeypatch.setenv("SCHLOMO_VORLAGEN", str(tmp_path / "vorlagen"))
    return d


def test_load_save_and_rollback(konf):
    k = uf.FUNCTIONS["konfiguration_laden"]({})
    assert k["testkatalog"]["version"] == "syn-1" and k["versionen"]["testkatalog"] == [] and k["vorlagen"] == []
    neu = copy.deepcopy(k["kategorienskala"]) | {"version": "syn-2"}
    neu["eintraege"][0]["bezeichnung"] = "Kategorie A neu"
    out = uf.FUNCTIONS["katalog_speichern"]({"name": "kategorienskala", "dokument": neu})
    assert out == {"version": "syn-2", "versionen": ["syn-1"]}
    assert json.loads((konf / "kategorienskala.json").read_text(encoding="utf-8"))["eintraege"][0]["bezeichnung"] == "Kategorie A neu"
    with pytest.raises(EngineError) as e:  # a version is written once
        uf.FUNCTIONS["katalog_speichern"]({"name": "kategorienskala", "dokument": neu})
    assert e.value.code == "E_BLOCKIERT"
    out = uf.FUNCTIONS["rollback"]({"name": "kategorienskala", "version": "syn-1", "neue_version": "syn-3"})
    assert out["versionen"] == ["syn-1", "syn-2"]
    now = json.loads((konf / "kategorienskala.json").read_text(encoding="utf-8"))
    assert now["version"] == "syn-3" and now["eintraege"][0]["bezeichnung"] == "Kategorie A"


def test_source_is_mandatory_and_scale_checked(konf):
    k = uf.FUNCTIONS["konfiguration_laden"]({})
    ohne = copy.deepcopy(k["testkatalog"]) | {"version": "syn-2"}
    del ohne["eintraege"][0]["quelle"]
    with pytest.raises(EngineError) as e:
        uf.FUNCTIONS["katalog_speichern"]({"name": "testkatalog", "dokument": ohne})
    assert e.value.code == "E_SCHEMA"
    leer_manual = copy.deepcopy(k["testkatalog"]) | {"version": "syn-2"}
    leer_manual["eintraege"][0]["quelle"] = {"manual": " ", "seite": "3"}
    with pytest.raises(EngineError) as e:
        uf.FUNCTIONS["katalog_speichern"]({"name": "testkatalog", "dokument": leer_manual})
    assert e.value.code == "E_SCHEMA"
    leer_kennwert = copy.deepcopy(k["testkatalog"]) | {"version": "syn-2"}
    leer_kennwert["eintraege"][0]["retest"]["quelle"]["seite"] = ""
    with pytest.raises(EngineError):
        uf.FUNCTIONS["katalog_speichern"]({"name": "testkatalog", "dokument": leer_kennwert})
    leer = copy.deepcopy(k["kategorienskala"]) | {"version": "syn-2"}
    leer["eintraege"][0]["quelle"] = ""
    with pytest.raises(EngineError):
        uf.FUNCTIONS["katalog_speichern"]({"name": "kategorienskala", "dokument": leer})
    ueber = copy.deepcopy(k["kategorienskala"]) | {"version": "syn-2"}
    ueber["eintraege"][1]["von"] = 60  # overlaps the first range
    with pytest.raises(EngineError):
        uf.FUNCTIONS["katalog_speichern"]({"name": "kategorienskala", "dokument": ueber})
    with pytest.raises(EngineError) as e:  # the rule set is not edited in the app
        uf.FUNCTIONS["katalog_speichern"]({"name": "regelwerk", "dokument": k["regelwerk"]})
    assert e.value.code == "E_SCHEMA"
    assert json.loads((konf / "testkatalog.json").read_text(encoding="utf-8"))["version"] == "syn-1"


def test_without_configuration_folder_it_is_created(env, monkeypatch):
    """EGM B2, C11: the browser variant has no einrichten; the first save creates konfiguration/ next to the store."""
    monkeypatch.delenv("SCHLOMO_KONFIGURATION", raising=False)
    skala = json.loads((KONF / "kategorienskala.json").read_text(encoding="utf-8"))
    out = uf.FUNCTIONS["katalog_speichern"]({"name": "kategorienskala", "dokument": skala})
    ziel = env["data"].resolve().parent / "konfiguration"
    assert out["version"] == "syn-1" and (ziel / "kategorienskala.json").is_file()
    from schlomo_engine import config
    assert config.config_dir() == ziel


def test_version_labels_and_natural_order(konf):
    """EGM C4, C18: a version is a file name, so no path parts; versions sort naturally."""
    k = uf.FUNCTIONS["konfiguration_laden"]({})
    for bad in ("../../x", "a:b", "", "x" * 41):
        with pytest.raises(EngineError) as e:
            uf.FUNCTIONS["katalog_speichern"]({"name": "kategorienskala", "dokument": k["kategorienskala"] | {"version": bad}})
        assert e.value.code == "E_SCHEMA"
    with pytest.raises(EngineError):
        uf.FUNCTIONS["rollback"]({"name": "kategorienskala", "version": "../syn-1", "neue_version": "syn-5"})
    for v in ("syn-2", "syn-10", "syn-3"):
        uf.FUNCTIONS["katalog_speichern"]({"name": "kategorienskala", "dokument": k["kategorienskala"] | {"version": v}})
    assert uf.FUNCTIONS["konfiguration_laden"]({})["versionen"]["kategorienskala"] == ["syn-1", "syn-2", "syn-10"]


def test_import_rule_set_and_hints(konf, tmp_path):
    """EGM C3: the rule set and the hint wordings come into the app by import, as a new version, checked."""
    regelwerk = json.loads((KONF / "regelwerk.json").read_text(encoding="utf-8")) | {"version": "syn-2"}
    (tmp_path / "rw.json").write_text(json.dumps(regelwerk), encoding="utf-8")
    out = uf.FUNCTIONS["konfiguration_importieren"]({"name": "regelwerk", "pfad": str(tmp_path / "rw.json")})
    assert out == {"version": "syn-2", "versionen": ["syn-1"]}
    (tmp_path / "kaputt.json").write_text("{", encoding="utf-8")
    with pytest.raises(EngineError) as e:
        uf.FUNCTIONS["konfiguration_importieren"]({"name": "hinweise", "pfad": str(tmp_path / "kaputt.json")})
    assert e.value.code == "E_SCHEMA"
    with pytest.raises(EngineError) as e:
        uf.FUNCTIONS["konfiguration_importieren"]({"name": "lernbausteine", "pfad": str(tmp_path / "rw.json")})
    assert e.value.code == "E_SCHEMA"


def test_comparison_overview_counts_only(konf):
    from schlomo_engine import store
    from test_step_1_4 import GI
    sid = uf.sitzung_anlegen({"bezeichnung": "Fall 51", "modus": "gutachten", "gutachtentyp": "spf"})["session"]["session_id"]
    record = store.load(sid)
    record["gutachten_input"] = copy.deepcopy(GI) | {"session_id": sid}
    record["interne_diagnose"] = {"text": "[synthetisch]", "icd10_code": "F70", "erfasst_vor_vorschlaegen": True}
    record["diagnosevorschlaege"] = []
    record["vergleich"] = {"engine": "gleich", "claude": "abweichend"}
    store.save(record)
    before = store.load(sid)
    out = uf.FUNCTIONS["diagnosevergleich_uebersicht"]({})["uebersicht"]
    assert out["engine"]["gleich"] == 1 and out["claude"]["abweichend"] == 1
    assert "F70" not in json.dumps(out) and store.load(sid) == before  # counts only, nothing written


def test_comparison_load_writes_only_on_change(konf):
    """EGM B3: diagnosevergleich_laden is polled by the app; it must not write each time (MCP write conflicts)."""
    from schlomo_engine import store
    from test_step_1_4 import GI
    sid = uf.sitzung_anlegen({"bezeichnung": "Fall 53", "modus": "gutachten", "gutachtentyp": "spf"})["session"]["session_id"]
    uf.bekannte_namen_setzen({"session_id": sid, "namen": []})
    assert uf.eingabe_speichern({"session_id": sid, "gutachten_input": copy.deepcopy(GI) | {"session_id": sid},
                                 "unsichere_bestaetigt": True})["gespeichert"]
    assert uf.interne_diagnose_speichern({"session_id": sid, "interne_diagnose": {"text": "[synthetisch] intern"}})["gespeichert"]
    uf.diagnosevergleich_laden({"session_id": sid})
    vorher = store.load(sid).digest
    uf.diagnosevergleich_laden({"session_id": sid})
    assert store.load(sid).digest == vorher


def test_internal_diagnosis_and_note_go_through_recognition(konf):
    """EGM B4: free text in the internal diagnosis and the note is checked like every other free text."""
    from test_step_1_4 import GI
    sid = uf.sitzung_anlegen({"bezeichnung": "Fall 54", "modus": "gutachten", "gutachtentyp": "spf"})["session"]["session_id"]
    uf.bekannte_namen_setzen({"session_id": sid, "namen": [{"text": "Synthia Quastberger", "rolle": "das Kind"}]})
    uf.eingabe_speichern({"session_id": sid, "gutachten_input": copy.deepcopy(GI) | {"session_id": sid}, "unsichere_bestaetigt": True})
    out = uf.interne_diagnose_speichern({"session_id": sid, "interne_diagnose": {"text": "Synthia Quastberger hat ..."}})
    assert out["gespeichert"] is False and out["funde"][0]["sicher"]
    assert uf.interne_diagnose_speichern({"session_id": sid, "interne_diagnose": {"text": "[synthetisch] intern"}})["gespeichert"]
    uf.diagnosevergleich_laden({"session_id": sid})
    assert uf.vergleich_notiz_speichern({"session_id": sid, "notiz": "wie bei Synthia Quastberger"})["gespeichert"] is False
    assert uf.vergleich_notiz_speichern({"session_id": sid, "notiz": "[synthetisch] Notiz"})["gespeichert"] is True
