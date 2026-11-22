<script lang="ts">
  // Screen 10: test catalogue, rule set (read only, with versions), category scale, templates. No case data here.
  import { anonUebersicht, type AnonStatus } from '../lib/anon';
  import AppShell from '../lib/components/AppShell.svelte';
  import VersionList from '../lib/components/VersionList.svelte';
  import DateiWahl from '../lib/components/DateiWahl.svelte';
  import Zustand from '../lib/components/Zustand.svelte';
  import { fehlerText } from '../lib/engine/fehler';
  import { call } from '../lib/engine/client';
  import KategorienSkala from './katalog/KategorienSkala.svelte';
  import Testkatalog from './katalog/Testkatalog.svelte';
  import Vorlagen from './katalog/Vorlagen.svelte';

  let k = $state<any>(null);
  let anon = $state<AnonStatus>({ stufe: 'uebersicht', gesperrt: 0 });
  let laden = $state(true);
  let fehler = $state<unknown>(null);
  let reiter = $state<'testkatalog' | 'regelwerk' | 'kategorienskala' | 'vorlagen'>('testkatalog');

  async function laden_(still = false) {
    if (!still) { laden = true; fehler = null; }
    try {
      k = await call('konfiguration_laden');
      anon = anonUebersicht((await call<{ sessions: any[] }>('sitzungen_auflisten')).sessions);
    } catch (e) {
      if (!still) fehler = e;
    } finally {
      laden = false;
    }
  }
  laden_();
  const IMPORT = [['regelwerk', 'Regelwerk'], ['hinweise', 'Hinweis-Wortlaute'], ['berater', 'Berater-Perspektiven'],
    ['icd10-referenz', 'ICD-10-Referenz'], ['testkatalog', 'Testkatalog'], ['kategorienskala', 'Kategorienskala']] as const;
  let importArt = $state<string>('regelwerk');
  let importMeldung = $state('');
  let importFehler = $state<string | null>(null);
  async function importieren(pfad: string) {
    importFehler = null;
    importMeldung = '';
    try {
      const r = await call<{ version: string }>('konfiguration_importieren', { name: importArt, pfad });
      importMeldung = `Importiert: Version ${r.version}.`;
      await laden_(true);
    } catch (e) {
      const f = fehlerText(e);
      importFehler = f.code === 'E_SCHEMA' ? 'Die Datei passt nicht zum Schema dieser Art, eine Quelle ist leer oder die Version ist ungültig.'
        : f.code === 'E_BLOCKIERT' ? 'Diese Version gibt es schon. Bitte die Version in der Datei erhöhen.' : f.text;
    }
  }
  const REITER = [['testkatalog', 'Testkatalog'], ['regelwerk', 'Regelwerk'], ['kategorienskala', 'Kategorienskala'], ['vorlagen', 'Vorlagen']] as const;
  function tasten(e: KeyboardEvent) {
    const i = REITER.findIndex(([r]) => r === reiter);
    const n = e.key === 'ArrowRight' ? (i + 1) % REITER.length : e.key === 'ArrowLeft' ? (i + REITER.length - 1) % REITER.length : -1;
    if (n < 0) return;
    reiter = REITER[n][0];
    document.getElementById(`kt-${reiter}`)?.focus();
  }
</script>

<AppShell aktiv="katalog" anonStatus={anon} bereich="Wissen" titel="Testkatalog und Regelwerk">
  <Zustand {laden} {fehler} erneut={() => laden_()} ladenText="Katalog wird geladen …">
    <p class="lb" style="margin:0">Keine Falldaten auf dieser Seite. Verfahren, Normgruppen und Grenzen tragen Sie selbst ein; die App liefert bewusst keine Normwerte, Grenzwerte oder Verfahren mit. Jeder Eintrag braucht eine Quelle.</p>
    <section class="cd box" aria-labelledby="h-imp">
      <h2 class="h3" id="h-imp">Konfigurationsdatei importieren</h2>
      <span class="lb">Regelwerk, Hinweis-Wortlaute, Berater-Perspektiven, ICD-10-Referenz, Testkatalog oder Kategorienskala als JSON-Datei. Geprüft wie jede Änderung; der bisherige Stand bleibt als Version.</span>
      <div class="row">
        <div><label class="lb" for="imp-art">Art</label>
          <select class="in" id="imp-art" bind:value={importArt}>{#each IMPORT as [v, l] (v)}<option value={v}>{l}</option>{/each}</select></div>
      </div>
      <DateiWahl id="imp-pfad" label="Konfiguration importieren" endungen={['json']} onwahl={importieren} />
      <div role="status">{importMeldung}</div>
      {#if importFehler}<div class="err" role="alert">✕ {importFehler} Der bisherige Stand gilt weiter.</div>{/if}
    </section>
    <div role="tablist" aria-label="Bereiche" class="row" tabindex="-1" onkeydown={tasten}>
      {#each REITER as [r, l] (r)}
        <button role="tab" type="button" class="btn" id="kt-{r}" aria-selected={reiter === r} aria-controls="kp-{r}" tabindex={reiter === r ? 0 : -1} onclick={() => (reiter = r)}>{l}</button>
      {/each}
    </div>
    <div role="tabpanel" id="kp-{reiter}" aria-labelledby="kt-{reiter}">
      {#if reiter === 'testkatalog'}
        <Testkatalog katalog={k?.testkatalog} versionen={k?.versionen?.testkatalog ?? []} ongeaendert={() => laden_(true)} />
      {:else if reiter === 'kategorienskala'}
        <KategorienSkala skala={k?.kategorienskala} versionen={k?.versionen?.kategorienskala ?? []} ongeaendert={() => laden_(true)} />
      {:else if reiter === 'vorlagen'}
        <Vorlagen vorlagen={k?.vorlagen ?? []} ongeaendert={() => laden_(true)} />
      {:else}
        <section class="stack" aria-label="Regelwerk">
          {#if !k?.regelwerk}
            <div class="empty"><h3 class="h2" style="color:var(--tx)">Kein Regelwerk</h3><div>Ohne Regelwerk ist jede Regel nicht prüfbar und der Export gesperrt.</div></div>
          {:else}
            <div class="row"><span class="pl na">Version {k.regelwerk.version}</span><span class="lb">Das Regelwerk ändern Sie nicht in der App; Lernvorschläge dürfen es nie verändern.</span></div>
            <div class="cd tbx"><table class="t"><caption class="sr">Regelwerk Version {k.regelwerk.version}</caption>
              <thead><tr><th scope="col">ID</th><th scope="col">Regel</th><th scope="col">Gutachtentyp</th><th scope="col">Quelle</th><th scope="col">Status</th></tr></thead>
              <tbody>{#each k.regelwerk.regeln as r (r.regel_id)}<tr><td>{r.regel_id}</td><td>{r.titel}{r.beschreibung && r.beschreibung !== r.titel ? ` · ${r.beschreibung}` : ''}</td>
                <td>{r.gutachtentyp.join(', ')}</td><td>{Object.values(r.quelle).join(', ')}</td>
                <td><span class="pl {r.status === 'freigegeben' ? 'ok' : 'na'}">{r.status === 'freigegeben' ? '✓ Freigegeben' : r.status === 'ausser_kraft' ? 'Außer Kraft' : 'Entwurf'}</span></td></tr>{/each}</tbody></table></div>
            <VersionList name="regelwerk" aktiv={k.regelwerk.version} versionen={k.versionen?.regelwerk ?? []} ongeaendert={() => laden_(true)} />
          {/if}
        </section>
      {/if}
    </div>
  </Zustand>
</AppShell>

<style>
  .box { padding: 16px; display: flex; flex-direction: column; gap: 10px; }
  [role="tab"][aria-selected="true"] { border-color: var(--ac); color: var(--ac); background: var(--acS); }
</style>
