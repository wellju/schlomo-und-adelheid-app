<script lang="ts">
  // ReleaseGate: the lock is enforced in the logic (freigeben refuses with blockers), not only in the button; the
  // engine checks again (anonymisierung_freigeben). The note about incompleteness is fixed text.
  let { blocker, onbestaetigen }: { blocker: string[]; onbestaetigen: () => Promise<void> } = $props();
  let gesehen = $state(false);
  let laeuft = $state(false);
  const gruende = $derived([...blocker, ...(gesehen ? [] : ['Bestätigung der Durchsicht fehlt'])]);
  async function freigeben() {
    if (gruende.length || laeuft) return;
    laeuft = true;
    try { await onbestaetigen(); } finally { laeuft = false; }
  }
</script>

<section class="cd gate" aria-labelledby="h-gate">
  <h2 class="h3" id="h-gate">Schwärzung bestätigen</h2>
  <p class="lb" style="margin:0">Die Erkennung kann Angaben übersehen. Mit der Bestätigung erklären Sie, dass der Text keine Namen, Daten oder seltenen Merkmale mehr enthält, die das Kind erkennbar machen. Erst dann geht er an Eingabe, Prüfung oder Claude.</p>
  <label class="row"><input type="checkbox" bind:checked={gesehen}> Ich habe den ganzen Text und jeden Fund geprüft.</label>
  {#if gruende.length}<ul class="lb" aria-label="Noch gesperrt">{#each gruende as g (g)}<li>{g}</li>{/each}</ul>{/if}
  <button class="btn p" type="button" aria-disabled={gruende.length > 0} disabled={laeuft} onclick={freigeben}>
    {gruende.length ? 'Weitergabe gesperrt' : 'Schwärzung bestätigen'}</button>
</section>

<style>
  .gate { padding: 16px; display: flex; flex-direction: column; gap: 10px; }
  ul { margin: 0; padding-left: 18px; }
  .btn[aria-disabled="true"] { opacity: .55; cursor: not-allowed; }
</style>
