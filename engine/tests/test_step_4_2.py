"""Step 4.2: clear text for the redaction view and manual redaction (RAM only). Synthetic."""
import json

import pytest

from schlomo_engine import ram, store, ui_functions as uf
from schlomo_engine.errors import EngineError

TEXT = "Synthia Quastberger besucht die zweite Stufe. Die Lehrerin Frau Brombeerstrauch berichtet. Synthia liest gern."


def _doc(env, tmp_path):
    from docx import Document
    ram.clear()
    d = Document()
    d.add_paragraph(TEXT)
    d.save(tmp_path / "a.docx")
    sid = uf.sitzung_anlegen({"bezeichnung": "Fall 9", "modus": "gutachten", "gutachtentyp": "spf"})["session"]["session_id"]
    uf.bekannte_namen_setzen({"session_id": sid, "namen": [{"text": "Synthia Quastberger", "rolle": "das Kind"}]})
    dok = uf.dokument_importieren({"session_id": sid, "pfad": str(tmp_path / "a.docx"), "quelle_rolle": "Bericht"})
    return {"session_id": sid, "dok_id": dok["dok_id"]}


def test_dokument_text_until_release(env, tmp_path):
    args = _doc(env, tmp_path)
    t = uf.FUNCTIONS["dokument_text"](args)
    assert t["erkennung_gelaufen"] is False and any(TEXT in p["text"] for p in t["teile"])
    uf.erkennung_ausfuehren(args)
    t = uf.FUNCTIONS["dokument_text"](args)
    assert t["erkennung_gelaufen"] and t["funde"]
    haupt = next(p for p in t["teile"] if TEXT in p["text"])
    assert all(haupt["text"][f["start"]:f["end"]] == f["text"] for f in t["funde"] if f["teil"] == haupt["teil"])
    with pytest.raises(EngineError) as e:
        uf.FUNCTIONS["dokument_text"]({"session_id": args["session_id"], "dok_id": "d-00000000"})
    assert e.value.code == "E_NICHT_GEFUNDEN"


def test_manual_redaction(env, tmp_path):
    args = _doc(env, tmp_path)
    add = uf.FUNCTIONS["fund_hinzufuegen"]
    m = {"text": "Brombeerstrauch", "kategorie": "direkte_identifikatoren", "ersatz": "[die Lehrerin]"}
    with pytest.raises(EngineError) as e:  # before the recognition: it would replace the findings
        add(args | m)
    assert e.value.code == "E_BLOCKIERT"
    state = uf.erkennung_ausfuehren(args)
    for bad in ({"kategorie": "bilder"}, {"ersatz": ""}, {"text": "x"}):
        with pytest.raises(EngineError):
            add(args | m | bad)
    before = len(state["funde"])
    already = [f for f in state["funde"] if "Brombeerstrauch" in f["text"]]
    if already:  # NER found it: overlap is skipped, nothing new
        with pytest.raises(EngineError) as e:
            add(args | m)
        assert e.value.code == "E_NICHT_GEFUNDEN"
    else:
        out = add(args | m)
        assert out["neu"] == 1 and len(out["funde"]) == before + 1
    for f in uf.FUNCTIONS["dokument_text"](args)["funde"]:
        if f["status"] == "offen":
            uf.schwaerzung_entscheiden(args | {"fund_id": f["fund_id"], "entscheidung": "uebernehmen"})
    uf.anonymisierung_freigeben(args | {"geprueft_bestaetigt": True})
    released = store.load(args["session_id"])["session"]["dokumente"][0]["text_anonymisiert"]
    assert "Brombeerstrauch" not in released and "Quastberger" not in released
    assert "Brombeerstrauch" not in json.dumps(store.load(args["session_id"]))
    with pytest.raises(EngineError) as e:  # the clear text is gone after the release (ui-api.md, EGM C12)
        uf.FUNCTIONS["dokument_text"](args)
    assert e.value.code == "E_NICHT_GEFUNDEN"
