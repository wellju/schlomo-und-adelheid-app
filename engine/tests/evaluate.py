"""Run the corpus through import, OCR, recognition and release; measure misses and false alarms.
Used by test_step_1_3.py and by the model comparison (python tests/evaluate.py <model> ...)."""
import difflib
import re
import sys
import time

from schlomo_engine import external, importer, ram, recognition
from schlomo_engine.ram import ImportedDoc

FUZZY = 0.85  # an OCR-garbled name still counts as a leak if it is this similar to the original


def load(doc) -> ImportedDoc:
    imp = importer.import_bytes(doc.path.read_bytes(), doc.path.suffix, "s-00000000", "d-00000000")
    for page, png in importer.render_pages_png(imp, imp.ocr_seiten):
        imp.parts.append(ram.Part("haupttext", external.ocr_png(png), page))
    imp.ocr_seiten = []
    return imp


def _leaks(value: str, released: str) -> bool:
    if value.casefold() in released.casefold():
        return True
    tokens = re.findall(r"[\wäöüÄÖÜß@.+/-]{4,}", released)
    for part in re.findall(r"[\wäöüÄÖÜß@.+/-]{4,}", value):
        if any(difflib.SequenceMatcher(None, part.casefold(), t.casefold()).ratio() >= FUZZY for t in tokens):
            return True
    return False


def evaluate(corpus, imported: dict, use_ner: bool = True) -> dict:
    """Psychologist accepts every proposal and every uncertain finding (worst case for false alarms, best for
    privacy). Misses: a direct identifier, date or hidden content of the ground truth still readable in the released
    text. The run skips release and re-check; false alarms are a lower bound."""
    misses, misses_weitere, false_alarms, uncertain, total = [], [], 0, 0, 0
    for doc in corpus:
        imp = imported[doc.name]
        names = [recognition.KnownName(n["text"], n["rolle"]) for n in doc.bekannte_namen]
        funde = recognition.detect_document(imp.parts, names, None, use_ner)
        for f in funde:
            f.status = "uebernommen" if f.status == "offen" else f.status
        released = recognition.anonymized_text(imp.parts, funde, imp.bilder)
        truth = doc.direkte + doc.daten + doc.orte + doc.seltene
        for f in funde:
            if f.kategorie == "versteckte_inhalte":
                continue
            total += 1
            uncertain += f.unsicher
            # A finding is a true hit if it covers a truth value or lies inside one; inside counts only from four
            # characters, so short fragments no longer pass as hits by accident (EGM E38).
            ft = f.text.casefold()
            if not any(v.casefold() in ft or (len(ft) >= 4 and ft in v.casefold()) for v in truth):
                false_alarms += 1
        for value in doc.direkte + doc.daten:
            if _leaks(value, released):
                misses.append((doc.name, doc.format, value))
        # places, institutions and rare features are measured too, reported apart (EGM E23)
        for value in doc.orte + doc.seltene:
            if value.casefold() in released.casefold():
                misses_weitere.append((doc.name, doc.format, value))
        for value in doc.versteckt:
            if _leaks(value, released):
                misses.append((doc.name, doc.format, "versteckt"))
    return {"misses": misses, "misses_weitere": misses_weitere, "false_alarms": false_alarms, "funde": total,
            "unsicher": uncertain}


if __name__ == "__main__":
    import os
    import tempfile
    from pathlib import Path
    import corpus as c

    os.environ["SCHLOMO_SELTENE_MERKMALE"] = str(Path(tempfile.mkdtemp()) / "seltene.json")
    Path(os.environ["SCHLOMO_SELTENE_MERKMALE"]).write_text(str(c.RARE_TERMS).replace("'", '"'), encoding="utf-8")
    docs = c.build(Path(tempfile.mkdtemp()) / "korpus")
    imported = {d.name: load(d) for d in docs}
    for model in sys.argv[1:]:
        use_ner = model != "ohne_ner"
        load_s = 0.0
        if use_ner:
            os.environ["SCHLOMO_SPACY_MODEL"] = model
            recognition.reset_nlp()
            t0 = time.perf_counter()
            recognition.nlp()
            load_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        r = evaluate(docs, imported, use_ner)
        print(f"{model}: laden={load_s:.1f}s erkennung_33_dok={time.perf_counter() - t0:.1f}s "
              f"verfehlt={len(r['misses'])} verfehlt_orte_merkmale={len(r['misses_weitere'])} fehlalarme={r['false_alarms']} funde={r['funde']} "
              f"unsicher={r['unsicher']} {r['misses'][:8]}")
