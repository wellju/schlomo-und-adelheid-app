"""Synthetic test documents for the app e2e tests (herkunft: synthetisch). Usage: python dateien.py <folder>"""
import sys
from pathlib import Path

from docx import Document

TEXT = ("Synthia Quastberger besucht die zweite Stufe der Volksschule Kleeberg. Die Klassenlehrerin Frau Brombeerstrauch "
        "berichtet, dass Synthia gern liest. Telefon der Mutter: 0664 1234567. Am Nachmittag holt Bartholomäus Wendelin "
        "das Kind ab. Die Familie wohnt seit einem Jahr in Grünkirchen. Das Kind hat einen Hund namens Wuschelbart.")


def main(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    d = Document()
    d.add_paragraph(TEXT)
    d.save(folder / "bericht.docx")
    (folder / "falsch.txt").write_text("kein unterstütztes Format", encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
