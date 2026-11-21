"""Import of PDF, DOCX, XLSX, JPG, PNG, HEIC; DOC and XLS via LibreOffice (projektrahmen.md, Harte Vorgaben 7).
Reads bytes only, never writes the original, never runs macros. Every text that could leak is captured as a Part,
hidden content separately, so recognition (step 1.3) sees all of it and only visible text can be released."""
import io
import re
import zipfile

from lxml import etree

from . import external
from .errors import EngineError
from .ram import ImportedDoc, Part

MAX_BYTES = 200 * 1024 * 1024
VISIBLE = {"haupttext", "kopf_fusszeile", "fussnote"}
HIDDEN = {"verborgen", "aenderung", "kommentar", "metadaten", "custom_xml", "eingebettet", "makro", "blatt_verborgen",
          "zellkommentar", "definierte_namen", "anmerkung", "anhang", "formularfeld", "skript", "ocr_schicht"}
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_VBA_OLE = "_VBA_PROJECT".encode("utf-16-le")
_MIN_TEXT_CHARS = 20  # a PDF page with less extractable text is treated as a scan


def detect_format(raw: bytes, ext: str) -> str:
    """Decide by content, not by file name; the extension only separates DOC from XLS inside OLE."""
    if raw.startswith(b"%PDF"):
        return "pdf"
    if raw.startswith(b"PK"):
        try:
            names = set(zipfile.ZipFile(io.BytesIO(raw)).namelist())
        except zipfile.BadZipFile:
            raise EngineError("E_DATEITYP", "beschaedigt")
        if "word/document.xml" in names:
            return "docx"
        if "xl/workbook.xml" in names:
            return "xlsx"
        raise EngineError("E_DATEITYP", "format")  # e.g. PPTX: not supported
    if raw.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if raw[4:8] == b"ftyp" and raw[8:12] in (b"heic", b"heix", b"mif1", b"msf1", b"heim", b"heis"):
        return "heic"
    if raw.startswith(_OLE) and ext in ("doc", "xls"):
        return ext
    raise EngineError("E_DATEITYP", "format")


def import_bytes(raw: bytes, ext: str, session_id: str, dok_id: str) -> ImportedDoc:
    if len(raw) > MAX_BYTES:
        raise EngineError("E_DATEITYP", "groesse")
    fmt = detect_format(raw, ext.lower().lstrip("."))
    if fmt in ("doc", "xls"):
        if _VBA_OLE in raw:
            raise EngineError("E_MAKRO")  # LibreOffice would have to open a macro document; refuse instead
        converted = external.libreoffice_convert(raw, fmt, fmt + "x")
        doc = _read_docx(converted) if fmt == "doc" else _read_xlsx(converted)
    else:
        doc = {"pdf": _read_pdf, "docx": _read_docx, "xlsx": _read_xlsx}.get(fmt, _read_image)(raw)
    seiten, parts, bilder, ocr_seiten = doc
    if fmt == "pdf":
        fmt = "pdf_scan" if ocr_seiten else "pdf_text"
    return ImportedDoc(session_id=session_id, dok_id=dok_id, format=fmt, raw=raw, seiten=seiten, parts=parts,
                       bilder=bilder, ocr_seiten=ocr_seiten)


# ---------------------------------------------------------------- DOCX

def _flag_on(rpr, tag: str) -> bool | None:
    el = rpr.find(f"{W}{tag}") if rpr is not None else None
    return None if el is None else el.get(f"{W}val", "true").lower() not in ("0", "false", "off")


def _hidden_styles(styles_xml: bytes | None) -> set[str]:
    """Style IDs whose run properties hide text (w:vanish, w:specVanish, w:webHidden), following w:basedOn (E14)."""
    if not styles_xml:
        return set()
    own, based = {}, {}
    for s in etree.fromstring(styles_xml).iter(f"{W}style"):
        sid = s.get(f"{W}styleId")
        rpr = s.find(f"{W}rPr")
        flags = [_flag_on(rpr, tag) for tag in _HIDE_TAGS]
        own[sid] = True if any(flags) else False if any(f is False for f in flags) else None
        if (b := s.find(f"{W}basedOn")) is not None:
            based[sid] = b.get(f"{W}val")

    def hidden(sid, depth=0):
        if sid is None or depth > 20:
            return False
        return own[sid] if own.get(sid) is not None else hidden(based.get(sid), depth + 1)
    return {sid for sid in own if hidden(sid)}


_HIDE_TAGS = ("vanish", "specVanish", "webHidden")


def _paragraph_parts(root, default_art: str, hidden_styles: set[str] = frozenset()) -> list[Part]:
    """Split paragraph text into visible text, hidden text (direct or by paragraph or character style) and deleted
    tracked changes (w:delText)."""
    parts: list[Part] = []
    for p in root.iter(f"{W}p"):
        buckets: dict[str, list[str]] = {}
        p_style = p.find(f"{W}pPr/{W}pStyle")
        p_hidden = p_style is not None and p_style.get(f"{W}val") in hidden_styles
        for node in p.iter(f"{W}t", f"{W}delText", f"{W}instrText"):
            if node.tag == f"{W}instrText":
                continue  # field codes are not content
            run = next((a for a in node.iterancestors(f"{W}r")), None)
            rpr = run.find(f"{W}rPr") if run is not None else None
            direct = [_flag_on(rpr, tag) for tag in _HIDE_TAGS]
            r_style = rpr.find(f"{W}rStyle") if rpr is not None else None
            by_style = p_hidden or (r_style is not None and r_style.get(f"{W}val") in hidden_styles)
            hidden = any(direct) or (by_style and not any(f is False for f in direct))
            art = "aenderung" if node.tag == f"{W}delText" else "verborgen" if hidden else default_art
            buckets.setdefault(art, []).append(node.text or "")
        parts += [Part(art, "".join(t)) for art, t in buckets.items() if "".join(t).strip()]
    return parts


def _xml_text(data: bytes) -> str:
    return " ".join(t.strip() for t in etree.fromstring(data).itertext() if t.strip())


def _read_docx(raw: bytes):
    z = zipfile.ZipFile(io.BytesIO(raw))
    names = z.namelist()
    hs = _hidden_styles(z.read("word/styles.xml") if "word/styles.xml" in names else None)
    parts = _paragraph_parts(etree.fromstring(z.read("word/document.xml")), "haupttext", hs)
    for name in sorted(names):
        if re.fullmatch(r"word/(header|footer)\d*\.xml", name):
            parts += _paragraph_parts(etree.fromstring(z.read(name)), "kopf_fusszeile", hs)
        elif name in ("word/footnotes.xml", "word/endnotes.xml"):
            parts += _paragraph_parts(etree.fromstring(z.read(name)), "fussnote", hs)
        elif name == "word/comments.xml":
            parts += [Part("kommentar", p.text) for p in _paragraph_parts(etree.fromstring(z.read(name)), "kommentar")]
        elif name.startswith("docProps/") and name.endswith(".xml") and (text := _xml_text(z.read(name))):
            parts.append(Part("metadaten", text))
        elif name.startswith("customXml/item") and name.endswith(".xml") and (text := _xml_text(z.read(name))):
            parts.append(Part("custom_xml", text))
        elif name.startswith("word/embeddings/"):
            parts.append(Part("eingebettet", ""))
        elif name.endswith("vbaProject.bin"):
            parts.append(Part("makro", ""))  # never loaded or executed, only recorded
    bilder = sum(1 for n in names if n.startswith("word/media/"))
    return 1, parts, bilder, []


# ---------------------------------------------------------------- XLSX

def _read_xlsx(raw: bytes):
    from openpyxl import load_workbook  # macros are never executed by openpyxl; keep_vba stays False

    wb = load_workbook(io.BytesIO(raw), data_only=True)
    parts: list[Part] = []
    bilder = 0
    for ws in wb.worksheets:
        sheet_hidden = ws.sheet_state != "visible"
        hidden_rows = {r for r, d in ws.row_dimensions.items() if d.hidden}
        # a dimension covers the column range min..max, not only its first letter (E14)
        hidden_cols = {c for d in ws.column_dimensions.values() if d.hidden and d.min
                       for c in range(d.min, (d.max or d.min) + 1)}
        visible, hidden = [], []
        for row in ws.iter_rows():
            for cell in row:
                if cell.comment is not None and cell.comment.text.strip():
                    parts.append(Part("zellkommentar", cell.comment.text))
                if cell.value is None:
                    continue
                target = hidden if (cell.row in hidden_rows or cell.column in hidden_cols) else visible
                target.append(str(cell.value))
        if visible:
            parts.append(Part("blatt_verborgen" if sheet_hidden else "haupttext", "\t".join(visible)))
        if hidden:
            parts.append(Part("blatt_verborgen" if sheet_hidden else "verborgen", "\t".join(hidden)))
        bilder += len(getattr(ws, "_images", []))
    if names := [str(dn.attr_text) for dn in wb.defined_names.values()]:
        parts.append(Part("definierte_namen", " ".join(names)))
    props = wb.properties
    meta = " ".join(str(v) for v in (props.creator, props.lastModifiedBy, props.title, props.subject,
                                     props.description, props.keywords) if v)
    if meta:
        parts.append(Part("metadaten", meta))
    return len(wb.worksheets), parts, bilder, []


# ---------------------------------------------------------------- PDF

def _read_pdf(raw: bytes):
    import pikepdf
    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c

    parts: list[Part] = []
    ocr_seiten: list[int] = []
    bilder = 0
    with pikepdf.open(io.BytesIO(raw)) as pk:
        # Optional content switched off by default (hidden layers): text extraction would still return it (E14).
        oc = pk.Root.get("/OCProperties")
        layers_off = bool(oc is not None and oc.get("/D") is not None and len(oc.D.get("/OFF", [])) > 0)
    pdf = pdfium.PdfDocument(raw)
    for i in range(len(pdf)):
        page = pdf[i]
        text = page.get_textpage().get_text_range()
        objs = list(page.get_objects())
        bilder += sum(1 for o in objs if o.type == pdfium_c.FPDF_PAGEOBJ_IMAGE)
        box = page.get_mediabox()
        invisible = layers_off or any(o.type == pdfium_c.FPDF_PAGEOBJ_TEXT and _text_unseen(o, box, pdfium_c)
                                      for o in objs)
        if invisible:
            # Text a reader does not see (render mode 3, white, outside the page, hidden layer) is never trusted
            # (ADR 0001): keep it as hidden content and OCR the rendered page instead.
            if text.strip():
                parts.append(Part("ocr_schicht", text, i + 1))
            ocr_seiten.append(i + 1)
        elif len(text.strip()) < _MIN_TEXT_CHARS:
            ocr_seiten.append(i + 1)
        else:
            parts.append(Part("haupttext", text, i + 1))
    seiten = len(pdf)
    pdf.close()

    with pikepdf.open(io.BytesIO(raw)) as pk:
        info = " ".join(str(v) for v in pk.docinfo.values()) if pk.docinfo else ""
        if info.strip():
            parts.append(Part("metadaten", info))
        for i, page in enumerate(pk.pages):
            for annot in page.obj.get("/Annots", []) or []:
                contents = annot.get("/Contents")
                if contents is not None and str(contents).strip():
                    parts.append(Part("anmerkung", str(contents), i + 1))
        root = pk.Root
        names = root.get("/Names")
        if names is not None and "/EmbeddedFiles" in names:
            parts.append(Part("anhang", ""))
        if (names is not None and "/JavaScript" in names) or "/OpenAction" in root:
            parts.append(Part("skript", ""))
        acro = root.get("/AcroForm")
        for field in (acro.get("/Fields", []) if acro is not None else []):
            value = field.get("/V")
            if value is not None and str(value).strip():
                parts.append(Part("formularfeld", str(value)))
    return seiten, parts, bilder, ocr_seiten


def _text_unseen(obj, box, pdfium_c) -> bool:
    import ctypes
    if pdfium_c.FPDFTextObj_GetTextRenderMode(obj.raw) == 3:
        return True
    r, g, b, a = (ctypes.c_uint() for _ in range(4))
    if pdfium_c.FPDFPageObj_GetFillColor(obj.raw, r, g, b, a) and (a.value == 0 or min(r.value, g.value, b.value) >= 250):
        return True  # white or fully transparent text
    left, bottom, right, top = obj.get_bounds()
    return right <= box[0] or left >= box[2] or top <= box[1] or bottom >= box[3]  # outside the page


# ---------------------------------------------------------------- images

def _read_image(raw: bytes):
    from PIL import ExifTags, Image
    import pillow_heif

    pillow_heif.register_heif_opener()
    with Image.open(io.BytesIO(raw)) as im:
        meta = [f"{ExifTags.TAGS.get(k, k)}={v}" for k, v in im.getexif().items()]
        meta += [f"{k}={v}" for k, v in im.info.items() if isinstance(v, str)]
    parts = [Part("metadaten", " ".join(meta))] if meta else []
    return 1, parts, 0, [1]


def render_pages_png(doc: ImportedDoc, pages: list[int]):
    """Yield (page, PNG bytes) at 300 dpi for OCR. Images are converted to PNG in memory."""
    from PIL import Image
    import pillow_heif

    if not pages:
        return
    if doc.format.startswith("pdf"):
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(doc.raw)
        try:
            for n in pages:
                buf = io.BytesIO()
                pdf[n - 1].render(scale=300 / 72).to_pil().save(buf, "PNG")
                yield n, buf.getvalue()
        finally:
            pdf.close()
    else:
        pillow_heif.register_heif_opener()
        with Image.open(io.BytesIO(doc.raw)) as im:
            buf = io.BytesIO()
            im.convert("RGB").save(buf, "PNG")
            yield 1, buf.getvalue()
