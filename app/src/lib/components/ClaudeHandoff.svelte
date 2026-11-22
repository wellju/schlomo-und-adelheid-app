<script lang="ts">
  // ClaudeHandoff (ADR 0002): every AI step is a hand-over to Claude; the app holds no API key.
  // Desktop: shows the slash command for the Code-Tab and waits until the result is in the case store.
  // Browser: saves the package, takes the answer as file or pasted text and lets the engine check it
  // (schema, package ID, evidence, rule result). Decisions in a taken answer are always "offen".
  import { onDestroy } from 'svelte';
  import { app } from '../app.svelte';
  import { speichern as speichernDialog, pfadFeld } from '../datei';
  import { call } from '../engine/client';
  import { fehlerText } from '../engine/fehler';

  let {
    sid, art, titel, befehl, paketArgs = {}, gesperrt = null, stand, onuebernommen, hinweis = '', onfehler, meldungen = {},
  }: {
    sid: string; art: string; titel: string; befehl: string; paketArgs?: Record<string, unknown>;
    gesperrt?: string | null; stand: () => Promise<number>; onuebernommen: () => void; hinweis?: string;
    onfehler?: (code: string) => void; meldungen?: Record<string, string>;
  } = $props();

  type Zustand = 'bereit' | 'gespeichert' | 'wartet' | 'ungueltig' | 'uebernommen';
  let zustand = $state<Zustand>('bereit');
  let grund = $state('');
  let antwort = $state('');
  let paketId = $state('');
  let pfad = $state('');
  let fehler = $state<string | null>(null);
  let timer: ReturnType<typeof setInterval> | null = null;
  const modus = $derived(app.einstellungen?.verbindung ?? 'desktop');
  const GRUND: Record<string, string> = {
    E_SCHEMA: 'Schema: Die Antwort hat nicht das erwartete Format.',
    E_PAKET_FREMD: 'Fremde Paket-ID: Die Antwort gehört zu einem anderen Paket.',
    E_BELEG: 'Belegprüfung: Ein Satz verweist auf kein Eingabefeld.',
    E_REGELABWEICHUNG: 'Regelabweichung: Die Antwort weicht vom Ergebnis der Fachregelprüfung ab.',
  };

  function stopp() { if (timer) clearInterval(timer); timer = null; }
  onDestroy(stopp);

  // Desktop: the count of results (drafts, findings, protocol states) is taken when the hand-over starts; the wait
  // ends when it grows. Anything else refreshing the screen meanwhile does not move this mark.
  async function warten() {
    fehler = null;
    stopp();
    let start: number;
    try { start = await stand(); } catch (e) { fehler = fehlerText(e).text; return; }
    zustand = 'wartet';
    let fehlversuche = 0;
    timer = setInterval(async () => {
      try {
        if ((await stand()) > start) { stopp(); zustand = 'uebernommen'; onuebernommen(); }
        fehlversuche = 0;
      } catch (e) {
        // one failed poll is normal (a write of the Code-Tab at the same moment); five in a row are reported (EGM B7)
        if (++fehlversuche >= 5) { stopp(); zustand = 'bereit'; fehler = `Warten abgebrochen: ${fehlerText(e).text}`; }
      }
    }, 2000);
  }

  async function paketSpeichern() {
    fehler = null;
    try {
      const ziel = pfadFeld() ? pfad.trim() : await speichernDialog('Fallpaket', 'json', `${art}.json`);
      if (!ziel) return;
      const r = await call<{ fallpaket: { paket_id: string } }>('erzeuge_paket', { session_id: sid, art, ziel_pfad: ziel, ...paketArgs });
      paketId = r.fallpaket.paket_id;
      zustand = 'gespeichert';
    } catch (e) {
      const f = fehlerText(e);
      fehler = meldungen[f.code] ?? f.text + (f.grund ? ` (${f.grund})` : '');
      onfehler?.(f.code);
    }
  }

  async function dateiLesen(e: Event) {
    const f = (e.currentTarget as HTMLInputElement).files?.[0];
    if (f) antwort = await f.text();
  }

  async function einlesen() {
    fehler = null;
    try {
      await call('lies_rueckgabe', { session_id: sid, text: antwort });
      zustand = 'uebernommen';
      antwort = '';
      onuebernommen();
    } catch (e) {
      const f = fehlerText(e);
      zustand = 'ungueltig';
      grund = GRUND[f.code] ?? f.text;
    }
  }
  const STATUS: Record<Zustand, [string, string]> = {
    bereit: ['na', '○ Bereit'], gespeichert: ['ai', 'Paket gespeichert'], wartet: ['wn', '◷ Wartet auf Ergebnis'],
    ungueltig: ['er', '✕ Antwort ungültig'], uebernommen: ['ok', '✓ Übernommen'],
  };
</script>

<section class="cd ch" aria-label="Übergabe an Claude: {titel}">
  <div class="row"><strong>{titel}</strong><span class="lb">Verbindung: {modus === 'desktop' ? 'Claude Desktop (Code-Tab)' : 'Claude im Browser'}</span>
    <span class="pl {STATUS[zustand][0]}" role="status">{STATUS[zustand][1]}</span></div>
  {#if gesperrt}
    <div class="warn"><strong style="color:var(--wnT)">! Übergabe gesperrt.</strong> {gesperrt}</div>
  {:else if modus === 'desktop'}
    <div>Im Code-Tab im Arbeitsordner eingeben: <code>{befehl}</code></div>
    {#if hinweis}<div class="lb">{hinweis}</div>{/if}
    <div class="row">
      {#if zustand === 'wartet'}
        <button class="btn" type="button" onclick={() => { stopp(); zustand = 'bereit'; }}>Warten abbrechen</button>
      {:else}
        <button class="btn p" type="button" onclick={warten}>{zustand === 'uebernommen' ? 'Erneut übergeben' : 'Übergeben und warten'}</button>
      {/if}
    </div>
  {:else}
    <div class="lb">Paket in ein neues Gespräch auf claude.ai hochladen, die Antwort als Datei oder aus der Zwischenablage hier einfügen. Jede Übergabe in einem neuen Gespräch.</div>
    {#if hinweis}<div class="lb">{hinweis}</div>{/if}
    {#if pfadFeld()}
      <div><label class="lb" for="ch-pfad-{art}">Speicherort des Pakets: Pfad (nur Entwicklung)</label><input class="in" id="ch-pfad-{art}" bind:value={pfad}></div>
    {/if}
    <div class="row"><button class="btn" class:p={zustand === 'bereit' || zustand === 'uebernommen'} type="button" onclick={paketSpeichern}>Paket speichern</button>
      {#if paketId}<span class="lb">Paket {paketId}</span>{/if}</div>
    {#if zustand === 'gespeichert' || zustand === 'ungueltig'}
      <label class="lb" for="ch-antwort-{art}">Antwort von Claude (Text oder Datei)</label>
      <textarea class="in" id="ch-antwort-{art}" rows="5" bind:value={antwort}></textarea>
      <div class="row">
        <label class="btn s">Antwort aus Datei<input class="sr" type="file" accept=".json,.txt,.md" onchange={dateiLesen}></label>
        <button class="btn p" type="button" disabled={!antwort.trim()} onclick={einlesen}>Antwort einfügen</button>
      </div>
    {/if}
  {/if}
  {#if zustand === 'ungueltig'}
    <div class="err" role="alert"><strong style="color:var(--erT)">✕ Antwort ungültig.</strong> {grund} Ihr Stand ist unverändert. Bitte das Paket erneut speichern und in einem neuen Gespräch übergeben.</div>
  {/if}
  {#if fehler}<div class="err" role="alert">✕ {fehler}</div>{/if}
</section>

<style>
  .ch { padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }
  code { font-family: ui-monospace, Consolas, monospace; font-size: 13px; background: var(--acS); padding: 2px 6px; border-radius: 4px; }
  label.btn:focus-within { outline: 2px solid var(--ac); outline-offset: 2px; }
</style>
