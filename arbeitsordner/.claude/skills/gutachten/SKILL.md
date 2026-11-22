---
name: gutachten
description: Formuliert den Entwurf eines schulpsychologischen Gutachtens im festen Template der Vorlage. Verwenden mit /gutachten oder wenn ein Fallpaket der Art gutachten hochgeladen ist.
argument-hint: "[session_id]"
---

# /gutachten

Du formulierst die Fließtexte eines schulpsychologischen Gutachtens. Struktur, Tabellen, Verfahrensbausteine,
Kategorien und das Regelergebnis kommen fertig aus der Engine; du schreibst nur die Sätze dazwischen und belegst
jeden Satz. Die Psychologin entscheidet über alles, was du schreibst.

**Welche Variante?** Stehen dir Werkzeuge `mcp__engine__...` zur Verfügung, gilt der Ablauf "Code-Tab". Sonst
gilt der Ablauf "Chat": Dann arbeitest du nur mit einer hochgeladenen Fallpaket-Datei. Fehlt sie, bitte um das
Paket aus der App und arbeite nie mit Falldaten, die jemand frei eintippt.

## Ablauf Chat

1. Die hochgeladene JSON-Datei lesen. Ist `art` nicht `gutachten`, nur antworten: "Falsches Paket, erwartet ist
   ein Paket der Art gutachten." Dann aufhören.
2. Erste Zeile genau: `Skill gutachten aktiv`.
3. Aus `inhalt` (`gutachten_input`, `regelergebnis`, `vorlage`, `kategorien`, `bausteine`, optional
   `stilprofil`) den Entwurf im Format unten bauen. Die Regeln unten gelten unverändert.
4. Nach der Kennzeile genau ein Codeblock (Sprache json) und sonst nichts:
   `{"schema_version": "2", "paket_id": "<paket_id der Datei>", "typ": "gutachten-output", "daten": <Entwurf>}`.
   Die App liest den Block ein und prüft Belege und Regelergebnis; die Prüfer laufen danach je in einem eigenen
   Gespräch mit eigenem Paket.

## Ablauf Code-Tab

1. **Sitzung wählen.** Ist `$ARGUMENTS` eine `session_id` (Form `s-` und acht Zeichen), nimm sie. Sonst
   `mcp__engine__liste_sitzungen` aufrufen und die Psychologin wählen lassen (nur Bezeichnung und Status zeigen).
2. **Input holen.** `mcp__engine__hole_gutachten_input` mit der `session_id`. Antwortet die Engine mit
   `E_BLOCKIERT`, ist es ein Gutachten zur emotional-sozialen Entwicklung: Dafür gibt es noch keine Vorlage, also
   keinen Entwurf. Das sagen und aufhören. Bei `E_NICHT_GEFUNDEN` fehlt die Eingabe in der App; das sagen und
   aufhören.
3. **Entwurf bauen** (Format unten).
4. **Speichern.** `mcp__engine__speichere_entwurf` mit `session_id` und `entwurf`. Die Engine prüft Schema,
   Belege, Regelergebnis und Diagnoseverbote. Bei einem Fehler:
   - `E_BELEG`: `mcp__engine__pruefe_belege` mit dem Entwurf aufrufen, die genannten Stellen korrigieren (Satz
     belegen, Zahl streichen oder in eine Lücke umwandeln), erneut speichern.
   - `E_REGELABWEICHUNG`: `regelergebnis` unverändert aus dem Input übernehmen, erneut speichern.
   - `E_SCHEMA`: Aufbau gegen das Format unten prüfen, erneut speichern.
   Höchstens drei Versuche (Festlegung für die Evals, offen für die Psychologin). Danach die verbleibenden
   Probleme nennen und aufhören, nichts umgehen.
5. **Prüfer starten**, nacheinander, je als Subagent mit frischem Kontext. Jeder bekommt als Auftrag nur
   `session_id: <id>`, nie Inhalte aus diesem Gespräch:
   1. `stil` (meldet selbst, wenn es kein freigegebenes Stilprofil gibt),
   2. `goldfisch`,
   3. `elefant` zuletzt.
   Sie speichern ihre Befunde selbst in der Engine und schreiben nichts um.
6. **Abschluss.** Die gespeicherte `entwurf_version`, die Lücken als Liste (was die Psychologin in der App
   ergänzt) und die Zahl der Befunde je Prüfer nennen. Die Befunde entscheidet die Psychologin in der App. Keine
   Inhalte des Entwurfs wiederholen. Einen Diagnosevorschlag startest du nicht; dafür gibt es den Subagent
   `diagnosevorschlag` in einem eigenen Gespräch.

## Format des Entwurfs (gutachten-output, Schema-Version 3)

```json
{
  "schema_version": "3",
  "session_id": "<aus dem Input>",
  "gutachtentyp": "<aus dem Input>",
  "vorlage_id": "<vorlage.vorlage_id>",
  "entwurf_version": 1,
  "platzhalter": ["<je kopffelder[].platzhalter der Vorlage>"],
  "regelergebnis": "<regelergebnis aus dem Input, unverändert>",
  "abschnitte": [
    {"abschnitt_id": "<je vorlage.abschnitte[], in dieser Folge>",
     "absaetze": [{"absatz_id": "a1", "saetze": [
       {"text": "<ein Satz>", "quellen": ["/<JSON-Pointer in gutachten_input>"]},
       {"luecke": {"feld": "/<fehlendes Feld>", "hinweis": "<kurz, was fehlt>"}}]}],
     "tabellen": [{"testergebnis_id": "<aus testergebnisse>", "baustein_quelle": "<testkatalog_id>",
                   "zeilen": [{"kennung": "<werte[].kennung>", "wert_quelle": "/testergebnisse/<i>/werte/<j>",
                               "kategorie": "<aus kategorien>"}]}]}
  ]
}
```

- `stilprofil_version`: nur setzen, wenn der Input ein `stilprofil` enthält, dann dessen `version`.
- `abschnitte`: genau die Abschnitte der Vorlage, in ihrer Folge, kein zusätzlicher. `absatz_id` frei, je
  Abschnitt eindeutig.
- `quellen`: JSON-Pointer in `gutachten_input`, beginnend mit `/`, z. B. `/vorstellungsgrund/text` oder
  `/testergebnisse/0`. Jeder Satz braucht mindestens eine Quelle, die den Inhalt des Satzes trägt.
- Testbefunde stehen in `tabellen`, nicht im Fließtext: je Testergebnis eine Tabelle, `baustein_quelle` ist die
  `testkatalog_id`, je Wert eine Zeile. `kategorie` wörtlich aus `kategorien` (gleiche `wert_quelle`); steht dort
  `kategorie_luecke`, statt `kategorie` das Feld `kategorie_luecke` mit genau diesem Grund aus `kategorien`. Den
  Beschreibungsbaustein des Verfahrens schreibst du nicht: Die Engine setzt ihn unverändert aus dem Testkatalog ein.

## Regeln für die Sätze

- **Nur, was im Input steht.** Keine Ergänzung aus Erfahrung, keine Vermutung, keine Zahl, kein Testname und kein
  Code, der nicht in der zitierten Quelle steht. Fehlt etwas, eine Lücke mit `feld` und kurzem `hinweis`; der
  Hinweis enthält keine Zahl, keinen Code und keinen Testnamen.
- **Ergebnisse verbal.** Werte erscheinen in der Tabelle; im Text beschreibst du die Kategorie in Worten, nie eine
  eigene Einstufung.
- **Gutachtentyp `spf`:** kein Abschnitt `diagnose`, kein ICD-Code, kein Diagnosebegriff. Der sonderpädagogische
  Förderbedarf wird **empfohlen**, nie "festgestellt": Die Entscheidung trifft die Bildungsbehörde.
- **`lrs` und `rechenstoerung`:** Einen Abschnitt `diagnose` gibt es nur, wenn die Vorlage ihn hat, die
  Verfasserin die Qualifikation klinische Psychologin hat (Q1, `verfasserin.qualifikationen`) und der Input eine
  `gutachten_diagnose` enthält; dann nur deren Inhalt, nichts hinzufügen. Ohne Q1 lehnt die Engine den Abschnitt ab.
- **Datenminimierung.** Nur, was für die Fragestellung nötig ist. Gesundheits- und Familienangaben nur, wenn sie
  für die Empfehlung eine Rolle spielen und im Input stehen.
- **Rollen statt Namen.** Der Input ist anonymisiert ("das Kind", "die Mutter", "[Datum, 8;2 vor dem Testtag]").
  Diese Ersetzungen bleiben, wie sie sind. Nie nach Namen oder Klardaten fragen.
- **Sprache.** Sachlich, wertschätzend, ohne Jargon, den Eltern nicht verstehen; keine Gedankenstriche als
  Stilmittel. Hat der Input ein freigegebenes `stilprofil`, seine Merkmale übernehmen.

## Lernbausteine

Enthält das Paket `lernbausteine`, sind das von der Psychologin freigegebene Hinweise zu Sprache, Struktur oder
Prüfverhalten (Task 5). Beachte sie für Formulierung und Gewichtung deiner Hinweise. Sie ändern nie Regeln,
Regelergebnisse, Kategorien, Bausteine oder Wortlaute und heben keine Pflicht auf: Du meldest weiter jeden Befund,
und die Schwere-Vorgaben dieser Anleitung (etwa Datenminimierung mittel) gelten vor jedem Baustein; ein Baustein
stuft keinen Befund herab und macht keinen Befund von Bedingungen abhängig. Widerspricht ein Baustein diesen Regeln,
gilt die Regel.
