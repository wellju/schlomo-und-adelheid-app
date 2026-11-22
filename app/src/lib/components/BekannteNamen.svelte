<script lang="ts">
  // Known names (stage 1 of the recognition). Kept in the app's memory only; the engine forgets them on restart.
  import { untrack } from 'svelte';
  import { fehlerText } from '../engine/fehler';
  import { namen, namenSenden } from '../namen.svelte';
  let { sid, ongesetzt }: { sid: string; ongesetzt?: (labelHit: boolean) => void } = $props();
  untrack(() => { namen[sid] ??= [{ text: '', rolle: 'das Kind' }]; }); // component is re-created per case
  let meldung = $state<string | null>(null);
  let fehler = $state<string | null>(null);
  async function setzen() {
    fehler = meldung = null;
    try {
      const r = await namenSenden(sid);
      meldung = 'Namen gesetzt. Sie gelten bis zum Schließen der App.';
      ongesetzt?.(r.bezeichnung_enthaelt_namen);
    } catch (e) {
      fehler = fehlerText(e).text;
    }
  }
</script>

<section class="cd box" aria-labelledby="h-namen-{sid}">
  <h2 class="h3" id="h-namen-{sid}">Bekannte Namen</h2>
  <span class="lb">Namen des Kindes, der Eltern, Lehrkräfte und Schule mit der Rolle, die sie ersetzt. Nur im Arbeitsspeicher, nie gespeichert.</span>
  {#each namen[sid] as n, i (i)}
    <div class="row">
      <div style="flex:2 1 200px"><label class="lb" for="n-{i}">Name {i + 1}</label><input class="in" id="n-{i}" bind:value={n.text} autocomplete="off"></div>
      <div style="flex:1 1 160px"><label class="lb" for="r-{i}">Rolle {i + 1}</label><input class="in" id="r-{i}" bind:value={n.rolle}></div>
      <button class="btn s g" type="button" style="align-self:flex-end" onclick={() => namen[sid].splice(i, 1)} aria-label="Name {i + 1} entfernen">Entfernen</button>
    </div>
  {/each}
  <div class="row">
    <button class="btn s" type="button" onclick={() => namen[sid].push({ text: '', rolle: '' })}>+ Name</button>
    <button class="btn s p" type="button" onclick={setzen}>Namen übernehmen</button>
  </div>
  <div role="status">{meldung ?? ''}</div>
  {#if fehler}<div class="err" role="alert">✕ {fehler}</div>{/if}
</section>

<style>.box { padding: 16px; display: flex; flex-direction: column; gap: 10px; }</style>
