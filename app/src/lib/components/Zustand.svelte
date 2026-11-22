<script lang="ts">
  // State blocks of every screen (Übergabe-Board "State-Bausteine"): Laden as skeleton, Fehler with role="alert"
  // (what happened, what was kept, next step), Leer with exactly one action, Warnung above the normal content.
  import type { Snippet } from 'svelte';
  import { fehlerText } from '../engine/fehler';

  let {
    laden = false, fehler = null, leer = false, ladenText = 'Wird geladen …', erhalten = 'Ihre gespeicherten Daten sind unverändert.',
    erneut, leerTitel = '', leerText = '', leerAktion, warnung, children,
  }: {
    laden?: boolean; fehler?: unknown; leer?: boolean; ladenText?: string; erhalten?: string; erneut?: () => void;
    leerTitel?: string; leerText?: string; leerAktion?: Snippet; warnung?: Snippet; children?: Snippet;
  } = $props();
  const f = $derived(fehler ? fehlerText(fehler) : null);
</script>

{#if laden}
  <div class="cd sk-box" aria-busy="true" role="status" aria-label={ladenText}>
    <div class="sk" style="width:30%"></div><div class="sk" style="width:90%"></div><div class="sk" style="width:80%"></div>
    <span class="lb">{ladenText}</span>
  </div>
{:else if f}
  <div class="err stack-s" role="alert">
    <strong style="color:var(--erT)">✕ {f.text}</strong>
    <span>{erhalten} Fehlercode: {f.code}{#if f.grund} ({f.grund}){/if}. Die Protokolldatei enthält keine Falldaten.</span>
    {#if erneut}<button class="btn" type="button" onclick={erneut}>Erneut versuchen</button>{/if}
  </div>
{:else if leer}
  <div class="empty">
    <h2 class="h2" style="color:var(--tx)">{leerTitel}</h2>
    <div style="max-width:520px">{leerText}</div>
    {@render leerAktion?.()}
  </div>
{:else}
  {@render warnung?.()}
  {@render children?.()}
{/if}

<style>
  .sk-box { padding: 18px; display: flex; flex-direction: column; gap: 16px; }
  .stack-s { display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
</style>
