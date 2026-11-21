# UI-Vertrag App zu Engine

Stand 21.11.2026, Status Entwurf aus dem Spike (Punkt 4), überarbeitet nach EGM (docs/reviews/egm-spike.md).
Task 1 baut die Engine-Seite, Task 4 die App-Seite. Feldnamen wie in `contracts/`. Gilt nur für die Startart
`engine ui`; die Startart `engine mcp` hat keinen dieser Aufrufe (docs/listen.md, App-only-Funktionen; ADR 0001,
Durchsetzung im Code).

## Kanal

- stdin/stdout des Sidecars, eine JSON-Nachricht je Zeile (UTF-8, `\n`). Die App startet die Engine über das
  Tauri-Shell-Plugin (`externalBin`, `shell:allow-spawn`), liest `CommandEvent::Stdout` und schreibt mit
  `child.write` (Quelle: tauri-docs v2, develop/sidecar.mdx).
- ADR 0001 ließ stdin/stdout oder 127.0.0.1 mit Zufallsport und Einmal-Token offen ("Wahl in Task 4 nach Spike").
  Der Spike wählt stdin/stdout: kein offener Port, keine Firewall-Abfrage, kein Token in Prozesslisten oder Logs; der
  Kanal endet mit dem Prozess der App. Das ist eine Festlegung innerhalb von ADR 0001, keine Abweichung.
- stderr der Engine enthält nur Logzeilen nach Nachtrag 1 (Ereignisart, Zeitpunkt, Zähler, Fehlercode, technische
  IDs `s-`, `d-`, `p-`), nie Inhalte.

## Nachrichten

```
Anfrage:  {"id": "r-17", "fn": "dokument_importieren", "args": {...}}
Antwort:  {"id": "r-17", "ok": true, "result": {...}}
Fehler:   {"id": "r-17", "ok": false, "fehler": {"code": "E_DATEITYP", "grund": "schema"}}
Ereignis: {"event": "fortschritt", "id": "r-17", "schritt": "ocr", "anteil": 0.4}
```

- `id` vergibt die App, die Engine antwortet genau einmal je `id`. Ereignisse tragen die `id` der laufenden Anfrage.
- Fehler enthalten nur Code und optional einen festen Grund aus einer Liste, nie Text aus Dokumenten oder Eingaben.

## Datenschutzgrenzen im Kanal

- **Klartext beim Import:** Rohtext, Seitenbilder und Funde eines Dokuments liegen zwischen `dokument_importieren`
  und `anonymisierung_freigeben` nur im Arbeitsspeicher der Engine, geführt unter `dok_id`. Nie im Fallspeicher, nie
  auf Datenträger, nie im Log. Sie werden verworfen bei Freigabe, bei `beenden`, beim Absturz und wenn die App
  schließt (ADR 0001: Import vor Freigabe geht dann verloren).
- **Klartext zur App:** Funde und Vorschau der Schwärzung gehen nur über diesen Kanal an die App und werden dort
  ebenfalls nur im Arbeitsspeicher gehalten.
- **`pfad`:** nur für den einen Aufruf, nie gespeichert, nie geloggt, nie in einem Paket (Originaldateinamen
  gehören zu den Dingen, die nie gespeichert werden, ADR 0001).
- **`bezeichnung` einer Sitzung und `quelle_rolle`:** neutral ("Fall 7", "Bericht Schule"). Bekannte Namen, jeder
  Regeltreffer (auch ein unsicherer wie eine Jahreszahl), Initialen und NER-Personen führen zu `E_BEZEICHNUNG`
  (bei `quelle_rolle` ohne NER, weil NER auf Einzelwörtern wie "Foto" anschlägt). Weil bei `sitzung_anlegen` noch
  keine Namen bekannt sind, meldet `bekannte_namen_setzen` mit `bezeichnung_enthaelt_namen`, ob die Bezeichnung
  einen Namen enthält; die App fordert dann `sitzung_umbenennen`. Nie geloggt.
- **Freitext aus der App:** `eingabe_speichern` und `text_aendern` lassen die Erkennung (bekannte Namen, Regeln,
  NER) über jeden Freitext laufen, bevor gespeichert wird. Ein sicherer Treffer verhindert das Speichern immer;
  unsichere Treffer verhindern es, bis die App `unsichere_bestaetigt: true` mitschickt. Dann antwortet die Engine
  mit `gespeichert: false` und `funde` (`feld` als JSON-Pointer, `text`, `kategorie`, `sicher`); der Text der Funde
  geht nur an die App. Ohne Namensliste dieses Prozesslaufs (nach einem Neustart) antwortet sie mit `E_BLOCKIERT`,
  Grund `namen_fehlen`; die App fragt die Namen dann erneut ab (eine leere Liste ist erlaubt).
- **Gleichzeitiges Schreiben:** ui und mcp sind getrennte Prozesse. Ein Speichern auf einen inzwischen geänderten
  Fallspeicher wird mit `E_BLOCKIERT`, Grund `konflikt`, abgelehnt; die App lädt neu und wiederholt. Die MCP-Tools
  wiederholen selbst.
- **Interne Diagnose:** nur über `interne_diagnose_speichern` und `diagnosevergleich_laden`, beide nur mit Q1.
  `sitzung_laden` liefert sie nie.

## Funktionen

Aufzählungswerte wie in `contracts/`: `modus` gutachten, intervision, supervision; `gutachtentyp` spf, lrs,
rechenstoerung, emotional_soziale_entwicklung; Paket-`art` wie in fallpaket.schema.json.

| Funktion | Eingabe | Ausgabe | Hinweis |
|:--|:--|:--|:--|
| `status` | keine | `engine_version`, Schema-Versionen | Start-Handshake; die App bricht bei abweichender Version ab (Gegenmaßnahme zu tauri issue 15134) |
| `beenden` | keine | keine | Arbeitsspeicher leeren |
| `sitzung_anlegen` | `bezeichnung`, `modus`, `gutachtentyp` | `session` (session.schema.json) | `emotional_soziale_entwicklung`: anlegbar, Entwurf und Export blockiert (Nachtrag 1); `E_BEZEICHNUNG` siehe oben |
| `sitzung_umbenennen` | `session_id`, `bezeichnung` | `session` | gleiche Prüfung wie beim Anlegen, mit den bekannten Namen |
| `sitzungen_auflisten` | keine | Liste `session` | |
| `sitzung_laden` | `session_id` | fallspeicher.schema.json ohne `interne_diagnose`, `diagnosevorschlaege` und `vergleich` | |
| `dokument_importieren` | `session_id`, `pfad`, `quelle_rolle` | `dok_id`, `format`, `seiten`, `ocr_noetig` | Formate wie `session.dokumente[].format`; Probegutachten für `/stil-lernen` mit `quelle_rolle` "Probegutachten"; `E_BEZEICHNUNG` siehe oben |
| `ocr_ausfuehren` | `session_id`, `dok_id` | `seiten_erkannt` | Ereignis `fortschritt` |
| `bekannte_namen_setzen` | `session_id`, `namen` (Liste mit `text` und `rolle`) | `anzahl`, `bezeichnung_enthaelt_namen` | Stufe 1 der Erkennung; nur im Arbeitsspeicher, nie gespeichert, nie geloggt; nach jedem Start der Engine neu zu setzen. Varianten: Teile von Doppelnamen, Initialen, Nachname mit Vorname, Umschrift (Müller, Mueller), Beugung |
| `erkennung_ausfuehren` | `session_id`, `dok_id`, optional `testdatum` (ISO, transient) | `funde` (UI-intern, transient: `fund_id`, `kategorie`, `teil`, `start`, `end`, `text`, `quelle`, `sicherheit`, `ersatz`, `status`, `unsicher`), `funde_je_kategorie`, `hinweise` | Schwelle 0,75, einstellbar über `SCHLOMO_SCHWELLE`; `hinweise`: `namen_fehlen` (keine Namensliste gesetzt), `seltene_merkmale_ohne_liste` (Erstsprache und Herkunft bleiben ungeprüft, solange die Liste fehlt) |
| `schwaerzung_entscheiden` | `session_id`, `dok_id`, `fund_id`, `entscheidung` (uebernehmen, verwerfen, aendern), `ersatz` | aktualisierter Fund, `funde_je_kategorie` | versteckte Inhalte und bekannte Namen lassen sich nicht verwerfen (`E_BLOCKIERT`); verwirft die Psychologin einen Regeltreffer, der einen bekannten Namen enthält (z. B. "Hort Lukas"), bleibt der Name ersetzt |
| `anonymisierung_freigeben` | `session_id`, `dok_id`, `geprueft_bestaetigt` (muss `true` sein) | `session.dokumente[].freigabe` | `E_ANONYMISIERUNG_OFFEN`, solange die Erkennung nicht lief, ein Fund offen ist oder die Nachprüfung des freigegebenen Textes (bekannte Namen, Regeln) einen sicheren Treffer findet; ausgenommen sind nur die Stellen verworfener Funde, nie gleicher Text an anderer Stelle. Ein Dokument ohne Funde ist freigebbar, sobald die Erkennung lief |
| `alter_berechnen` | `geburtsdatum`, `testdatum` (ISO) | `alter` (`jahre`, `monate`, `abgeleitet: true`) | transient, Daten werden verworfen |
| `schulbesuch_berechnen` | `schulbeginn_oesterreich`, `testdatum` (ISO) | `schulbesuch_oesterreich_monate` | transient |
| `normwerte_ableiten` | `testkatalog_id`, `alter`, `testdatum` (ISO) | `normen_alter_jahre`, `normgruppe` (falls im Katalog) | Normjahr aus dem Testkatalog; transient |
| `eingabe_speichern` | `session_id`, `gutachten_input`, optional `unsichere_bestaetigt` | `gespeichert`, dann `session` mit Versionen der geladenen Konfiguration, sonst `funde` | Schemaprüfung (auch: keine Diagnose im SPF, Diagnose nur mit Q1), Freitextprüfung siehe oben |
| `fachregeln_pruefen` | `session_id` | `regelergebnis` vollständig | lokal; Claude sieht nur `fuer_claude` |
| `befund_entscheiden` | `session_id`, `befund_id`, `entscheidung` (annehmen, verwerfen), optional `kommentar` | `befund`, `lernsignal` (`befund_angenommen` bzw. `befund_verworfen`; Bereich `sprache` bei Stil, sonst `pruefverhalten`) oder `null` | Supervision erzeugt kein Lernsignal |
| `text_aendern` | `session_id`, `abschnitt_id`, `absatz_id`, `nachher`, optional `unsichere_bestaetigt` | `gespeichert`, dann `entwurf_version` (neu) und `lernsignal` `text_geaendert` (vorher und nachher je höchstens 500 Zeichen, nie in Supervision), sonst `funde` | Freitextprüfung siehe oben; der Absatz behält die Quellen der bisherigen Sätze, ohne Quellen `E_BELEG` |
| `interne_diagnose_speichern` | `session_id`, `interne_diagnose` (`text`, optional `icd10_code`, `schweregrad`) | Status | nur mit Q1 (`E_Q1`); nach dem ersten Vergleich nicht mehr änderbar (`E_BLOCKIERT`); bleibt im Fallspeicher |
| `diagnosevergleich_laden` | `session_id` | interne Diagnose, Engine- und Claude-Vorschlag, `vergleich` (gleich, abweichend, nicht_vergleichbar über den ICD-Code) | nur mit Q1; `E_BLOCKIERT`, solange keine interne Diagnose eingetragen ist (blinder Vergleich) |
| `vergleich_notiz_speichern` | `session_id`, `notiz` | `vergleich` | höchstens 2000 Zeichen; nie in Lernsignale |
| `vorlage_importieren` | `pfad` | `datei`, `titel` (fette Absätze), `kopf_beschriftungen`, `felder` | kopiert nach `wissensbasis/vorlagen/` (`SCHLOMO_VORLAGEN`); gleicher Dateiname: `E_BLOCKIERT`, nie überschreiben; kaputte oder fremde Datei: `E_DATEITYP` |
| `vorlage_zuordnen` | `vorlage` (vorlage.schema.json mit `datei`) | `vorlage_id` | prüft, dass jede Überschrift und jede Kopf-Beschriftung in der Vorlage vorkommt (`E_ABSCHNITT_FEHLT`, `E_KOPFFELD_FEHLT`); `datei` ohne Pfad und ohne Laufwerk (`E_SCHEMA`, Grund `pfad`); Metadaten atomar |
| `docx_exportieren` | `session_id`, `ziel_pfad` (.docx) | `entwurf_version` | `E_BLOCKIERT` ohne Regelwerk, wenn eine Regel mit `blockiert_export` nicht `erfuellt` ist (auch `nicht_pruefbar`, etwa D1 ohne Begriffsliste), bei Typ emotional-soziale Entwicklung und bei vorhandener Zieldatei; `E_BELEG` bei fehlenden Belegen, auch in Lückenhinweisen; `E_ABSCHNITT_FEHLT`, wenn ein Entwurfsabschnitt keinen Platz in der Vorlage hat oder ein Vorlagenabschnitt leer bliebe; `vorlage_id` nur `[a-z0-9-]+`; Datei entsteht ganz oder gar nicht. Im Export: Änderungen angenommen, keine Kommentare, keine Änderungsverfolgung, keine angehängte Vorlage, keine Custom-Eigenschaften, kein Vorschaubild, Metadaten leer |

MCP-Weg ohne erneute Erkennung (bewusste Abweichung von Nachtrag 1, Datenschutzgrenzen, EGM Task 2 E04): Die
Startart `mcp` lädt keine Erkennung (ADR 0001). Was sie an Claude gibt, kam über geprüfte Wege herein: Dokumente
nur nach `anonymisierung_freigeben`, Freitext nur nach der Freitextprüfung in `eingabe_speichern` und
`text_aendern`, Entwürfe und Befunde schreibt Claude selbst aus diesen Daten. Die erneute Prüfung vor dem Export
läuft deshalb nur im Browser-Weg (`erzeuge_paket`).

Noch nicht gebaut (App-only laut docs/listen.md, folgen mit der Oberfläche in Task 4): `katalog_speichern`,
`stilprofil_freigeben`, `konfiguration_freigeben`, `rollback`. Bis dahin pflegt die Psychologin Konfiguration und
Stilprofil nicht über die App; die Engine liest nur freigegebene Stände.

Browser-Variante (ADR 0002), Namen wie in docs/listen.md:

| Funktion | Eingabe | Ausgabe | Hinweis |
|:--|:--|:--|:--|
| `erzeuge_paket` | `session_id`, `art`; bei `hypothese` zusätzlich `vignette`, `schlussfolgerung` | `fallpaket` | Erkennung (bekannte Namen und Regeln) läuft über alle Freitexte des Pakets erneut, ausgenommen nur Felder mit Zeigern, IDs und Versionen; jeder sichere Treffer blockiert (`E_ANONYMISIERUNG_OFFEN`); ohne Namensliste `E_BLOCKIERT`, Grund `namen_fehlen`. NER und unsichere Treffer sind dort entschieden, wo der Text hereinkam (Freigabe, Freitextprüfung). `diagnosevorschlag` nur mit Q1 und ohne `gutachten_diagnose` (blinder Vergleich); `stil_lernen` nur Dokumente mit `quelle_rolle` Probegutachten; offene Pakete je Sitzung im Datenordner; nie enthalten: interne Diagnose, `awmf_*`, Schweregrad, Dateinamen, Klardaten |
| `lies_rueckgabe` | `session_id`, `text` (JSON oder Chatantwort mit Codeblock) | `gueltig`, Ergebnis je Typ | Ablauf unten; ein Paket nimmt genau eine Rückgabe an |

`lies_rueckgabe` schließt das Paket, bevor es die Rückgabe
speichert: Ein Abbruch dazwischen verliert die Rückgabe, lässt aber nie eine zweite zu. Es prüft in dieser Reihenfolge (ADR 0002, Schritt 4 und Garantien): Schema laut
rueckgabe.schema.json (`E_SCHEMA`); `paket_id` gehört zu einem eigenen, offenen Paket (`E_PAKET_FREMD`);
`pruefe_belege` auf Zahlen, Testnamen, Codes und Quellenreferenzen (`E_BELEG`); Regelergebnis gegen frischen Lauf
(`E_REGELABWEICHUNG`). Die App zeigt "Antwort ungültig" mit dem Grund. Übernommene IDs vergibt die Engine neu,
Entscheidungen stehen auf `offen`.

## Fehlercodes

`E_SCHEMA`, `E_NICHT_GEFUNDEN`, `E_DATEITYP`, `E_MAKRO`, `E_LIBREOFFICE_FEHLT`, `E_BEZEICHNUNG`,
`E_ANONYMISIERUNG_OFFEN`, `E_BLOCKIERT`, `E_Q1`, `E_ABSCHNITT_FEHLT`, `E_KOPFFELD_FEHLT`, `E_PAKET_FREMD`,
`E_BELEG`, `E_REGELABWEICHUNG`, `E_VERSION`, `E_OCR_FEHLT`, `E_INTERN`.

`E_VERSION` erzeugt die App selbst, wenn `status` eine andere `engine_version` oder andere Schema-Versionen meldet
als erwartet; die Engine löst ihn nie aus. Gründe (`grund`): `schema`, `unbekannte_funktion`, `json`, `argumente`,
`datenordner`, `groesse`, `format`, `beschaedigt`, `konflikt`, `namen_fehlen`, `pfad`. Die MCP-Tools melden
Fehler ebenso nur als Code, auch Argumentfehler des MCP-SDK (dessen Meldung den Eingabewert wiederholen würde).

## Vorlagen: Abgleichregel (aus Spike Punkt 5)

- Die echten Vorlagen nutzen Legacy-Formularfelder (FORMTEXT), keine Inhaltssteuerelemente und keine
  Überschriften-Formatvorlagen. Abschnittstitel sind fett formatierte Absätze.
- Normalisierung eines Titels: jede Folge aus Leerraum und Doppelpunkten wird zu einem Leerzeichen, Leerzeichen am
  Rand entfallen, Groß- und Kleinschreibung zählt nicht.
- Abschnitt: fetter Absatz (direkte Formatierung oder Fett aus der Absatz- bzw. Zeichenformatvorlage), dessen
  normalisierter Text gleich `abschnitte[].ueberschrift` ist. Abschnittstext ist das erste FORMTEXT-Feld nach dem
  Titel und vor dem nächsten erkannten Titel; liegt keines dazwischen, gilt der Abschnitt als nicht gefunden.
  Ersetzt wird nur das Feldergebnis, das Feld bleibt erhalten.
- Kopf: Die Kopffelder sind unbenannt und bleiben Platzhalter. Die Psychologin setzt Name, Daten und Geschäftszahl
  im fertigen DOCX selbst ein (Nachtrag 1, Gutachtenstruktur; ADR 0001, Schritt 10). Die Engine prüft nur, dass
  jedes `kopffelder[].bezeichnung` als Beschriftung neben einem Feld vorkommt, und schreibt nichts hinein.
- Nichtfund: kein Raten, kein Anhängen am Ende. Export blockiert mit `E_ABSCHNITT_FEHLT` bzw. `E_KOPFFELD_FEHLT`,
  die App zeigt den Zuordnungsdialog.
