"""Synthetic test files for every import format. All values are invented markers (SYN-...), never real data."""
import io
import zipfile
from pathlib import Path

import pikepdf
from PIL import Image, ImageDraw, ImageFont

OCR_WORD = "Kolibri"


def text_image(text: str = f"Synthetischer Testtext {OCR_WORD}") -> Image.Image:
    im = Image.new("RGB", (1400, 200), "white")
    ImageDraw.Draw(im).text((40, 60), text, fill="black", font=ImageFont.load_default(size=64))
    return im


def make_docx(path: Path) -> None:
    from docx import Document
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls

    doc = Document()
    doc.core_properties.author = "SYN-AUTOR"
    doc.sections[0].header.paragraphs[0].text = "SYN-KOPFZEILE"
    p = doc.add_paragraph("SYN-HAUPTTEXT sichtbar. ")
    hidden = p.add_run("SYN-VERBORGEN")
    hidden.font.hidden = True
    p._p.append(parse_xml(f'<w:del {nsdecls("w")} w:id="1" w:author="x" w:date="2026-01-01T00:00:00Z">'
                          '<w:r><w:delText>SYN-GELOESCHT</w:delText></w:r></w:del>'))
    doc.add_comment(p.runs[0], text="SYN-KOMMENTAR", author="x")
    buf = io.BytesIO()
    text_image("Bild").save(buf, "PNG")
    buf.seek(0)
    doc.add_picture(buf)
    doc.save(path)


def make_xlsx(path: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.comments import Comment

    wb = Workbook()
    ws = wb.active
    ws["A1"] = "SYN-ZELLE-SICHTBAR"
    ws["A2"] = "SYN-ZEILE-VERBORGEN"
    ws.row_dimensions[2].hidden = True
    ws["B1"].value = "x"
    ws["B1"].comment = Comment("SYN-ZELLKOMMENTAR", "x")
    hidden = wb.create_sheet("Versteckt")
    hidden["A1"] = "SYN-BLATT-VERBORGEN"
    hidden.sheet_state = "hidden"
    wb.properties.creator = "SYN-AUTOR"
    wb.save(path)


def make_pdf_text(path: Path) -> None:
    """Page 1 normal text with annotation, page 2 invisible text only (old OCR layer)."""
    pdf = pikepdf.new()
    font = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1,
                                                BaseFont=pikepdf.Name.Helvetica))
    for content in (b"BT /F1 12 Tf 72 720 Td (SYN-PDF-HAUPTTEXT mit genug Zeichen fuer eine Textseite) Tj ET",
                    b"BT 3 Tr /F1 12 Tf 72 720 Td (SYN-OCR-SCHICHT unsichtbar und nicht vertrauenswuerdig) Tj ET"):
        page = pikepdf.Dictionary(Type=pikepdf.Name.Page, MediaBox=[0, 0, 595, 842],
                                  Resources=pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font)),
                                  Contents=pdf.make_stream(content))
        pdf.pages.append(pikepdf.Page(page))
    pdf.pages[0].obj.Annots = pdf.make_indirect(pikepdf.Array([pikepdf.Dictionary(
        Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Text, Rect=[0, 0, 10, 10],
        Contents=pikepdf.String("SYN-ANMERKUNG"))]))
    pdf.docinfo["/Author"] = "SYN-AUTOR"
    pdf.save(path)


def make_pdf_scan(path: Path) -> None:
    text_image().save(path, "PDF", resolution=150)


def make_images(folder: Path) -> dict[str, Path]:
    import pillow_heif
    pillow_heif.register_heif_opener()
    im = text_image()
    exif = Image.Exif()
    exif[0x013B] = "SYN-FOTOGRAF"  # Artist
    paths = {"jpg": folder / "bild.jpg", "png": folder / "bild.png", "heic": folder / "bild.heic"}
    im.save(paths["jpg"], "JPEG", exif=exif)
    im.save(paths["png"], "PNG")
    im.save(paths["heic"], quality=95)
    return paths


def make_pptx(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("ppt/presentation.xml", "<p/>")


def make_ole_with_macro(path: Path) -> None:
    path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100 + "_VBA_PROJECT".encode("utf-16-le"))
