<script lang="ts">
  // Screens 07 (intervision) and 08 (supervision): the conversation runs in Claude; this screen shows phase, key
  // question or concern, protocol, reviews and hints, and ends the session. The text she types in Claude goes there
  // without local anonymisation (ADR 0002), hence the warning at the start.
  import { app } from '../lib/app.svelte';
  import AppShell from '../lib/components/AppShell.svelte';
  import ClaudeHandoff from '../lib/components/ClaudeHandoff.svelte';
  import FindingCard from '../lib/components/FindingCard.svelte';
  import Zustand from '../lib/components/Zustand.svelte';
  import { call } from '../lib/engine/client';
  import { fehlerText } from '../lib/engine/fehler';
  import { ladeFall, type Fall } from '../lib/fall';
  import { href } from '../lib/router.svelte';

  let { sid, modus }: { sid: string; modus: 'intervision' | 'supervision' } = $props();
  let fall = $state<Fall | null>(null);
  let vorgaben = $state<any>(null);
  let laden = $state(true);
  let fehler = $state<unknown>(null);
  let bestaetigt = $state(false);
  let aktionFehler = $state<string | null>(null);
  let beendet = $state(false);

  async function laden_(still = false) {
    if (!still) { laden = true; fehler = null; }
    try {
      fall = await ladeFall(sid);
      vorgaben ??= await call('rubberduck_vorgaben');
    } catch (e) {
      if (!still) fehler = e;
    } finally {
      laden = false;
    }
  }
  laden_();
  $effect(() => { // the Code-Tab saves each phase; keep the view current while it runs
    if (app.einstellungen?.verbindung === 'browser') return;
    const t = setInterval(() => laden_(true), 4000);
    return () => clearInterval(t);
  });

  const iv = $derived(modus === 'intervision');
  const proto = $derived<any>(fall?.protokolle?.at(-1) ?? null);
  const PHASEN = $derived(iv
    ? [['rollen', 'Rollen'], ['spontanerzaehlung', 'Erzählung'], ['schluesselfrage', 'Schlüsselfrage'], ['methodenwahl', 'Methode'], ['beratung', 'Beratung'], ['abschluss', 'Abschluss']]
    : [['anliegen', 'Anliegen'], ['klaerung', 'Klärung'], ['bearbeitung', 'Bearbeitung'], ['integration', 'Integration'], ['abschluss', 'Abschluss']]);
  const phase = $derived(proto?.phase ?? null);
  const ende = $derived(!!proto && (iv ? ['beendet', 'abgebrochen'].includes(proto.phase) : proto.status !== 'laufend'));
  const pruefer = $derived(iv ? ['elefant', 'goldfisch'] : ['goldfisch']);
  const geprueft = $derived<string[]>(fall?.protokoll_pruefungen ?? []);
  const offenePruefer = $derived(pruefer.filter((p) => !geprueft.includes(p)));
  const befunde = $derived<any[]>(iv ? proto?.pruefbefunde ?? [] : proto?.goldfisch_befunde ?? []);
  const alleBefunde = $derived<any[]>([...befunde, ...(fall?.befunde ?? []).filter((b: any) => !befunde.some((x) => x.befund_id === b.befund_id))]);
  const schluessel = $derived(iv ? proto?.schluesselfrage?.endgueltig : proto?.anliegen);
  const ohneHinweise = $derived(vorgaben && !vorgaben.hinweise);
  const desktop = $derived(app.einstellungen?.verbindung !== 'browser');
  const anzahlStaende = async () => (await ladeFall(sid)).protokolle?.length ?? 0;
  const anzahlPruefungen = async () => (await ladeFall(sid)).protokoll_pruefungen?.length ?? 0;
  const PRUEFER_NAME: Record<string, string> = { elefant: 'Elefant', goldfisch: 'Goldfisch' };

  async function entscheiden(b: any, e: 'annehmen' | 'verwerfen') {
    aktionFehler = null;
    try { await call('befund_entscheiden', { session_id: sid, befund_id: b.befund_id, entscheidung: e }); await laden_(true); }
    catch (err) { aktionFehler = fehlerText(err).text; }
  }
  async function beenden() {
    if (!bestaetigt || offenePruefer.length) return; // the engine checks the reviews again (pruefung_fehlt)
    aktionFehler = null;
    try {
      await call('protokoll_beenden', { session_id: sid });
      beendet = true;
      await laden_(true);
    } catch (e) {
      const f = fehlerText(e);
      aktionFehler = f.grund === 'Eine Prüfung fehlt noch' ? `Noch nicht geprüft: ${offenePruefer.map((p) => PRUEFER_NAME[p]).join(', ')}.` : f.text;
    }
  }
</script>

<AppShell aktiv="faelle" anonStatus={{ stufe: 'kein_fall' }} modus={iv ? 'normal' : 'supervision'}
          bereich="{fall?.session.bezeichnung ?? 'Sitzung'} · {iv ? 'Intervision · mehrere KI-Stimmen' : 'Supervision · eine KI-Stimme'}"
          titel={iv ? 'Rubberduck Intervision' : 'Rubberduck Supervision'}>
  <Zustand {laden} {fehler} erneut={() => laden_()} ladenText="Sitzung wird geladen …">
    <div class="warn" role="note" data-testid="warnhinweis"><strong style="color:var(--wnT)">! Nur anonymisierte Vignetten.</strong> Rollen statt Namen, keine Daten, keine Orte, keine seltenen Merkmale. Ihr Text geht direkt an Claude, ohne lokale Anonymisierung.</div>
    {#if !desktop && iv}
      <div class="lb" role="note">Im Browser-Modus sind alle Berater ein Modell mit gemeinsamem Kontext; sie sind nicht unabhängig voneinander.</div>
    {/if}
    {#each proto?.hinweise ?? [] as h, i (i)}
      <div class="err banner" role="alert" data-testid="hinweisbanner"><strong style="color:var(--erT)">! Hinweis der KI{h.art === 'akute_gefaehrdung' ? ' · akute Gefährdung' : ''}</strong>
        {h.text} Die Sitzung läuft weiter.</div>
    {/each}
    {#if ohneHinweise}
      <div class="err" role="alert"><strong style="color:var(--erT)">✕ Keine Sitzung möglich.</strong> Die Hinweis-Wortlaute für Kindeswohl und akute Gefährdung fehlen in der Konfiguration (hinweise.json). Ohne sie startet weder Intervision noch Supervision.</div>
    {:else if vorgaben?.herkunft?.hinweise === 'synthetisch'}
      <div class="lb" role="note">Hinweis-Wortlaute sind synthetische Platzhalter, nur für Tests.</div>
    {/if}
    {#if iv && vorgaben?.berater_perspektiven}
      <div class="row"><span class="lb">Berater-Perspektiven:</span>{#each vorgaben.berater_perspektiven as b (b.name)}<span class="pl ai">{b.name}</span>{/each}</div>
    {/if}

    {#if !ende && !ohneHinweise}
      {#if desktop}
        <ClaudeHandoff {sid} art={modus} titel="Sitzung läuft in Claude" befehl="/{modus} {sid}" stand={anzahlStaende}
                       hinweis="Claude speichert jede Phase in der Engine; diese Ansicht folgt. Vor dem Abschluss prüfen {iv ? 'Elefant und Goldfisch' : 'der Goldfisch'} das Protokoll." onuebernommen={() => laden_(true)} />
      {:else if !proto}
        <ClaudeHandoff {sid} art={modus} titel="Sitzung in Claude führen" befehl="" stand={anzahlStaende}
                       hinweis="Paket hochladen, die ganze Sitzung im Gespräch führen; am Ende gibt Claude das Protokoll als einen Block zurück." onuebernommen={() => laden_(true)} />
      {/if}
    {/if}

    {#if !proto}
      <div class="empty"><h2 class="h2" style="color:var(--tx)">Noch keine Sitzung</h2><div>{iv ? 'Eine Sitzung führt Sie durch sechs Phasen. Sie erzählen den Fall, legen eine Schlüsselfrage fest und hören dann mehreren KI-Beratern zu.' : 'Eine Supervision geht vom Anliegen über die Klärung der Ebenen bis zur Integration. Die KI-Stimme ist gekennzeichnet.'}</div></div>
    {:else}
      <ol class="phasen" aria-label="Phasen">
        {#each PHASEN as [k, l], i (k)}
          <li class:akt={phase === k} aria-current={phase === k ? 'step' : undefined}>{i + 1} {l}{phase === k ? ' · aktuell' : ''}</li>
        {/each}
      </ol>
      {#if schluessel}
        <section class="cd pin" aria-label={iv ? 'Schlüsselfrage' : 'Anliegen'}><div class="lb">{iv ? 'Schlüsselfrage · fixiert seit Phase 3' : 'Anliegen'}</div><div class="doc">{schluessel}</div></section>
      {/if}
      <section class="cd box" aria-labelledby="h-proto"><h2 class="h3" id="h-proto">Protokoll</h2>
        {#if iv}
          {#if proto.rollen}<div class="lb">Fallerzählerin: Sie · Moderation: KI · Berater: {proto.rollen.berater.map((b: any) => b.perspektive).join(', ')}</div>{/if}
          {#if proto.spontanerzaehlung?.zusammenfassung}<div><strong>Erzählung:</strong> {proto.spontanerzaehlung.zusammenfassung}</div>{/if}
          {#if proto.methode}<div><strong>Methode:</strong> {proto.methode}</div>{/if}
          {#each proto.beratung ?? [] as b, i (i)}<div class="cd beitrag"><span class="pl ai">KI · {b.berater_id}</span> {b.beitrag}</div>{/each}
        {:else}
          {#each proto.ebenen ?? [] as e, i (i)}<div class="cd beitrag"><span class="pl svp">KI · Supervision</span> <strong>{e.ebene}</strong> {(e.hypothesen ?? []).join(' · ')}</div>{/each}
        {/if}
        {#if proto.abschluss?.mitnahme}<div><strong>Mitnahme:</strong> {proto.abschluss.mitnahme}</div>{/if}
        <span class="lb">Die Sitzung bezieht sich auf eine anonymisierte Vignette. Inhalte werden nicht in ein Gutachten übernommen.</span>
      </section>

      {#if phase === 'abschluss' && !ende}
        {#if !desktop}
          {#each offenePruefer as p (p)}
            <ClaudeHandoff {sid} art="protokoll_{p}" titel="Prüfung {PRUEFER_NAME[p]} · neues Gespräch" befehl="" stand={anzahlPruefungen} onuebernommen={() => laden_(true)} />
          {/each}
        {:else if offenePruefer.length}
          <div class="lb" role="status">Im Code-Tab prüfen noch: {offenePruefer.map((p) => PRUEFER_NAME[p]).join(', ')}.</div>
        {/if}
        <section class="cd box" aria-labelledby="h-ende"><h2 class="h3" id="h-ende">Sitzung beenden</h2>
          <div>{iv ? 'Schlüsselfrage' : 'Anliegen'}: <span class="doc">„{schluessel}“</span></div>
          <label class="row"><input type="checkbox" bind:checked={bestaetigt}> {iv ? 'Die Schlüsselfrage' : 'Das Anliegen'} und die Mitnahme stimmen so, wie ich sie formuliert habe.</label>
          <button class="btn p" type="button" aria-disabled={!bestaetigt || offenePruefer.length > 0} onclick={beenden}>Sitzung beenden</button>
          {#if offenePruefer.length}<span class="lb">Erst nach der Prüfung durch {offenePruefer.map((p) => PRUEFER_NAME[p]).join(' und ')}.</span>{/if}
        </section>
      {/if}
      {#if ende || beendet}<div class="cd box" role="status"><strong>✓ Sitzung {proto?.phase === 'abgebrochen' || proto?.status === 'abgebrochen' ? 'abgebrochen' : 'beendet'}.</strong></div>{/if}
      {#if alleBefunde.length}
        <section class="cd box" aria-labelledby="h-pb"><div class="row"><h2 class="h3" id="h-pb">Prüfbefunde vor dem Abschluss</h2><span class="pl ai">KI</span></div>
          {#each alleBefunde as b (b.befund_id)}<FindingCard befund={b} onentscheide={(e) => entscheiden(b, e)} />{/each}
          {#if !iv}<span class="lb">Entscheidungen in der Supervision erzeugen kein Lernsignal.</span>{/if}
        </section>
      {/if}
    {/if}
    {#if aktionFehler}<div class="err" role="alert">✕ {aktionFehler}</div>{/if}
    <a href={href('faelle')}>Zur Übersicht</a>
  </Zustand>
</AppShell>

<style>
  .box { padding: 16px; display: flex; flex-direction: column; gap: 10px; }
  .phasen { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 8px; }
  .phasen li { padding: 6px 12px; border-radius: 999px; border: 1px solid var(--bd); background: var(--sf); font-size: 13px; }
  .phasen li.akt { border-color: var(--ac); color: var(--ac); background: var(--acS); font-weight: 600; }
  .pin { padding: 12px 16px; border-left-width: 1px; }
  .beitrag { padding: 10px 12px; background: var(--bg); }
  .banner { display: block; }
  .btn[aria-disabled="true"] { opacity: .55; cursor: not-allowed; }
</style>
