// Known names per session (stage 1 of the recognition): app memory only, never stored, never logged; sent again
// after every engine start (docs/ui-api.md).
import { beiEngineEnde, call } from './engine/client';

export type Name = { text: string; rolle: string };
export const namen = $state<Record<string, Name[]>>({});
const gesendet = new Set<string>();

export async function namenSenden(sid: string): Promise<{ bezeichnung_enthaelt_namen: boolean }> {
  const liste = (namen[sid] ?? []).filter((n) => n.text.trim() && n.rolle.trim());
  const r = await call<{ bezeichnung_enthaelt_namen: boolean }>('bekannte_namen_setzen', { session_id: sid, namen: liste });
  gesendet.add(sid);
  return r;
}
export const namenGesendet = (sid: string) => gesendet.has(sid);
export function namenVergessen() { gesendet.clear(); } // after an engine restart
beiEngineEnde.push(namenVergessen);
