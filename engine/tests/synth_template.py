"""Synthetic DOCX template built like the real ones (spike point 5): unnamed header fields next to labels, bold
section titles in three ways (direct, paragraph style, character style), legacy FORMTEXT fields, a comment."""
import io
import zipfile
from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

LABELS = ["Name:", "Geburtsdatum:", "Klasse:", "Schule:", "Geschäftszahl:"]
SECTIONS = [("vorstellungsgrund", "Vorstellungsgrund", "direct"), ("anamnese", "Anamnese", "pstyle"),
            ("testbefunde", "Testbefunde", "rstyle"), ("leistungsproben", "Diagnostische Leistungsproben", "direct"),
            ("empfehlung", "Empfehlung", "direct")]


def _field(name: str = "") -> list:
    return [parse_xml(x) for x in (
        f'<w:r {nsdecls("w")}><w:fldChar w:fldCharType="begin"><w:ffData><w:name w:val="{name}"/><w:enabled/>'
        '<w:calcOnExit w:val="0"/><w:textInput/></w:ffData></w:fldChar></w:r>',
        f'<w:r {nsdecls("w")}><w:instrText xml:space="preserve"> FORMTEXT </w:instrText></w:r>',
        f'<w:r {nsdecls("w")}><w:fldChar w:fldCharType="separate"/></w:r>',
        f'<w:r {nsdecls("w")}><w:t>     </w:t></w:r>',
        f'<w:r {nsdecls("w")}><w:fldChar w:fldCharType="end"/></w:r>')]


def build(path: Path, skip_field_after: str | None = None, with_custom_xml: bool = True) -> None:
    doc = Document()
    doc.core_properties.author = "SYN-VORLAGENAUTOR"
    pstyle = doc.styles.add_style("Abschnittstitel", WD_STYLE_TYPE.PARAGRAPH)
    pstyle.font.bold = True
    rstyle = doc.styles.add_style("FettZeichen", WD_STYLE_TYPE.CHARACTER)
    rstyle.font.bold = True
    table = doc.add_table(rows=len(LABELS), cols=2)
    for row, label in zip(table.rows, LABELS):
        row.cells[0].paragraphs[0].add_run(label)
        for r in _field():
            row.cells[1].paragraphs[0]._p.append(r)
    doc.add_paragraph("Nicht fetter Hinweistext der Vorlage.")
    for i, (_, title, kind) in enumerate(SECTIONS, 1):
        if kind == "pstyle":
            doc.add_paragraph(title, style="Abschnittstitel")
        elif kind == "rstyle":
            doc.add_paragraph().add_run(title, style="FettZeichen")
        else:
            doc.add_paragraph().add_run(title).bold = True
        if title != skip_field_after:
            p = doc.add_paragraph()
            for r in _field(f"Text{i}"):
                p._p.append(r)
    first = doc.paragraphs[0]
    doc.add_comment(first.runs[0], text="SYN-VORLAGENKOMMENTAR", author="x")
    buf = io.BytesIO()
    doc.save(buf)
    if with_custom_xml:
        src = zipfile.ZipFile(io.BytesIO(buf.getvalue()))
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as z:
            for n in src.namelist():
                z.writestr(n, src.read(n))
            z.writestr("customXml/item99.xml", "<x>SYN-CUSTOM</x>")
        path.write_bytes(out.getvalue())
    else:
        path.write_bytes(buf.getvalue())


def vorlage(datei: str) -> dict:
    return {"schema_version": "1", "vorlage_id": "spf-syn", "version": "1", "gutachtentyp": "spf", "datei": datei,
            "abschnitte": [{"abschnitt_id": a, "ueberschrift": t} for a, t, _ in SECTIONS],
            "kopffelder": [{"platzhalter": "name_kind", "bezeichnung": "Name"},
                           {"platzhalter": "geschaeftszahl", "bezeichnung": "Geschäftszahl"}],
            "status": "entwurf"}
