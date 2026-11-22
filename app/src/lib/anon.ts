// Anonymisation status of the header (AnonStatusBadge): derived from the session's documents only.
export type AnonStatus =
  | { stufe: 'nicht_geprueft' }
  | { stufe: 'offen'; anzahl: number }
  | { stufe: 'unsicher' }
  | { stufe: 'bestaetigt' }
  | { stufe: 'uebersicht'; gesperrt: number }
  | { stufe: 'kein_fall' };

type Dok = { freigabe: { status: string; funde_je_kategorie: Record<string, number> } };
type Session = { modus: string; dokumente: Dok[] };

export function anonVonSession(s: Session): AnonStatus {
  if (s.modus !== 'gutachten') return { stufe: 'kein_fall' }; // Rubberduck holds no imported documents
  if (!s.dokumente.length) return { stufe: 'nicht_geprueft' };
  if (s.dokumente.some((d) => d.freigabe.status === 'blockiert' || d.freigabe.funde_je_kategorie.unsicher > 0)) {
    return { stufe: 'unsicher' };
  }
  const offen = s.dokumente.filter((d) => d.freigabe.status !== 'freigegeben').length;
  return offen ? { stufe: 'offen', anzahl: offen } : { stufe: 'bestaetigt' };
}

export function anonUebersicht(sessions: Session[]): AnonStatus {
  return { stufe: 'uebersicht', gesperrt: sessions.filter((s) => anonVonSession(s).stufe === 'unsicher').length };
}
