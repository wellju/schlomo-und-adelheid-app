"""Step 1.3: recognition, replacement, decisions, release; corpus acceptance. Synthetic data only."""
import json
import os
from datetime import date

import pytest

import corpus as c
import synth_files as sf
from evaluate import evaluate, load
from schlomo_engine import external, ram, recognition, store, ui_functions as uf
from schlomo_engine.errors import EngineError

needs_tools = pytest.mark.skipif(
    not (external.find("tesseract", "SCHLOMO_TESSERACT") and external.find("soffice", "SCHLOMO_SOFFICE")),
    reason="Tesseract and LibreOffice needed for the full corpus")


@pytest.fixture
def rare(tmp_path, monkeypatch):
    path = tmp_path / "seltene_merkmale.json"
    path.write_text(json.dumps(c.RARE_TERMS), encoding="utf-8")
    monkeypatch.setenv("SCHLOMO_SELTENE_MERKMALE", str(path))


def _kinds(funde):
    return {(f.kategorie, f.text) for f in funde}


def test_known_names_with_inflection_and_initial():
    names = [recognition.KnownName("Lenja Quastberger", "das Kind")]
    text = "Lenjas Heft lag bei L. Quastberger; QUASTBERGER fehlte. Lenja Quastberger kam."
    funde = recognition.detect_text(text, 0, names, None, use_ner=False)
    hits = [f.text for f in funde if f.quelle == "liste"]
    assert hits == ["Lenjas", "L. Quastberger", "QUASTBERGER", "Lenja Quastberger"]
    assert all(f.ersatz == "[das Kind]" for f in funde if f.quelle == "liste")


@pytest.mark.parametrize("text,hit,kategorie", [
    ("am 03.04.2017 geboren", "03.04.2017", "datumsangaben"), ("am 3. März 2019", "3. März 2019", "datumsangaben"),
    ("seit Oktober 2023", "Oktober 2023", "datumsangaben"), ("Termin 2026-05-04", "2026-05-04", "datumsangaben"),
    ("Tel. 0664 123 4567", "0664 123 4567", "direkte_identifikatoren"),
    ("mail: a.b@beispielpost.at", "a.b@beispielpost.at", "direkte_identifikatoren"),
    ("GZ 1234/2026-5", "GZ 1234/2026-5", "direkte_identifikatoren"),
    ("SV 1234 010117", "1234 010117", "direkte_identifikatoren"),
    ("wohnt Quellenstraße 12/3", "Quellenstraße 12/3", "direkte_identifikatoren"),
    ("1100 Wien", "1100 Wien", "orte_einrichtungen"), ("Volksschule Favoriten", "Volksschule Favoriten", "orte_einrichtungen"),
    ("im 10. Bezirk", "10. Bezirk", "orte_einrichtungen"), ("ein Bruder (12) lebt", "Bruder (12)", "seltene_merkmale"),
])
def test_rules(text, hit, kategorie):
    """E44: the rule hit covers the whole value, not only a part of it."""
    funde = recognition.detect_text(text, 0, [], None, use_ner=False)
    assert any(f.kategorie == kategorie and f.quelle == "regel" and hit in f.text for f in funde), [f.text for f in funde]


def test_rare_terms_from_configuration_only(rare, monkeypatch):
    assert any(f.kategorie == "seltene_merkmale" for f in recognition.detect_text("spricht Dari", 0, [], None, False))
    monkeypatch.delenv("SCHLOMO_SELTENE_MERKMALE")
    assert not recognition.detect_text("spricht Dari", 0, [], None, False)  # nothing invented without the list


def test_relative_dates():
    assert recognition.relative_date("03.01.2018", date(2026, 3, 10)) == "[Datum, 8;2 vor dem Testtag]"
    assert recognition.relative_date("Oktober 2026", date(2026, 3, 10)) == "[Datum, 0;6 nach dem Testtag]"
    assert recognition.relative_date("03.01.2018", None) == "[Datum]"
    # month names with "s", and dates split over an OCR line break
    assert recognition.relative_date("3. August\n2025", date(2026, 3, 10)) == "[Datum, 0;7 vor dem Testtag]"
    assert recognition.relative_date("August \n2025", date(2026, 3, 10)) == "[Datum, 0;7 vor dem Testtag]"


def test_ner_hits_are_uncertain():
    funde = recognition.detect_text("Der Bericht von Ursula Fleischhacker liegt vor.", 0, [], None)
    per = [f for f in funde if f.quelle == "ner" and f.kategorie == "direkte_identifikatoren"]
    assert per and all(f.unsicher for f in per)


def test_bezeichnung_with_name_or_date_rejected(env):
    for label in ("Fall Lenja Quastberger", "Fall vom 03.04.2026"):
        with pytest.raises(EngineError) as e:
            uf.sitzung_anlegen({"bezeichnung": label, "modus": "supervision"})
        assert e.value.code == "E_BEZEICHNUNG"
    assert uf.sitzung_anlegen({"bezeichnung": "Fall 7", "modus": "supervision"})["session"]


def test_full_flow_decide_and_release(env, rare, tmp_path):
    ram.clear()
    text, v = c._case(1)
    c._docx(text, tmp_path / "a.docx", hidden=f"Rückfrage bei {v['therapeutin']}")
    sid = uf.sitzung_anlegen({"bezeichnung": "Fall 8", "modus": "gutachten", "gutachtentyp": "spf"})["session"]["session_id"]
    uf.bekannte_namen_setzen({"session_id": sid, "namen": [{"text": v["kind"], "rolle": "das Kind"},
                                                          {"text": v["mutter"], "rolle": "die Mutter"}]})
    dok = uf.dokument_importieren({"session_id": sid, "pfad": str(tmp_path / "a.docx"), "quelle_rolle": "Bericht"})
    args = {"session_id": sid, "dok_id": dok["dok_id"]}
    state = uf.erkennung_ausfuehren(args | {"testdatum": "2026-06-15"})
    hidden_texts = [f["text"] for f in state["funde"] if f["kategorie"] == "versteckte_inhalte"]
    assert any("Rückfrage" in t for t in hidden_texts)  # comment; docx metadata parts count as hidden as well

    with pytest.raises(EngineError) as e:  # uncertain NER findings still open
        uf.anonymisierung_freigeben(args | {"geprueft_bestaetigt": True})
    assert e.value.code == "E_ANONYMISIERUNG_OFFEN"
    hidden = next(f for f in state["funde"] if f["kategorie"] == "versteckte_inhalte")
    with pytest.raises(EngineError) as e:  # hidden content can never be released
        uf.schwaerzung_entscheiden(args | {"fund_id": hidden["fund_id"], "entscheidung": "verwerfen"})
    assert e.value.code == "E_BLOCKIERT"
    for f in state["funde"]:
        if f["status"] == "offen":
            uf.schwaerzung_entscheiden(args | {"fund_id": f["fund_id"], "entscheidung": "uebernehmen"})
    with pytest.raises(EngineError) as e:  # explicit confirmation required
        uf.anonymisierung_freigeben(args | {"geprueft_bestaetigt": False})
    assert e.value.code == "E_SCHEMA"
    out = uf.anonymisierung_freigeben(args | {"geprueft_bestaetigt": True})
    assert out["freigabe"]["status"] == "freigegeben" and out["freigabe"]["funde_je_kategorie"]["unsicher"] == 0

    stored = store.load(sid)["session"]["dokumente"][0]
    released = stored["text_anonymisiert"]
    # E43: every value of the ground truth that the text holds, not only seven
    keys = ("kind", "kind_vor", "mutter", "lehrer", "therapeutin", "telefon", "email", "geburt", "adresse", "aktenzahl",
            "svnr", "test", "kopfdatum", "einreise", "tag_ohne_jahr", "schuljahr", "plz_ort", "sprache", "geschw")
    for value in (v[k] for k in keys if v[k] in text):
        assert value not in released, value
    assert "[das Kind]" in released and "vor dem Testtag]" in released
    assert ram.get(sid, dok["dok_id"]) is None  # clear text dropped after release
    assert "Rückfrage" not in json.dumps(store.load(sid))


def test_known_name_cannot_be_rejected(env, tmp_path):
    """E08: a known name is changed or replaced, never kept in clear text."""
    ram.clear()
    sid = uf.sitzung_anlegen({"bezeichnung": "Fall 5", "modus": "supervision"})["session"]["session_id"]
    sf.make_docx(tmp_path / "a.docx")
    uf.bekannte_namen_setzen({"session_id": sid, "namen": [{"text": "SYN-HAUPTTEXT", "rolle": "das Kind"}]})
    dok = uf.dokument_importieren({"session_id": sid, "pfad": str(tmp_path / "a.docx"), "quelle_rolle": "Bericht"})
    args = {"session_id": sid, "dok_id": dok["dok_id"]}
    name = next(f for f in uf.erkennung_ausfuehren(args)["funde"] if f["quelle"] == "liste")
    with pytest.raises(EngineError) as e:
        uf.schwaerzung_entscheiden(args | {"fund_id": name["fund_id"], "entscheidung": "verwerfen"})
    assert e.value.code == "E_BLOCKIERT"
    assert uf.schwaerzung_entscheiden(args | {"fund_id": name["fund_id"], "entscheidung": "aendern",
                                              "ersatz": "[Kind]"})["fund"]["status"] == "geaendert"


def test_rejected_rule_hit_keeps_inner_name_replaced(env):
    """E03: rejecting a too-wide institution hit does not expose the known name inside it; the rejected text is
    exempt from the re-check by position only (E08), so the same text elsewhere still blocks."""
    ram.clear()
    sid = uf.sitzung_anlegen({"bezeichnung": "Fall 6", "modus": "supervision"})["session"]["session_id"]
    uf.bekannte_namen_setzen({"session_id": sid, "namen": [{"text": "Synthia Quastberger", "rolle": "das Kind"}]})
    doc = ram.ImportedDoc(sid, "d-0000000a", "docx", b"", 1,
                          [ram.Part("haupttext", "[synthetisch] Im Hort Synthia spielte das Kind gern.")])
    ram.put(doc)
    record = store.load(sid)
    record["session"]["dokumente"].append({"dok_id": doc.dok_id, "format": "docx", "quelle_rolle": "Bericht",
                                           "freigabe": {"status": "offen", "funde_je_kategorie": uf._funde_counts(doc)}})
    store.save(record)
    args = {"session_id": sid, "dok_id": doc.dok_id}
    funde = uf.erkennung_ausfuehren(args)["funde"]
    hort = next(f for f in funde if f["text"].startswith("Hort"))
    uf.schwaerzung_entscheiden(args | {"fund_id": hort["fund_id"], "entscheidung": "verwerfen"})
    for f in funde:
        if f["status"] == "offen" and f is not hort:
            uf.schwaerzung_entscheiden(args | {"fund_id": f["fund_id"], "entscheidung": "uebernehmen"})
    uf.anonymisierung_freigeben(args | {"geprueft_bestaetigt": True})
    released = next(d for d in store.load(sid)["session"]["dokumente"] if d["dok_id"] == doc.dok_id)["text_anonymisiert"]
    assert "Synthia" not in released and "Hort [das Kind]" in released


@needs_tools
def test_corpus_acceptance(rare, tmp_path):
    """Acceptance (Task 1): no direct identifier, date, hidden content, place or rare feature of the ground truth
    readable after release (EGM E06, E22, E23)."""
    docs = c.build(tmp_path / "korpus")
    assert len(docs) >= 30 and {d.format for d in docs} == set(c.FORMATE)
    assert len({d.bekannte_namen[0]["text"] for d in docs}) == len(docs)  # 33 different children
    assert len({c._case(i)[1]["vorlage"] for i in range(len(docs))}) == 4  # four templates
    assert sum(1 for d in docs if d.versteckt) == 6  # hidden content in DOCX and XLSX
    result = evaluate(docs, {d.name: load(d) for d in docs})
    assert result["misses"] == [], result["misses"]
    assert result["misses_weitere"] == [], result["misses_weitere"]


if os.environ.get("SCHLOMO_MODELLVERGLEICH"):  # optional measurement, e.g. "ohne_ner,de_core_news_sm,de_core_news_md"
    @needs_tools
    def test_model_comparison(rare, tmp_path, monkeypatch, capsys):
        """E39: the model comparison of docs/task-1-ergebnis.md as a reproducible run; the installer model has no
        miss."""
        docs = c.build(tmp_path / "korpus")
        imported = {d.name: load(d) for d in docs}
        rows = {}
        for model in os.environ["SCHLOMO_MODELLVERGLEICH"].split(","):
            if model != "ohne_ner":
                monkeypatch.setenv("SCHLOMO_SPACY_MODEL", model)
                recognition.reset_nlp()
            r = evaluate(docs, imported, use_ner=model != "ohne_ner")
            rows[model] = (len(r["misses"]), len(r["misses_weitere"]), r["false_alarms"], r["funde"], r["unsicher"])
        recognition.reset_nlp()
        with capsys.disabled():
            for model, row in rows.items():
                print(f"\n{model}: verfehlt={row[0]} verfehlt_orte_merkmale={row[1]} fehlalarme={row[2]} funde={row[3]} "
                      f"unsicher={row[4]}")
        assert rows.get("de_core_news_md", (0,))[0] == 0
