"""Error codes from docs/ui-api.md. Errors carry a code and an optional fixed reason, never document text."""

CODES = frozenset({
    "E_SCHEMA", "E_NICHT_GEFUNDEN", "E_DATEITYP", "E_MAKRO", "E_LIBREOFFICE_FEHLT", "E_BEZEICHNUNG",
    "E_ANONYMISIERUNG_OFFEN", "E_BLOCKIERT", "E_Q1", "E_ABSCHNITT_FEHLT", "E_KOPFFELD_FEHLT", "E_PAKET_FREMD",
    "E_BELEG", "E_REGELABWEICHUNG", "E_VERSION", "E_INTERN", "E_OCR_FEHLT",
})

REASONS = frozenset({"schema", "unbekannte_funktion", "json", "argumente", "datenordner", "groesse", "format",
                     "beschaedigt",
                     "konflikt", "namen_fehlen", "pfad"})


class EngineError(Exception):
    def __init__(self, code: str, reason: str | None = None):
        if code not in CODES:
            raise ValueError(f"unknown error code {code}")
        if reason is not None and reason not in REASONS:
            raise ValueError(f"unknown reason {reason}")
        super().__init__(code)
        self.code = code
        self.reason = reason

    def as_dict(self) -> dict:
        return {"code": self.code, **({"grund": self.reason} if self.reason else {})}
