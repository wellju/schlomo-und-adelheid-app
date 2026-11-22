<script lang="ts">
  // Screen 06: preview in the order and with the headings of the template, header fields stay placeholders, no
  // diagnosis section for SPF; export only through the engine (all locks there), never over an existing file.
  import { anonVonSession } from '../lib/anon';
  import AppShell from '../lib/components/AppShell.svelte';
  import Zustand from '../lib/components/Zustand.svelte';
  import { speichern as speichernDialog, pfadFeld } from '../lib/datei';
  import { call } from '../lib/engine/client';
  import { fehlerText } from '../lib/engine/fehler';
  import { ladeFall, type Fall } from '../lib/fall';
  import { href } from '../lib/router.svelte';

  let { sid }: { sid: string } = $props();
  let fall = $state<Fall | null>(null);
  let vorschau = $state<any>(null);
  let laden = $state(true);
  let fehler = $state<unknown>(null);
  let leer = $state(false);
  let pfad = $state('');
  let ergebnis = $state<string | null>(null);
  let exportFehler = $state<string | null>(null);

  async function laden_() {
    laden = true;
    fehler = null;
    leer = false;
    try {
      fall = await ladeFall(sid);
      if (!fall.entwuerfe?.length) { leer = true; return; }
      vorschau = await call('export_vorschau', { session_id: sid });
    } catch (e) {
      fehler = e;
    } finally {
      laden = false;
    }
  }
  laden_();

  const SPERRE: Record<string, string> = {
    E_BLOCKIERT: 'Eine Regel mit der Wirkung „sperrt den Export“ ist nicht erfüllt oder nicht prüfbar, das Regelwerk fehlt, oder der Gutachtentyp hat keine Vorlage.',
    E_BELEG: 'Ein Satz oder Lückenhinweis verweist auf kein Eingabefeld.',
    E_NICHT_GEFUNDEN: 'Die Vorlage ist nicht importiert oder nicht zugeordnet.',
    E_SCHEMA: 'Die Vorlage des Entwurfs ist ungültig.',
  };

  async function exportieren() {
    exportFehler = ergebnis = null;
    try {
      const ziel = pfadFeld() ? pfad.trim() : await speichernDialog('Word-Dokument', 'docx', 'Gutachten.docx');
      if (!ziel) return;
      const r = await call<{ entwurf_version: number }>('docx_exportieren', { session_id: sid, ziel_pfad: ziel });
      ergebnis = `Exportiert: Entwurf Version ${r.entwurf_version}. Namen und Kopfdaten setzen Sie jetzt im Dokument ein.`;
    } catch (e) {
      const f = fehlerText(e);
      exportFehler = f.code === 'E_BLOCKIERT' && !vorschau?.sperre ? 'Die Zieldatei gibt es schon. Bitte einen neuen Namen wählen.' : f.text;
    }
  }
</script>

<AppShell aktiv="faelle" anonStatus={fall ? anonVonSession(fall.session) : { stufe: 'nicht_geprueft' }} bereich={fall?.session.bezeichnung ?? 'Fall'}
          titel="Export" fall={fall ? { session_id: sid, bereich: 'export', modus: fall.session.modus } : undefined}>
  <Zustand {laden} {fehler} erneut={laden_} ladenText="Vorschau wird erstellt …" {leer} leerTitel="Noch kein Entwurf"
           leerText="Exportiert wird der aktuelle Entwurf im Layout Ihrer Vorlage.">
    {#snippet leerAktion()}<a class="btn p" href={href('fall', sid, 'pruefung')}>Zu Entwurf und Prüfung</a>{/snippet}
    {#snippet warnung()}
      {#if vorschau?.sperre}
        <div class="warn" role="status"><strong style="color:var(--wnT)">! Export gesperrt.</strong> {SPERRE[vorschau.sperre.code] ?? 'Der Export ist gesperrt.'}
          {#if vorschau.sperre.code === 'E_NICHT_GEFUNDEN'}<a href={href('katalog')}>Vorlage importieren</a>{/if}</div>
      {/if}
    {/snippet}
    {#if vorschau}
      <div class="zwei">
        <article class="cd seite doc" aria-label="Vorschau im Layout der Vorlage">
          {#if vorschau.kopffelder.length}
            <dl class="kopf">{#each vorschau.kopffelder as k (k.platzhalter)}<dt>{k.bezeichnung}</dt><dd>[{k.bezeichnung}]</dd>{/each}</dl>
          {/if}
          {#each vorschau.abschnitte as a (a.abschnitt_id)}
            {#if !(fall?.session.gutachtentyp === 'spf' && a.abschnitt_id === 'diagnose')}
              <h2 class="h3">{vorschau.ueberschriften[a.abschnitt_id] ?? a.abschnitt_id}</h2>
              {#if a.text}<p class="absatz">{a.text}</p>{/if}
              {#each a.tabellen as rows, i (i)}
                <table class="t"><caption class="sr">Tabelle {i + 1}</caption>
                  <tbody>{#each rows as r, j (j)}<tr>{#each r as c, k (k)}{#if j === 0}<th scope="col">{c}</th>{:else}<td>{c}</td>{/if}{/each}</tr>{/each}</tbody></table>
              {/each}
            {/if}
          {/each}
        </article>
        <section class="cd box" aria-labelledby="h-exp">
          <h2 class="h3" id="h-exp">Als DOCX exportieren</h2>
          <ul class="lb"><li>Kopf aus den Platzhaltern der Vorlage, Logo bleibt</li><li>Keine Kommentare, keine Änderungsverfolgung, Metadaten leer</li>
            {#if fall?.session.gutachtentyp === 'spf'}<li>Kein Diagnoseabschnitt im SPF-Gutachten</li>{/if}<li>Eine vorhandene Datei wird nie überschrieben</li></ul>
          {#if pfadFeld()}<label class="lb" for="ziel">Zieldatei: Pfad (nur Entwicklung)</label><input class="in" id="ziel" bind:value={pfad}>{/if}
          <button class="btn p" type="button" aria-disabled={!!vorschau.sperre} onclick={() => !vorschau.sperre && exportieren()}>
            {vorschau.sperre ? 'Export gesperrt' : 'DOCX exportieren'}</button>
          <div role="status">{ergebnis ?? ''}</div>
          {#if exportFehler}<div class="err" role="alert">✕ {exportFehler} Es wurde keine Datei geschrieben.</div>{/if}
        </section>
      </div>
    {/if}
  </Zustand>
</AppShell>

<style>
  .zwei { display: grid; grid-template-columns: minmax(0, 3fr) minmax(280px, 1fr); gap: 20px; align-items: start; }
  .seite { padding: 32px 40px; }
  .absatz { white-space: pre-wrap; }
  .kopf { display: grid; grid-template-columns: max-content 1fr; gap: 2px 16px; margin: 0 0 20px; font-family: Inter, system-ui, sans-serif; font-size: 13px; }
  .kopf dd { margin: 0; color: var(--mu); }
  .box { padding: 16px; display: flex; flex-direction: column; gap: 10px; }
  ul { margin: 0; padding-left: 18px; }
  .btn[aria-disabled="true"] { opacity: .55; cursor: not-allowed; }
  @media (max-width: 1023px) { .zwei { grid-template-columns: 1fr; } }
</style>
