---
name: diagnosevorschlag
description: Blinder Diagnosevorschlag im Chat für den Vergleich in der App. Verwenden, wenn ein Fallpaket der Art diagnosevorschlag hochgeladen ist; gibt genau einen Rückgabe-Block aus.
---

# Diagnosevorschlag im Chat

Du erstellst einen Diagnosevorschlag, ohne Entwurf und ohne Diagnose der Psychologin zu kennen. Er dient nur dem
Vergleich in der App und geht nie in das Gutachten. Nutze dieses Gespräch nur für dieses Paket.

1. Die hochgeladene JSON-Datei lesen. Ist `art` nicht `diagnosevorschlag`, nur antworten: "Falsches Paket,
   erwartet ist ein Paket der Art diagnosevorschlag." Dann aufhören. Fehlt die Datei, um das Paket aus der App
   bitten.
2. Erste Zeile genau: `Skill diagnosevorschlag aktiv`.
3. Aus `inhalt.gutachten_input` und `inhalt.kategorien` ableiten. `kriterien` ist `erfuellt`, `nicht_erfuellt`
   oder `nicht_pruefbar`; fehlen Angaben, `nicht_pruefbar`. Einen ICD-10-Code nur, wenn du sicher bist; die App
   übernimmt ihn nur aus ihren lokalen Referenzdaten.
4. Nach der Kennzeile genau ein Codeblock (Sprache json) und sonst nichts:

```json
{"schema_version": "2", "paket_id": "<paket_id der Datei>", "typ": "diagnosevorschlag", "daten": {
  "schema_version": "1", "session_id": "<inhalt.gutachten_input.session_id>", "quelle": "claude",
  "kriterien": "erfuellt|nicht_erfuellt|nicht_pruefbar", "icd10_code": "<optional>",
  "begruendung": [{"text": "<Satz>", "quellen": ["/<JSON-Pointer in gutachten_input>"]}],
  "schweregrad_vorschlag": "<optional, nur wenn kriterien erfuellt: leicht|mittelgradig|schwer|schwerst>",
  "hinweis": "Vorschlag einer KI, keine Diagnose. Ein Schweregrad ist nur ein grober Vorschlag."}}
```
