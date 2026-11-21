"""Synthetic anonymisation corpus (Task 1, Tests): 33 documents, 33 sets of persons, 11 formats, 4 templates.
Every name, date, number and address is invented for this test (herkunft: synthetisch)."""
import random
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from schlomo_engine import external

RARE_TERMS = ["Tigrinya", "Dari", "Somali", "Paschtu", "Kurmandschi"]  # synthetic rare-features list for tests

# 33 first and 33 last names, invented combinations; every corpus document gets its own persons (EGM E06).
VORNAMEN = ["Lenja", "Timo", "Farid", "Zeynep", "Mila", "Jonas", "Amira", "Elias", "Nora", "David", "Lina", "Emre",
            "Sofia", "Luka", "Hana", "Noah", "Ilvy", "Matteo", "Selin", "Oskar", "Yara", "Benedikt", "Leyla", "Kian",
            "Romy", "Arian", "Talia", "Fynn", "Mira", "Samir", "Greta", "Ahmad", "Vida"]
NACHNAMEN = ["Quastberger", "Wendrich", "Nourizadeh", "Altunkaya", "Hrubesch", "Pfeilmoser", "Selmanovic",
             "Grubhofer", "Klepetar", "Ostermayr", "Brandauer", "Zehentmayr", "Pototschnig", "Kogelnik", "Ebenbauer",
             "Trummer", "Hasenöhrl", "Fleischhacker", "Kranawetter", "Schwaighofer", "Obermüller", "Haidinger",
             "Pernkopf", "Wallnöfer", "Leitgeb", "Mayerhofer", "Stadlbauer", "Rauchenwald", "Dornhackl", "Weißenbök",
             "Lechleitner", "Zwettler", "Gruberbauer"]
LAENDER = ["Afghanistan", "Syrien", "Eritrea", "Serbien", "Somalia", "Tschetschenien", "Bosnien", "Irak", "Iran",
           "Rumänien", "Polen"]
BEZIRKE = ["Favoriten", "Simmering", "Meidling", "Ottakring", "Floridsdorf", "Donaustadt", "Brigittenau", "Liesing",
           "Hernals", "Penzing", "Leopoldstadt"]
MONATE = ["März", "April", "Mai", "Juni", "Oktober", "November"]
# 11 formats, each three times; hidden content in DOCX and XLSX (EGM E22)
FORMATE = ["docx", "xlsx", "pdf_text", "pdf_scan", "jpg", "png", "heic", "doc", "xls", "docx_versteckt",
           "xlsx_versteckt"]


@dataclass
class CorpusDoc:
    name: str
    path: Path
    format: str
    bekannte_namen: list[dict]
    direkte: list[str] = field(default_factory=list)
    daten: list[str] = field(default_factory=list)
    orte: list[str] = field(default_factory=list)
    seltene: list[str] = field(default_factory=list)
    versteckt: list[str] = field(default_factory=list)
    text: str = ""


def _person(rnd, used: set) -> tuple[str, str]:
    while True:
        pair = (rnd.choice(VORNAMEN), rnd.choice(NACHNAMEN))
        if pair not in used:
            used.add(pair)
            return pair


def _case(i: int) -> tuple[str, dict]:
    """Text and values of document i. Template, date forms and phone format vary independently of the format."""
    rnd = random.Random(i)
    vor, nach = VORNAMEN[i], NACHNAMEN[(i * 7) % 33]
    if i % 6 == 0:
        nach = f"{nach}-{NACHNAMEN[(i * 7 + 5) % 33]}"  # double surname
    used = {(vor, nach)}
    m_vor = _person(rnd, used)[0]
    lehrer, therapeutin = " ".join(_person(rnd, used)), " ".join(_person(rnd, used))
    tag, monat, jahr = rnd.randint(1, 28), rnd.randint(1, 12), rnd.choice([2016, 2017, 2018])
    ein_jahr = rnd.choice([2021, 2022, 2023])
    v = {
        "kind": f"{vor} {nach}", "kind_vor": vor, "mutter": f"{m_vor} {nach.split('-')[0]}", "lehrer": lehrer,
        "therapeutin": therapeutin,
        "geburt": [f"{tag:02d}.{monat:02d}.{jahr}", f"{tag}. {MONATE[monat % 6]} {jahr}", f"{jahr}-{monat:02d}-{tag:02d}",
                   f"{tag:02d}/{monat:02d}/{jahr}"][i % 4],
        "test": f"{rnd.randint(1, 28)}.{rnd.randint(1, 12)}.2026",
        "kopfdatum": [f"{rnd.randint(1, 28)}. {rnd.choice(MONATE)} 2026", f"2026-0{rnd.randint(1, 9)}-1{rnd.randint(0, 9)}",
                      f"{rnd.randint(10, 28)}.0{rnd.randint(1, 9)}.2026"][i % 3],
        "einreise": [f"{rnd.choice(MONATE)} {ein_jahr}", f"0{rnd.randint(1, 9)}/{ein_jahr}", f"{ein_jahr}"][(i // 4) % 3],
        "tag_ohne_jahr": f"{rnd.randint(1, 28)}. {rnd.choice(MONATE)}",
        "schuljahr": f"{ein_jahr}/{(ein_jahr + 1) % 100:02d}",
        "land": LAENDER[i % 11], "sprache": RARE_TERMS[i % 5], "bezirk": BEZIRKE[(i * 3) % 11],
        "geschw": f"{rnd.choice(['Bruder', 'Schwester', 'Halbbruder'])} ({rnd.randint(9, 15)})",
        "adresse": f"{rnd.choice(['Quellen', 'Linden', 'Hasen', 'Mühl'])}{rnd.choice(['straße', 'gasse', 'weg'])} "
                   f"{rnd.randint(2, 180)}/{rnd.randint(1, 20)}",
        "plz_ort": f"1{rnd.randint(10, 23)}0 Wien",
        "telefon": [f"0664 {rnd.randint(100, 999)} {rnd.randint(1000, 9999)}",
                    f"+43 1 {rnd.randint(100, 999)} {rnd.randint(10, 99)} {rnd.randint(10, 99)}",
                    f"+49 30 {rnd.randint(1000000, 9999999)}",
                    f"+381 11 {rnd.randint(100, 999)} {rnd.randint(1000, 9999)}"][i % 4],
        "email": f"{m_vor.lower()}.{vor.lower()}@beispielpost.at",
        "aktenzahl": f"GZ {rnd.randint(1000, 9999)}/2026-{rnd.randint(1, 9)}",
        "svnr": f"{rnd.randint(1000, 9999)} {tag:02d}{monat:02d}{jahr % 100}",
        "vorlage": (i + i // 11) % 4,
    }
    text = (_anamnese, _lehrerbericht, _vorbefund, _kurzbrief)[v["vorlage"]](v)
    return text, v


def _anamnese(v):
    return (f"Wien, am {v['kopfdatum']}\n"
            f"Vorstellungsgrund: {v['kind']} (geb. {v['geburt']}) wurde am {v['test']} vorgestellt.\n"
            f"Die Mutter, Frau {v['mutter']}, berichtet, dass die Familie im {v['einreise']} aus {v['land']} "
            f"eingereist ist.\n"
            f"Erstsprache ist {v['sprache']}. {v['kind_vor']} besucht die Volksschule {v['bezirk']}, "
            f"Klassenlehrer ist Herr {v['lehrer']}.\n"
            f"Ein {v['geschw']} lebt im Haushalt.\n"
            f"Kontakt: {v['adresse']}, {v['plz_ort']}, Telefon {v['telefon']}, E-Mail {v['email']}.\n"
            f"Vorbefund von Frau Mag. {v['therapeutin']}, {v['aktenzahl']}, SV-Nr. {v['svnr']}.")


def _lehrerbericht(v):
    return (f"Datum: {v['kopfdatum']}\n"
            f"Bericht der Klassenlehrkraft Herr {v['lehrer']} über {v['kind']}, geboren am {v['geburt']}.\n"
            f"{v['kind_vor']}s Leistungen im Schuljahr {v['schuljahr']} sind schwankend. Seit {v['einreise']} in "
            f"Österreich, zuvor in {v['land']}.\n"
            f"Zu Hause wird {v['sprache']} gesprochen; ein {v['geschw']} besucht dieselbe Schule in {v['plz_ort']}.\n"
            f"Elterngespräch am {v['tag_ohne_jahr']} mit Frau {v['mutter']} ({v['telefon']}).\n"
            f"Wohnadresse laut Schülerstammblatt: {v['adresse']}. {v['aktenzahl']}.\n"
            f"Rückmeldung bitte an {v['email']}. Testung am {v['test']}. SV-Nr. {v['svnr']}.")


def _vorbefund(v):
    return (f"Befund vom {v['kopfdatum']}\n"
            f"Patient: {v['kind']}, Geburtsdatum {v['geburt']}, SV-Nr. {v['svnr']}, {v['aktenzahl']}.\n"
            f"Untersuchung durch Dr. {v['therapeutin']} am {v['test']}. Begleitet von der Mutter {v['mutter']}.\n"
            f"Anamnese: Einreise {v['einreise']} aus {v['land']}, Muttersprache {v['sprache']}, {v['geschw']}.\n"
            f"Schule: Volksschule {v['bezirk']}, Lehrer Herr {v['lehrer']}. Wohnhaft {v['adresse']}, {v['plz_ort']}.\n"
            f"Kontrolltermin am {v['tag_ohne_jahr']}. Erreichbar unter {v['telefon']} oder {v['email']}.")


def _kurzbrief(v):
    return (f"{v['plz_ort']}, {v['kopfdatum']}\n"
            f"Sehr geehrte Frau {v['mutter']},\n"
            f"wir bestätigen den Termin für {v['kind_vor']} am {v['test']} (Nachtermin {v['tag_ohne_jahr']}).\n"
            f"Bitte bringen Sie den Vorbefund von Frau Mag. {v['therapeutin']} ({v['aktenzahl']}) mit. "
            f"Geburtsdatum {v['geburt']}, SV-Nr. {v['svnr']}.\n"
            f"Das Kind {v['kind']} besucht seit dem Schuljahr {v['schuljahr']} die Volksschule {v['bezirk']}; "
            f"Klassenlehrer ist Herr {v['lehrer']}. Familiensprache {v['sprache']}, Herkunft {v['land']}, "
            f"Einreise {v['einreise']}, {v['geschw']}.\n"
            f"Adresse: {v['adresse']}. Rückfragen: {v['telefon']}, {v['email']}.")


def _image(text: str) -> Image.Image:
    lines = [w for line in text.splitlines() for w in textwrap.wrap(line, 70)]
    try:
        font = ImageFont.truetype("arial.ttf", 34)  # system font with umlauts and sharp s, like real letters
    except OSError:
        font = ImageFont.load_default(size=34)
    im = Image.new("RGB", (1800, 70 + 52 * len(lines)), "white")
    draw = ImageDraw.Draw(im)
    for n, line in enumerate(lines):
        draw.text((40, 35 + 52 * n), line, fill="black", font=font)
    return im


def _docx(text: str, path: Path, hidden: str | None = None, head_in_header: bool = False) -> None:
    from docx import Document
    from docx.oxml import OxmlElement
    doc = Document()
    lines = text.splitlines()
    if head_in_header:  # "Datum im Kopf": the first line sits in the page header
        doc.sections[0].header.paragraphs[0].text = lines.pop(0)
    for line in lines:
        p = doc.add_paragraph(line)
    if hidden:
        doc.add_comment(p.runs[0], text=hidden, author="x")
        run = doc.add_paragraph().add_run(f"Interne Notiz: {hidden}")
        run._r.get_or_add_rPr().append(OxmlElement("w:vanish"))
        doc.core_properties.author = hidden
    doc.save(path)


def _xlsx(text: str, path: Path, hidden: str | None = None) -> None:
    from openpyxl import Workbook
    wb = Workbook()
    for n, line in enumerate(text.splitlines(), 1):
        wb.active.cell(row=n, column=1, value=line)
    if hidden:
        wb.active.cell(row=1, column=4, value=hidden)
        wb.active.column_dimensions.group("C", "E", hidden=True)  # range C..E, the value sits in D
        ws = wb.create_sheet("Notizen")
        ws["A1"] = hidden
        ws.sheet_state = "hidden"
    wb.save(path)


def build(folder: Path) -> list[CorpusDoc]:
    import pillow_heif
    pillow_heif.register_heif_opener()
    folder.mkdir(parents=True, exist_ok=True)
    docs = []
    for i in range(33):
        text, v = _case(i)
        fmt = FORMATE[i % len(FORMATE)]
        name = f"k{i:02d}"
        hidden = f"Rückfrage bei {v['therapeutin']}" if fmt.endswith("_versteckt") else None
        if fmt in ("docx", "docx_versteckt"):
            path = folder / f"{name}.docx"
            _docx(text, path, hidden=hidden, head_in_header=i % 2 == 0)
        elif fmt in ("xlsx", "xlsx_versteckt"):
            path = folder / f"{name}.xlsx"
            _xlsx(text, path, hidden=hidden)
        elif fmt in ("doc", "xls", "pdf_text"):
            src = folder / f"{name}_src.{'xlsx' if fmt == 'xls' else 'docx'}"
            (_xlsx if fmt == "xls" else _docx)(text, src)
            target = "pdf" if fmt == "pdf_text" else fmt
            path = folder / f"{name}.{target}"
            path.write_bytes(external.libreoffice_convert(src.read_bytes(), src.suffix[1:], target))
            src.unlink()
        elif fmt == "pdf_scan":
            path = folder / f"{name}.pdf"
            _image(text).save(path, "PDF", resolution=150)
        else:
            path = folder / f"{name}.{fmt}"
            im = _image(text)
            (im.save(path, quality=95) if fmt == "heic" else im.save(path))
        nach = v["kind"].split(" ", 1)[1]
        schule = f"Volksschule {v['bezirk']}"
        docs.append(CorpusDoc(
            name=name, path=path, format=fmt, text=text,
            bekannte_namen=[{"text": v["kind"], "rolle": "das Kind"}, {"text": v["mutter"], "rolle": "die Mutter"}],
            direkte=[v["kind"], v["kind_vor"], *nach.split("-"), v["mutter"], v["lehrer"], v["therapeutin"],
                     v["adresse"], v["telefon"], v["email"], v["aktenzahl"], v["svnr"]],
            daten=[v[k] for k in ("geburt", "test", "kopfdatum", "einreise", "tag_ohne_jahr", "schuljahr") if v[k] in text],
            orte=[v["plz_ort"], v["land"], *([schule] if schule in text else [])],
            seltene=[v["sprache"], v["geschw"]],
            versteckt=[hidden] if hidden else [],
        ))
    return docs
