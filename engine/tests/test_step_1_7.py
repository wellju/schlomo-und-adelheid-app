"""Step 1.7: fixes after the EGM gate of Task 1 (docs/reviews/egm-task-1.md). One test or more per finding ID.
Synthetic data only."""
import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

import corpus as c
import synth_files as sf
import synth_template as st
from conftest import SRC, read_json_line
from schlomo_engine import (belege, config, docx_template, external, importer, mcp_server as m, packages, ram,
                            recognition, rules, store, ui_functions as uf)
from schlomo_engine.contracts import validate
from schlomo_engine.errors import EngineError
from test_step_1_4 import GI, SYN
from test_step_1_5 import setup  # noqa: F401  (fixture)
from test_step_1_6 import INTERN, STILPROFIL, _paket, _rueckgabe, full  # noqa: F401  (fixture)

NAME = "Synthia Quastberger"


def _codes(fn, *args, **kwargs) -> str:
    with pytest.raises(EngineError) as e:
        fn(*args, **kwargs)
    return e.value.code


def _texts(funde) -> set[str]:
    return {f.text for f in funde}


# ---------------------------------------------------------------- recognition (E03, E04, E11, E12, E26, E46)

@pytest.mark.parametrize("text,expected", [
    ("am 12. März kam er", "12. März"),
    ("seit 03/2021 in Wien", "03/2021"),
    ("geboren 12/03/2015", "12/03/2015"),
    ("Stichtag 2015/03/12", "2015/03/12"),
    ("im Schuljahr 2022/23", "2022/23"),
    ("2019 eingereist", "2019"),
    ("am 12.\n03.2015 vorgestellt", "12.\n03.2015"),
])
def test_date_forms(text, expected):
    funde = recognition.detect_text(text, 0, [], None, use_ner=False)
    assert any(f.kategorie == "datumsangaben" and expected in f.text for f in funde), [f.text for f in funde]


def test_year_alone_is_uncertain():
    (f,) = recognition.detect_text("2019 eingereist", 0, [], None, use_ner=False)
    assert f.unsicher and f.ersatz == "[Jahr]"


@pytest.mark.parametrize("number", ["+49 30 1234567", "+381 11 123 4567", "0090 212 555 1234", "+43 1 234 56 78",
                                    "0664 123 4567"])
def test_phone_numbers_any_country(number):
    funde = recognition.detect_text(f"erreichbar unter {number}.", 0, [], None, use_ner=False)
    assert any(f.ersatz == "[Telefonnummer]" and f.text.strip() == number for f in funde), [f.text for f in funde]


@pytest.mark.parametrize("text", ["Synthia Quastberger-Wendrich", "Quastberger", "Wendrich", "S. Quastberger-Wendrich",
                                  "Quastberger-Wendrich, Synthia", "S.Q.", "synthia", "Synthias Heft",
                                  "Quastbergers Mutter"])
def test_name_variants(text):
    names = [recognition.KnownName("Synthia Quastberger-Wendrich", "das Kind")]
    funde = recognition.detect_text(f"[synthetisch] {text} war da.", 0, names, None, use_ner=False)
    assert any(f.quelle == "liste" for f in funde), (text, [f.text for f in funde])


def test_umlaut_transliteration():
    names = [recognition.KnownName("Jonas Müller", "der Vater")]
    for text in ("Herr Mueller kam", "Jonas MÜLLER", "Muellers Auto"):
        assert any(f.quelle == "liste" for f in recognition.detect_text(text, 0, names, None, use_ner=False)), text


def test_particles_are_no_names():
    names = [recognition.KnownName("Lena van der Berg", "das Kind")]
    funde = recognition.detect_text("Der Bericht der Schule nennt Berg.", 0, names, None, use_ner=False)
    assert _texts(funde) == {"Berg."} or _texts(funde) == {"Berg"}


def test_title_rule_catches_unlisted_person_and_yields_to_known_name():
    names = [recognition.KnownName("Petra Quastberger", "die Mutter")]
    funde = recognition.detect_text("Frau Petra Quastberger und Frau Mag. Ilse Quastberger", 0, names, None,
                                    use_ner=False)
    assert [(f.text, f.ersatz) for f in funde] == [("Petra Quastberger", "[die Mutter]"),
                                                   ("Frau Mag. Ilse Quastberger", "[Person]")]


def test_overlap_priority_rule_list_ner():
    """E46: a rule hit wins over a list hit inside it, the list hit is kept as inner hit; NER never displaces."""
    names = [recognition.KnownName("Lenja Quastberger", "das Kind")]
    (f,) = recognition.detect_text("Mail: lenja.quastberger@beispielpost.at", 0, names, None, use_ner=False)
    assert f.quelle == "regel" and f.ersatz == "[E-Mail]"
    funde = recognition.detect_text("Lenja Quastberger kam.", 0, names, None, use_ner=True)
    assert [f.quelle for f in funde if "Lenja" in f.text] == ["liste"]


def test_threshold_and_ner_certainty():
    """E46: NER hits carry 0.6 and stay open; list and certain rule hits are proposals."""
    doc = [ram.Part("haupttext", "[synthetisch] Gestern traf Bertram Holzinger den Hausmeister am 3.4.2026.")]
    funde = recognition.detect_document(doc, [], None)
    ner = [f for f in funde if f.quelle == "ner"]
    assert ner and all(f.sicherheit == recognition.NER_SICHERHEIT and f.status == "offen" for f in ner)
    assert all(f.status == "vorgeschlagen" for f in funde if f.sicherheit >= recognition.SCHWELLE)


def test_threshold_configurable(env):
    probe = "import schlomo_engine.recognition as r; print(r.SCHWELLE)"
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, env=env["env"] | {"SCHLOMO_SCHWELLE": "0.9"},
                         timeout=60)
    assert out.stdout.decode().strip() == "0.9"
    bad = subprocess.run([sys.executable, "-c", probe], capture_output=True, env=env["env"] | {"SCHLOMO_SCHWELLE": "1.5"},
                         timeout=60)
    assert bad.returncode != 0


# ---------------------------------------------------------------- free text typed in the app (E01, E02, E20)

def test_free_text_with_name_is_not_saved(setup):
    sid = setup["sid"]
    uf.bekannte_namen_setzen({"session_id": sid, "namen": [{"text": NAME, "rolle": "das Kind"}]})
    gi = copy.deepcopy(setup["gi"])
    gi["vorstellungsgrund"] = {"text": f"[synthetisch] {NAME} kam am 3.4.2026 in die Beratung."}
    out = uf.eingabe_speichern({"session_id": sid, "gutachten_input": gi, "unsichere_bestaetigt": True})
    # certain hits cannot be confirmed away
    assert out["gespeichert"] is False and {f["feld"] for f in out["funde"] if f["sicher"]} == {"/vorstellungsgrund/text"}
    assert NAME not in json.dumps(store.load(sid), ensure_ascii=False)


def test_uncertain_hit_needs_confirmation(setup):
    sid = setup["sid"]
    uf.bekannte_namen_setzen({"session_id": sid, "namen": []})
    gi = copy.deepcopy(setup["gi"])
    gi["vorstellungsgrund"] = {"text": "[synthetisch] Die Familie kam 2019 nach Wien."}
    out = uf.eingabe_speichern({"session_id": sid, "gutachten_input": gi})
    assert out["gespeichert"] is False and out["funde"] and not any(f["sicher"] for f in out["funde"])
    assert uf.eingabe_speichern({"session_id": sid, "gutachten_input": gi, "unsichere_bestaetigt": True})["gespeichert"]


def test_text_change_with_date_is_not_saved(setup):
    sid = setup["sid"]
    out = uf.text_aendern({"session_id": sid, "abschnitt_id": "empfehlung", "absatz_id": "a3",
                           "nachher": "[synthetisch] Gespräch am 3.4.2026.", "unsichere_bestaetigt": True})
    assert out["gespeichert"] is False and len(store.load(sid)["entwuerfe"]) == 1
    assert not store.load(sid).get("lernsignale")


def test_names_must_be_entered_again_after_restart(setup):
    sid = setup["sid"]
    ram.clear()  # what a restart does
    with pytest.raises(EngineError) as e:
        uf.eingabe_speichern({"session_id": sid, "gutachten_input": setup["gi"]})
    assert (e.value.code, e.value.reason) == ("E_BLOCKIERT", "namen_fehlen")
    with pytest.raises(EngineError) as e:
        uf.erzeuge_paket({"session_id": sid, "art": "gutachten"})
    assert (e.value.code, e.value.reason) == ("E_BLOCKIERT", "namen_fehlen")


@pytest.mark.parametrize("art", ["gutachten", "pruefung_elefant", "pruefung_goldfisch", "pruefung_stil",
                                 "diagnosevorschlag"])
def test_package_recheck_blocks_every_type(full, art):
    """E20: a name that got into the stored record anyway blocks every package type. E02: also behind a slash."""
    sid = full["sid"]
    uf.bekannte_namen_setzen({"session_id": sid, "namen": [{"text": NAME, "rolle": "das Kind"}]})
    record = store.load(sid)
    record["gutachten_input"]["vorstellungsgrund"]["text"] = f"/ siehe {NAME}"
    record["entwuerfe"][-1]["abschnitte"][0]["absaetze"][0]["saetze"][0]["text"] = f"[synthetisch] {NAME}."
    store.save(record)
    assert _codes(uf.erzeuge_paket, {"session_id": sid, "art": art}) == "E_ANONYMISIERUNG_OFFEN"
    assert not packages._open_packages(sid)


def test_stil_lernen_package_blocked_by_name_and_only_sample_reports(full):
    """E19, E49: only documents imported as Probegutachten go to /stil-lernen."""
    sid = full["sid"]
    record = store.load(sid)
    record["session"]["dokumente"] += [
        {"dok_id": "d-0000000b", "format": "docx", "quelle_rolle": "Bericht", "text_anonymisiert": "[synthetisch] Bericht",
         "freigabe": {"status": "freigegeben", "funde_je_kategorie": uf._funde_counts(ram.ImportedDoc("", "", "", b"", 1)),
                      "geprueft_bestaetigt": True}},
        {"dok_id": "d-0000000c", "format": "docx", "quelle_rolle": packages.PROBEGUTACHTEN,
         "text_anonymisiert": "[synthetisch] Probegutachten", "freigabe": {
             "status": "freigegeben", "funde_je_kategorie": uf._funde_counts(ram.ImportedDoc("", "", "", b"", 1)),
             "geprueft_bestaetigt": True}}]
    store.save(record)
    texts = [p["text"] for p in _paket(sid, "stil_lernen")["inhalt"]["probetexte"]]
    assert texts == ["[synthetisch] Probegutachten"]
    assert [p["text"] for p in m.hole_probetexte(sid)["probetexte"]] == texts


# ---------------------------------------------------------------- release (E08, E48)

def test_document_without_findings_can_be_released(env):
    ram.clear()
    sid = uf.sitzung_anlegen({"bezeichnung": "Fall 30", "modus": "supervision"})["session"]["session_id"]
    uf.bekannte_namen_setzen({"session_id": sid, "namen": []})
    doc = ram.ImportedDoc(sid, "d-0000000d", "docx", b"", 1, [ram.Part("haupttext", "[synthetisch] Nichts Besonderes.")])
    ram.put(doc)
    record = store.load(sid)
    record["session"]["dokumente"].append({"dok_id": doc.dok_id, "format": "docx", "quelle_rolle": "Bericht",
                                           "freigabe": {"status": "offen", "funde_je_kategorie": uf._funde_counts(doc)}})
    store.save(record)
    args = {"session_id": sid, "dok_id": doc.dok_id}
    assert _codes(uf.anonymisierung_freigeben, args | {"geprueft_bestaetigt": True}) == "E_ANONYMISIERUNG_OFFEN"
    state = uf.erkennung_ausfuehren(args)
    assert [f for f in state["funde"] if f["kategorie"] != "versteckte_inhalte"] == []
    assert "seltene_merkmale_ohne_liste" in state["hinweise"]  # E13
    assert uf.anonymisierung_freigeben(args | {"geprueft_bestaetigt": True})["freigabe"]["status"] == "freigegeben"


def test_rejected_text_is_exempt_only_at_its_position():
    """E08: the same text elsewhere, never decided, is not exempt."""
    parts = [ram.Part("haupttext", "Praxis Alpha; später Praxis Alpha;")]
    funde = recognition.detect_document(parts, [], None, use_ner=False)
    funde[0].status = "verworfen"
    text, kept = recognition.anonymize(parts, funde, 0)
    assert text == "Praxis Alpha; später [Einrichtung];" and kept == [(0, 12)]


# ---------------------------------------------------------------- store, labels (E09, E17, E47)

def test_concurrent_write_is_refused_and_mcp_retries(full, monkeypatch):
    sid = full["sid"]
    ui_view, mcp_view = store.load(sid), store.load(sid)
    ui_view["session"]["bezeichnung"] = "Fall 98"
    store.save(ui_view)
    mcp_view.setdefault("befunde", []).append(mcp_view["befunde"][0] | {"befund_id": "bf-0000bbbb"})
    with pytest.raises(EngineError) as e:  # never overwrites the newer state (lost update)
        store.save(mcp_view)
    assert (e.value.code, e.value.reason) == ("E_BLOCKIERT", "konflikt")
    real_load, calls = store.load, []

    def stale_once(session_id):  # first attempt works on a record that another process changes meanwhile
        record = real_load(session_id)
        if not calls:
            calls.append(1)
            other = real_load(session_id)
            other["session"]["bezeichnung"] = "Fall 99"
            store.save(other)
        return record
    monkeypatch.setattr(store, "load", stale_once)
    befund = {"stelle": {"abschnitt_id": "empfehlung"}, "problem": "x", "schwere": "gering", "begruendung": "y",
              "pruefer": "goldfisch"}
    assert m.speichere_befunde(sid, "goldfisch", [befund])["befunde"] == 1
    final = real_load(sid)
    assert final["session"]["bezeichnung"] == "Fall 99" and len(final["befunde"]) == 2


def test_labels(env):
    ram.clear()
    for label in ("Fall L.Q.", "Fall L. Q.", "Fall 2019"):
        assert _codes(uf.sitzung_anlegen, {"bezeichnung": label, "modus": "supervision"}) == "E_BEZEICHNUNG", label
    sid = uf.sitzung_anlegen({"bezeichnung": "Fall 32", "modus": "supervision"})["session"]["session_id"]
    record = store.load(sid)
    record["session"]["bezeichnung"] = "Fall Quastberger"  # a surname NER does not know as a person
    store.save(record)
    out = uf.bekannte_namen_setzen({"session_id": sid, "namen": [{"text": NAME, "rolle": "das Kind"}]})
    assert out["bezeichnung_enthaelt_namen"] is True
    assert _codes(uf.sitzung_umbenennen, {"session_id": sid, "bezeichnung": "Fall Quastberger"}) == "E_BEZEICHNUNG"
    assert uf.sitzung_umbenennen({"session_id": sid, "bezeichnung": "Fall 31"})["session"]["bezeichnung"] == "Fall 31"
    sf.make_docx(env["work"].parent / "a.docx")
    args = {"session_id": sid, "pfad": str(env["work"].parent / "a.docx")}
    assert _codes(uf.dokument_importieren, args | {"quelle_rolle": f"Bericht von {NAME}"}) == "E_BEZEICHNUNG"
    assert uf.dokument_importieren(args | {"quelle_rolle": "Foto"})["dok_id"]


# ---------------------------------------------------------------- rules per ID (E10, E30, E32, E33, E34, E51, E52)

def _by_id(result):
    out = {}
    for e in result["ergebnisse"]:
        out.setdefault(e["regel_id"], []).append(e)
    return out


def _cfg_with(tmp_path, change):
    folder = tmp_path / "konf"
    folder.mkdir()
    for f in SYN.glob("*.json"):
        (folder / f.name).write_bytes(f.read_bytes())
    regelwerk = json.loads((folder / "regelwerk.json").read_text(encoding="utf-8"))
    change(regelwerk)
    (folder / "regelwerk.json").write_text(json.dumps(regelwerk, ensure_ascii=False), encoding="utf-8")
    return config.load(folder), folder


LESETEST = {"testergebnis_id": "t3", "verfahren": "Synthetischer Lesetest", "testkatalog_id": "lesetest-a",
            "einzeltestung": True, "ki_niveau": 0.9, "werte": []}


@pytest.mark.parametrize("change,rule_id,expected", [
    (lambda g: g["testergebnisse"][0].update(normen_alter_jahre=8), "normen_alter", "erfuellt"),
    (lambda g: g["testergebnisse"][0].pop("normen_alter_jahre"), "normen_alter", "nicht_pruefbar"),
    (lambda g: g["testergebnisse"][0].update(gesamt_iq=75), "awmf_f", "nicht_pruefbar"),  # no band fits
    (lambda g: g["testergebnisse"].append(g["testergebnisse"][0] | {"testergebnis_id": "t2"}), "awmf_f",
     "nicht_pruefbar"),  # not exactly one IQ
    (lambda g: g["testergebnisse"].append(dict(LESETEST)), "konfidenz_95", "nicht_erfuellt"),  # E32: not only IQ
])
def test_rule_cases_per_id(change, rule_id, expected):
    gi = copy.deepcopy(GI)
    change(gi)
    assert expected in [e["ergebnis"] for e in _by_id(rules.pruefe_fachregeln(gi, config.load(SYN)))[rule_id]]


def test_awmf_d_and_e_failures(tmp_path):
    def change(r):
        for x in r["regeln"]:
            if x["regel_id"] == "awmf_d":
                x["parameter"]["innere_konsistenz_min"] = 0.99
            if x["regel_id"] == "awmf_e":
                x["parameter"]["iq_min_unter"] = 40
    cfg, _ = _cfg_with(tmp_path, change)
    r = _by_id(rules.pruefe_fachregeln(GI, cfg))
    assert r["awmf_d"][0]["ergebnis"] == "nicht_erfuellt"
    assert r["awmf_e"][0]["ergebnis"] == "nicht_erfuellt"  # E51: iq_min 40 is not below 40


def test_konfidenz_on_lrs():
    gi = copy.deepcopy(GI) | {"gutachtentyp": "lrs", "testergebnisse": [dict(LESETEST, ki_niveau=0.95)]}
    assert [e["ergebnis"] for e in _by_id(rules.pruefe_fachregeln(gi, config.load(SYN)))["konfidenz_95"]] == ["erfuellt"]


def test_regelwerk_cannot_lower_the_effect(tmp_path):
    """E33: Nachtrag 1 fixes the effect per ID; a 'wirkung' in the regelwerk is ignored for those IDs."""
    cfg, _ = _cfg_with(tmp_path, lambda r: [x.update(wirkung="hinweis") for x in r["regeln"]])
    r = _by_id(rules.pruefe_fachregeln(GI, cfg))
    assert {e["wirkung"] for rid in ("q1", "d1", "spf_s1", "spf_s2", "spf_s3") for e in r[rid]} == {"blockiert_export"}
    assert r["awmf_a"][0]["wirkung"] == "blockiert_diagnose"


def test_q1_checks_codes_in_other_fields():
    """E52: without gutachten_diagnose, an ICD code elsewhere still needs Q1."""
    gi = copy.deepcopy(GI) | {"gutachtentyp": "lrs", "verfasserin": {"qualifikationen": ["schulpsychologin"]},
                              "empfehlung": {"text": "Verdacht auf F81.0", "spf_empfohlen": False}}
    (q1,) = _by_id(rules.pruefe_fachregeln(gi, config.load(SYN)))["q1"]
    assert q1["ergebnis"] == "nicht_erfuellt" and "/empfehlung/text" in q1["felder"]


def test_diagnosis_package_is_blind():
    """E10: Claude's proposal never sees the psychologist's own diagnosis."""
    gi = copy.deepcopy(GI) | {"gutachtentyp": "lrs", "gutachten_diagnose": {"text": "[synthetisch]", "icd10_code": "F81.0"}}
    record = {"session": {"session_id": GI["session_id"], "dokumente": []}, "gutachten_input": gi}
    inhalt = packages.inhalt(record, "diagnosevorschlag", config.load(SYN), {})
    assert "gutachten_diagnose" not in inhalt["gutachten_input"] and "F81.0" not in json.dumps(inhalt)


def test_export_blocked_when_export_rule_not_checkable(setup, tmp_path, monkeypatch):
    """E30: D1 without term list is nicht_pruefbar and stops the export."""
    def change(r):
        for x in r["regeln"]:
            if x["regel_id"] == "d1":
                x["parameter"].pop("begriffe")
    _, folder = _cfg_with(tmp_path, change)
    monkeypatch.setenv("SCHLOMO_KONFIGURATION", str(folder))
    target = tmp_path / "out.docx"
    assert _codes(uf.docx_exportieren, {"session_id": setup["sid"], "ziel_pfad": str(target)}) == "E_BLOCKIERT"
    assert not target.exists()


# ---------------------------------------------------------------- evidence and drafts (E31, E54, E55, E56)

def test_json_pointer_rfc6901():
    doc = {"a": [1, 2], "": "leer", "b/c": 3, "d~e": 4}
    assert belege.resolve(doc, "") == doc and belege.resolve(doc, "/") == "leer"
    assert belege.resolve(doc, "/b~1c") == 3 and belege.resolve(doc, "/d~0e") == 4 and belege.resolve(doc, "/a/1") == 2
    for bad in ("a", "/a/01", "/a/²", "/a/-", "//a", "/a/2"):
        with pytest.raises(KeyError):
            belege.resolve(doc, bad)


def test_vorlage_id_is_never_a_path(setup):
    with pytest.raises(EngineError) as e:
        validate("gutachten-output", copy.deepcopy(setup["draft"]) | {"vorlage_id": "../../x"})
    assert e.value.code == "E_SCHEMA"


def test_check_draft_reports_evidence_before_rule_deviation(setup):
    """E54: order as in ui-api.md."""
    draft = copy.deepcopy(setup["draft"])
    draft["regelergebnis"]["gesamt"] = "erfuellt" if draft["regelergebnis"]["gesamt"] != "erfuellt" else "nicht_erfuellt"
    draft["abschnitte"][0]["absaetze"][0]["saetze"][0]["text"] = "Seit 7 Jahren."
    assert _codes(packages.check_draft, draft, store.load(setup["sid"]), setup["cfg"]) == "E_BELEG"


def test_return_closes_package_before_saving(full, monkeypatch):
    """E55: a crash between the two writes never allows a second return of the same package."""
    sid = full["sid"]
    paket = _paket(sid, "pruefung_goldfisch")
    befund = {"befund_id": "bf-11111111", "stelle": {"abschnitt_id": "empfehlung"}, "problem": "x", "schwere": "gering",
              "begruendung": "y", "pruefer": "goldfisch", "entscheidung": {"status": "offen"}}
    text = json.dumps(_rueckgabe(paket["paket_id"], "befunde", [befund]))

    def crash(record):
        raise OSError("crash")
    real_save = store.save
    monkeypatch.setattr(store, "save", crash)
    with pytest.raises(OSError):
        uf.lies_rueckgabe({"session_id": sid, "text": text})
    monkeypatch.setattr(store, "save", real_save)  # not undo(): that would also drop the fixture's settings
    assert _codes(uf.lies_rueckgabe, {"session_id": sid, "text": text}) == "E_PAKET_FREMD"


def test_stilprofil_versions_natural_order(full):
    """E36: "10" is newer than "9"."""
    for v in ("syn-9", "syn-10"):
        (packages.stilprofile_dir() / f"{v}.json").write_text(json.dumps(STILPROFIL | {"version": v}), encoding="utf-8")
    assert packages.released_stilprofil()["version"] == "syn-10"


def test_mcp_output_is_validated(full, monkeypatch):
    """E35: a content that breaks fallpaket.schema.json never reaches Claude."""
    monkeypatch.setattr(packages, "inhalt", lambda *a: {"gutachten_input": {"kaputt": True}})
    with pytest.raises(ToolError) as e:
        m.hole_gutachten_input(full["sid"])
    assert str(e.value) == "E_SCHEMA"


# ---------------------------------------------------------------- DOCX templates and export (E27, E50, E58 to E61)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _template_with_traces(path: Path) -> None:
    """The synthetic template plus what a real template may carry: tracked insertion, revision tracking, attached
    template with a user path, company name, custom properties, thumbnail."""
    st.build(path)
    src = zipfile.ZipFile(io.BytesIO(path.read_bytes()))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name in src.namelist():
            data = src.read(name)
            if name == "word/document.xml":
                data = data.replace(b"</w:body>", f'<w:p><w:ins w:id="9" w:author="SYN-AUTOR"><w:r><w:t>SYN-EINGEFUEGT'
                                                  f'</w:t></w:r></w:ins></w:p></w:body>'.encode())
            elif name == "word/settings.xml":
                data = data.replace(b"</w:settings>", b'<w:trackRevisions/><w:attachedTemplate r:id="rIdT" '
                                    b'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
                                    b"</w:settings>")
            elif name == "docProps/app.xml":
                data = data.replace(b"</Properties>", b"<Company>SYN-FIRMA</Company></Properties>")
            z.writestr(name, data)
        z.writestr("word/_rels/settings.xml.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.'
                   'openxmlformats.org/package/2006/relationships"><Relationship Id="rIdT" Type="http://schemas.'
                   'openxmlformats.org/officeDocument/2006/relationships/attachedTemplate" '
                   'Target="file:///D:/Profile/SYN-USER/Vorlage.dotm" TargetMode="External"/></Relationships>')
        z.writestr("docProps/custom.xml", "<Properties><property name='SYN-CUSTOM'/></Properties>")
    path.write_bytes(out.getvalue())


def test_export_allowlist(setup, tmp_path):
    template = tmp_path / "Vorlage SPF 2.docx"
    _template_with_traces(template)
    datei = uf.vorlage_importieren({"pfad": str(template)})["datei"]
    uf.vorlage_zuordnen({"vorlage": st.vorlage(datei)})
    target = tmp_path / "export.docx"
    uf.docx_exportieren({"session_id": setup["sid"], "ziel_pfad": str(target)})
    z = zipfile.ZipFile(target)
    names = set(z.namelist())
    allowed = {"[Content_Types].xml", "_rels/.rels", "docProps/core.xml", "docProps/app.xml", "word/document.xml",
               "word/_rels/document.xml.rels", "word/styles.xml", "word/stylesWithEffects.xml", "word/settings.xml",
               "word/webSettings.xml", "word/fontTable.xml", "word/theme/theme1.xml", "word/numbering.xml"}
    assert names <= allowed, names - allowed
    everything = b"".join(z.read(n) for n in names)
    for trace in (b"SYN-USER", b"SYN-FIRMA", b"SYN-CUSTOM", b"SYN-AUTOR", b"SYN-VORLAGENAUTOR", b"trackRevisions",
                  b"attachedTemplate", b"<w:ins ", b"thumbnail"):
        assert trace not in everything, trace
    assert b"SYN-EINGEFUEGT" in z.read("word/document.xml")  # an accepted insertion keeps its text
    for rels in (n for n in names if n.endswith(".rels")):  # no dangling relationship
        base = rels.split("_rels/")[0]
        for target_ in __import__("re").findall(rb'Target="([^"]+)"', z.read(rels)):
            t = target_.decode()
            assert t.startswith("http") or t.lstrip("/") in names or \
                __import__("posixpath").normpath(base + t) in names, (rels, t)


def test_draft_section_without_template_slot_blocks(setup):
    record = store.load(setup["sid"])
    draft = copy.deepcopy(record["entwuerfe"][-1])
    draft["abschnitte"].append({"abschnitt_id": "schullaufbahn", "absaetze": [{"absatz_id": "z", "saetze": [
        {"text": "[synthetisch] verschwindet sonst.", "quellen": ["/empfehlung"]}]}]})
    record["entwuerfe"].append(draft | {"entwurf_version": 2})
    store.save(record)
    target = setup["tmp"] / "x.docx"
    assert _codes(uf.docx_exportieren, {"session_id": setup["sid"], "ziel_pfad": str(target)}) == "E_ABSCHNITT_FEHLT"
    assert not target.exists() and not list(setup["tmp"].glob(".x.docx.*"))  # E60: no half file, no temp left


def test_broken_templates_give_file_type_errors(tmp_path):
    (tmp_path / "kaputt.docx").write_bytes(b"PK\x03\x04 kaputt")
    assert _codes(uf.vorlage_importieren, {"pfad": str(tmp_path / "kaputt.docx")}) == "E_DATEITYP"
    good = tmp_path / "gut.docx"
    st.build(good)
    raw = good.read_bytes()
    with pytest.raises(EngineError) as e:  # FORMTEXT without its result part
        docx_template._set_field_result(
            __import__("lxml.etree", fromlist=["etree"]).fromstring(
                f'<w:p xmlns:w="{W}"><w:r><w:fldChar w:fldCharType="begin"/></w:r></w:p>'.encode()), "x")
    assert e.value.code == "E_DATEITYP"
    assert docx_template.analyze(raw)["felder"] > 0


def test_template_import_never_overwrites(env, tmp_path, monkeypatch):
    monkeypatch.setenv("SCHLOMO_VORLAGEN", str(tmp_path / "vorlagen"))
    template = tmp_path / "Vorlage.docx"
    st.build(template)
    datei = uf.vorlage_importieren({"pfad": str(template)})["datei"]
    assert _codes(uf.vorlage_importieren, {"pfad": str(template)}) == "E_BLOCKIERT"
    with pytest.raises(EngineError) as e:
        uf.vorlage_zuordnen({"vorlage": st.vorlage("D:" + datei)})
    assert e.value.code == "E_SCHEMA"


# ---------------------------------------------------------------- import: hidden content and errors (E14 to E16, E25)

def _docx_bytes(document_body: str, styles: str = "") -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", f'<w:document xmlns:w="{W}"><w:body>{document_body}</w:body></w:document>')
        if styles:
            z.writestr("word/styles.xml", f'<w:styles xmlns:w="{W}">{styles}</w:styles>')
    return out.getvalue()


def test_docx_hidden_by_style_and_spec_vanish():
    styles = ('<w:style w:styleId="Versteckt"><w:rPr><w:vanish/></w:rPr></w:style>'
              '<w:style w:styleId="Erbt"><w:basedOn w:val="Versteckt"/></w:style>'
              '<w:style w:styleId="Sichtbar"><w:basedOn w:val="Versteckt"/><w:rPr><w:vanish w:val="0"/></w:rPr></w:style>')
    body = ('<w:p><w:pPr><w:pStyle w:val="Erbt"/></w:pPr><w:r><w:t>SYN-ABSATZSTIL</w:t></w:r></w:p>'
            '<w:p><w:r><w:rPr><w:rStyle w:val="Versteckt"/></w:rPr><w:t>SYN-ZEICHENSTIL</w:t></w:r></w:p>'
            '<w:p><w:r><w:rPr><w:specVanish/></w:rPr><w:t>SYN-SPEC</w:t></w:r></w:p>'
            '<w:p><w:r><w:rPr><w:rStyle w:val="Sichtbar"/></w:rPr><w:t>SYN-SICHTBAR</w:t></w:r></w:p>')
    doc = importer.import_bytes(_docx_bytes(body, styles), ".docx", "s-00000000", "d-00000000")
    visible = " ".join(p.text for p in doc.parts if p.art in importer.VISIBLE)
    hidden = " ".join(p.text for p in doc.parts if p.art in importer.HIDDEN)
    assert visible == "SYN-SICHTBAR" and all(x in hidden for x in ("SYN-ABSATZSTIL", "SYN-ZEICHENSTIL", "SYN-SPEC"))


def test_docx_custom_xml_embedding_and_macro_part():
    out = io.BytesIO(_docx_bytes("<w:p><w:r><w:t>sichtbar</w:t></w:r></w:p>"))
    with zipfile.ZipFile(out, "a") as z:
        z.writestr("customXml/item1.xml", "<x>SYN-CUSTOM</x>")
        z.writestr("word/embeddings/oleObject1.bin", b"\x00")
        z.writestr("word/vbaProject.bin", b"\x00")
    arts = {p.art for p in importer.import_bytes(out.getvalue(), ".docx", "s-00000000", "d-00000000").parts}
    assert {"custom_xml", "eingebettet", "makro"} <= arts


def test_xlsx_hidden_column_range_defined_names_hidden_sheet(tmp_path):
    from openpyxl import Workbook
    from openpyxl.workbook.defined_name import DefinedName
    wb = Workbook()
    ws = wb.active
    ws["A1"], ws["D1"] = "sichtbar", "SYN-SPALTE-D"
    ws.column_dimensions.group("C", "E", hidden=True)
    wb.defined_names["SYN_NAME"] = DefinedName("SYN_NAME", attr_text="Sheet!$A$1")
    hidden_sheet = wb.create_sheet("Notiz")
    hidden_sheet["A1"] = "SYN-BLATT"
    hidden_sheet.sheet_state = "hidden"
    wb.save(tmp_path / "a.xlsx")
    doc = importer.import_bytes((tmp_path / "a.xlsx").read_bytes(), ".xlsx", "s-00000000", "d-00000000")
    by_art = {p.art: p.text for p in doc.parts}
    assert by_art["haupttext"] == "sichtbar" and "SYN-SPALTE-D" in by_art["verborgen"]
    assert "SYN-BLATT" in by_art["blatt_verborgen"] and "definierte_namen" in by_art


def _pdf(path: Path, content: bytes, extra=None) -> bytes:
    import pikepdf
    pdf = pikepdf.new()
    font = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1,
                                                BaseFont=pikepdf.Name.Helvetica))
    page = pdf.add_blank_page(page_size=(595, 842))
    page.obj.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))
    page.obj.Contents = pdf.make_stream(content)
    if extra:
        extra(pdf, page)
    pdf.save(path)
    return path.read_bytes()


VISIBLE_LINE = b"BT /F1 12 Tf 72 760 Td (SYN-SICHTBAR mit genug Zeichen fuer eine Textseite im Test) Tj ET "


@pytest.mark.parametrize("hidden", [
    b"BT 1 1 1 rg /F1 12 Tf 72 700 Td (SYN-WEISS) Tj ET",
    b"BT /F1 12 Tf 72 2000 Td (SYN-AUSSERHALB) Tj ET",
])
def test_pdf_unseen_text_is_hidden_and_page_goes_to_ocr(tmp_path, hidden):
    doc = importer.import_bytes(_pdf(tmp_path / "a.pdf", VISIBLE_LINE + hidden), ".pdf", "s-00000000", "d-00000000")
    assert doc.ocr_seiten == [1] and not any(p.art in importer.VISIBLE for p in doc.parts)


def test_pdf_hidden_layer_attachment_script_form(tmp_path):
    import pikepdf

    def extra(pdf, page):
        ocg = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.OCG, Name="SYN-EBENE"))
        pdf.Root.OCProperties = pikepdf.Dictionary(OCGs=[ocg], D=pikepdf.Dictionary(OFF=[ocg]))
        pdf.Root.Names = pikepdf.Dictionary(EmbeddedFiles=pikepdf.Dictionary(Names=[]),
                                            JavaScript=pikepdf.Dictionary(Names=[]))
        field = pdf.make_indirect(pikepdf.Dictionary(FT=pikepdf.Name.Tx, T="f", V="SYN-FORMULAR"))
        pdf.Root.AcroForm = pikepdf.Dictionary(Fields=[field])
    doc = importer.import_bytes(_pdf(tmp_path / "a.pdf", VISIBLE_LINE, extra), ".pdf", "s-00000000", "d-00000000")
    arts = {p.art for p in doc.parts}
    assert doc.ocr_seiten == [1] and {"anhang", "skript", "formularfeld"} <= arts


def test_import_error_codes(tmp_path, monkeypatch):
    """E25: codes named in the result document."""
    monkeypatch.setattr(importer, "MAX_BYTES", 10)
    assert _codes(importer.import_bytes, b"%PDF-1.4 zu gross", ".pdf", "s-00000000", "d-00000000") == "E_DATEITYP"
    monkeypatch.undo()
    sf.make_ole_with_macro(tmp_path / "a.xls")
    assert _codes(importer.import_bytes, (tmp_path / "a.xls").read_bytes(), ".xls", "s-00000000", "d-00000000") == "E_MAKRO"
    monkeypatch.setattr(external, "find", lambda *a: None)
    assert _codes(external.ocr_png, b"png") == "E_OCR_FEHLT"
    assert _codes(external.libreoffice_convert, b"x", "doc", "docx") == "E_LIBREOFFICE_FEHLT"


@pytest.mark.skipif(not external.find("soffice", "SCHLOMO_SOFFICE"), reason="LibreOffice needed")
def test_libreoffice_leaves_no_temp_folder(tmp_path):
    before = set(Path(tempfile.gettempdir()).glob("sua-*"))
    with pytest.raises(EngineError) as e:  # an OLE file that is no Word document
        external.libreoffice_convert(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 600, "doc", "docx")
    assert e.value.code == "E_INTERN"
    assert set(Path(tempfile.gettempdir()).glob("sua-*")) <= before


def test_stale_temp_folders_are_swept():
    old = Path(tempfile.mkdtemp(prefix="sua-"))
    (old / "in.doc").write_bytes(b"SYN-REST")
    os.utime(old, (time.time() - 3600, time.time() - 3600))
    fresh = Path(tempfile.mkdtemp(prefix="sua-"))
    external.cleanup_stale()
    assert not old.exists() and fresh.exists()
    fresh.rmdir()


# ---------------------------------------------------------------- privacy over the real channels (E07, E18, E21, E45)

def test_mcp_start_loads_no_import_or_recognition_module(env):
    probe = ("import sys, schlomo_engine.mcp_server as m; print(sorted(n for n in sys.modules if n.split('.')[0] in "
             "('spacy', 'pytesseract', 'pypdfium2', 'docx', 'pikepdf', 'PIL', 'openpyxl', 'pillow_heif') or n in "
             "('schlomo_engine.importer', 'schlomo_engine.recognition', 'schlomo_engine.external', "
             "'schlomo_engine.docx_template', 'schlomo_engine.ui_functions')))")
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, env=env["env"], cwd=env["work"], timeout=60)
    assert out.stdout.decode().strip() == "[]", out.stdout


class _Engine:
    """Interactive `engine ui` subprocess; stderr goes to a file so a full pipe never blocks."""

    def __init__(self, env, extra_env=None):
        self.log = tempfile.TemporaryFile()
        self.proc = subprocess.Popen([sys.executable, "-m", "schlomo_engine", "ui"], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=self.log, env=env["env"] | (extra_env or {}),
                                     cwd=env["work"])
        self.n = 0

    def __call__(self, fn, **args):
        self.n += 1
        self.proc.stdin.write((json.dumps({"id": f"r-{self.n}", "fn": fn, "args": args}, ensure_ascii=False) + "\n")
                              .encode("utf-8"))
        self.proc.stdin.flush()
        while True:
            msg = read_json_line(self.proc, timeout=300)
            if "ok" in msg:
                return msg

    def close(self) -> str:
        self("beenden")
        self.proc.wait(timeout=60)
        self.log.seek(0)
        return self.log.read().decode("utf-8")


@pytest.mark.skipif(not (external.find("tesseract", "SCHLOMO_TESSERACT") and external.find("soffice", "SCHLOMO_SOFFICE")),
                    reason="Tesseract and LibreOffice needed for the corpus run")
def test_log_of_full_corpus_run_holds_no_content(env, tmp_path):
    """E07, E18, E21: every function of the ui path with all 33 corpus documents; the log holds only allowed keys,
    no value of the ground truth, no file name, no path, no internal diagnosis, no ICD code."""
    rare = tmp_path / "seltene.json"
    rare.write_text(json.dumps(c.RARE_TERMS), encoding="utf-8")
    docs = c.build(tmp_path / "korpus")
    e = _Engine(env, {"SCHLOMO_KONFIGURATION": str(SYN), "SCHLOMO_SELTENE_MERKMALE": str(rare),
                      "SCHLOMO_VORLAGEN": str(tmp_path / "vorlagen")})
    sid = e("sitzung_anlegen", bezeichnung="Fall 40", modus="gutachten", gutachtentyp="spf")["result"]["session"]["session_id"]
    for d in docs:
        assert e("bekannte_namen_setzen", session_id=sid, namen=d.bekannte_namen)["ok"]
        dok = e("dokument_importieren", session_id=sid, pfad=str(d.path), quelle_rolle="Bericht")["result"]
        if dok["ocr_noetig"]:
            assert e("ocr_ausfuehren", session_id=sid, dok_id=dok["dok_id"])["ok"]
        state = e("erkennung_ausfuehren", session_id=sid, dok_id=dok["dok_id"])["result"]
        for f in state["funde"]:
            if f["status"] == "offen":
                e("schwaerzung_entscheiden", session_id=sid, dok_id=dok["dok_id"], fund_id=f["fund_id"],
                  entscheidung="uebernehmen")
        assert e("anonymisierung_freigeben", session_id=sid, dok_id=dok["dok_id"], geprueft_bestaetigt=True)["ok"]
    gi = copy.deepcopy(GI) | {"session_id": sid}
    assert e("eingabe_speichern", session_id=sid, gutachten_input=gi, unsichere_bestaetigt=True)["result"]["gespeichert"]
    assert e("fachregeln_pruefen", session_id=sid)["ok"]
    assert e("erzeuge_paket", session_id=sid, art="diagnosevorschlag")["ok"]
    assert e("interne_diagnose_speichern", session_id=sid, interne_diagnose={"text": INTERN, "icd10_code": "F70"},
             unsichere_bestaetigt=True)["result"]["gespeichert"]
    assert e("diagnosevergleich_laden", session_id=sid)["ok"]
    marker = tmp_path / "SYN-PFAD-4711" / f"{docs[0].kind_marker if hasattr(docs[0], 'kind_marker') else 'x'}.docx"
    errors = [e("dokument_importieren", session_id=sid, pfad=str(marker), quelle_rolle="Bericht"),
              e("lies_rueckgabe", session_id=sid, text=f"kaputt {INTERN} {docs[0].direkte[0]}"),
              e("sitzung_laden", session_id=f"s-{INTERN}")]
    assert all(not r["ok"] and set(r["fehler"]) <= {"code", "grund"} for r in errors)
    log = e.close()
    lines = [json.loads(line) for line in log.splitlines()]
    assert len(lines) > 100  # an empty log proves nothing
    allowed = {"t", "event", "count", "code", "session_id", "dok_id", "paket_id", "befund_id", "request_id", "dauer_ms"}
    assert all(set(line) <= allowed for line in lines)
    for d in docs:
        for value in d.direkte + d.daten + d.orte + d.seltene + d.versteckt:
            assert value not in log, value
        assert d.path.name not in log and d.path.stem not in log
    for forbidden in (INTERN, "F70", "SYN-PFAD", str(tmp_path), "korpus"):
        assert forbidden not in log, forbidden


def test_mcp_log_and_errors_hold_no_content(full):
    """E18, E21: MCP over the real protocol; stderr is read, not discarded; argument errors carry no input value."""
    sid = full["sid"]
    log = tempfile.TemporaryFile()
    proc = subprocess.Popen([sys.executable, "-m", "schlomo_engine", "mcp"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=log, env=dict(os.environ, PYTHONPATH=str(SRC)))
    try:
        def call(i, msg):
            proc.stdin.write((json.dumps(msg) + "\n").encode())
            proc.stdin.flush()
            while True:
                answer = read_json_line(proc, timeout=60)
                if answer.get("id") == i:
                    return answer
        call(1, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}})
        proc.stdin.write(b'{"jsonrpc": "2.0", "method": "notifications/initialized"}\n')
        outputs = [call(i, {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": n, "arguments": a}})
                   for i, (n, a) in enumerate([
                       ("hole_gutachten_input", {"session_id": sid}), ("pruefe_fachregeln", {"session_id": sid}),
                       ("hole_elefant_paket", {"session_id": sid}),
                       ("hole_entwurf", {"session_id": f"s-{INTERN}"}),
                       ("hole_entwurf", {"session_id": {"text": INTERN}}),
                       ("speichere_diagnosevorschlag", {"session_id": sid, "vorschlag": {"text": INTERN}})], 2)]
    finally:
        proc.kill()
        proc.wait()
    raw = json.dumps(outputs, ensure_ascii=False)
    assert "interne_diagnose" not in raw and "awmf_" not in raw
    for o in outputs[3:]:
        assert o["result"]["isError"] and INTERN not in json.dumps(o, ensure_ascii=False), o
    log.seek(0)
    text = log.read().decode("utf-8")
    assert text.strip() and INTERN not in text and "F70" not in text
