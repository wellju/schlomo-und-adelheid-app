// Case record without the diagnosis fields (sitzung_laden never returns them, docs/ui-api.md).
import { call } from './engine/client';

export type Dokument = { dok_id: string; format: string; quelle_rolle: string; text_anonymisiert?: string;
  freigabe: { status: 'offen' | 'blockiert' | 'freigegeben'; funde_je_kategorie: Record<string, number>; geprueft_bestaetigt?: boolean } };
export type Session = { session_id: string; bezeichnung: string; modus: string; gutachtentyp?: string; status: string; dokumente: Dokument[] };
export type Fall = { session: Session; gutachten_input?: any; entwuerfe?: any[]; befunde?: any[]; [k: string]: any };

export const ladeFall = (sid: string) => call<Fall>('sitzung_laden', { session_id: sid });

// Working copy of an imported document (dokument_text, transient): clear text, app memory only.
export type Teil = { teil: number; art: string; seite: number | null; text: string };
export type Fund = { fund_id: string; kategorie: string; teil: number; start: number; end: number; text: string;
  quelle: string; sicherheit: number; ersatz: string; status: string; unsicher: boolean };
