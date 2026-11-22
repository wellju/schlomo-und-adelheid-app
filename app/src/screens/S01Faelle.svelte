<script lang="ts">
  // Screen 01: case overview, new case with report type (emotional-social development: draft and export locked).
  import { anonUebersicht, anonVonSession } from '../lib/anon';
  import AnonStatusBadge from '../lib/components/AnonStatusBadge.svelte';
  import AppShell from '../lib/components/AppShell.svelte';
  import Zustand from '../lib/components/Zustand.svelte';
  import { call } from '../lib/engine/client';
  import { fehlerText } from '../lib/engine/fehler';
  import { GUTACHTENTYP, STATUS } from '../lib/kategorien';
  import { gehe, href } from '../lib/router.svelte';

  type Session = { session_id: string; bezeichnung: string; modus: string; gutachtentyp?: string; status: string; dokumente: any[] };
  let sessions = $state<Session[]>([]);
  let laden = $state(true);
  let fehler = $state<unknown>(null);
  let suche = $state('');
  let filter = $state<'alle' | 'entwurf' | 'pruefung' | 'abgeschlossen'>('alle');
  let neu = $state({ bezeichnung: '', modus: 'gutachten', gutachtentyp: 'spf' });
  let anlegeFehler = $state<string | null>(null);

  async function laden_() {
    laden = true;
    fehler = null;
    try {
      sessions = (await call<{ sessions: Session[] }>('sitzungen_auflisten')).sessions;
    } catch (e) {
      fehler = e;
    } finally {
      laden = false;
    }
  }
  laden_();

  const gesperrt = $derived(sessions.filter((s) => anonVonSession(s).stufe === 'unsicher'));
  const sichtbar = $derived(sessions.filter((s) =>
    (filter === 'alle' || (filter === 'entwurf' ? ['import', 'eingabe', 'entwurf'].includes(s.status) : s.status === filter)) &&
    s.bezeichnung.toLowerCase().includes(suche.trim().toLowerCase())));

  async function anlegen(e: SubmitEvent) {
    e.preventDefault();
    anlegeFehler = null;
    try {
      const args = neu.modus === 'gutachten' ? neu : { bezeichnung: neu.bezeichnung, modus: neu.modus };
      const r = await call<{ session: Session }>('sitzung_anlegen', args);
      const s = r.session;
      gehe(...(s.modus === 'gutachten' ? ['fall', s.session_id, 'dokumente'] : [s.modus, s.session_id]));
    } catch (err) {
      anlegeFehler = fehlerText(err).text;
    }
  }
  const ziel = (s: Session) => (s.modus === 'gutachten' ? href('fall', s.session_id, 'dokumente') : href(s.modus, s.session_id));
  const FILTER = [['alle', 'Alle'], ['entwurf', 'Entwurf'], ['pruefung', 'In Prüfung'], ['abgeschlossen', 'Exportiert']] as const;
</script>

<AppShell aktiv="faelle" anonStatus={anonUebersicht(sessions)} bereich="Übersicht" titel="Fälle">
  <form class="cd neu" onsubmit={anlegen} aria-labelledby="h-neu">
    <h2 class="h3" id="h-neu">Neuer Fall oder neue Sitzung</h2>
    <div class="felder">
      <div><label class="lb" for="bez">Neutrale Bezeichnung</label><input class="in" id="bez" required maxlength="40" bind:value={neu.bezeichnung} placeholder="z. B. Fall 15"></div>
      <div><label class="lb" for="modus">Art</label>
        <select class="in" id="modus" bind:value={neu.modus}><option value="gutachten">Gutachten</option><option value="intervision">Intervision</option><option value="supervision">Supervision</option></select></div>
      {#if neu.modus === 'gutachten'}
        <div><label class="lb" for="gtyp">Gutachtentyp</label>
          <select class="in" id="gtyp" bind:value={neu.gutachtentyp}>
            <option value="spf">SPF</option><option value="lrs">LRS</option><option value="rechenstoerung">Rechenstörung</option>
            <option value="emotional_soziale_entwicklung">Emotional-soziale Entwicklung (Entwurf und Export gesperrt, keine Vorlage)</option>
          </select></div>
      {/if}
      <button class="btn p" type="submit">+ Anlegen</button>
    </div>
    <span class="lb">Kinder werden nur mit Platzhaltern wie „Kind A“ geführt. Keine Namen, keine Initialen in der Bezeichnung.</span>
    {#if anlegeFehler}<div class="err" role="alert">✕ {anlegeFehler}</div>{/if}
  </form>

  <Zustand {laden} {fehler} erneut={laden_} ladenText="Fälle werden geladen …" leer={!sessions.length} leerTitel="Noch keine Fälle"
           leerText="Ein Fall bündelt Dokumente, Anonymisierung, Eingaben und den Gutachtenentwurf. Legen Sie oben den ersten Fall an.">
    {#snippet warnung()}
      {#if gesperrt.length}
        <div class="warn" role="status"><strong style="color:var(--wnT)">! {gesperrt.length} {gesperrt.length === 1 ? 'Fall' : 'Fälle'} mit unsicherer Anonymisierung.</strong>
          Gesperrt für KI-Prüfung und Rubberduck, bis die Funde geprüft sind:
          {#each gesperrt as s, i (s.session_id)}{i ? ', ' : ' '}<a href={href('fall', s.session_id, 'anonymisierung')}>{s.bezeichnung}</a>{/each}</div>
      {/if}
    {/snippet}
    <div class="row">
      <div style="flex:1 1 280px;max-width:420px"><label class="lb" for="such">Fälle durchsuchen</label><input class="in" id="such" type="search" bind:value={suche}></div>
      <div class="row" role="group" aria-label="Statusfilter">
        {#each FILTER as [k, l] (k)}<button class="btn s" type="button" aria-pressed={filter === k} onclick={() => (filter = k)}>{l}</button>{/each}
      </div>
    </div>
    <div class="cd tbx">
      <table class="t">
        <thead><tr><th scope="col">Fall</th><th scope="col">Art</th><th scope="col">Status</th><th scope="col">Anonymisierung</th><th scope="col">Bereiche</th></tr></thead>
        <tbody>
          {#each sichtbar as s (s.session_id)}
            <tr>
              <td><a href={ziel(s)}><strong>{s.bezeichnung}</strong></a></td>
              <td>{s.modus === 'gutachten' ? GUTACHTENTYP[s.gutachtentyp!] : s.modus === 'intervision' ? 'Intervision' : 'Supervision'}</td>
              <td><span class="pl {STATUS[s.status].ton}">{STATUS[s.status].label}</span></td>
              <td><AnonStatusBadge status={anonVonSession(s)} live={false} /></td>
              <td><div class="row">
                {#if s.modus === 'gutachten'}
                  <a class="btn s" href={href('fall', s.session_id, 'dokumente')}>Dokumente</a>
                  <a class="btn s" href={href('fall', s.session_id, 'eingabe')}>Gutachten</a>
                {:else}
                  <a class="btn s" href={ziel(s)}>Fortsetzen</a>
                {/if}
              </div></td>
            </tr>
          {:else}
            <tr><td colspan="5" class="mu">Kein Fall passt zur Suche oder zum Filter.</td></tr>
          {/each}
        </tbody>
      </table>
    </div>
  </Zustand>
</AppShell>

<style>
  .neu { padding: 16px; display: flex; flex-direction: column; gap: 10px; }
  .felder { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; align-items: end; }
</style>
