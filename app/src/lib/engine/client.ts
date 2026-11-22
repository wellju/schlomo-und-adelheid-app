// One entry point to the engine (docs/ui-api.md). The transport is the Tauri shell in the app and the development
// bridge under `vite serve`; both speak the same JSON lines. Errors carry only a code and a fixed reason.
export class EngineFehler extends Error {
  constructor(public code: string, public grund: string | null = null) {
    super(code);
  }
}

/** Called when the shell reports a terminated engine: its memory (names, working copies) is gone. */
export const beiEngineEnde: (() => void)[] = [];

export type Ereignis = { event: string; [k: string]: unknown };
type Antwort = { id?: string; ok: boolean; result?: any; fehler?: { code: string; grund: string | null }; event?: string };
export interface Transport {
  send(fn: string, args: object, onEvent?: (e: Ereignis) => void): Promise<Antwort>;
}

class DevTransport implements Transport {
  constructor(private token: string) {}
  async send(fn: string, args: object, onEvent?: (e: Ereignis) => void): Promise<Antwort> {
    const res = await fetch('/__engine', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-schlomo-token': this.token },
      body: JSON.stringify({ fn, args }),
    });
    const reader = res.body!.pipeThrough(new TextDecoderStream()).getReader();
    let buf = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (value) buf += value;
      let i: number;
      while ((i = buf.indexOf('\n')) >= 0) {
        const msg = JSON.parse(buf.slice(0, i)) as Antwort;
        buf = buf.slice(i + 1);
        if (msg.event) onEvent?.(msg as unknown as Ereignis);
        else return msg;
      }
      if (done) return { ok: false, fehler: { code: 'E_INTERN', grund: null } };
    }
  }
}

class TauriTransport implements Transport {
  private pending = new Map<string, { done: (a: Antwort) => void; onEvent?: (e: Ereignis) => void }>();
  private seq = 0;
  private ready: Promise<void>;
  constructor() {
    this.ready = import('@tauri-apps/api/event').then(({ listen }) =>
      listen<string>('engine-line', ({ payload }) => {
        const msg = JSON.parse(payload) as Antwort;
        if (msg.id === 'engine-ende') { // the shell reports a terminated engine: every open call fails
          for (const [, p] of this.pending) p.done({ ok: false, fehler: { code: 'E_INTERN', grund: null } });
          this.pending.clear();
          beiEngineEnde.forEach((f) => f());
          return;
        }
        const p = msg.id ? this.pending.get(msg.id) : undefined;
        if (!p) return;
        if (msg.event) p.onEvent?.(msg as unknown as Ereignis);
        else {
          this.pending.delete(msg.id!);
          p.done(msg);
        }
      }).then(() => undefined),
    );
  }
  async send(fn: string, args: object, onEvent?: (e: Ereignis) => void): Promise<Antwort> {
    await this.ready;
    const { invoke } = await import('@tauri-apps/api/core');
    const id = `a-${++this.seq}`;
    return new Promise((done) => {
      this.pending.set(id, { done, onEvent });
      invoke('engine_send', { line: JSON.stringify({ id, fn, args }) }).catch(() => {
        this.pending.delete(id);
        done({ ok: false, fehler: { code: 'E_INTERN', grund: null } });
      });
    });
  }
}

function pick(): Transport {
  if ('__TAURI_INTERNALS__' in window) return new TauriTransport();
  if (import.meta.env.DEV) { // constant false in a production build: the bridge client is removed
    const token = document.querySelector<HTMLMetaElement>('meta[name="schlomo-dev-token"]')?.content;
    if (token) return new DevTransport(token);
  }
  throw new Error('Keine Verbindung zur Engine');
}

let transport: Transport | null = null;
export const istEntwicklung = () => !('__TAURI_INTERNALS__' in window);

// Time limit per call (EGM B7): a hanging engine gives an error instead of an endless skeleton. Import, OCR and
// recognition of a long document may take minutes.
const LANG = new Set(['dokument_importieren', 'ocr_ausfuehren', 'erkennung_ausfuehren', 'anonymisierung_freigeben', 'docx_exportieren']);
const zeitlimit = (fn: string) => (LANG.has(fn) ? 15 * 60_000 : 120_000);

export async function call<T = any>(fn: string, args: object = {}, onEvent?: (e: Ereignis) => void): Promise<T> {
  transport ??= pick();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const ablauf = new Promise<Antwort>((done) => {
    timer = setTimeout(() => done({ ok: false, fehler: { code: 'E_INTERN', grund: 'zeitlimit' } }), zeitlimit(fn));
  });
  const a = await Promise.race([transport.send(fn, args, onEvent), ablauf]).finally(() => clearTimeout(timer));
  if (!a.ok) throw new EngineFehler(a.fehler?.code ?? 'E_INTERN', a.fehler?.grund ?? null);
  return a.result as T;
}

declare const __ERWARTET__: { engine_version: string; schema_versionen: Record<string, string> };

/** Version handshake at start; a mismatch is E_VERSION, raised by the app itself (docs/ui-api.md). */
export async function handshake(): Promise<{ engine_version: string }> {
  const s = await call<{ engine_version: string; schema_versionen: Record<string, string> }>('status');
  if (s.engine_version !== __ERWARTET__.engine_version ||
      JSON.stringify(s.schema_versionen) !== JSON.stringify(__ERWARTET__.schema_versionen)) {
    throw new EngineFehler('E_VERSION');
  }
  return s;
}
