// Engine categories (recognition.KATEGORIEN) to the design's marks. The design draws seven types; the engine
// recognises five, so PER also covers contact data and file numbers, ORT also schools (docs/task-4-ergebnis.md).
export const KATEGORIE: Record<string, { tag: string; klasse: string; label: string }> = {
  direkte_identifikatoren: { tag: 'PER', klasse: 'm-per', label: 'Person, Kontakt, Aktenzahl' },
  datumsangaben: { tag: 'DAT', klasse: 'm-dat', label: 'Datum' },
  orte_einrichtungen: { tag: 'ORT', klasse: 'm-ort', label: 'Ort, Schule, Einrichtung' },
  seltene_merkmale: { tag: 'SEL', klasse: 'm-sel', label: 'seltenes Merkmal' },
  versteckte_inhalte: { tag: 'VER', klasse: 'm-akz', label: 'versteckter Inhalt' },
};
export const SICHTBAR = ['haupttext', 'kopf_fusszeile', 'fussnote'];

export const FORMAT: Record<string, string> = {
  pdf_text: 'PDF', pdf_scan: 'PDF (Scan)', docx: 'DOCX', xlsx: 'XLSX', jpg: 'JPG', png: 'PNG', heic: 'HEIC',
  doc: 'DOC (über LibreOffice)', xls: 'XLS (über LibreOffice)',
};

export const GUTACHTENTYP: Record<string, string> = {
  spf: 'SPF', lrs: 'LRS', rechenstoerung: 'Rechenstörung', emotional_soziale_entwicklung: 'Emotional-soziale Entwicklung',
};

export const STATUS: Record<string, { label: string; ton: 'na' | 'ai' | 'ok' | 'wn' }> = {
  import: { label: 'Import', ton: 'na' }, eingabe: { label: 'Eingabe', ton: 'na' }, entwurf: { label: 'Entwurf', ton: 'na' },
  pruefung: { label: 'In Prüfung', ton: 'ai' }, abgeschlossen: { label: 'Exportiert', ton: 'ok' },
  abgebrochen: { label: 'Abgebrochen', ton: 'wn' },
};
