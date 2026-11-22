// German texts per error code (docs/ui-api.md). The engine sends only code and reason, never content.
import { EngineFehler } from './client';

const CODES: Record<string, string> = {
  E_SCHEMA: 'Die Eingabe hat nicht das erwartete Format.',
  E_NICHT_GEFUNDEN: 'Der Eintrag wurde nicht gefunden.',
  E_DATEITYP: 'Dieser Dateityp wird nicht unterstützt.',
  E_MAKRO: 'Die Datei enthält Makros und wird nicht geöffnet.',
  E_LIBREOFFICE_FEHLT: 'Für DOC und XLS wird LibreOffice benötigt, es wurde nicht gefunden.',
  E_BEZEICHNUNG: 'Die Bezeichnung enthält vermutlich einen Namen oder ein Kürzel. Bitte neutral benennen, etwa „Fall 7“.',
  E_ANONYMISIERUNG_OFFEN: 'Die Anonymisierung ist noch nicht vollständig geprüft.',
  E_BLOCKIERT: 'Der Schritt ist gesperrt.',
  E_Q1: 'Nur mit der Qualifikation „Klinische Psychologin“ möglich.',
  E_ABSCHNITT_FEHLT: 'Ein Abschnitt der Vorlage wurde nicht gefunden.',
  E_KOPFFELD_FEHLT: 'Ein Kopffeld der Vorlage wurde nicht gefunden.',
  E_PAKET_FREMD: 'Die Antwort gehört zu einem anderen Paket.',
  E_BELEG: 'Die Belegprüfung ist fehlgeschlagen: Ein Satz verweist auf keine Eingabe.',
  E_REGELABWEICHUNG: 'Die Antwort weicht vom Ergebnis der Fachregelprüfung ab.',
  E_PHASENFOLGE: 'Dieser Schritt passt nicht zur aktuellen Phase.',
  E_VERSION: 'App und Engine haben unterschiedliche Versionen. Bitte die App neu installieren.',
  E_OCR_FEHLT: 'Texterkennung (Tesseract) ist nicht verfügbar.',
  E_INTERN: 'In der Engine ist ein unerwarteter Fehler aufgetreten.',
};

const GRUENDE: Record<string, string> = {
  schema: 'Format nicht gültig',
  unbekannte_funktion: 'Funktion unbekannt',
  json: 'Nachricht nicht lesbar',
  argumente: 'Angaben unvollständig',
  datenordner: 'Datenordner liegt im Arbeitsordner',
  groesse: 'Datei zu groß',
  format: 'Format nicht erkannt',
  beschaedigt: 'Datei beschädigt',
  konflikt: 'Gleichzeitig in Claude geändert, bitte neu laden',
  namen_fehlen: 'Namensliste fehlt',
  pfad: 'Pfad nicht erlaubt',
  hinweise_fehlen: 'Hinweis-Wortlaute fehlen in der Konfiguration',
  pruefung_fehlt: 'Eine Prüfung fehlt noch',
  zeitlimit: 'Die Engine hat nicht rechtzeitig geantwortet',
  gesperrt: 'Diese Datei ist für Lernvorschläge gesperrt',
  signale: 'Lernsignale unbekannt, von anderer Herkunft, anderem Bereich oder Prüfer, oder schon verwendet',
};

export function fehlerText(e: unknown): { code: string; text: string; grund: string | null } {
  if (e instanceof EngineFehler) {
    return { code: e.code, text: CODES[e.code] ?? CODES.E_INTERN, grund: e.grund ? (GRUENDE[e.grund] ?? e.grund) : null };
  }
  return { code: 'E_INTERN', text: 'Die Verbindung zur Engine ist unterbrochen.', grund: null };
}
