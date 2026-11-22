<script lang="ts">
  // FindingDecision: segment group with aria-pressed. Verallgemeinern takes the engine's replacement (role, relative
  // date, general place), Schwärzen replaces with "[geschwärzt]", Behalten keeps the text. No default for SEL and
  // uncertain findings: they stay open until the psychologist decides.
  import { KATEGORIE } from '../kategorien';
  import type { Fund } from '../fall';
  let { fund, aktiv, onentscheide }: {
    fund: Fund; aktiv: boolean; onentscheide: (entscheidung: 'uebernehmen' | 'verwerfen' | 'aendern', ersatz?: string) => void;
  } = $props();
  const k = $derived(KATEGORIE[fund.kategorie]);
  const wert = $derived(fund.status === 'verworfen' ? 'behalten' : fund.status === 'geaendert' && fund.ersatz === '[geschwärzt]'
    ? 'schwaerzen' : fund.status === 'offen' ? null : 'verallgemeinern');
  const nichtBehaltbar = $derived(fund.kategorie === 'versteckte_inhalte' || (fund.quelle === 'liste' && fund.kategorie === 'direkte_identifikatoren'));
</script>

<li class="cd fd" class:akt={aktiv} id="fund-{fund.fund_id}" tabindex="-1">
  <div class="row"><span class="m {k.klasse}">{k.tag}</span><strong class="doc">{fund.text.length > 80 ? fund.text.slice(0, 80) + ' …' : fund.text}</strong>
    {#if fund.unsicher && fund.status === 'offen'}<span class="pl er">✕ unsicher · Entscheidung nötig</span>{:else if fund.status === 'offen'}<span class="pl wn">! offen</span>{/if}</div>
  <div class="lb">{k.label} · Vorschlag: {fund.ersatz} · Quelle: {fund.quelle === 'liste' ? 'bekannter Name' : fund.quelle === 'regel' ? 'Regel' : fund.quelle === 'ner' ? 'Namenserkennung' : fund.quelle === 'manuell' ? 'manuell' : 'Import'}</div>
  <div class="row" role="group" aria-label="Entscheidung zu {fund.text.slice(0, 40)}">
    <button class="btn s" type="button" aria-pressed={wert === 'verallgemeinern'} onclick={() => onentscheide('uebernehmen')}>Verallgemeinern</button>
    <button class="btn s" type="button" aria-pressed={wert === 'schwaerzen'} onclick={() => onentscheide('aendern', '[geschwärzt]')}>Schwärzen</button>
    <button class="btn s" type="button" aria-pressed={wert === 'behalten'} disabled={nichtBehaltbar}
            onclick={() => onentscheide('verwerfen')}>Behalten{nichtBehaltbar ? ' (nicht möglich)' : ''}</button>
  </div>
</li>

<style>
  .fd { padding: 12px; display: flex; flex-direction: column; gap: 6px; }
  .fd.akt { border-color: var(--ac); }
</style>
