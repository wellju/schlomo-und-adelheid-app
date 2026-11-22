# Anleitung Schlomo und Adelheid

Stand 22.11.2026, Version 0.4 (Task 4). Für die Psychologin. Echtbetrieb mit echten Fällen erst nach der Freigabe
nach Task 4; bis dahin nur mit erfundenen Beispielen arbeiten.

## Was die App macht

Die App liest Ihre Dokumente ein, schwärzt sie lokal, nimmt Ihre Eingaben auf, prüft Fachregeln und exportiert das
Gutachten im Layout Ihrer Vorlage. Alles, was eine KI tut (Entwurf, Prüfungen, Rubberduck, Stilprofil,
Diagnosevorschlag), übergibt die App an Claude. Die App hat keinen eigenen Zugang zu Claude und keinen
API-Schlüssel. Sie entscheiden über jeden Vorschlag; nichts wird automatisch übernommen.

## Installation

### Windows

1. Die intelligente App-Steuerung (Smart App Control) muss ausgeschaltet sein; sonst blockiert Windows die Engine.
   Auf einem Dienstgerät klären Sie das mit der IT (Microsoft: support.microsoft.com/kb/5008908).
2. Den Installer `Schlomo und Adelheid_..._x64-setup.exe` starten. Er installiert nur für Ihr Benutzerkonto, ohne
   Administratorrechte.
3. Der Installer ist noch nicht signiert. Windows zeigt dann "Der Computer wurde durch Windows geschützt". Klicken Sie
   auf "Weitere Informationen" und dann auf "Trotzdem ausführen". (Wortlaut nach dem ersten Build auf Ihrem Gerät
   prüfen; offen in docs/task-4-ergebnis.md.)

### macOS (Apple Silicon und Intel)

1. Die passende Datei öffnen (`..._aarch64.dmg` für Apple Silicon, `..._x64.dmg` für Intel) und die App in den
   Ordner Programme ziehen.
2. Die App ist nicht signiert. Beim ersten Start meldet macOS, dass sie nicht geöffnet werden kann. Öffnen Sie dann
   Systemeinstellungen, Datenschutz und Sicherheit, und wählen Sie bei der Meldung zur App "Dennoch öffnen".
   (Wortlaut nach dem ersten Build prüfen.)

### Erster Start

1. Unter Einstellungen die Verbindung wählen: Claude Desktop (Code-Tab) oder Claude im Browser.
2. Die Qualifikation eintragen. Ohne "Klinische Psychologin" bleiben Diagnosefelder und Diagnosevergleich gesperrt.
3. Für Claude Desktop: "Arbeitsordner einrichten" und einen neuen, leeren Ordner wählen, etwa
   `Dokumente\Schlomo Arbeitsordner`. Die App legt dort Skills, Prüfer und die Verbindung zur Engine an.
4. Unter Testkatalog und Regelwerk Ihre Vorlagen importieren und zuordnen, das Regelwerk und die Hinweis-Wortlaute als
   Datei importieren, Verfahren und Kategorienskala mit Quellen eintragen. Die App liefert keine Normwerte,
   Grenzwerte, Regeln oder Verfahren mit; ohne Regelwerk bleibt der Export gesperrt.

## Wo welche Daten liegen

- Echte Gutachten und Originaldokumente bleiben in einem eigenen Ordner außerhalb des Arbeitsordners, etwa
  `Dokumente\Schlomo-Rohdaten`. Die App liest sie nur beim Import und verändert sie nie.
- Der Fallspeicher der App liegt im App-Datenordner Ihres Benutzerkontos. Gespeichert werden nur der freigegebene,
  geschwärzte Text, Ihre Eingaben, Entwürfe und Befunde; nie Originaldateinamen, Geburts- oder Testdatum.
- Der Arbeitsordner für Claude Desktop enthält nie Falldaten. Claude bekommt Falldaten nur über die Engine.
- Schließen Sie die App vor der Bestätigung der Schwärzung, ist der Import verloren. Das ist gewollt.

**Laden Sie nie rohe Dateien direkt in Claude hoch**, weder im Browser noch im Code-Tab. Immer zuerst in der App
importieren und anonymisieren. Was Sie im Rubberduck (Intervision, Supervision) in Claude schreiben, geht ohne
Prüfung der App an Claude: nur anonymisierte Vignetten, Rollen statt Namen, keine Daten, keine Orte, keine seltenen
Merkmale.

## Kapitel Desktop: Arbeiten mit Claude Desktop (Code-Tab)

1. In Claude Desktop den Code-Tab öffnen und den Arbeitsordner wählen. Beim ersten Mal fragt Claude, ob der
   MCP-Server "engine" verwendet werden darf: einmal zustimmen.
2. In der App zeigt jede Übergabe den genauen Befehl, etwa `/gutachten s-1234abcd`. Diesen im Code-Tab eingeben und
   in der App "Übergeben und warten" wählen. Die App zeigt das Ergebnis, sobald es in der Engine gespeichert ist.
3. Gutachten: `/gutachten` schreibt den Entwurf und startet danach Stil, Goldfisch und Elefant, jeder mit frischem
   Kontext. Die Befunde erscheinen in der App unter Entwurf und Prüfung.
4. Intervision und Supervision: `/intervision <id>` bzw. `/supervision <id>`. Die App zeigt Phase, Schlüsselfrage
   und Protokoll. Beenden Sie die Sitzung in der App, nachdem Sie die Schlüsselfrage bestätigt haben.
5. Stilprofil: `/stil-lernen <id>` mit einer Sitzung, in der Probegutachten freigegeben sind. Das Ergebnis ist ein
   Entwurf, den nur Sie in der App freigeben.

Aufbewahrung der Gesprächsverläufe: Claude Desktop hebt Code-Tab-Sitzungen lokal auf. Die Einstellung
`desktopSessionCleanupPeriodDays` (Vorlage: 7 Tage, siehe `benutzer-einstellungen.json` im Installationspaket) wirkt
nur in Ihren Benutzereinstellungen von Claude, nicht im Arbeitsordner. Tragen Sie sie dort ein.

## Kapitel Browser: Arbeiten mit Claude im Browser

1. In der App bei der Übergabe "Paket speichern" wählen und den Ort angeben.
2. Auf claude.ai ein **neues Gespräch** beginnen, das Plugin "Schlomo und Adelheid" ist aktiv (Plugin-ZIP aus dem
   Installationspaket einmal in Claude hinzufügen), und die Paketdatei hochladen.
3. Claude antwortet mit genau einem Codeblock. Die Antwort kopieren und in der App bei "Antwort einfügen"
   einfügen, oder als Datei speichern und wählen.
4. Die App prüft die Antwort (Schema, Paketnummer, Belege, Regelergebnis). Bei "Antwort ungültig" ist Ihr Stand
   unverändert: das Paket erneut speichern und in einem neuen Gespräch übergeben.
5. Reihenfolge beim Gutachten: Entwurf, Stilprüfung, Goldfisch, Elefant, jeweils in einem neuen Gespräch. Im
   Rubberduck sind im Browser alle Berater ein Modell mit gemeinsamem Kontext; sie sind nicht unabhängig.

Aufbewahrung der Gesprächsverläufe: Gespräche auf claude.ai liegen in Ihrem Claude-Konto. Löschen Sie Gespräche mit
Fallbezug nach Abschluss; welche Aufbewahrung für Ihr Konto gilt, steht in den Einstellungen Ihres Kontos und ist mit
dem Arbeitgeber zu klären (offen).

## Lernen und Qualität

Aus Ihren Entscheidungen zu Prüfbefunden und Ihren Textänderungen entstehen Lernsignale. Im Code-Tab schlägt
`/verbessern` daraus eine kleine Änderung an Sprache, Struktur oder Prüfverhalten vor, nur wenn mindestens drei
Signale derselben Art dafür sprechen. Regelwerk, Kategorienskala, Vorlagen, Testkatalog, Hinweis-Wortlaute,
ICD-10-Referenz und Diagnosevergleich sind dafür gesperrt; Supervision fließt nie ein. Die Engine prüft jeden
Vorschlag mit einer Eval-Suite. Vor dem Übernehmen lassen Sie den LLM-Teil der Evals mit dem Vorschlag laufen
(`evals/lernschleife/mit_vorschlag.py` baut die Konfiguration dafür) und bestätigen das in der App. Übernehmen
oder verwerfen Sie unter "Lernen und Qualität"; jede Übernahme ist eine neue Version, die Sie jederzeit zurücksetzen
können.

## Wenn etwas nicht geht

- Die Protokolldatei der Engine heißt `engine.log` und liegt im Log-Ordner der App (Windows:
  `%LOCALAPPDATA%\at.schlomo-und-adelheid.app\logs`, macOS: `~/Library/Logs/at.schlomo-und-adelheid.app`; Pfad nach
  dem ersten Build prüfen).
- Jede Fehlermeldung nennt, was passiert ist, was erhalten blieb, und einen Fehlercode. Die Protokolldatei der Engine
  enthält keine Falldaten und kann an den Support gehen.
- "App und Engine haben unterschiedliche Versionen": die App neu installieren.
- "Gleichzeitig in Claude geändert": neu laden, dann wiederholen.
