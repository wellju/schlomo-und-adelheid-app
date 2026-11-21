---
name: pruefen-stil
description: Stilprüfung im Chat. Verwenden, wenn ein Fallpaket der Art pruefung_stil hochgeladen ist; meldet nur Abweichungen vom freigegebenen Stilprofil als genau einen Rückgabe-Block.
---

# Stilprüfung im Chat

Du prüfst nur die Sprache eines Entwurfs gegen das freigegebene Stilprofil. Inhalt, Zahlen und Regeln prüfst du
nicht. Du schreibst nichts um.

1. Die hochgeladene JSON-Datei lesen. Ist `art` nicht `pruefung_stil`, nur antworten: "Falsches Paket, erwartet
   ist ein Paket der Art pruefung_stil." Dann aufhören. Fehlt die Datei, um das Paket aus der App bitten.
2. Erste Zeile genau: `Skill pruefen-stil aktiv`.
3. Jede Stelle in `inhalt.entwurf`, an der der Text von einem Merkmal in `inhalt.stilprofil` abweicht, ist ein
   Befund; das Merkmal und, wenn vorhanden, ein Formulierungsbeispiel zitieren. Übereinstimmungen nicht melden.
4. Nach der Kennzeile genau ein Codeblock (Sprache json) und sonst nichts:

```json
{"schema_version": "2", "paket_id": "<paket_id der Datei>", "typ": "befunde", "daten": [
  {"befund_id": "bf-00000001", "stelle": {"abschnitt_id": "<id>", "absatz_id": "<id>", "zitat": "<höchstens 300 Zeichen>"},
   "problem": "<Abweichung>", "schwere": "gering", "begruendung": "<Merkmal des Stilprofils>", "pruefer": "stil",
   "entscheidung": {"status": "offen"}}]}
```

`befund_id` fortlaufend, `entscheidung.status` immer `offen`, ohne Befund eine leere Liste. Schwere als Vorschlag,
bis die Psychologin es festlegt (offen).
