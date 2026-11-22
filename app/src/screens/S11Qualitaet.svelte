<script lang="ts">
  // Screen 11: what the learning signals show, and the learning loop (Task 5): proposals of /verbessern with their eval
  // result, release or discard by the psychologist, version history of the learned blocks with rollback. The rule set,
  // category scale, templates, text blocks, wordings and the diagnosis comparison are locked for proposals.
  import { anonUebersicht, type AnonStatus } from '../lib/anon';
  import { app } from '../lib/app.svelte';
  import AppShell from '../lib/components/AppShell.svelte';
  import ClaudeHandoff from '../lib/components/ClaudeHandoff.svelte';
  import VersionList from '../lib/components/VersionList.svelte';
  import Zustand from '../lib/components/Zustand.svelte';
  import { call } from '../lib/engine/client';
  import { fehlerText } from '../lib/engine/fehler';

  let u = $state<any>(null);
  let lern = $state<{ vorschlaege: any[]; lernbausteine: any; signale: any[] } | null>(null);
  let versionen = $state<string[]>([]);
  let anon = $state<AnonStatus>({ stufe: 'uebersicht', gesperrt: 0 });
  let laden = $state(true);
  let fehler = $state<unknown>(null);
  let aktionFehler = $state<string | null>(null);
  let meldung = $state('');
  let sessionId = $state('');

  async function laden_(still = false) {
    if (!still) { laden = true; fehler = null; }
    try {
      u = await call('lernsignale_uebersicht');
      lern = await call('vorschlaege_laden');
      versionen = (await call('konfiguration_laden')).versionen?.lernbausteine ?? [];
      const sessions = (await call<{ sessions: any[] }>('sitzungen_auflisten')).sessions;
      anon = anonUebersicht(sessions);
      sessionId = sessions[0]?.session_id ?? '';
    } catch (e) { if (!still) fehler = e; } finally { laden = false; }
  }
  laden_();
  const PRUEFER: Record<string, string> = { elefant: 'Elefant', goldfisch: 'Goldfisch', stil: 'Stil' };
  const BEREICH: Record<string, string> = { sprache: 'Sprache', struktur: 'Struktur', pruefverhalten: 'Prüfverhalten' };
  const ZIEL: Record<string, string> = { entwurf: 'Entwurf', stil: 'Stil', goldfisch: 'Goldfisch', elefant: 'Elefant' };
  const STATUS: Record<string, [string, string]> = { offen: ['na', '○ Eval offen'], eval_bestanden: ['ok', '✓ Eval bestanden'],
    eval_abgelehnt: ['er', '✕ Eval abgelehnt'], freigegeben: ['ok', '✓ Freigegeben'], verworfen: ['na', 'Verworfen'] };
  const FALL: Record<string, string> = { empfehlung_statt_feststellung: 'Empfehlung statt Feststellung', keine_diagnose: 'Keine Diagnose',
    keine_regelparameter: 'Keine Regeln, Grenzwerte, gesperrten Bereiche', befunde_nicht_unterdruecken: 'Meldepflicht und Schwere bleiben', datenminimierung: 'Datenminimierung' };
  const name = (m: Record<string, string>, k: string | undefined) => (k ? (m[k] ?? k) : '');  // unknown values shown as they are (EGM C16)
  const vorher = (v: any) => lern?.lernbausteine?.bausteine?.find((b: any) => b.baustein_id === v.aenderung.baustein_id);
  let llmGelaufen = $state<Record<string, boolean>>({});
  const anteil = (p: any) => { const n = p.befund_angenommen + p.befund_verworfen; return n ? `${Math.round((p.befund_verworfen / n) * 100)} %` : '–'; };
  const stand = async () => (await call<{ vorschlaege: any[] }>('vorschlaege_laden')).vorschlaege.length;
  const offen = $derived((lern?.vorschlaege ?? []).filter((v) => !['freigegeben', 'verworfen'].includes(v.status)));
  const erledigt = $derived((lern?.vorschlaege ?? []).filter((v) => ['freigegeben', 'verworfen'].includes(v.status)));

  async function llmBestaetigen(v: any) {
    aktionFehler = null;
    try { await call('llm_evals_bestaetigen', { vorschlag_id: v.vorschlag_id, bestaetigt: true }); await laden_(true); }
    catch (e) { aktionFehler = fehlerText(e).text; }
  }

  async function entscheiden(v: any, wie: 'freigeben' | 'verwerfen') {
    aktionFehler = null;
    meldung = '';
    try {
      const r = await call(wie === 'freigeben' ? 'konfiguration_freigeben' : 'vorschlag_verwerfen', { vorschlag_id: v.vorschlag_id });
      meldung = wie === 'freigeben' ? `Übernommen als Version ${r.version} der Lernbausteine.` : 'Vorschlag verworfen.';
      await laden_(true);
    } catch (e) {
      const f = fehlerText(e);
      aktionFehler = f.grund === 'Gleichzeitig in Claude geändert, bitte neu laden'
        ? 'Die Lernbausteine haben sich seit der Prüfung geändert. Bitte den Vorschlag mit /verbessern neu prüfen lassen.' : f.text;
    }
  }
</script>

<AppShell aktiv="qualitaet" anonStatus={anon} bereich="Qualität" titel="Lernen und Qualität">
  <Zustand {laden} {fehler} erneut={() => laden_()} ladenText="Kennzahlen werden berechnet …">
    {#snippet warnung()}
      {#if u && u.gutachten < 10}
        <div class="warn" role="status"><strong style="color:var(--wnT)">! Wenig Datengrundlage.</strong> Die Kennzahlen beruhen auf {u.gutachten} Gutachten. Verläufe sind erst ab etwa 10 Gutachten aussagekräftig.</div>
      {/if}
    {/snippet}
    <p class="lb" style="margin:0">Auswertung nur aus anonymisierten Fällen. Supervision erzeugt keine Lernsignale, der Diagnosevergleich fließt nie ein.</p>
    {#if !u?.signale}
      <div class="empty"><h2 class="h2" style="color:var(--tx)">Noch keine Lernsignale</h2><div>Sobald Sie Prüfbefunde annehmen oder verwerfen oder Entwurfstext ändern, entstehen Lernsignale. Das System übernimmt nie selbst einen Vorschlag.</div></div>
    {:else}
      <div class="kacheln">
        <div class="cd kachel"><div class="lb">Lernsignale</div><div class="zahl">{u.signale}</div></div>
        <div class="cd kachel"><div class="lb">Gutachten mit Entwurf</div><div class="zahl">{u.gutachten}</div></div>
        <div class="cd kachel"><div class="lb">Offene Lücken in den aktuellen Entwürfen</div><div class="zahl">{u.offene_luecken}</div></div>
        <div class="cd kachel"><div class="lb">Geänderte Absätze</div><div class="zahl">{u.je_art?.text_geaendert ?? 0}</div></div>
      </div>
      <div class="cd tbx"><table class="t"><caption class="sr">Entscheidungen je Prüfer</caption>
        <thead><tr><th scope="col">Prüfer</th><th scope="col">Angenommen</th><th scope="col">Verworfen</th><th scope="col">Anteil verworfen</th></tr></thead>
        <tbody>{#each Object.entries(u.je_pruefer ?? {}) as [k, p] (k)}<tr><td>{PRUEFER[k] ?? k}</td><td>{(p as any).befund_angenommen}</td><td>{(p as any).befund_verworfen}</td><td>{anteil(p)}</td></tr>{/each}</tbody></table></div>
    {/if}

    <section class="cd box" aria-labelledby="h-verb"><h2 class="h3" id="h-verb">Verbesserungen vorschlagen</h2>
      <span class="lb">Vorschläge entstehen nur aus mindestens drei Lernsignalen derselben Herkunft und desselben Bereichs, nur für Sprache, Struktur und Prüfverhalten. Regelwerk, Kategorienskala, Vorlagen, Testkatalog, Hinweis-Wortlaute, ICD-10-Referenz, Diagnosevergleich und Supervision sind gesperrt. Signale zum Bereich Struktur entstehen derzeit nicht.</span>
      {#if (lern?.signale ?? []).length}
        <div class="row">{#each lern!.signale as g (`${g.herkunft}/${g.bereich}/${g.pruefer}`)}<span class="pl {g.frei >= 3 ? 'ai' : 'na'}">{g.herkunft === 'gutachten' ? 'Gutachten' : 'Intervision'} · {name(BEREICH, g.bereich)}{g.pruefer ? ` · ${name(PRUEFER, g.pruefer)}` : ''}: {g.frei} frei</span>{/each}</div>
      {/if}
      {#if app.einstellungen?.verbindung === 'browser'}
        <div class="lb" role="note">/verbessern gibt es nur im Code-Tab von Claude Desktop, weil die Eval-Suite dort mit der Engine läuft.</div>
      {:else if sessionId}
        <ClaudeHandoff sid={sessionId} art="verbessern" titel="Verbesserungen vorschlagen" befehl="/verbessern" {stand}
                       hinweis="Claude schlägt eine Änderung vor und lässt die Eval-Suite laufen. Übernehmen können nur Sie, hier." onuebernommen={() => laden_(true)} />
      {/if}
    </section>

    {#each offen as v (v.vorschlag_id)}
      <article class="cd box" aria-label="Vorschlag {v.vorschlag_id}">
        <div class="row"><span class="pl ai">KI-Vorschlag</span><span class="pl na">{name(BEREICH, v.bereich)}{v.aenderung.ziel ? ` · ${name(ZIEL, v.aenderung.ziel)}` : ''}</span>
          <span class="pl {(STATUS[v.status] ?? ['na'])[0]}">{(STATUS[v.status] ?? ['', v.status])[1]}</span></div>
        {#if v.aenderung.art !== 'hinzufuegen'}
          <div class="lb">Vorher ({vorher(v) ? `${name(BEREICH, vorher(v).bereich)} · ${name(ZIEL, vorher(v).ziel)}` : v.aenderung.baustein_id}):</div>
          <div class="doc alt">{vorher(v)?.text ?? 'Baustein nicht mehr aktiv'}</div>
        {/if}
        <div class="lb">{v.aenderung.art === 'entfernen' ? 'Nachher: Baustein entfällt' : v.aenderung.art === 'aendern' ? 'Nachher:' : 'Neuer Baustein:'}</div>
        {#if v.aenderung.art !== 'entfernen'}<div class="doc">{v.aenderung.text}</div>{/if}
        <div class="lb">Beleg: {v.begruendung} · {v.signal_ids.length} Lernsignale aus {v.herkunft === 'gutachten' ? 'Gutachten' : 'Intervision'}</div>
        {#if v.eval}
          <ul class="faelle" aria-label="Eval-Fälle">{#each v.eval.faelle as f (f.fall_id)}
            <li><span class="pl {f.nachher ? 'ok' : 'er'}">{f.nachher ? '✓' : '✕'} {FALL[f.fall_id] ?? f.fall_id}</span>{#if f.grund} <span class="lb">{f.grund}{f.vorher ? ' (vorher bestanden)' : ''}</span>{/if}</li>{/each}</ul>
          {#if v.status === 'eval_bestanden'}
            {#if v.llm_bestaetigt}
              <span class="pl ok">✓ LLM-Teil der Evals bestätigt am {v.llm_bestaetigt.am}</span>
            {:else}
              <span class="lb">Vor dem Übernehmen den LLM-Teil der Evals mit diesem Vorschlag laufen lassen (evals/lernschleife/mit_vorschlag.py, siehe Anleitung).</span>
              <label class="row"><input type="checkbox" bind:checked={llmGelaufen[v.vorschlag_id]}> Der LLM-Teil der Evals lief mit diesem Vorschlag und hat bestanden.</label>
              <button class="btn s" type="button" aria-disabled={!llmGelaufen[v.vorschlag_id]} onclick={() => llmGelaufen[v.vorschlag_id] && llmBestaetigen(v)}>Bestätigen</button>
            {/if}
          {/if}
        {/if}
        <div class="row">
          <button class="btn p" type="button" aria-disabled={v.status !== 'eval_bestanden' || !v.llm_bestaetigt}
                  onclick={() => v.status === 'eval_bestanden' && v.llm_bestaetigt && entscheiden(v, 'freigeben')}>Übernehmen</button>
          <button class="btn" type="button" onclick={() => entscheiden(v, 'verwerfen')}>Verwerfen</button>
          {#if v.status !== 'eval_bestanden' || !v.llm_bestaetigt}<span class="lb">Übernehmen erst nach bestandener Eval und bestätigtem LLM-Teil.</span>{/if}
        </div>
      </article>
    {:else}
      <div class="empty"><h2 class="h2" style="color:var(--tx)">Noch keine Vorschläge</h2><div>Das System übernimmt keinen Vorschlag selbst.</div></div>
    {/each}

    <section class="cd box" aria-labelledby="h-pv"><h2 class="h3" id="h-pv">Lernbausteine · aktiv</h2>
      {#if lern?.lernbausteine?.bausteine?.length}
        <ul class="faelle">{#each lern.lernbausteine.bausteine as b (b.baustein_id)}<li><span class="pl na">{name(BEREICH, b.bereich)} · {name(ZIEL, b.ziel)} · {b.herkunft === 'intervision' ? 'Intervision' : 'Gutachten'}</span> {b.text}</li>{/each}</ul>
      {:else}
        <span class="lb">Keine gelernten Bausteine aktiv.</span>
      {/if}
      {#if lern?.lernbausteine && (versionen.length || lern.lernbausteine.bausteine.length)}
        <VersionList name="lernbausteine" aktiv={lern.lernbausteine.version} {versionen} ongeaendert={() => laden_(true)} />
      {/if}
      {#if erledigt.length}<span class="lb">{erledigt.length} erledigte Vorschläge.</span>{/if}
    </section>
    <div role="status">{meldung}</div>
    {#if aktionFehler}<div class="err" role="alert">✕ {aktionFehler} Das aktive Prüfverhalten ist unverändert.</div>{/if}
  </Zustand>
</AppShell>

<style>
  .box { padding: 16px; display: flex; flex-direction: column; gap: 10px; }
  .kacheln { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
  .kachel { padding: 14px 16px; }
  .zahl { font-size: 28px; font-weight: 600; }
  .alt { text-decoration: line-through; color: var(--mu); }
  .faelle { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
  .btn[aria-disabled="true"] { opacity: .55; cursor: not-allowed; }
</style>
