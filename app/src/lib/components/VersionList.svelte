<script lang="ts">
  // VersionList: active state and earlier versions; a rollback creates a new version and deletes nothing.
  import { call } from '../engine/client';
  import { fehlerText } from '../engine/fehler';
  import { naechsteVersion } from '../version';
  let { name, aktiv, versionen, ongeaendert }: { name: string; aktiv: string; versionen: string[]; ongeaendert: () => void } = $props();
  let fehler = $state<string | null>(null);
  let hinweis = $state<string | null>(null);
  async function zurueck(v: string) {
    fehler = null;
    try {
      const r = await call<{ eval?: { bestanden: boolean } }>('rollback', { name, version: v, neue_version: naechsteVersion(aktiv, versionen) });
      hinweis = r.eval && !r.eval.bestanden ? 'Der wiederhergestellte Stand besteht die heutige Eval-Suite nicht. Er ist aktiv; prüfen Sie ihn.' : null;
      ongeaendert();
    } catch (e) {
      fehler = `Rollback fehlgeschlagen: ${fehlerText(e).text} Der aktive Stand ist unverändert.`;
    }
  }
</script>

<section aria-label="Versionsverlauf {name}" class="vl">
  <h3 class="h3">Versionsverlauf</h3>
  <ul>
    <li class="row"><span class="pl ok">✓ Aktiv</span> Version {aktiv}</li>
    {#each [...versionen].reverse() as v (v)}
      <li class="row"><span class="pl na">Version {v}</span><button class="btn s" type="button" onclick={() => zurueck(v)}>Auf Version {v} zurück</button></li>
    {:else}
      <li class="lb">Noch keine früheren Versionen.</li>
    {/each}
  </ul>
  {#if fehler}<div class="err" role="alert">✕ {fehler}</div>{/if}
  {#if hinweis}<div class="warn" role="status">! {hinweis}</div>{/if}
</section>

<style>
  .vl { display: flex; flex-direction: column; gap: 8px; }
  ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
</style>
