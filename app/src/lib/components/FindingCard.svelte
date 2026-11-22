<script lang="ts">
  // FindingCard: problem, reason and source in a fixed order; severity as shape and text, colour only adds.
  let { befund, onentscheide }: { befund: any; onentscheide: (e: 'annehmen' | 'verwerfen') => void } = $props();
  const SCHWERE: Record<string, [string, string]> = { hoch: ['er', '▲ Hoch'], mittel: ['wn', '◆ Mittel'], gering: ['na', '● Gering'] };
  const status = $derived(befund.entscheidung.status);
  const stelle = $derived([befund.stelle.abschnitt_id, befund.stelle.absatz_id, befund.stelle.protokoll_phase].filter(Boolean).join(', '));
</script>

<article class="cd fc" aria-label="Befund {befund.problem.slice(0, 60)}">
  <div class="row"><span class="pl {SCHWERE[befund.schwere][0]}">{SCHWERE[befund.schwere][1]}</span><span class="lb">{stelle}</span>
    {#if status !== 'offen'}<span class="pl {status === 'angenommen' ? 'ok' : 'na'}">{status === 'angenommen' ? '✓ Angenommen' : '✕ Verworfen'}</span>{/if}</div>
  <div>{befund.problem}</div>
  {#if befund.stelle.zitat}<div class="doc lb">„{befund.stelle.zitat}“</div>{/if}
  <div class="lb">Begründung: {befund.begruendung}{befund.regel_id ? ` · Regel ${befund.regel_id}` : ''}</div>
  <div class="row">
    <button class="btn s" class:p={status === 'offen'} type="button" aria-pressed={status === 'angenommen'} onclick={() => onentscheide('annehmen')}>Annehmen</button>
    <button class="btn s" type="button" aria-pressed={status === 'verworfen'} onclick={() => onentscheide('verwerfen')}>Verwerfen</button>
  </div>
</article>

<style>.fc { padding: 12px; display: flex; flex-direction: column; gap: 6px; }</style>
