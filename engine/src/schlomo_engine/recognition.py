"""Recognition in three stages (docs/spike-ergebnis.md, Vorgaben für Task 1):
1. known names the psychologist enters (RAM only, inflected forms), 2. rules for dates, numbers, addresses,
places, institutions and rare features, 3. named-entity recognition as a safety net.
Findings below SCHWELLE count as "unsicher" and block the release until each one is decided."""
import json
import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .ids import new_id

# Start value: list and rule hits are reliable (>= 0.8); NER-only hits (0.6) always need a human decision, because a
# missed name is the worst failure and NER alone is too noisy to remove text silently.
# Configurable through SCHLOMO_SCHWELLE (prompts-v2.md, Task 1); values outside (0, 1] are rejected at start.
SCHWELLE = float(os.environ.get("SCHLOMO_SCHWELLE", "0.75"))
if not 0 < SCHWELLE <= 1:
    raise ValueError("SCHLOMO_SCHWELLE must lie in (0, 1]")
NER_SICHERHEIT = 0.6
VISIBLE_ARTS = ("haupttext", "kopf_fusszeile", "fussnote")
KATEGORIEN = ("direkte_identifikatoren", "datumsangaben", "orte_einrichtungen", "seltene_merkmale",
              "versteckte_inhalte", "bilder", "unsicher")

_MONATE = ("Jänner|Januar|Feber|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember")
_MONAT_NR = {m.lower(): i for i, ms in enumerate(
    [("jänner", "januar"), ("feber", "februar"), ("märz",), ("april",), ("mai",), ("juni",), ("juli",), ("august",),
     ("september",), ("oktober",), ("november",), ("dezember",)], 1) for m in ms}
_WIEN_BEZIRKE = ("Innere Stadt|Leopoldstadt|Landstraße|Wieden|Margareten|Mariahilf|Neubau|Josefstadt|Alsergrund|"
                 "Favoriten|Simmering|Meidling|Hietzing|Penzing|Rudolfsheim-Fünfhaus|Ottakring|Hernals|Währing|"
                 "Döbling|Brigittenau|Floridsdorf|Donaustadt|Liesing")
_TITEL = r"Mag\.a?|Dr\.in|Dr\.|Univ\.-Prof\.|Prof\.|Dipl\.-\w+\.?|DSA|OSR|Prim\."  # titles before a name
_EINRICHTUNG = (r"Volksschule|Mittelschule|Sonderschule|Kindergarten|Kindergruppe|Hort|Gymnasium|Schule|VS|MS|ASO|SPZ|"
                r"Ambulatorium|Kinderklinik|Klinik|Krankenhaus|Spital|Praxis|Beratungsstelle")

# (name, regex, kategorie, sicherheit, ersatz). Order matters only for readability; overlaps are resolved later.
RULES = [
    ("email", r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "direkte_identifikatoren", 0.99, "[E-Mail]"),
    ("iban", r"\bAT\d{2}(?:\s?\d{4}){4}\b", "direkte_identifikatoren", 0.99, "[Kontonummer]"),
    ("aktenzahl", r"\b(?:GZ|Gz|Zl|Zahl|Aktenzahl|Geschäftszahl|Akt)[.:]?\s*(?=[\w./-]*\d)[\w./-]+",
     "direkte_identifikatoren", 0.95, "[Aktenzahl]"),
    ("svnr", r"\b\d{4}\s*(?:0[1-9]|[12]\d|3[01])(?:0[1-9]|1[0-2])\d{2}\b", "direkte_identifikatoren", 0.9,
     "[SV-Nummer]"),
    ("datum_numerisch", r"\b\d{1,2}\.\s*\d{1,2}\.\s*(?:\d{4}|\d{2})\b", "datumsangaben", 0.95, None),
    ("datum_iso", r"\b\d{4}-\d{2}-\d{2}\b", "datumsangaben", 0.95, None),
    ("datum_text", rf"\b\d{{1,2}}\.\s*(?:{_MONATE})\s*\d{{4}}\b", "datumsangaben", 0.95, None),
    ("monat_jahr", rf"\b(?:{_MONATE})\s+\d{{4}}\b", "datumsangaben", 0.9, None),
    ("tag_monat", r"\b\d{1,2}\.\s?\d{1,2}\.(?!\s?\d)", "datumsangaben", 0.7, None),
    ("tag_monatsname", rf"\b\d{{1,2}}\.\s*(?:{_MONATE})\b", "datumsangaben", 0.9, None),
    ("datum_schraeg", r"\b\d{1,2}/\d{1,2}/(?:\d{4}|\d{2})\b|\b(?:19|20)\d{2}/\d{1,2}/\d{1,2}\b", "datumsangaben",
     0.95, None),
    ("monat_jahr_schraeg", r"\b(?:0?[1-9]|1[0-2])/(?:19|20)\d{2}\b", "datumsangaben", 0.9, None),
    ("schuljahr", r"\b(?:19|20)\d{2}/(?:(?:19|20)\d{2}|\d{2})\b", "datumsangaben", 0.9, "[Schuljahr]"),
    # A year alone may be a date ("2019 eingereist") or not (norm year); the psychologist decides.
    ("jahr", r"\b(?:19|20)\d{2}\b", "datumsangaben", 0.7, "[Jahr]"),
    ("telefon", r"(?<![\w.])(?:\+43|0043|0)[\s/-]?\d{1,4}(?:[\s/-]?\d{2,}){2,}", "direkte_identifikatoren", 0.9,
     "[Telefonnummer]"),
    ("telefon_ausland", r"(?<![\w.])(?:\+|00)[1-9]\d{0,2}[\s/-]?(?:\(0\)\s?)?\d{1,4}(?:[\s/-]?\d{2,})+",
     "direkte_identifikatoren", 0.9, "[Telefonnummer]"),
    ("adresse", r"\b[A-ZÄÖÜ][\wäöüß-]*(?:straße|strasse|gasse|weg|platz|allee|ring|zeile|kai|steig)\s+\d+[a-z]?"
                r"(?:/\d+)*", "direkte_identifikatoren", 0.95, "[Adresse]"),
    ("adresse_nummer", r"\b[A-ZÄÖÜ][\wäöüß-]{3,}\s+(?!(?:19|20)\d{2}/)\d{1,4}[a-z]?/\d{1,4}\b(?!/\d)", "direkte_identifikatoren", 0.85,
     "[Adresse]"),
    ("plz_ort", r"\b[1-9]\d{3}\s+[A-ZÄÖÜ][a-zäöüß]+", "orte_einrichtungen", 0.9, "[Ort]"),
    ("bezirk", rf"\b(?:{_WIEN_BEZIRKE})\b|\b\d{{1,2}}\.\s?Bezirk\b", "orte_einrichtungen", 0.85, "[Bezirk]"),
    ("einrichtung", rf"\b(?:{_EINRICHTUNG})\s+(?:[A-ZÄÖÜ0-9][\wäöüß.-]*)(?:\s[A-ZÄÖÜ][\wäöüß-]*)?",
     "orte_einrichtungen", 0.9, "[Einrichtung]"),
    ("geschwister", r"\b(?:Bruder|Schwester|Halbbruder|Halbschwester|Geschwister|Zwilling\w*)\s*\(\s*\d{1,2}"
                    r"(?:\s*(?:J\.|Jahre))?\s*\)", "seltene_merkmale", 0.8, "[Geschwister]"),
    # Persons the psychologist did not list: a form of address or title before a capitalised name. Yields to a
    # known-name hit, so "Frau <Mutter>" keeps the role replacement.
    ("anrede", rf"\b(?:Herrn?|Frau|{_TITEL})\s+(?:(?:{_TITEL})\s+)*(?P<name>[A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)?"
               r"(?:\s[A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)?)?)", "direkte_identifikatoren", 0.85, "[Person]"),
]
_YIELD_TO_LIST = {"anrede"}
_COMPILED = [(n, re.compile(r), k, s, e) for n, r, k, s, e in RULES]


@dataclass
class KnownName:
    text: str
    rolle: str


@dataclass
class Fund:
    fund_id: str
    kategorie: str
    teil: int
    start: int
    end: int
    text: str
    quelle: str        # liste, regel, ner, import
    sicherheit: float
    ersatz: str
    status: str        # vorgeschlagen, offen, uebernommen, verworfen, geaendert
    # Known-name hits inside this (rule) hit. They are applied when this hit is rejected, so rejecting a too-wide
    # rule hit such as "Hort Lukas" never exposes the name (EGM E03).
    innen: list = field(default_factory=list)

    @property
    def unsicher(self) -> bool:
        return self.sicherheit < SCHWELLE

    def for_ui(self) -> dict:
        return {k: getattr(self, k) for k in ("fund_id", "kategorie", "teil", "start", "end", "text", "quelle",
                                              "sicherheit", "ersatz", "status")} | {"unsicher": self.unsicher}


# ---------------------------------------------------------------- configuration

def rare_terms() -> list[str]:
    """Rare features list maintained by the psychologist (konfiguration/seltene_merkmale.json, array of strings).
    Nothing is invented: without the file the list is empty."""
    path = os.environ.get("SCHLOMO_SELTENE_MERKMALE")
    if not path or not Path(path).exists():
        return []
    terms = json.loads(Path(path).read_text(encoding="utf-8"))
    return [t for t in terms if isinstance(t, str) and t.strip()]


_NLP = None


def nlp():
    """Lazy NER model; never imported by start type mcp."""
    global _NLP
    if _NLP is None:
        import spacy
        _NLP = spacy.load(os.environ.get("SCHLOMO_SPACY_MODEL", "de_core_news_md"),
                          disable=["parser", "lemmatizer", "attribute_ruler", "morphologizer", "tagger"])
    return _NLP


def reset_nlp() -> None:
    global _NLP
    _NLP = None


# ---------------------------------------------------------------- dates

def parse_date(s: str) -> date | None:
    s = re.sub(r"\s+", " ", s.strip())
    if m := re.fullmatch(r"(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{2}|\d{4})", s):
        d, mo, y = map(int, m.groups())
        y = y + (2000 if y < 50 else 1900) if y < 100 else y
    elif m := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s):
        y, mo, d = map(int, m.groups())
    elif m := re.fullmatch(rf"(\d{{1,2}})\.\s?({_MONATE})\s?(\d{{4}})", s):
        d, mo, y = int(m[1]), _MONAT_NR[m[2].lower()], int(m[3])
    elif m := re.fullmatch(rf"({_MONATE})\s(\d{{4}})", s):
        d, mo, y = 1, _MONAT_NR[m[1].lower()], int(m[2])
    elif m := re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s):
        d, mo, y = map(int, m.groups())
    elif m := re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", s):
        y, mo, d = map(int, m.groups())
    elif m := re.fullmatch(r"(\d{1,2})/(\d{4})", s):
        d, mo, y = 1, int(m[1]), int(m[2])
    else:
        return None
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def relative_date(s: str, testtag: date | None) -> str:
    """Dates become relative to the test day in years;months (projektrahmen.md, Harte Vorgaben 5)."""
    d = parse_date(s)
    if d is None or testtag is None:
        return "[Datum]"
    early, late = sorted((d, testtag))
    months = (late.year - early.year) * 12 + (late.month - early.month) - (1 if late.day < early.day else 0)
    if months == 0:
        return "[Datum, im Monat des Testtags]"
    direction = "vor" if d < testtag else "nach"
    return f"[Datum, {months // 12};{months % 12} {direction} dem Testtag]"


# ---------------------------------------------------------------- detection

# Name particles are not names on their own ("von", "der" would match everywhere).
_PARTIKEL = {"von", "van", "der", "den", "de", "del", "della", "da", "di", "du", "la", "le", "zu", "zur", "bin",
             "ibn", "al", "el", "ter", "ten", "und"}
_UMSCHRIFT = (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"))


def _spellings(v: str) -> set[str]:
    """Umlaut and transliterated forms both ways (Müller, Mueller)."""
    out = {v}
    for a, b in _UMSCHRIFT:
        out |= {s.replace(a, b).replace(a.upper(), b.capitalize()) for s in out}
        out |= {s.replace(b, a).replace(b.capitalize(), a.upper()) for s in out}
    return out


def _name_variants(text: str) -> set[str]:
    full = " ".join(text.split())
    tokens = [t for t in full.split(" ") if len(t.strip(".")) >= 2 and t.casefold() not in _PARTIKEL]
    parts = {p for t in tokens for p in t.split("-") if len(p) >= 2}  # parts of double names
    variants = {full, *tokens, *parts}
    if len(tokens) >= 2:
        first, last = tokens[0], tokens[-1]
        variants |= {f"{first[0]}. {last}", f"{first[0]}.{last}", f"{last}, {first}", f"{last} {first}",
                     f"{last}, {first[0]}.", f"{last} {first[0]}.", f"{first[0]}. {last[0]}.", f"{first[0]}.{last[0]}."}
    return {s for v in variants for s in _spellings(v)}


def _name_patterns(names: list[KnownName]):
    for n in names:
        for v in sorted(_name_variants(n.text), key=len, reverse=True):
            # Optional inflection or possessive endings: s, es, ens, n, en, 's, ’s, '
            tail = "" if v.endswith(".") else r"(?:s|es|ens|n|en|'s|’s|')?(?!\w)"
            yield re.compile(rf"(?<!\w){re.escape(v)}{tail}", re.IGNORECASE), n.rolle


def detect_text(text: str, teil: int, names: list[KnownName], testtag: date | None, use_ner: bool = True) -> list[Fund]:
    raw: list[Fund] = []

    def add(start, end, kategorie, quelle, sicherheit, ersatz):
        raw.append(Fund("", kategorie, teil, start, end, text[start:end], quelle, sicherheit, ersatz, ""))


    for pattern, rolle in _name_patterns(names):
        for m in pattern.finditer(text):
            add(m.start(), m.end(), "direkte_identifikatoren", "liste", 1.0, f"[{rolle}]")
    listed = [(f.start, f.end) for f in raw]
    for _name, rx, kategorie, sicherheit, ersatz in _COMPILED:
        for m in rx.finditer(text):
            # yields only if one known name covers the whole name part ("Frau <Mutter>"), not a shared surname
            if _name in _YIELD_TO_LIST and any(s <= m.start("name") and m.end() <= e for s, e in listed):
                continue
            add(m.start(), m.end(), kategorie, "regel", sicherheit,
                ersatz if ersatz is not None else relative_date(m.group(0), testtag))
    for term in rare_terms():
        for m in re.finditer(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.IGNORECASE):
            add(m.start(), m.end(), "seltene_merkmale", "liste", 0.8, "[Merkmal]")
    if use_ner:
        for ent in nlp()(text).ents:
            if ent.label_ == "PER":
                add(ent.start_char, ent.end_char, "direkte_identifikatoren", "ner", NER_SICHERHEIT, "[Person]")
            elif ent.label_ in ("LOC", "ORG"):
                add(ent.start_char, ent.end_char, "orte_einrichtungen", "ner", NER_SICHERHEIT,
                    "[Ort]" if ent.label_ == "LOC" else "[Einrichtung]")
    return _resolve_overlaps(raw)


# Rules first: a rule hit such as an e-mail address may contain a known name and must be replaced as a whole.
# NER comes last and never displaces a list or rule hit, so rejecting an NER hit cannot expose a known name.
_PRIORITY = {"regel": 0, "liste": 1, "ner": 2}


def _resolve_overlaps(found: list[Fund]) -> list[Fund]:
    """Keep the most reliable, then the longest hit; drop hits overlapping an already kept one. A dropped known-name
    hit lying inside a kept hit is attached to it as inner hit."""
    kept: list[Fund] = []
    for f in sorted(found, key=lambda f: (_PRIORITY[f.quelle], -(f.end - f.start), f.start)):
        if all(f.end <= k.start or f.start >= k.end for k in kept):
            kept.append(f)
        elif f.quelle == "liste":
            outer = next((k for k in kept if k.start <= f.start and f.end <= k.end and k.quelle != "liste"), None)
            if outer is not None and all(f.end <= i.start or f.start >= i.end for i in outer.innen):
                outer.innen.append(f)
    return sorted(kept, key=lambda f: f.start)


def detect_document(parts, names: list[KnownName], testtag: date | None, use_ner: bool = True) -> list[Fund]:
    funde: list[Fund] = []
    for i, part in enumerate(parts):
        if part.art in VISIBLE_ARTS:
            funde += detect_text(part.text, i, names, testtag, use_ner)
        else:
            # Hidden content never enters the released text; it is listed so the psychologist sees what is removed.
            funde.append(Fund("", "versteckte_inhalte", i, 0, len(part.text), part.text, "import", 1.0, "", ""))
    for f in funde:
        f.fund_id = new_id("f")
        f.status = "offen" if f.unsicher else "vorgeschlagen"
    return funde


# ---------------------------------------------------------------- release

APPLIED = ("vorgeschlagen", "uebernommen", "geaendert")


def anonymize(parts, funde: list[Fund], bilder: int) -> tuple[str, list[tuple[int, int]]]:
    """Released text and the spans in it that the psychologist kept on purpose (rejected findings). The re-check
    exempts hits by these spans, never by equal text elsewhere (EGM E08)."""
    out, kept, pos = [], [], 0
    for i, part in enumerate(parts):
        if part.art not in VISIBLE_ARTS:
            continue
        text, local, cur = "", [], 0
        for f in sorted((f for f in funde if f.teil == i and f.status != "offen"), key=lambda f: f.start):
            if f.status in APPLIED:
                seg = f.ersatz
            else:  # verworfen: original text, with known names inside still replaced
                seg = part.text[f.start:f.end]
                for inner in sorted(f.innen, key=lambda x: -x.start):
                    a, b = inner.start - f.start, inner.end - f.start
                    seg = seg[:a] + inner.ersatz + seg[b:]
            text += part.text[cur:f.start]
            if f.status not in APPLIED:
                local.append((len(text), len(text) + len(seg)))
            text += seg
            cur = f.end
        text += part.text[cur:]
        lead = len(text) - len(text.lstrip())
        if text.strip():
            kept += [(pos + a - lead, pos + b - lead) for a, b in local]
            out.append(text.strip())
            pos += len(out[-1]) + 2
    if bilder:
        out.append(f"[{bilder} Bild entfernt]" if bilder == 1 else f"[{bilder} Bilder entfernt]")
    return "\n\n".join(out), kept


def anonymized_text(parts, funde: list[Fund], bilder: int) -> str:
    return anonymize(parts, funde, bilder)[0]


def counts(funde: list[Fund], bilder: int) -> dict:
    c = {k: 0 for k in KATEGORIEN}
    for f in funde:
        if f.status != "verworfen":
            c[f.kategorie] += 1
        if f.unsicher and f.status == "offen":
            c["unsicher"] += 1
    c["bilder"] = bilder
    return c
