"""Transient store for imported clear text (Nachtrag 1: RAM only, never on disk, never in logs). Holds everything
between dokument_importieren and anonymisierung_freigeben under dok_id; cleared on beenden and process exit."""
from dataclasses import dataclass, field


@dataclass
class Part:
    art: str            # e.g. haupttext, kopf_fusszeile, kommentar, verborgen, metadaten (see importer.HIDDEN)
    text: str
    seite: int | None = None


@dataclass
class ImportedDoc:
    session_id: str
    dok_id: str
    format: str
    raw: bytes                       # original bytes, kept for OCR rendering; never written anywhere
    seiten: int
    parts: list[Part] = field(default_factory=list)
    bilder: int = 0
    ocr_seiten: list[int] = field(default_factory=list)   # 1-based pages that still need OCR
    funde: list = field(default_factory=list)             # recognition.Fund, step 1.3
    erkennung_gelaufen: bool = False

    @property
    def versteckte_inhalte(self) -> int:
        from .importer import HIDDEN
        return sum(1 for p in self.parts if p.art in HIDDEN)


_DOCS: dict[str, ImportedDoc] = {}
_NAMES: dict[str, list] = {}  # session_id -> recognition.KnownName list


def put(doc: ImportedDoc) -> None:
    _DOCS[doc.dok_id] = doc


def get(session_id: str, dok_id: str) -> ImportedDoc | None:
    doc = _DOCS.get(dok_id)
    return doc if doc and doc.session_id == session_id else None


def drop(dok_id: str) -> None:
    _DOCS.pop(dok_id, None)


def set_names(session_id: str, names: list) -> None:
    _NAMES[session_id] = names


def names(session_id: str) -> list:
    return _NAMES.get(session_id, [])


def names_set(session_id: str) -> bool:
    """True once the psychologist entered the names in this process run (an empty list counts: no names apply).
    After a restart the list is gone and must be entered again before free text is checked (EGM E02)."""
    return session_id in _NAMES


def clear() -> None:
    _DOCS.clear()
    _NAMES.clear()
