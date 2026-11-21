"""DOCX templates as found in the spike (docs/spike-ergebnis.md, Punkt 5): legacy text form fields (FORMTEXT), bold
section titles without heading styles, unnamed header fields next to a label. Matching rule: docs/ui-api.md."""
import copy
import io
import posixpath
import re
import zipfile

from lxml import etree

from .errors import EngineError

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
# Never written to an export, even if the template contains them (ADR 0001, Engine-Bausteine).
FORBIDDEN = (re.compile(r"^word/comments.*\.xml$"), re.compile(r"^word/people\.xml$"), re.compile(r"^customXml/"),
             re.compile(r"^word/vbaProject\.bin$"), re.compile(r"^word/vbaData\.xml$"),
             re.compile(r"^docProps/custom\.xml$"), re.compile(r"^word/_rels/settings\.xml\.rels$"),
             re.compile(r"^docProps/thumbnail\.\w+$"))  # a thumbnail may show a page of an earlier report
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def norm(s: str) -> str:
    """Runs of whitespace and colons become one space, edges stripped, case ignored (docs/ui-api.md)."""
    return re.sub(r"[\s:]+", " ", s).strip().casefold()


def _on(el) -> bool:
    return el is not None and el.get(f"{W}val", "true").lower() not in ("0", "false", "off")


class _Styles:
    def __init__(self, xml: bytes | None):
        self.by_id = {}
        if xml:
            for s in etree.fromstring(xml).iter(f"{W}style"):
                self.by_id[s.get(f"{W}styleId")] = s

    def bold(self, style_id: str | None, seen=None) -> bool | None:
        seen = seen or set()
        style = self.by_id.get(style_id)
        if style is None or style_id in seen:
            return None
        b = style.find(f"{W}rPr/{W}b")
        if b is not None:
            return _on(b)
        based = style.find(f"{W}basedOn")
        return self.bold(based.get(f"{W}val"), seen | {style_id}) if based is not None else None


def _text(p) -> str:
    return "".join(t.text or "" for t in p.iter(f"{W}t"))


def _has_field(p) -> bool:
    return any("FORMTEXT" in (i.text or "") for i in p.iter(f"{W}instrText"))


def _is_title(p, styles: _Styles) -> bool:
    """Bold paragraph with text and without a form field. Bold may come from the run, the run style or the
    paragraph style chain."""
    if not _text(p).strip() or _has_field(p):
        return False
    p_style = p.find(f"{W}pPr/{W}pStyle")
    p_bold = styles.bold(p_style.get(f"{W}val")) if p_style is not None else None
    for r in p.iter(f"{W}r"):
        if not "".join(t.text or "" for t in r.iter(f"{W}t")).strip():
            continue
        b = r.find(f"{W}rPr/{W}b")
        r_style = r.find(f"{W}rPr/{W}rStyle")
        bold = _on(b) if b is not None else (styles.bold(r_style.get(f"{W}val")) if r_style is not None else None)
        if not (bold if bold is not None else bool(p_bold)):
            return False
    return True


def _load(raw: bytes):
    """Broken or foreign files raise E_DATEITYP, never KeyError or a parser error (EGM E58)."""
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        names = z.namelist()
        if "word/document.xml" not in names:
            raise EngineError("E_DATEITYP", "format")
        styles = _Styles(z.read("word/styles.xml") if "word/styles.xml" in names else None)
        return z, names, etree.fromstring(z.read("word/document.xml")), styles
    except (zipfile.BadZipFile, etree.XMLSyntaxError, KeyError):
        raise EngineError("E_DATEITYP", "beschaedigt") from None


def _body_paragraphs(doc):
    """Top-level paragraphs of the body in order (tables are handled as header separately)."""
    return [el for el in doc.find(f"{W}body") if el.tag == f"{W}p"]


def _header_labels(doc) -> list[str]:
    labels = []
    for row in doc.iter(f"{W}tr"):
        cells = row.findall(f"{W}tc")
        if any(_has_field(p) for c in cells for p in c.iter(f"{W}p")):
            labels += [_text(c).strip() for c in cells
                       if _text(c).strip() and not any(_has_field(p) for p in c.iter(f"{W}p"))]
    return labels


def analyze(raw: bytes) -> dict:
    """Structure only: title candidates, header labels, number of fields, allowed parts. No content is filled in."""
    z, names, doc, styles = _load(raw)
    return {
        "titel": [_text(p).strip() for p in _body_paragraphs(doc) if _is_title(p, styles)],
        "kopf_beschriftungen": _header_labels(doc),
        "felder": sum(1 for i in doc.iter(f"{W}instrText") if "FORMTEXT" in (i.text or "")),
        "teile": [n for n in names if not any(f.match(n) for f in FORBIDDEN)],
    }


def check_mapping(raw: bytes, vorlage: dict) -> None:
    """Every section title and header label of the metadata must be found in the template, else block."""
    info = analyze(raw)
    titles = {norm(t) for t in info["titel"]}
    if any(norm(a["ueberschrift"]) not in titles for a in vorlage["abschnitte"]):
        raise EngineError("E_ABSCHNITT_FEHLT")
    labels = {norm(t) for t in info["kopf_beschriftungen"]}
    if any(norm(k["bezeichnung"]) not in labels for k in vorlage["kopffelder"]):
        raise EngineError("E_KOPFFELD_FEHLT")


def _set_field_result(p, text: str) -> None:
    runs = list(p.iter(f"{W}r"))
    kinds = [r.find(f"{W}fldChar").get(f"{W}fldCharType") if r.find(f"{W}fldChar") is not None else None for r in runs]
    if "separate" not in kinds or "end" not in kinds[kinds.index("separate"):]:
        raise EngineError("E_DATEITYP", "beschaedigt")  # FORMTEXT without result part
    sep = kinds.index("separate")
    end = kinds.index("end", sep)
    text = _CONTROL.sub("", text)  # XML 1.0 cannot carry control characters
    old = runs[sep + 1:end]
    new = copy.deepcopy(old[0]) if old else etree.SubElement(etree.Element(f"{W}tmp"), f"{W}r")
    for r in old:
        r.getparent().remove(r)
    for child in list(new):
        if child.tag != f"{W}rPr":
            new.remove(child)
    for i, line in enumerate(text.split("\n")):
        if i:
            etree.SubElement(new, f"{W}br")
        t = etree.SubElement(new, f"{W}t")
        t.set(XML_SPACE, "preserve")
        t.text = line
    runs[sep].addnext(new)


def _table(rows: list[list[str]]):
    tbl = etree.Element(f"{W}tbl")
    props = etree.SubElement(tbl, f"{W}tblPr")
    borders = etree.SubElement(props, f"{W}tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        etree.SubElement(borders, f"{W}{side}", {f"{W}val": "single", f"{W}sz": "4"})
    for n, row in enumerate(rows):
        tr = etree.SubElement(tbl, f"{W}tr")
        for value in row:
            tc = etree.SubElement(tr, f"{W}tc")
            p = etree.SubElement(tc, f"{W}p")
            r = etree.SubElement(p, f"{W}r")
            if n == 0:
                etree.SubElement(etree.SubElement(r, f"{W}rPr"), f"{W}b")
            t = etree.SubElement(r, f"{W}t")
            t.text = value
    return tbl


def fill(raw: bytes, vorlage: dict, sections: dict[str, str], tables: dict[str, list[list[list[str]]]]) -> bytes:
    """Write section texts into the field result after each title; optional tables after that paragraph. The field
    must lie after its title and before the next title. Header fields stay placeholders. Only allowed parts are
    written; metadata is neutral."""
    z, names, doc, styles = _load(raw)
    check_mapping(raw, vorlage)
    paragraphs = _body_paragraphs(doc)
    title_idx = [i for i, p in enumerate(paragraphs) if _is_title(p, styles)]
    mapped = {a["abschnitt_id"] for a in vorlage["abschnitte"]}
    if not ({*sections, *tables} <= mapped) or not (mapped <= {*sections, *tables}):
        raise EngineError("E_ABSCHNITT_FEHLT")  # nothing of the draft may vanish, no template section stays empty
    for a in vorlage["abschnitte"]:
        start = next(i for i in title_idx if norm(_text(paragraphs[i])) == norm(a["ueberschrift"]))
        stop = next((i for i in title_idx if i > start), len(paragraphs))
        target = next((paragraphs[i] for i in range(start + 1, stop) if _has_field(paragraphs[i])), None)
        if target is None:
            raise EngineError("E_ABSCHNITT_FEHLT")
        _set_field_result(target, sections.get(a["abschnitt_id"], ""))
        anchor = target
        for rows in tables.get(a["abschnitt_id"], []):
            tbl = _table(rows)
            anchor.addnext(tbl)
            spacer = etree.Element(f"{W}p")
            tbl.addnext(spacer)
            anchor = spacer
    _accept_revisions(doc)
    allowed = analyze(raw)["teile"]
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target_zip:
        for name in allowed:
            data = z.read(name)
            if name == "word/document.xml":
                data = etree.tostring(doc, xml_declaration=True, encoding="UTF-8", standalone=True)
            elif name == "docProps/core.xml":
                data = _neutral_core(data)
            elif name == "docProps/app.xml":
                data = _blank(data, ("Company", "Manager", "Template", "HyperlinkBase"))
            elif name == "word/settings.xml":
                data = _drop_elements(data, ("trackRevisions", "attachedTemplate", "rsids"))
            elif name.endswith(".rels"):
                data = _drop_rels(data, allowed, name)
            elif name == "[Content_Types].xml":
                types = etree.fromstring(data)
                for o in list(types):
                    if o.get("PartName") and o.get("PartName").lstrip("/") not in allowed:
                        types.remove(o)
                data = etree.tostring(types, xml_declaration=True, encoding="UTF-8", standalone=True)
            target_zip.writestr(name, data)
    return out.getvalue()


def _neutral_core(data: bytes) -> bytes:
    core = etree.fromstring(data)
    for el in core:
        if etree.QName(el).localname in ("creator", "lastModifiedBy", "title", "subject", "description", "keywords",
                                         "category", "lastPrinted"):
            el.text = ""
    return etree.tostring(core, xml_declaration=True, encoding="UTF-8", standalone=True)


def _drop_rels(data: bytes, allowed: list[str], rels_name: str) -> bytes:
    """Remove relationships to parts that are not exported; targets resolve against the folder of the source part."""
    base = posixpath.dirname(posixpath.dirname(rels_name))  # word/_rels/document.xml.rels -> word
    rels = etree.fromstring(data)
    for rel in list(rels):
        target = rel.get("Target", "")
        if rel.get("TargetMode") == "External":
            if not rel.get("Type", "").endswith("/hyperlink"):  # templates, frames, OLE links: user paths (E50)
                rels.remove(rel)
            continue
        part = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(base, target))
        if part not in allowed:
            rels.remove(rel)
    return etree.tostring(rels, xml_declaration=True, encoding="UTF-8", standalone=True)


def _accept_revisions(doc) -> None:
    """Tracked insertions are accepted (content kept), deletions, change records and comment marks removed."""
    for el in list(doc.iter(f"{W}ins", f"{W}moveTo")):
        parent, i = el.getparent(), el.getparent().index(el)
        for child in reversed(list(el)):
            parent.insert(i, child)
        parent.remove(el)
    for tag in ("del", "moveFrom", "rPrChange", "pPrChange", "sectPrChange", "tblPrChange", "trPrChange",
                "tcPrChange", "numberingChange", "commentRangeStart", "commentRangeEnd", "commentReference"):
        for el in list(doc.iter(f"{W}{tag}")):
            el.getparent().remove(el)


def _blank(data: bytes, names: tuple[str, ...]) -> bytes:
    root = etree.fromstring(data)
    for el in root:
        if etree.QName(el).localname in names:
            el.text = ""
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _drop_elements(data: bytes, names: tuple[str, ...]) -> bytes:
    root = etree.fromstring(data)
    for el in list(root):
        if etree.QName(el).localname in names:
            root.remove(el)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
