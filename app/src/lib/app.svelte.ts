// App-wide state: engine connection and settings (Screen 13). Settings live in the engine's data folder, not here.
import { call, handshake } from './engine/client';

export type Einstellungen = {
  schema_version: '1';
  verbindung: 'desktop' | 'browser';
  qualifikationen: ('schulpsychologin' | 'klinische_psychologin' | 'gesundheitspsychologin')[];
  darstellung: 'system' | 'hell' | 'dunkel';
};

export const app = $state({
  verbunden: false,
  startFehler: null as unknown,
  engineVersion: '',
  einstellungen: null as Einstellungen | null,
  eingerichtet: false,
  einstellungenBeschaedigt: false,
});

export const hatQ1 = () => !!app.einstellungen?.qualifikationen.includes('klinische_psychologin');

export function darstellungSetzen(d: Einstellungen['darstellung']) {
  document.documentElement.dataset.theme = d;
  try { localStorage.setItem('darstellung', d); } catch { /* storage may be blocked; the engine keeps the setting */ }
}

export async function starten() {
  app.startFehler = null;
  try {
    const s = await handshake();
    app.engineVersion = s.engine_version;
    const r = await call<{ einstellungen: Einstellungen; vorhanden: boolean; beschaedigt: boolean }>('einstellungen_laden');
    app.einstellungen = r.einstellungen;
    app.eingerichtet = r.vorhanden;
    app.einstellungenBeschaedigt = r.beschaedigt;
    darstellungSetzen(app.einstellungen.darstellung);
    app.verbunden = true;
  } catch (e) {
    app.verbunden = false;
    app.startFehler = e;
  }
}
