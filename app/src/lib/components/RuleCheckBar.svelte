<script lang="ts">
  // RuleCheckBar: each rule as a button with aria-expanded; result with symbol and text, reason and source.
  // Diagnosis rules (wirkung blockiert_diagnose) are shown only with Q1 and never belong in an SPF report.
  let { ergebnis, regeln, regelwerkVersion, q1 }: {
    ergebnis: { ergebnisse: any[]; gesamt: string } | null; regeln: Record<string, { titel: string; quelle: any; status: string }>;
    regelwerkVersion?: string; q1: boolean;
  } = $props();
  let offen = $state<string | null>(null);
  const ERG: Record<string, [string, string]> = { erfuellt: ['ok', '✓ Erfüllt'], nicht_erfuellt: ['er', '✕ Verletzt'], nicht_pruefbar: ['na', '? Nicht prüfbar'] };
  const WIRK: Record<string, string> = { blockiert_export: 'sperrt den Export', blockiert_diagnose: 'nur intern, Diagnosevergleich', hinweis: 'Hinweis' };
  const sichtbar = $derived((ergebnis?.ergebnisse ?? []).filter((e) => q1 || e.wirkung !== 'blockiert_diagnose'));
  const quelle = (q: any) => (q ? Object.values(q).join(', ') : 'keine Quelle');
</script>

<section class="cd rcb" aria-labelledby="h-regeln">
  <div class="row"><h2 class="h3" id="h-regeln">Regelprüfung</h2>
    {#if ergebnis}<span class="lb">Regelwerk {regelwerkVersion}</span>{/if}</div>
  {#if regelwerkVersion === 'nicht_konfiguriert'}
    <div class="err" role="alert"><strong style="color:var(--erT)">✕ Regelprüfung nicht möglich.</strong> Ihr Regelwerk hat noch keinen Stand. Eingaben werden gespeichert, aber nicht geprüft, und der Export bleibt gesperrt.</div>
  {:else if !ergebnis}
    <p class="lb" style="margin:0">Die Regeln werden direkt nach dem Speichern der Eingabe geprüft.</p>
  {:else}
    <div class="row">
      {#each sichtbar as e (e.regel_id + (e.testergebnis_id ?? ''))}
        {@const id = e.regel_id + (e.testergebnis_id ?? '')}
        <button class="btn s" type="button" aria-expanded={offen === id} aria-controls="regel-{id}" onclick={() => (offen = offen === id ? null : id)}>
          <span class="pl {ERG[e.ergebnis][0]}">{ERG[e.ergebnis][1]}</span> {regeln[e.regel_id]?.titel ?? e.regel_id}{e.regel_status === 'entwurf' ? ' (Entwurf)' : ''}</button>
      {/each}
    </div>
    {#each sichtbar as e (e.regel_id + (e.testergebnis_id ?? ''))}
      {@const id = e.regel_id + (e.testergebnis_id ?? '')}
      {#if offen === id}
        <dl class="detail" id="regel-{id}">
          <dt class="lb">Regel</dt><dd>{regeln[e.regel_id]?.titel ?? e.regel_id} · Wirkung: {WIRK[e.wirkung]}</dd>
          <dt class="lb">Ergebnis</dt><dd>{e.begruendung}</dd>
          <dt class="lb">Quelle</dt><dd>{quelle(regeln[e.regel_id]?.quelle)}</dd>
        </dl>
      {/if}
    {/each}
    <span class="lb">Diagnosebezogene Regeln prüft die App nur intern für den Diagnosevergleich. Sie erscheinen nie im SPF-Gutachten.</span>
  {/if}
</section>

<style>
  .rcb { padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }
  .detail { display: grid; grid-template-columns: 90px 1fr; gap: 4px 12px; margin: 0; padding: 10px 12px; background: var(--bg); border-radius: 6px; }
  dd { margin: 0; }
</style>
