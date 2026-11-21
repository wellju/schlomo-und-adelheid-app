# Schlomo und Adelheid

Local tool for school psychology reports (SPF, LRS, Rechenstörung, emotional-soziale Entwicklung) with Claude.
Case documents never leave the device in clear text: a local engine imports them, finds names, dates, addresses and
other identifiers, and releases only anonymised text after the psychologist has decided every uncertain finding.
Rule checks, evidence checks and the DOCX export run deterministically in the engine, without a language model.

Status: engine (Task 1) built and tested; app (Tauri), Claude plugin and installer follow.

## Repository

| Folder | Content |
|:--|:--|
| `engine/` | Python engine with two start types: `engine ui` (sidecar of the app, JSON lines over stdin/stdout) and `engine mcp` (MCP server for Claude, only anonymised and released data) |
| `contracts/` | JSON Schemas (draft 2020-12) for every exchange between app, engine and Claude |
| `docs/ui-api.md` | Contract between app and engine |

Design documents and the project plan are kept outside this repository; references to them in comments
(`ADR 0001`, `Nachtrag 1`, `projektrahmen.md`) point there.

## Development

Python 3.12 or newer. Tesseract (with `deu`) and LibreOffice are needed for OCR and for DOC and XLS; tests that need
them are skipped without them, unless `SCHLOMO_ABNAHME=1` is set (then a skip fails the run).

```
cd engine
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m spacy download de_core_news_md
.venv/Scripts/python -m pytest
python -I ../contracts/tests/check_contracts.py ../contracts
```

All test data is synthetic. Never add real case data, real reports or real names to this repository, its issues or
its pull requests.

## License

Apache License 2.0, see `LICENSE`. Third-party components keep their own licenses; notably the German spaCy model
`de_core_news_md` (MIT, trained on data including the TIGER corpus, which its metadata lists as commercially
licensed by Explosion), pikepdf (MPL-2.0) and pillow-heif (BSD, bundles libheif under LGPL).
