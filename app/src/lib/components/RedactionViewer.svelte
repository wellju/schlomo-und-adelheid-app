<script lang="ts">
  // RedactionViewer: text of the working copy with every finding marked by type tag (not colour alone). Clear text
  // stays in this component's memory; selecting text offers it for a manual redaction.
  import { KATEGORIE, SICHTBAR } from '../kategorien';
  import type { Fund, Teil } from '../fall';
  let { teile, funde, aktiv, onwahl, onauswahl }: {
    teile: Teil[]; funde: Fund[]; aktiv: string | null; onwahl: (id: string) => void; onauswahl: (text: string) => void;
  } = $props();

  function stuecke(t: Teil) {
    const fs = funde.filter((f) => f.teil === t.teil).sort((a, b) => a.start - b.start);
    const out: { text: string; fund?: Fund }[] = [];
    let pos = 0;
    for (const f of fs) {
      if (f.start < pos) continue;
      if (f.start > pos) out.push({ text: t.text.slice(pos, f.start) });
      out.push({ text: t.text.slice(f.start, f.end), fund: f });
      pos = f.end;
    }
    if (pos < t.text.length) out.push({ text: t.text.slice(pos) });
    return out;
  }
  function auswahl() {
    const s = window.getSelection()?.toString().trim();
    if (s && s.length >= 2 && s.length <= 200) onauswahl(s);
  }
  const sichtbar = $derived(teile.filter((t) => SICHTBAR.includes(t.art)));
</script>

<!-- svelte-ignore a11y_no_static_element_interactions: selecting text with the mouse is an extra path; the same
     action is available by keyboard in the manual redaction field -->
<div class="cd doc ansicht" onmouseup={auswahl}>
  {#each sichtbar as t (t.teil)}
    <div class="teil">
      {#if t.art !== 'haupttext' || t.seite}<div class="lb">{t.art === 'haupttext' ? `Seite ${t.seite}` : t.art === 'kopf_fusszeile' ? 'Kopf- oder Fußzeile' : 'Fußnote'}</div>{/if}
      <p>{#each stuecke(t) as s, i (i)}{#if s.fund}{@const k = KATEGORIE[s.fund.kategorie]}<button type="button"
        class="m {k.klasse} mk" class:aus={s.fund.status === 'verworfen'} class:akt={aktiv === s.fund.fund_id}
        onclick={() => onwahl(s.fund!.fund_id)}>{s.text}<span class="tg" aria-hidden="true">{k.tag}{s.fund.unsicher && s.fund.status === 'offen' ? ' · unsicher' : ''}</span><span class="sr">: {k.label}, {s.fund.status === 'verworfen' ? 'behalten' : s.fund.status === 'offen' ? 'offen' : 'ersetzt'}</span></button>{:else}{s.text}{/if}{/each}</p>
    </div>
  {:else}
    <p class="mu">Kein sichtbarer Text. Gescannte Seiten brauchen zuerst die Texterkennung.</p>
  {/each}
</div>

<style>
  .ansicht { padding: 20px 24px; max-height: 70vh; overflow: auto; }
  .teil p { margin: 4px 0 16px; white-space: pre-wrap; }
  .mk { font: inherit; color: inherit; cursor: pointer; border-top: 0; border-left: 0; border-right: 0; }
  .mk.aus { opacity: .7; text-decoration: line-through; }
  .mk.akt { outline: 2px solid var(--ac); outline-offset: 1px; }
</style>
