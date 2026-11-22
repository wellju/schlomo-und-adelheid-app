<script lang="ts">
  // Screen 03: recognition, decision per finding, manual redaction, release. Uncertain findings block the release
  // in this screen's logic and in the engine.
  import { anonVonSession } from '../lib/anon';
  import AppShell from '../lib/components/AppShell.svelte';
  import FindingDecision from '../lib/components/FindingDecision.svelte';
  import RedactionViewer from '../lib/components/RedactionViewer.svelte';
  import ReleaseGate from '../lib/components/ReleaseGate.svelte';
  import Zustand from '../lib/components/Zustand.svelte';
  import { call } from '../lib/engine/client';
  import { fehlerText } from '../lib/engine/fehler';
  import { ladeFall, type Fall, type Fund, type Teil } from '../lib/fall';
  import { KATEGORIE } from '../lib/kategorien';
  import { namenGesendet } from '../lib/namen.svelte';
  import { gehe, href } from '../lib/router.svelte';

  let { sid, dok }: { sid: string; dok?: string } = $props();
  let fall = $state<Fall | null>(null);
  let laden = $state(true);
  let fehler = $state<unknown>(null);
  let teile = $state<Teil[]>([]);
  let funde = $state<Fund[]>([]);
  let gelaufen = $state(false);
  let erkennungLaeuft = $state(false);
  let hinweise = $state<string[]>([]);
  let aktiv = $state<string | null>(null);
  let aktionFehler = $state<string | null>(null);
  let testdatum = $state('');
  let manuell = $state({ text: '', kategorie: 'direkte_identifikatoren', ersatz: '[geschwärzt]' });
  let verloren = $state(false);

  const offeneDoks = $derived(fall?.session.dokumente.filter((d) => d.freigabe.status !== 'freigegeben') ?? []);
  const dokId = $derived(dok ?? offeneDoks[0]?.dok_id);
  const dokument = $derived(fall?.session.dokumente.find((d) => d.dok_id === dokId));

  async function laden_() {
    laden = true;
    fehler = null;
    verloren = false;
    try {
      fall = await ladeFall(sid);
      if (dokId && dokument?.freigabe.status !== 'freigegeben') {
        try {
          const t = await call<{ teile: Teil[]; funde: Fund[]; erkennung_gelaufen: boolean }>('dokument_text', { session_id: sid, dok_id: dokId });
          teile = t.teile;
          funde = t.funde;
          gelaufen = t.erkennung_gelaufen;
        } catch {
          verloren = true;
        }
      }
    } catch (e) {
      fehler = e;
    } finally {
      laden = false;
    }
  }
  laden_();

  async function erkennen() {
    aktionFehler = null;
    erkennungLaeuft = true;
    try {
      const r = await call<{ funde: Fund[]; hinweise: string[] }>('erkennung_ausfuehren',
        { session_id: sid, dok_id: dokId, ...(testdatum ? { testdatum } : {}) });
      funde = r.funde;
      hinweise = r.hinweise;
      gelaufen = true;
    } catch (e) {
      aktionFehler = fehlerText(e).text;
    } finally {
      erkennungLaeuft = false;
    }
  }

  async function entscheiden(f: Fund, entscheidung: 'uebernehmen' | 'verwerfen' | 'aendern', ersatz?: string) {
    aktionFehler = null;
    try {
      const r = await call<{ fund: Fund }>('schwaerzung_entscheiden', { session_id: sid, dok_id: dokId, fund_id: f.fund_id, entscheidung, ...(ersatz ? { ersatz } : {}) });
      funde = funde.map((x) => (x.fund_id === f.fund_id ? r.fund : x));
    } catch (e) {
      aktionFehler = fehlerText(e).text;
    }
  }

  async function hinzufuegen(e: SubmitEvent) {
    e.preventDefault();
    aktionFehler = null;
    try {
      const r = await call<{ funde: Fund[]; neu: number }>('fund_hinzufuegen', { session_id: sid, dok_id: dokId, ...manuell });
      funde = r.funde;
      manuell.text = '';
    } catch (err) {
      const f = fehlerText(err);
      aktionFehler = f.code === 'E_NICHT_GEFUNDEN' ? 'Der Text kommt nicht vor oder ist schon markiert.' : f.text;
    }
  }

  const offen = $derived(funde.filter((f) => f.status === 'offen'));
  const blocker = $derived([
    ...(gelaufen ? [] : ['Erkennung ist noch nicht gelaufen']),
    ...(offen.length ? [`${offen.length} ${offen.length === 1 ? 'Fund ist' : 'Funde sind'} offen (unsicher)`] : []),
  ]);

  async function freigeben() {
    if (blocker.length) return; // the lock lives here, not only in the button
    aktionFehler = null;
    try {
      await call('anonymisierung_freigeben', { session_id: sid, dok_id: dokId, geprueft_bestaetigt: true });
      teile = [];
      funde = [];
      const rest = offeneDoks.filter((d) => d.dok_id !== dokId);
      if (rest.length) gehe('fall', sid, 'anonymisierung', rest[0].dok_id);
      else gehe('fall', sid, 'dokumente');
    } catch (e) {
      aktionFehler = fehlerText(e).text;
    }
  }

  function waehle(id: string) {
    aktiv = id;
    document.getElementById(`fund-${id}`)?.focus();
  }
</script>

<AppShell aktiv="faelle" anonStatus={fall ? anonVonSession(fall.session) : { stufe: 'nicht_geprueft' }} bereich={fall?.session.bezeichnung ?? 'Fall'}
          titel="Anonymisierung" fall={fall ? { session_id: sid, bereich: 'anonymisierung', modus: fall.session.modus } : undefined}>
  <Zustand {laden} {fehler} erneut={laden_} ladenText="Dokument wird geladen …" leer={!!fall && !offeneDoks.length}
           leerTitel="Nichts zu anonymisieren" leerText="Alle Dokumente dieses Falls sind geprüft und freigegeben, oder es wurde noch keines importiert.">
    {#snippet leerAktion()}<a class="btn p" href={href('fall', sid, 'dokumente')}>Zu den Dokumenten</a>{/snippet}
    {#snippet warnung()}
      {#if offen.some((f) => f.unsicher)}
        <div class="warn" role="status"><strong style="color:var(--wnT)">! Erkennung unsicher.</strong> Die Weitergabe an KI-Funktionen ist gesperrt, bis jeder unsichere Fund entschieden ist.</div>
      {/if}
      {#if hinweise.includes('namen_fehlen') || (!namenGesendet(sid) && !gelaufen)}
        <div class="warn" role="status"><strong style="color:var(--wnT)">! Keine bekannten Namen gesetzt.</strong> Ohne Namensliste findet nur die Regel- und Namenserkennung Personen. <a href={href('fall', sid, 'dokumente')}>Namen setzen</a></div>
      {/if}
      {#if hinweise.includes('seltene_merkmale_ohne_liste')}
        <div class="warn" role="status"><strong style="color:var(--wnT)">! Keine Liste seltener Merkmale.</strong> Erstsprache und Herkunft bleiben ungeprüft; bitte selbst markieren.</div>
      {/if}
    {/snippet}
    {#if offeneDoks.length > 1}
      <div style="max-width:420px"><label class="lb" for="dok">Dokument</label>
        <select class="in" id="dok" value={dokId} onchange={(e) => gehe('fall', sid, 'anonymisierung', e.currentTarget.value)}>
          {#each offeneDoks as d (d.dok_id)}<option value={d.dok_id}>{d.quelle_rolle}</option>{/each}
        </select></div>
    {/if}
    {#if verloren}
      <div class="err" role="alert"><strong style="color:var(--erT)">✕ Die Arbeitskopie ist nicht mehr im Arbeitsspeicher.</strong> App oder Engine wurden neu gestartet; Bestätigtes bleibt erhalten. Bitte das Dokument erneut importieren. <a href={href('fall', sid, 'dokumente')}>Zu den Dokumenten</a></div>
    {:else}
      <section class="cd box" aria-labelledby="h-erk">
        <h2 class="h3" id="h-erk">Erkennung: {dokument?.quelle_rolle}</h2>
        <div class="row">
          <div><label class="lb" for="td">Testdatum (optional, für relative Datumsangaben, wird nicht gespeichert)</label><input class="in" id="td" type="date" bind:value={testdatum} style="max-width:220px"></div>
          <button class="btn" class:p={!gelaufen} type="button" style="align-self:flex-end" disabled={erkennungLaeuft} onclick={erkennen}>{gelaufen ? 'Erkennung neu starten' : 'Erkennung starten'}</button>
        </div>
        {#if erkennungLaeuft}<div role="status" aria-busy="true" class="lb">Erkennung läuft …</div>{/if}
        {#if gelaufen}
          <div class="row">{#each Object.entries(KATEGORIE) as [k, v] (k)}<span class="pl na">{v.tag} {funde.filter((f) => f.kategorie === k && f.status !== 'verworfen').length}</span>{/each}<span class="pl {offen.length ? 'er' : 'ok'}">{offen.length} offen</span></div>
        {/if}
        {#if aktionFehler}<div class="err" role="alert">✕ {aktionFehler} Ihre bisherigen Entscheidungen bleiben erhalten.</div>{/if}
      </section>
      {#if gelaufen}
        <div class="zwei">
          <RedactionViewer {teile} {funde} {aktiv} onwahl={waehle} onauswahl={(t) => (manuell.text = t)} />
          <div class="stack">
            <form class="cd box" onsubmit={hinzufuegen} aria-labelledby="h-man">
              <h2 class="h3" id="h-man">Selbst schwärzen</h2>
              <span class="lb">Text eingeben oder im Dokument markieren. Jedes Vorkommen wird ersetzt.</span>
              <label class="lb" for="mt">Text</label><input class="in" id="mt" bind:value={manuell.text} required minlength="2" maxlength="200">
              <label class="lb" for="mk">Art</label>
              <select class="in" id="mk" bind:value={manuell.kategorie}>{#each Object.entries(KATEGORIE).filter(([k]) => k !== 'versteckte_inhalte') as [k, v] (k)}<option value={k}>{v.label}</option>{/each}</select>
              <label class="lb" for="me">Ersetzen durch</label><input class="in" id="me" bind:value={manuell.ersatz} required maxlength="100">
              <button class="btn" type="submit">Schwärzen</button>
            </form>
            <section aria-labelledby="h-funde">
              <h2 class="h3" id="h-funde">Funde ({funde.length})</h2>
              <ul class="liste">{#each [...offen, ...funde.filter((f) => f.status !== 'offen')] as f (f.fund_id)}
                <FindingDecision fund={f} aktiv={aktiv === f.fund_id} onentscheide={(e, ers) => entscheiden(f, e, ers)} />{/each}</ul>
            </section>
            <ReleaseGate {blocker} onbestaetigen={freigeben} />
          </div>
        </div>
      {/if}
    {/if}
  </Zustand>
</AppShell>

<style>
  .box { padding: 16px; display: flex; flex-direction: column; gap: 10px; }
  .zwei { display: grid; grid-template-columns: minmax(0, 3fr) minmax(300px, 2fr); gap: 20px; align-items: start; }
  .liste { list-style: none; margin: 8px 0 0; padding: 0; display: flex; flex-direction: column; gap: 8px; max-height: 50vh; overflow: auto; }
  @media (max-width: 1023px) { .zwei { grid-template-columns: 1fr; } }
</style>
