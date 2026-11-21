---
name: stil-lernen
description: Erzeugt aus freigegebenen, anonymisierten Probegutachten ein Stilprofil mit Belegzitaten, immer im Status Entwurf. Verwenden mit /stil-lernen oder wenn ein Fallpaket der Art stil_lernen hochgeladen ist.
argument-hint: "[session_id]"
---

# /stil-lernen

Du beschreibst, wie die Psychologin schreibt, damit spätere Entwürfe ihrem Stil folgen. Du lernst nur Sprache,
nie Inhalte von Fällen. Das Profil bleibt ein Entwurf, bis die Psychologin es in der App freigibt.

**Welche Variante?** Stehen dir Werkzeuge `mcp__engine__...` zur Verfügung, gilt der Ablauf "Code-Tab". Sonst
der Ablauf "Chat" mit einer hochgeladenen Fallpaket-Datei; fehlt sie, um das Paket aus der App bitten.

## Ablauf Chat

1. Die hochgeladene JSON-Datei lesen. Ist `art` nicht `stil_lernen`, nur antworten: "Falsches Paket, erwartet ist
   ein Paket der Art stil_lernen." Dann aufhören.
2. Erste Zeile genau: `Skill stil-lernen aktiv`.
3. Aus `inhalt.probetexte` die Merkmale wie in Schritt 4 des Code-Tab-Ablaufs finden. `vorgaenger_version` ist
   `null`, `version` ist `v1`; die App nummeriert beim Speichern neu, falls die Version schon besteht.
4. Nach der Kennzeile genau ein Codeblock (Sprache json) und sonst nichts:
   `{"schema_version": "2", "paket_id": "<paket_id der Datei>", "typ": "stilprofil", "daten": <Profil>}`.

## Ablauf Code-Tab

1. **Sitzung wählen.** `$ARGUMENTS` als `session_id` nehmen, sonst `mcp__engine__liste_sitzungen` aufrufen und
   die Psychologin wählen lassen.
2. **Probetexte holen.** `mcp__engine__hole_probetexte` mit der `session_id`. Bei `E_NICHT_GEFUNDEN` hat die
   Sitzung kein freigegebenes Dokument mit der Quellrolle "Probegutachten": das sagen und aufhören.
3. **Vorgänger.** `mcp__engine__hole_stilprofil`: Gibt es ein freigegebenes Profil, ist dessen `version` die
   `vorgaenger_version`; bei `E_NICHT_GEFUNDEN` ist sie `null`.
4. **Merkmale finden.** Nur, was in mehreren Probetexten wiederkehrt; ein Merkmal aus einem einzigen Text kennzeichnest
   du in der Beschreibung als "nur in einem Probegutachten". Immer zusätzlich prüfen:
   - Stichwortstil in der Verhaltensbeobachtung (Kategorie `satzbau`),
   - Konjunktiv in der Anamnese, also berichtete Angaben als Wiedergabe (Kategorie `perspektive`),
   - Aufbau der Empfehlung, etwa Reihenfolge von Ergebnis, Begründung und Maßnahmen (Kategorie `struktur`).
   Ist eines davon in den Probetexten nicht erkennbar, legst du kein Merkmal dafür an und nennst es am Ende.
5. **Profil bauen** (Format unten) und mit `mcp__engine__speichere_stilprofil` speichern. Die Engine setzt den
   Status immer auf `entwurf`. Bei `E_BLOCKIERT` gibt es die Version schon: Nummer erhöhen und erneut speichern.
   Bei `E_SCHEMA` das Format prüfen. Höchstens drei Versuche (Festlegung für die Evals, offen für die Psychologin).
6. **Abschluss.** Version, Zahl der Merkmale je Kategorie, die nicht erkennbaren Zusatzmerkmale und der Hinweis,
   dass die Freigabe in der App erfolgt. Keine Zitate wiederholen.

## Format (stilprofil, Schema-Version 1)

```json
{
  "schema_version": "1",
  "version": "v1",
  "vorgaenger_version": null,
  "status": "entwurf",
  "anzahl_probegutachten": 3,
  "merkmale": [
    {"merkmal_id": "m1", "kategorie": "satzbau|wortwahl|struktur|perspektive|fachsprache|zurueckhaltung|sonstiges",
     "beschreibung": "<was typisch ist, in einem Satz>",
     "belegzitate": [{"text": "<wörtlich aus einem Probetext, höchstens 300 Zeichen>", "probe_id": "<probe_id>"}]}
  ],
  "formulierungsbeispiele": [{"abschnitt_id": "<z. B. empfehlung>", "text": "<höchstens 400 Zeichen>"}]
}
```

- `version`: `v` und eine Zahl; ist ein Vorgänger da, dessen Zahl plus eins.
- `anzahl_probegutachten`: Zahl der Probetexte aus Schritt 2.
- `belegzitate`: **wörtlich** aus dem Probetext mit genau dieser `probe_id`, mindestens eines je Merkmal, nichts
  umformulieren, nichts zusammensetzen.
- `formulierungsbeispiele`: kurze typische Wendungen, nie ganze Absätze oder Gutachten. `abschnitt_id` wie in den
  Gutachten (`vorstellungsgrund`, `anamnese`, `verhaltensbeobachtung`, `testbefunde`, `leistungsproben`,
  `empfehlung`).
- Die Probetexte sind anonymisiert ("das Kind", "[Datum ...]"). Keine Angabe aus einem Fall in Beschreibungen oder
  Beispiele übernehmen, die nicht schon im Zitat steht; Beispiele allgemein halten.
