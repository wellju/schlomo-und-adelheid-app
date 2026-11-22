---
name: verbessern
description: Schlägt aus mindestens drei Lernsignalen eine Änderung an Sprache, Struktur oder Prüfverhalten vor, lässt die Eval-Suite laufen und wartet auf die Freigabe in der App. Nur im Code-Tab. Verwenden mit /verbessern.
---

# /verbessern

Du schlägst genau eine kleine Änderung an den Lernbausteinen vor. Die Psychologin gibt sie in der App frei oder
verwirft sie; du übernimmst nie selbst etwas.

**Nur im Code-Tab.** Stehen dir keine Werkzeuge `mcp__engine__...` zur Verfügung, antworte nur: "/verbessern gibt es
nur im Code-Tab mit der Engine." Dann aufhören.

## Ablauf

1. `mcp__engine__hole_lernsignale`. Du erhältst die freien Lernsignale aus Gutachten und Intervision, Gruppen je
   Herkunft, Bereich und Prüfer mit der Zahl freier Signale, und die aktiven `bausteine` mit `baustein_id`. Gibt es
   keine Gruppe mit mindestens drei freien Signalen, sage das und höre auf. Signale eines offenen Vorschlags sind
   nicht frei; ein neuer Versuch mit denselben Signalen geht erst, wenn die Psychologin den alten verwirft.
2. Wähle eine Gruppe und lies ihre freien Signale (Art, Prüfer, Abschnitt, vorher und nachher). Suche ein Muster, das
   mindestens drei Signale teilen. Ohne klares Muster: sagen und aufhören.
3. Formuliere genau einen Baustein (höchstens 500 Zeichen, deutsch, ohne Namen, Daten, Orte):
   - Bereich `sprache` oder `struktur`: Ziel `entwurf` oder `stil`.
   - Bereich `pruefverhalten`: Ziel ist der Prüfer der Signale (`stil`, `goldfisch` oder `elefant`). Prüfverhalten
     heißt Formulierung und Gewichtung der Prüferhinweise, nie Regelparameter, Grenzwerte oder Zahlen, nie weniger
     Befunde melden, nie Befunde herabstufen.
   - Herkunft `intervision`: nur Prüfverhalten für `goldfisch` oder `elefant` (die Prüfer der Protokolle).
   - Bereich `struktur`: Lernsignale dieses Bereichs entstehen derzeit nicht; schlage nichts dafür vor.
   - Nie: Regelwerk, Kategorienskala, Vorlagen, Testkatalog, Hinweis-Wortlaute, ICD-10-Referenz, Diagnosevergleich,
     Supervision. Die Engine weist solche Vorschläge ab.
4. `mcp__engine__schlage_konfiguration_vor` mit dem einen Argument `vorschlag`:
   `{"vorschlag": {"datei": "lernbausteine.json", "herkunft": ..., "bereich": ..., "signal_ids": [mindestens drei],
   "aenderung": {"art": "hinzufuegen", "ziel": ..., "text": ...}, "begruendung": ...}}`. Zum Ändern oder
   Entfernen eines aktiven Bausteins `art` `aendern` bzw. `entfernen` mit seiner `baustein_id` aus Schritt 1.
   Bei `E_BLOCKIERT` (gesperrt oder zu wenige passende Signale) nicht umgehen: den Grund nennen und aufhören.
5. `mcp__engine__starte_evals` mit der `vorschlag_id`. Nenne das Ergebnis je Eval-Fall. Abgelehnt: den Fall nennen,
   nichts umformulieren und erneut einreichen, außer die Psychologin bittet darum.
6. Abschluss: Bestanden heißt nicht freigegeben. Vor der Freigabe muss der LLM-Teil der Evals mit dem Vorschlag
   laufen: `evals/lernschleife/mit_vorschlag.py` baut die Konfiguration, die Psychologin startet damit
   `evals/gutachten`, `evals/pruefer`, `evals/stil` und `evals/rubberduck` und bestätigt das Ergebnis in der App.
   Freigabe nur in der App unter "Lernen und Qualität". Keine Inhalte aus Fällen wiederholen.
