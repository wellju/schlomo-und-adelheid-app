<script lang="ts">
  // File choice: system dialog in the app, a path field in development (synthetic files only).
  import { oeffnen, pfadFeld } from '../datei';
  let { label, endungen, onwahl, id }: { label: string; endungen: string[]; onwahl: (pfad: string) => void; id: string } = $props();
  let pfad = $state('');
  async function waehlen() {
    const p = await oeffnen(label, endungen);
    if (p) onwahl(p);
  }
</script>

{#if pfadFeld()}
  <div class="row">
    <label class="lb" for={id}>{label}: Pfad (nur Entwicklung, synthetische Dateien)</label>
    <input class="in" {id} type="text" bind:value={pfad} style="flex:1 1 320px">
    <button class="btn" type="button" disabled={!pfad.trim()} onclick={() => { onwahl(pfad.trim()); pfad = ''; }}>{label}</button>
  </div>
{:else}
  <button class="btn" type="button" onclick={waehlen}>{label} …</button>
{/if}
