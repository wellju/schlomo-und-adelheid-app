"""Step 1.2: import of all formats, hidden content, originals unchanged, OCR, RAM only. Synthetic data only."""
import hashlib
import json

import pytest

import synth_files as sf
from conftest import read_json_line, run_ui
from schlomo_engine import external, ram, store, ui_functions as uf
from schlomo_engine.errors import EngineError

HAS_TESSERACT = external.find("tesseract", "SCHLOMO_TESSERACT") is not None
HAS_SOFFICE = external.find("soffice", "SCHLOMO_SOFFICE") is not None


@pytest.fixture
def session(env):
    ram.clear()
    return uf.sitzung_anlegen({"bezeichnung": "Fall 9", "modus": "gutachten", "gutachtentyp": "spf"})["session"]


def _import(session, path, rolle="Bericht der Klassenlehrerin"):
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result = uf.dokument_importieren({"session_id": session["session_id"], "pfad": str(path), "quelle_rolle": rolle})
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before, "original changed"
    return result, ram.get(session["session_id"], result["dok_id"])


def _arts(doc):
    return {p.art: p.text for p in doc.parts}


def _all_text(doc):
    return " ".join(p.text for p in doc.parts)


def test_docx_hidden_content(session, tmp_path):
    sf.make_docx(tmp_path / "a.docx")
    result, doc = _import(session, tmp_path / "a.docx")
    assert result["format"] == "docx" and not result["ocr_noetig"]
    arts = _arts(doc)
    assert "SYN-HAUPTTEXT" in arts["haupttext"] and "SYN-VERBORGEN" not in arts["haupttext"]
    assert "SYN-VERBORGEN" in arts["verborgen"]
    assert "SYN-GELOESCHT" in arts["aenderung"]
    assert "SYN-KOMMENTAR" in arts["kommentar"]
    assert "SYN-KOPFZEILE" in arts["kopf_fusszeile"]
    assert "SYN-AUTOR" in arts["metadaten"]
    assert doc.bilder == 1 and doc.versteckte_inhalte >= 4


def test_xlsx_hidden_content(session, tmp_path):
    sf.make_xlsx(tmp_path / "a.xlsx")
    result, doc = _import(session, tmp_path / "a.xlsx")
    assert result["format"] == "xlsx" and result["seiten"] == 2
    arts = _arts(doc)
    assert "SYN-ZELLE-SICHTBAR" in arts["haupttext"] and "SYN-ZEILE-VERBORGEN" not in arts["haupttext"]
    assert "SYN-ZEILE-VERBORGEN" in arts["verborgen"]
    assert "SYN-BLATT-VERBORGEN" in arts["blatt_verborgen"]
    assert "SYN-ZELLKOMMENTAR" in arts["zellkommentar"]
    assert "SYN-AUTOR" in arts["metadaten"]


def test_pdf_text_and_untrusted_ocr_layer(session, tmp_path):
    sf.make_pdf_text(tmp_path / "a.pdf")
    result, doc = _import(session, tmp_path / "a.pdf")
    assert result["format"] == "pdf_scan" and result["seiten"] == 2 and doc.ocr_seiten == [2]
    arts = _arts(doc)
    assert "SYN-PDF-HAUPTTEXT" in arts["haupttext"]
    assert "SYN-OCR-SCHICHT" in arts["ocr_schicht"] and "SYN-OCR-SCHICHT" not in arts["haupttext"]
    assert "SYN-ANMERKUNG" in arts["anmerkung"] and "SYN-AUTOR" in arts["metadaten"]


@pytest.mark.parametrize("fmt", ["jpg", "png", "heic"])
def test_images_need_ocr_and_keep_metadata(session, tmp_path, fmt):
    path = sf.make_images(tmp_path)[fmt]
    result, doc = _import(session, path)
    assert result["format"] == fmt and result["ocr_noetig"]
    if fmt == "jpg":
        assert "SYN-FOTOGRAF" in _arts(doc)["metadaten"]


@pytest.mark.skipif(not HAS_TESSERACT, reason="Tesseract not installed")
@pytest.mark.parametrize("kind", ["pdf_scan", "png", "heic"])
def test_ocr(session, tmp_path, kind):
    if kind == "pdf_scan":
        path = tmp_path / "scan.pdf"
        sf.make_pdf_scan(path)
    else:
        path = sf.make_images(tmp_path)[kind]
    result, doc = _import(session, path)
    assert result["ocr_noetig"]
    events = []

    class Ctx:
        def emit(self, e):
            events.append(e)
    out = uf.ocr_ausfuehren({"session_id": session["session_id"], "dok_id": result["dok_id"]}, Ctx())
    assert out["seiten_erkannt"] == 1 and events[-1]["anteil"] == 1.0
    assert sf.OCR_WORD.lower() in _arts(doc)["haupttext"].lower()
    assert doc.ocr_seiten == []


@pytest.mark.skipif(not HAS_SOFFICE, reason="LibreOffice not installed")
@pytest.mark.parametrize("src,old", [("docx", "doc"), ("xlsx", "xls")])
def test_doc_and_xls_via_libreoffice(session, tmp_path, src, old):
    modern = tmp_path / f"a.{src}"
    (sf.make_docx if src == "docx" else sf.make_xlsx)(modern)
    legacy = tmp_path / f"a.{old}"
    legacy.write_bytes(external.libreoffice_convert(modern.read_bytes(), src, old))
    result, doc = _import(session, legacy)
    assert result["format"] == old
    assert ("SYN-HAUPTTEXT" if old == "doc" else "SYN-ZELLE-SICHTBAR") in _all_text(doc)


@pytest.mark.parametrize("maker,name,code", [
    (sf.make_pptx, "a.pptx", "E_DATEITYP"),
    (sf.make_ole_with_macro, "a.doc", "E_MAKRO"),
    (lambda p: p.write_bytes(b"irgendwas"), "a.txt", "E_DATEITYP"),
])
def test_rejected_files(session, tmp_path, maker, name, code):
    maker(tmp_path / name)
    with pytest.raises(EngineError) as e:
        uf.dokument_importieren({"session_id": session["session_id"], "pfad": str(tmp_path / name),
                                 "quelle_rolle": "Bericht"})
    assert e.value.code == code
    assert store.load(session["session_id"])["session"]["dokumente"] == []


def test_store_holds_counts_only_and_ram_cleared_on_beenden(env, tmp_path):
    sf.make_docx(tmp_path / "a.docx")
    answers, stderr = run_ui(env, [
        {"id": "r-1", "fn": "sitzung_anlegen", "args": {"bezeichnung": "Fall 3", "modus": "supervision"}},
    ])
    sid = answers[0]["result"]["session"]["session_id"]
    answers, stderr = run_ui(env, [
        {"id": "r-2", "fn": "dokument_importieren", "args": {"session_id": sid, "pfad": str(tmp_path / "a.docx"),
                                                             "quelle_rolle": "Bericht"}},
        {"id": "r-3", "fn": "beenden"},
    ])
    assert answers[0]["ok"], answers[0]
    stored = (env["data"] / f"{sid}.json").read_text(encoding="utf-8")
    assert "SYN-" not in stored and str(tmp_path) not in stored.replace("\\\\", "\\")
    entry = json.loads(stored)["session"]["dokumente"][0]
    assert entry["freigabe"]["status"] == "offen" and entry["freigabe"]["funde_je_kategorie"]["bilder"] == 1
    assert "SYN-" not in stderr and "a.docx" not in stderr


def test_ocr_progress_events_before_answer(env, tmp_path):
    if not HAS_TESSERACT:
        pytest.skip("Tesseract not installed")
    path = sf.make_images(tmp_path)["png"]
    answers, _ = run_ui(env, [{"id": "r-1", "fn": "sitzung_anlegen",
                               "args": {"bezeichnung": "Fall 4", "modus": "supervision"}}])
    sid = answers[0]["result"]["session"]["session_id"]
    answers, _ = run_ui(env, [
        {"id": "r-2", "fn": "dokument_importieren", "args": {"session_id": sid, "pfad": str(path), "quelle_rolle": "Foto"}},
    ])
    dok_id = answers[0]["result"]["dok_id"]
    # RAM does not survive the process: a new engine process must not know the document any more.
    answers, _ = run_ui(env, [{"id": "r-3", "fn": "ocr_ausfuehren", "args": {"session_id": sid, "dok_id": dok_id}}])
    assert answers[0]["fehler"]["code"] == "E_NICHT_GEFUNDEN"
    import subprocess
    import sys
    proc = subprocess.Popen([sys.executable, "-m", "schlomo_engine", "ui"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env["env"], cwd=env["work"])
    try:
        def send(m):
            proc.stdin.write((json.dumps(m) + "\n").encode("utf-8"))
            proc.stdin.flush()
        send({"id": "r-4", "fn": "dokument_importieren",
              "args": {"session_id": sid, "pfad": str(path), "quelle_rolle": "Foto"}})
        dok_id = read_json_line(proc)["result"]["dok_id"]
        send({"id": "r-5", "fn": "ocr_ausfuehren", "args": {"session_id": sid, "dok_id": dok_id}})
        lines = []
        while not lines or "ok" not in lines[-1]:
            lines.append(read_json_line(proc))
        send({"id": "r-6", "fn": "beenden"})
    finally:
        proc.wait(timeout=60)
    assert lines[0] == {"event": "fortschritt", "schritt": "ocr", "anteil": 1.0, "id": "r-5"}
    assert lines[-1]["ok"] and lines[-1]["result"] == {"seiten_erkannt": 1}
