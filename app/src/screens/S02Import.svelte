<script lang="ts">
  // Screen 02: document import (original only read, working copy in the engine's memory), OCR with progress.
  import { anonVonSession } from '../lib/anon';
  import AppShell from '../lib/components/AppShell.svelte';
  import BekannteNamen from '../lib/components/BekannteNamen.svelte';
  import DateiWahl from '../lib/components/DateiWahl.svelte';
  import Zustand from '../lib/components/Zustand.svelte';
  import { call } from '../lib/engine/client';
  import { fehlerText } from '../lib/engine/fehler';
  import { ladeFall, type Fall } from '../lib/fall';
  import { FORMAT } from '../lib/kategorien';
  import { href } from '../lib/router.svelte';

  let { sid }: { sid: string } = $props();
  let fall = $state<Fall | null>(null);
  let laden = $state(true);
  let fehler = $state<unknown>(null);
  let rolle = $state('');
  let importFehler = $state<{ text: string; code: string } | null>(null);
  let bezeichnungHatNamen = $state(false);
  // Per imported document in this app run: OCR state, hidden parts and whether the working copy is still in memory.
  let lokal = $state<Record<string, { seiten: number; ocr: 'noetig' | 'laeuft' | 'fertig' | 'keine'; anteil: number; imSpeicher: boolean }>>({});

  async function laden_() {
    laden = true;
    fehler = null;
    try {
      fall = await ladeFall(sid);
      for (const d of fall.session.dokumente) {
        if (d.freigabe.status === 'freigegeben' || lokal[d.dok_id]) continue;
        try {
          const t = await call<{ ocr_offen: number }>('dokument_text', { session_id: sid, dok_id: d.dok_id });
          lokal[d.dok_id] = { seiten: 0, ocr: t.ocr_offen ? 'noetig' : 'keine', anteil: 0, imSpeicher: true };
        } catch {
          lokal[d.dok_id] = { seiten: 0, ocr: 'keine', anteil: 0, imSpeicher: false }; // app or engine restarted
        }
      }
    } catch (e) {
      fehler = e;
    } finally {
      laden = false;
    }
  }
  laden_();

  async function importieren(pfad: string) {
    importFehler = null;
    if (!rolle.trim()) {
      importFehler = { text: 'Bitte zuerst die Quelle als Rolle angeben, etwa „Bericht der Klassenlehrerin“.', code: 'E_SCHEMA' };
      return;
    }
    try {
      const r = await call<{ dok_id: string; seiten: number; ocr_noetig: boolean }>('dokument_importieren',
        { session_id: sid, pfad, quelle_rolle: rolle.trim() });
      lokal[r.dok_id] = { seiten: r.seiten, ocr: r.ocr_noetig ? 'noetig' : 'keine', anteil: 0, imSpeicher: true };
      rolle = '';
      fall = await ladeFall(sid);
    } catch (e) {
      const f = fehlerText(e);
      importFehler = { text: f.text, code: f.code };
    }
  }

  async function ocr(dok_id: string) {
    lokal[dok_id].ocr = 'laeuft';
    try {
      await call('ocr_ausfuehren', { session_id: sid, dok_id }, (ev) => {
        if (typeof ev.anteil === 'number') lokal[dok_id].anteil = ev.anteil;
      });
      lokal[dok_id].ocr = 'fertig';
    } catch (e) {
      lokal[dok_id].ocr = 'noetig';
      importFehler = { ...fehlerText(e) };
    }
  }

  const FREIGABE = { offen: ['wn', '! Anonymisierung offen'], blockiert: ['er', '✕ Unsicher · gesperrt'], freigegeben: ['ok', '✓ Schwärzung bestätigt'] } as const;
</script>

<AppShell aktiv="faelle" anonStatus={fall ? anonVonSession(fall.session) : { stufe: 'nicht_geprueft' }} bereich={fall?.session.bezeichnung ?? 'Fall'}
          titel="Dokumente importieren" fall={fall ? { session_id: sid, bereich: 'dokumente', modus: fall.session.modus } : undefined}>
  <Zustand {laden} {fehler} erneut={laden_} ladenText="Dokumente werden geladen …">
    {#if bezeichnungHatNamen}
      <div class="warn" role="status"><strong style="color:var(--wnT)">! Die Bezeichnung des Falls enthält einen der Namen.</strong> Bitte den Fall neutral umbenennen.</div>
    {/if}
    <BekannteNamen {sid} ongesetzt={(hit) => (bezeichnungHatNamen = hit)} />
    <section class="cd box" aria-labelledby="h-imp">
      <h2 class="h3" id="h-imp">Dokument hinzufügen</h2>
      <p class="lb" style="margin:0">PDF, DOCX, XLSX, JPG, PNG, HEIC. DOC und XLS nur mit installiertem LibreOffice. Das Original wird nur gelesen, nie verändert; die Arbeitskopie bleibt im Arbeitsspeicher, bis Sie die Schwärzung bestätigen. Schließen Sie die App vorher, ist der Import verloren.</p>
      <div style="max-width:420px"><label class="lb" for="rolle">Quelle als Rolle</label><input class="in" id="rolle" bind:value={rolle} placeholder="z. B. Bericht der Klassenlehrerin"></div>
      <DateiWahl id="pfad" label="Datei importieren" endungen={['pdf', 'docx', 'xlsx', 'jpg', 'jpeg', 'png', 'heic', 'doc', 'xls']} onwahl={importieren} />
      {#if importFehler}<div class="err" role="alert"><strong style="color:var(--erT)">✕ {importFehler.text}</strong> Fehlercode: {importFehler.code}. Bereits importierte Dokumente bleiben erhalten.</div>{/if}
    </section>

    {#if fall && !fall.session.dokumente.length}
      <div class="empty"><h2 class="h2" style="color:var(--tx)">Noch keine Dokumente</h2><div>Jedes Dokument wird geprüft und anonymisiert, bevor es in Eingabe, Prüfung oder Rubberduck verwendet werden kann.</div></div>
    {:else if fall}
      {#if fall.session.dokumente.some((d) => d.freigabe.funde_je_kategorie.versteckte_inhalte > 0)}
        <div class="warn" role="status"><strong style="color:var(--wnT)">! Versteckte Inhalte gefunden.</strong> Kommentare, verborgener Text oder Metadaten werden in der Anonymisierung als eigener Fund gezeigt und nie ungeprüft übernommen.</div>
      {/if}
      <ul class="karten">
        {#each fall.session.dokumente as d (d.dok_id)}
          {@const l = lokal[d.dok_id]}
          {@const fz = d.freigabe.funde_je_kategorie}
          <li class="cd karte">
            <div class="row"><strong>{d.quelle_rolle}</strong><span class="pl na">{FORMAT[d.format]}</span>
              <span class="pl {FREIGABE[d.freigabe.status][0]}">{FREIGABE[d.freigabe.status][1]}</span></div>
            <div class="lb">{#if l?.seiten}{l.seiten} {l.seiten === 1 ? 'Seite' : 'Seiten'} · {/if}{fz.versteckte_inhalte} versteckte Inhalte · {fz.bilder} Bilder</div>
            {#if d.freigabe.status !== 'freigegeben'}
              {#if l && !l.imSpeicher}
                <div class="warn">! Die Arbeitskopie ist nicht mehr im Arbeitsspeicher (App oder Engine neu gestartet). Bitte erneut importieren.</div>
              {:else if l?.ocr === 'noetig'}
                <div class="row"><span>Gescannte Seiten brauchen Texterkennung.</span><button class="btn s" type="button" onclick={() => ocr(d.dok_id)}>Texterkennung starten</button></div>
              {:else if l?.ocr === 'laeuft'}
                <div role="progressbar" aria-label="Texterkennung {d.quelle_rolle}" aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(l.anteil * 100)} class="bar"><span style="width:{Math.round(l.anteil * 100)}%"></span></div>
              {:else}
                <a class="btn s p" href={href('fall', sid, 'anonymisierung', d.dok_id)}>Anonymisieren</a>
              {/if}
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
  </Zustand>
</AppShell>

<style>
  .box { padding: 16px; display: flex; flex-direction: column; gap: 10px; }
  .karten { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; }
  .karte { padding: 14px; display: flex; flex-direction: column; gap: 8px; }
  .bar { height: 8px; border-radius: 4px; background: var(--sf2); overflow: hidden; }
  .bar span { display: block; height: 100%; background: var(--ac); }
</style>
