<script lang="ts">
  // Screen 05: draft and reviews as hand-overs in a fixed order (draft, style, Goldfisch, Elefant), draft with the
  // source of every sentence, findings decided one by one (learning signals in the engine).
  import { anonVonSession } from '../lib/anon';
  import { app } from '../lib/app.svelte';
  import AppShell from '../lib/components/AppShell.svelte';
  import ClaudeHandoff from '../lib/components/ClaudeHandoff.svelte';
  import FindingCard from '../lib/components/FindingCard.svelte';
  import Zustand from '../lib/components/Zustand.svelte';
  import { call } from '../lib/engine/client';
  import { fehlerText } from '../lib/engine/fehler';
  import { ladeFall, type Fall } from '../lib/fall';
  import { href } from '../lib/router.svelte';

  let { sid }: { sid: string } = $props();
  let fall = $state<Fall | null>(null);
  let laden = $state(true);
  let fehler = $state<unknown>(null);
  let schritt = $state(1);
  let tab = $state<'elefant' | 'goldfisch' | 'stil'>('elefant');
  let quelle = $state<{ zeiger: string[]; wert: string } | null>(null);
  let bearbeiten = $state<{ abschnitt_id: string; absatz_id: string; text: string } | null>(null);
  let aktionFehler = $state<string | null>(null);
  let fundeFreitext = $state<any[]>([]);

  async function laden_(still = false) {
    if (!still) { laden = true; fehler = null; }
    try {
      fall = await ladeFall(sid);
      if (!still) schritt = startSchritt();
    } catch (e) {
      if (!still) fehler = e;
    } finally {
      laden = false;
    }
  }
  laden_();
  // Desktop: reviewers save their findings in the Code-Tab one after the other; refresh quietly while this screen is open.
  $effect(() => {
    if (app.einstellungen?.verbindung === 'browser') return;
    const t = setInterval(() => laden_(true), 5000);
    return () => clearInterval(t);
  });

  const entwurf = $derived(fall?.entwuerfe?.at(-1) ?? null);
  const befunde = $derived<any[]>(fall?.befunde ?? []);
  const anzahl = (p: string) => befunde.filter((b) => b.pruefer === p).length;
  function startSchritt() {
    if (!fall?.entwuerfe?.length) return 1;
    return anzahl('goldfisch') ? 4 : anzahl('stil') ? 3 : 2;
  }
  const sperre = $derived.by(() => {
    if (!fall) return null;
    const a = anonVonSession(fall.session).stufe;
    if (fall.session.gutachtentyp === 'emotional_soziale_entwicklung') return 'Für emotional-soziale Entwicklung gibt es noch keine Vorlage: Entwurf und Export sind gesperrt.';
    if (a === 'unsicher' || a === 'offen') return 'Die Anonymisierung dieses Falls ist nicht bestätigt. Ohne Bestätigung gehen keine Inhalte an Claude.';
    if (!fall.gutachten_input) return 'Es gibt noch keine gespeicherte Eingabe.';
    return null;
  });

  function wert(zeiger: string): string {
    let v: any = fall?.gutachten_input;
    for (const teil of zeiger.split('/').slice(1)) v = v?.[teil.replace(/~1/g, '/').replace(/~0/g, '~')];
    if (v === undefined) return '(nicht vorhanden)';
    return typeof v === 'object' ? (v.text ?? JSON.stringify(v)) : String(v);
  }

  const anzahlEntwuerfe = async () => (await ladeFall(sid)).entwuerfe?.length ?? 0;
  let ohneStilprofil = $state(false);

  async function entscheiden(b: any, entscheidung: 'annehmen' | 'verwerfen') {
    aktionFehler = null;
    try {
      await call('befund_entscheiden', { session_id: sid, befund_id: b.befund_id, entscheidung });
      await laden_(true);
    } catch (e) {
      aktionFehler = fehlerText(e).text;
    }
  }

  async function absatzSpeichern(unsichere = false) {
    if (!bearbeiten) return;
    aktionFehler = null;
    try {
      const r = await call('text_aendern', { session_id: sid, abschnitt_id: bearbeiten.abschnitt_id, absatz_id: bearbeiten.absatz_id,
        nachher: bearbeiten.text, ...(unsichere ? { unsichere_bestaetigt: true } : {}) });
      if (!r.gespeichert) { fundeFreitext = r.funde; return; }
      fundeFreitext = [];
      bearbeiten = null;
      await laden_(true);
    } catch (e) {
      aktionFehler = fehlerText(e).text;
    }
  }
  const absatzText = (a: any) => a.saetze.map((s: any) => s.text ?? '').filter(Boolean).join(' ');
  const SCHRITTE = [['1 Entwurf', 'gutachten'], ['2 Stilprüfung', 'pruefung_stil'], ['3 Goldfisch · neues Gespräch', 'pruefung_goldfisch'], ['4 Elefant · zuletzt, neues Gespräch', 'pruefung_elefant']] as const;
  const desktop = $derived(app.einstellungen?.verbindung !== 'browser');
  const UEBERSCHRIFT: Record<string, string> = { vorstellungsgrund: 'Vorstellungsgrund', schullaufbahn: 'Schullaufbahn', vorbefunde: 'Vorbefunde',
    anamnese: 'Anamnese', verhaltensbeobachtung: 'Verhaltensbeobachtung', testbefunde: 'Testbefunde', leistungsproben: 'Leistungsproben',
    diagnose: 'Diagnose', empfehlung: 'Empfehlung' };
</script>

<AppShell aktiv="faelle" anonStatus={fall ? anonVonSession(fall.session) : { stufe: 'nicht_geprueft' }} bereich={fall?.session.bezeichnung ?? 'Fall'}
          titel="Entwurf und Prüfung" fall={fall ? { session_id: sid, bereich: 'pruefung', modus: fall.session.modus } : undefined}>
  <Zustand {laden} {fehler} erneut={() => laden_()} ladenText="Entwurf wird geladen …">
    {#if desktop}
      <ClaudeHandoff {sid} art="gutachten" titel="Entwurf und Prüfung" befehl="/gutachten {sid}" gesperrt={sperre}
                     hinweis="Claude schreibt den Entwurf und startet danach Stil, Goldfisch und Elefant je mit frischem Kontext. Befunde erscheinen hier, sobald sie gespeichert sind."
                     stand={anzahlEntwuerfe} onuebernommen={() => laden_(true)} />
    {:else}
      <ol class="schritte" aria-label="Reihenfolge der Übergaben">
        {#each SCHRITTE as [label], i (label)}
          <li><button class="btn s" type="button" aria-current={schritt === i + 1 ? 'step' : undefined} aria-pressed={schritt === i + 1}
                      disabled={i > 0 && !entwurf} onclick={() => (schritt = i + 1)}>{schritt > i + 1 ? '✓' : schritt === i + 1 ? '●' : '○'} {label}</button></li>
        {/each}
      </ol>
      {#key schritt}
        {@const [label, art] = SCHRITTE[schritt - 1]}
        <ClaudeHandoff {sid} {art} titel={label.slice(2)} befehl="" gesperrt={sperre} stand={anzahlEntwuerfe}
                       onfehler={(code) => (ohneStilprofil = art === 'pruefung_stil' && code === 'E_NICHT_GEFUNDEN')}
                       meldungen={art === 'pruefung_goldfisch' ? { E_NICHT_GEFUNDEN: 'Die Goldfisch-Kriterien fehlen in der Wissensbasis (goldfisch-kriterien.md). Ohne sie gibt es kein Goldfisch-Paket.' }
                         : art === 'pruefung_stil' ? { E_NICHT_GEFUNDEN: 'Es gibt kein freigegebenes Stilprofil.' } : {}}
                       onuebernommen={async () => { await laden_(true); if (schritt < 4) schritt += 1; }} />
      {/key}
      {#if schritt === 2 && ohneStilprofil}
        <div class="warn" role="status">Ohne freigegebenes Stilprofil gibt es keine Stilprüfung.
          <button class="btn s" type="button" onclick={() => { ohneStilprofil = false; schritt = 3; }}>Ohne Stilprüfung weiter</button>
          <a href={href('stilprofil')}>Zum Stilprofil</a></div>
      {/if}
    {/if}

    <div class="zwei">
      <section class="cd box" aria-labelledby="h-entwurf">
        <div class="row"><h2 class="h2" id="h-entwurf">Entwurf</h2>
          {#if entwurf}<span class="pl na">Version {entwurf.entwurf_version}</span>
            <span class="pl wn">{entwurf.abschnitte.flatMap((a: any) => a.absaetze ?? []).flatMap((p: any) => p.saetze).filter((s: any) => s.luecke).length} Lücken markiert</span>{/if}</div>
        {#if !entwurf}
          <div class="empty"><h3 class="h3" style="color:var(--tx)">Noch kein Entwurf</h3><div>Der Entwurf entsteht ausschließlich aus Ihren Eingaben. Jeder Satz verweist auf sein Eingabefeld, fehlende Angaben erscheinen als markierte Lücke.</div></div>
        {:else}
          <article class="doc">
            {#each entwurf.abschnitte as a (a.abschnitt_id)}
              <h3 class="h3 ab">{UEBERSCHRIFT[a.abschnitt_id] ?? a.abschnitt_id}</h3>
              {#each a.absaetze ?? [] as p (p.absatz_id)}
                {#if bearbeiten && bearbeiten.absatz_id === p.absatz_id && bearbeiten.abschnitt_id === a.abschnitt_id}
                  <label class="lb" for="edit-{p.absatz_id}">Absatz bearbeiten (behält die Quellen der bisherigen Sätze)</label>
                  <textarea class="in" id="edit-{p.absatz_id}" bind:value={bearbeiten.text}></textarea>
                  {#if fundeFreitext.length}<div class="warn" role="alert">! Mögliche identifizierende Angaben: {fundeFreitext.map((f) => f.text).join(', ')}.
                    {#if fundeFreitext.every((f) => !f.sicher)}<button class="btn s" type="button" onclick={() => absatzSpeichern(true)}>Geprüft, trotzdem speichern</button>{/if}</div>{/if}
                  <div class="row"><button class="btn s p" type="button" onclick={() => absatzSpeichern()}>Absatz speichern</button><button class="btn s g" type="button" onclick={() => (bearbeiten = null)}>Abbrechen</button></div>
                {:else}
                  <p>{#each p.saetze as s, i (i)}{#if s.luecke}<span class="luecke">Lücke: {s.luecke.hinweis}</span>{:else}<button type="button" class="satz"
                    aria-pressed={quelle?.zeiger === s.quellen} onclick={() => (quelle = { zeiger: s.quellen, wert: s.quellen.map(wert).join(' · ') })}>{s.text}</button>{/if}{' '}{/each}
                    <button class="btn s g" type="button" onclick={() => (bearbeiten = { abschnitt_id: a.abschnitt_id, absatz_id: p.absatz_id, text: absatzText(p) })}>Bearbeiten<span class="sr"> Absatz {p.absatz_id}</span></button></p>
                {/if}
              {/each}
              {#each a.tabellen ?? [] as t (t.testergebnis_id)}
                <div class="tbx"><table class="t"><caption class="sr">Ergebnistabelle {t.testergebnis_id}</caption>
                  <thead><tr><th scope="col">Kennung</th><th scope="col">Wert</th><th scope="col">Kategorie</th></tr></thead>
                  <tbody>{#each t.zeilen as z (z.kennung)}<tr><td>{z.kennung}</td><td>{wert(z.wert_quelle)}</td><td>{z.kategorie ?? `Lücke: ${z.kategorie_luecke ?? ''}`}</td></tr>{/each}</tbody></table></div>
              {/each}
            {/each}
          </article>
          <div class="cd quelle" aria-live="polite">
            {#if quelle}<div class="lb">Quelle des markierten Satzes</div><div>{quelle.zeiger.join(', ')}</div><div class="doc">„{quelle.wert}“</div><a href={href('fall', sid, 'eingabe')}>Zum Eingabefeld</a>
            {:else}<span class="lb">Satz wählen, um seine Quelle zu sehen.</span>{/if}
          </div>
          {#if aktionFehler}<div class="err" role="alert">✕ {aktionFehler} Der Entwurf ist unverändert.</div>{/if}
        {/if}
      </section>

      <aside class="cd box" aria-labelledby="h-bef">
        <div class="row"><h2 class="h2" id="h-bef">Prüfbefunde</h2><span class="pl ai">KI-Vorschläge</span></div>
        <div role="tablist" aria-label="Prüfer" class="row">
          {#each [['elefant', 'Elefant'], ['goldfisch', 'Goldfisch'], ['stil', 'Stil']] as [k, l] (k)}
            <button role="tab" type="button" class="btn s" id="tab-{k}" aria-selected={tab === k} aria-controls="panel-{k}" tabindex={tab === k ? 0 : -1}
                    onclick={() => (tab = k as typeof tab)}>{l} · {anzahl(k)}</button>
          {/each}
        </div>
        <div role="tabpanel" id="panel-{tab}" aria-labelledby="tab-{tab}" class="liste">
          {#each befunde.filter((b) => b.pruefer === tab) as b (b.befund_id)}
            <FindingCard befund={b} onentscheide={(e) => entscheiden(b, e)} />
          {:else}
            <p class="lb">Keine Befunde dieses Prüfers.</p>
          {/each}
        </div>
        <span class="lb">Annehmen ändert den Text nie von selbst; ändern Sie den Absatz im Entwurf. Ihre Entscheidungen fließen als Lernsignal in die Qualitätsübersicht.</span>
        {#if entwurf}<a class="btn" href={href('fall', sid, 'export')}>Weiter zum Export</a>{/if}
      </aside>
    </div>
  </Zustand>
</AppShell>

<style>
  .box { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
  .schritte { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 8px; }
  .zwei { display: grid; grid-template-columns: minmax(0, 3fr) minmax(300px, 2fr); gap: 20px; align-items: start; }
  .ab { margin-top: 12px; }
  .satz { font: inherit; color: inherit; background: none; border: 0; padding: 0; text-align: left; cursor: pointer; display: inline; }
  .satz:hover, .satz[aria-pressed="true"] { background: var(--acS); }
  .luecke { border: 1px dashed var(--wnT); color: var(--wnT); padding: 0 4px; border-radius: 3px; font-family: Inter, system-ui, sans-serif; font-size: 13px; }
  .quelle { padding: 10px 12px; background: var(--bg); display: flex; flex-direction: column; gap: 4px; }
  .liste { display: flex; flex-direction: column; gap: 8px; }
  [role="tab"][aria-selected="true"] { border-color: var(--ac); color: var(--ac); background: var(--acS); }
  @media (max-width: 1023px) { .zwei { grid-template-columns: 1fr; } }
</style>
