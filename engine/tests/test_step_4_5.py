"""Step 4.5: hint wordings for the Rubberduck screens, style profiles released in the app, learning signal overview."""
import json
from pathlib import Path

import pytest

from schlomo_engine import packages, ui_functions as uf
from schlomo_engine.errors import EngineError

KONF = Path(__file__).resolve().parent / "konfiguration_synthetisch"
PROFIL = {"schema_version": "1", "version": "v1", "status": "entwurf", "anzahl_probegutachten": 2,
          "merkmale": [{"merkmal_id": "m1", "kategorie": "satzbau", "beschreibung": "[synthetisch] Kurze Sätze.",
                        "belegzitate": [{"text": "[synthetisch] Ruhig.", "probe_id": "pg-00000001"}]}],
          "formulierungsbeispiele": [{"abschnitt_id": "empfehlung", "text": "[synthetisch] Empfohlen wird ..."}]}


@pytest.fixture
def stil(env, monkeypatch, tmp_path):
    monkeypatch.setenv("SCHLOMO_STILPROFILE", str(tmp_path / "stil"))
    return tmp_path / "stil"


def test_vorgaben_with_and_without_hints(env, monkeypatch, tmp_path):
    monkeypatch.setenv("SCHLOMO_KONFIGURATION", str(KONF))
    v = uf.FUNCTIONS["rubberduck_vorgaben"]({})
    assert v["hinweise"]["kindeswohl"].startswith("[synthetisch]") and v["herkunft"]["hinweise"] == "synthetisch"
    monkeypatch.setenv("SCHLOMO_KONFIGURATION", str(tmp_path / "leer"))
    assert uf.FUNCTIONS["rubberduck_vorgaben"]({})["hinweise"] is None


def test_release_style_profile(stil):
    packages.save_stilprofil(PROFIL)
    assert uf.FUNCTIONS["stilprofile_laden"]({})["aktiv"] is None
    assert uf.FUNCTIONS["stilprofil_freigeben"]({"version": "v1"}) == {"version": "v1", "status": "freigegeben"}
    out = uf.FUNCTIONS["stilprofile_laden"]({})
    assert out["aktiv"] == "v1" and out["stilprofile"][0]["merkmale"] == PROFIL["merkmale"]
    with pytest.raises(EngineError) as e:
        uf.FUNCTIONS["stilprofil_freigeben"]({"version": "v1"})
    assert e.value.code == "E_BLOCKIERT"
    with pytest.raises(EngineError) as e:
        uf.FUNCTIONS["stilprofil_freigeben"]({"version": "../x"})
    assert e.value.code == "E_NICHT_GEFUNDEN"


def test_learning_signal_overview_without_supervision(env):
    """EGM B14: a signal in a supervision record is never counted."""
    from schlomo_engine import store
    sid = uf.sitzung_anlegen({"bezeichnung": "Supervision 62", "modus": "supervision"})["session"]["session_id"]
    record = store.load(sid)
    record["lernsignale"] = [{"schema_version": "1", "signal_id": "ls-00000002", "herkunft": "intervision",
                              "art": "befund_verworfen", "bereich": "pruefverhalten", "pruefer": "goldfisch",
                              "konfiguration_version": "syn-1"}]
    store.save(record)
    assert uf.FUNCTIONS["lernsignale_uebersicht"]({})["signale"] == 0


def test_learning_signal_overview(env):
    from schlomo_engine import store
    sid = uf.sitzung_anlegen({"bezeichnung": "Fall 61", "modus": "intervision"})["session"]["session_id"]
    record = store.load(sid)
    record["lernsignale"] = [{"schema_version": "1", "signal_id": "ls-00000001", "herkunft": "intervision",
                              "art": "befund_verworfen", "bereich": "pruefverhalten", "pruefer": "goldfisch",
                              "konfiguration_version": "syn-1"}]
    store.save(record)
    out = uf.FUNCTIONS["lernsignale_uebersicht"]({})
    assert out["signale"] == 1 and out["je_pruefer"]["goldfisch"]["befund_verworfen"] == 1 and out["gutachten"] == 0
    assert "Fall 61" not in json.dumps(out)
