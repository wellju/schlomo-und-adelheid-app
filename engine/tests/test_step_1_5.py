"""Step 1.5: evidence check, input, findings, text changes, learning signals, templates and DOCX export."""
import copy
import io
import zipfile

import pytest
from docx import Document

import synth_template as st
from schlomo_engine import belege, config, docx_template, rules, store, ui_functions as uf
from schlomo_engine.contracts import validate
from schlomo_engine.errors import EngineError
from test_step_1_4 import GI, SYN


@pytest.fixture
def setup(env, monkeypatch, tmp_path):
    monkeypatch.setenv("SCHLOMO_KONFIGURATION", str(SYN))
    monkeypatch.setenv("SCHLOMO_VORLAGEN", str(tmp_path / "vorlagen"))
    sid = uf.sitzung_anlegen({"bezeichnung": "Fall 11", "modus": "gutachten", "gutachtentyp": "spf"})["session"]["session_id"]
    gi = copy.deepcopy(GI) | {"session_id": sid}
    uf.bekannte_namen_setzen({"session_id": sid, "namen": []})
    assert uf.eingabe_speichern({"session_id": sid, "gutachten_input": gi, "unsichere_bestaetigt": True})["gespeichert"]
    cfg = config.load(SYN)
    draft = {
        "schema_version": "3", "session_id": sid, "gutachtentyp": "spf", "vorlage_id": "spf-syn", "entwurf_version": 1,
        "regelergebnis": rules.fuer_claude(rules.pruefe_fachregeln(gi, cfg)), "platzhalter": ["name_kind"],
        "abschnitte": [
            {"abschnitt_id": "vorstellungsgrund", "absaetze": [{"absatz_id": "a1", "saetze": [
                {"text": "[synthetisch] Vorstellung in der 2. Schulstufe.", "quellen": ["/schullaufbahn"]}]}]},
            {"abschnitt_id": "anamnese", "absaetze": [{"absatz_id": "a2", "saetze": [
                {"luecke": {"feld": "/anamnese", "hinweis": "keine Anamnese eingegeben"}}]}]},
            {"abschnitt_id": "testbefunde", "tabellen": [{"testergebnis_id": "t1", "baustein_quelle": "iq-test-a",
                                                          "zeilen": [{"kennung": "I1", "wert_quelle": "/testergebnisse/0/werte/0",
                                                                      "kategorie": "Kategorie C-spezifisch"}]}]},
            {"abschnitt_id": "leistungsproben", "absaetze": [{"absatz_id": "a4", "saetze": [
                {"luecke": {"feld": "/leistungsproben", "hinweis": "Leistungsproben fehlen"}}]}]},
            {"abschnitt_id": "empfehlung", "absaetze": [{"absatz_id": "a3", "saetze": [
                {"text": "[synthetisch] Der SPF wird empfohlen.", "quellen": ["/empfehlung"]}]}]}]}
    validate("gutachten-output", draft)
    record = store.load(sid)
    record["entwuerfe"] = [draft]
    record["befunde"] = [{"befund_id": "bf-0000aaaa", "stelle": {"abschnitt_id": "empfehlung"}, "problem": "x",
                          "schwere": "mittel", "begruendung": "y", "pruefer": "goldfisch",
                          "entscheidung": {"status": "offen"}}]
    store.save(record)
    template = tmp_path / "Vorlage SPF.docx"
    st.build(template)
    datei = uf.vorlage_importieren({"pfad": str(template)})["datei"]
    uf.vorlage_zuordnen({"vorlage": st.vorlage(datei)})
    return {"sid": sid, "gi": gi, "cfg": cfg, "draft": draft, "template": template, "tmp": tmp_path}


def test_template_analysis_finds_all_bold_kinds(tmp_path):
    st.build(tmp_path / "v.docx")
    info = docx_template.analyze((tmp_path / "v.docx").read_bytes())
    assert info["titel"] == [t for _, t, _ in st.SECTIONS]  # direct, paragraph style and character style bold
    assert info["kopf_beschriftungen"] == st.LABELS and info["felder"] == 10
    assert "word/comments.xml" not in info["teile"] and not any(n.startswith("customXml/") for n in info["teile"])


def test_mapping_errors(tmp_path):
    st.build(tmp_path / "v.docx")
    raw = (tmp_path / "v.docx").read_bytes()
    bad = st.vorlage("v.docx")
    bad["kopffelder"].append({"platzhalter": "klasse", "bezeichnung": "Klassenvorstand"})
    with pytest.raises(EngineError) as e:
        docx_template.check_mapping(raw, bad)
    assert e.value.code == "E_KOPFFELD_FEHLT"
    bad = st.vorlage("v.docx")
    bad["abschnitte"].append({"abschnitt_id": "vorbefunde", "ueberschrift": "Vorbefunde"})
    with pytest.raises(EngineError) as e:
        docx_template.check_mapping(raw, bad)
    assert e.value.code == "E_ABSCHNITT_FEHLT"


def test_field_search_stops_at_next_title(tmp_path):
    st.build(tmp_path / "v.docx", skip_field_after="Anamnese")
    with pytest.raises(EngineError) as e:  # must not write Anamnese into the field of Testbefunde
        docx_template.fill((tmp_path / "v.docx").read_bytes(), st.vorlage("v.docx"), {"anamnese": "x"}, {})
    assert e.value.code == "E_ABSCHNITT_FEHLT"


def test_evidence_ok_and_failures(setup):
    gi, cfg, draft = setup["gi"], setup["cfg"], setup["draft"]
    assert belege.pruefe_belege(draft, gi, cfg) == []
    cases = [
        (lambda d: d["abschnitte"][0]["absaetze"][0]["saetze"][0].update(text="Seit 7 Jahren."), "zahl_ohne_beleg"),
        (lambda d: d["abschnitte"][0]["absaetze"][0]["saetze"][0].update(quellen=["/gibt/es/nicht"]), "quelle_unbekannt"),
        (lambda d: d["abschnitte"][2]["tabellen"][0]["zeilen"][0].update(kategorie="Kategorie A"), "kategorie_abweichend"),
        (lambda d: d["abschnitte"][2]["tabellen"][0].update(baustein_quelle="lesetest-a"), "baustein_fremd"),
        (lambda d: d["abschnitte"][-1]["absaetze"][0]["saetze"][0].update(text="Wie im Synthetischer Lesetest."),
         "verfahren_nicht_im_input"),
        (lambda d: d["abschnitte"][-1]["absaetze"][0]["saetze"][0].update(text="Befund passt zu F70."), "code_nicht_im_input"),
        (lambda d: d["abschnitte"][-1]["absaetze"][0]["saetze"][0].update(text="Keine Intelligenzminderung."),
         "diagnose_im_spf"),
        # E05: gap hints are checked like sentences
        (lambda d: d["abschnitte"][1]["absaetze"][0]["saetze"][0]["luecke"].update(hinweis="IQ 55 nachtragen"),
         "zahl_in_luecke"),
        (lambda d: d["abschnitte"][1]["absaetze"][0]["saetze"][0]["luecke"].update(hinweis="Code F70 offen"),
         "code_nicht_im_input"),
        (lambda d: d["abschnitte"][1]["absaetze"][0]["saetze"][0]["luecke"].update(hinweis="Synthetischer Lesetest"),
         "verfahren_in_luecke"),
        (lambda d: d["abschnitte"][1]["absaetze"][0]["saetze"][0]["luecke"].update(hinweis="Intelligenzminderung"),
         "diagnose_im_spf"),
        # E29: row values belong to the table's test, row labels to the value; E62: lower-case or spaced codes
        (lambda d: d["abschnitte"][2]["tabellen"][0]["zeilen"][0].update(wert_quelle="/testergebnisse/1/werte/0"),
         "quelle_fremd"),
        (lambda d: d["abschnitte"][2]["tabellen"][0]["zeilen"][0].update(kennung="I9"), "kennung_abweichend"),
        (lambda d: d["abschnitte"][-1]["absaetze"][0]["saetze"][0].update(text="Befund passt zu f70."), "code_nicht_im_input"),
        (lambda d: d["abschnitte"][-1]["absaetze"][0]["saetze"][0].update(text="Befund passt zu F 70."), "code_nicht_im_input"),
        # E56: "/" is the member with the empty name, not the whole input
        (lambda d: d["abschnitte"][0]["absaetze"][0]["saetze"][0].update(quellen=["/"]), "quelle_unbekannt"),
    ]
    for change, problem in cases:
        d = copy.deepcopy(draft)
        change(d)
        assert problem in {p["problem"] for p in belege.pruefe_belege(d, gi, cfg)}, problem


def test_export(setup):
    target = setup["tmp"] / "ausgabe" / "gutachten.docx"
    target.parent.mkdir()
    uf.docx_exportieren({"session_id": setup["sid"], "ziel_pfad": str(target)})
    z = zipfile.ZipFile(target)
    names = z.namelist()
    assert not any(n.startswith(("customXml/", "word/comments")) for n in names)
    assert "SYN-VORLAGENAUTOR" not in z.read("docProps/core.xml").decode("utf-8")
    xml = z.read("word/document.xml").decode("utf-8")
    assert "Vorstellung in der 2. Schulstufe." in xml and "[Lücke: keine Anamnese eingegeben]" in xml
    assert "[synthetisch] Baustein A" in xml and "Kategorie C-spezifisch" in xml and "Untertest" not in xml
    assert xml.count("FORMTEXT") == 10 and "<w:del " not in xml and "commentReference" not in xml
    doc = Document(io.BytesIO(target.read_bytes()))  # opens as a valid DOCX
    header = doc.tables[0]
    assert all(row.cells[1].text.strip("  ") == "" for row in header.rows)  # header stays placeholder
    assert doc.tables[1].rows[1].cells[2].text == "Kategorie C-spezifisch"
    with pytest.raises(EngineError) as e:  # no overwrite
        uf.docx_exportieren({"session_id": setup["sid"], "ziel_pfad": str(target)})
    assert e.value.code == "E_BLOCKIERT"


def test_export_blocked_by_rules_and_evidence(setup):
    record = store.load(setup["sid"])
    record["gutachten_input"]["leistungsproben"]["mathematik"]["text"] = ""  # spf_s2 not met
    store.save(record)
    with pytest.raises(EngineError) as e:
        uf.docx_exportieren({"session_id": setup["sid"], "ziel_pfad": str(setup["tmp"] / "a.docx")})
    assert e.value.code == "E_BLOCKIERT"
    record["gutachten_input"]["leistungsproben"]["mathematik"]["text"] = "synthetisch"
    record["entwuerfe"][-1]["abschnitte"][0]["absaetze"][0]["saetze"][0]["text"] = "Seit 7 Jahren."
    store.save(record)
    with pytest.raises(EngineError) as e:
        uf.docx_exportieren({"session_id": setup["sid"], "ziel_pfad": str(setup["tmp"] / "b.docx")})
    assert e.value.code == "E_BELEG"


def test_input_validation(setup):
    gi = copy.deepcopy(setup["gi"])
    with pytest.raises(EngineError):
        uf.eingabe_speichern({"session_id": setup["sid"], "gutachten_input": gi | {"session_id": "s-00000000"}})
    with pytest.raises(EngineError):
        uf.eingabe_speichern({"session_id": setup["sid"], "gutachten_input": gi | {"gutachten_diagnose": {"text": "x"}}})
    session = store.load(setup["sid"])["session"]
    assert session["status"] == "eingabe" and session["versionen"]["regelwerk"] == "syn-1"


def test_findings_and_text_changes_create_signals(setup):
    out = uf.befund_entscheiden({"session_id": setup["sid"], "befund_id": "bf-0000aaaa", "entscheidung": "verwerfen"})
    assert out["befund"]["entscheidung"]["status"] == "verworfen"
    assert out["lernsignal"]["art"] == "befund_verworfen" and out["lernsignal"]["bereich"] == "pruefverhalten"
    out = uf.text_aendern({"session_id": setup["sid"], "abschnitt_id": "empfehlung", "absatz_id": "a3",
                           "nachher": "[synthetisch] Ein SPF wird empfohlen.", "unsichere_bestaetigt": True})
    assert out["entwurf_version"] == 2 and out["lernsignal"]["vorher"] == "[synthetisch] Der SPF wird empfohlen."
    record = store.load(setup["sid"])
    assert len(record["lernsignale"]) == 2 and len(record["entwuerfe"]) == 2


def test_supervision_never_creates_signals(env):
    sid = uf.sitzung_anlegen({"bezeichnung": "Fall 12", "modus": "supervision"})["session"]["session_id"]
    record = store.load(sid)
    record["befunde"] = [{"befund_id": "bf-0000bbbb", "stelle": {"protokoll_phase": "abschluss"}, "problem": "x",
                          "schwere": "gering", "begruendung": "y", "pruefer": "goldfisch",
                          "entscheidung": {"status": "offen"}}]
    store.save(record)
    out = uf.befund_entscheiden({"session_id": sid, "befund_id": "bf-0000bbbb", "entscheidung": "annehmen"})
    assert out["lernsignal"] is None and "lernsignale" not in store.load(sid)


def test_emotional_social_type_cannot_export(setup):
    record = store.load(setup["sid"])
    record["gutachten_input"]["gutachtentyp"] = "emotional_soziale_entwicklung"
    store.save(record)
    with pytest.raises(EngineError) as e:
        uf.docx_exportieren({"session_id": setup["sid"], "ziel_pfad": str(setup["tmp"] / "c.docx")})
    assert e.value.code == "E_BLOCKIERT"
