<script lang="ts">
  import { tick } from 'svelte';
  import { app, starten } from './lib/app.svelte';
  import { route } from './lib/router.svelte';
  import { fehlerText } from './lib/engine/fehler';
  import S01Faelle from './screens/S01Faelle.svelte';
  import S02Import from './screens/S02Import.svelte';
  import S03Anonymisierung from './screens/S03Anonymisierung.svelte';
  import S04Eingabe from './screens/S04Eingabe.svelte';
  import S05Pruefung from './screens/S05Pruefung.svelte';
  import S06Export from './screens/S06Export.svelte';
  import S09Stilprofil from './screens/S09Stilprofil.svelte';
  import S10Katalog from './screens/S10Katalog.svelte';
  import S11Qualitaet from './screens/S11Qualitaet.svelte';
  import SRubberduck from './screens/SRubberduck.svelte';
  import S12Diagnosevergleich from './screens/S12Diagnosevergleich.svelte';
  import S13Einstellungen from './screens/S13Einstellungen.svelte';
  import Platzhalter from './screens/Platzhalter.svelte';

  starten();
  const key = $derived(route.teile.join('/'));
  // Move focus to the new screen title so screen readers announce the change of screen.
  $effect(() => {
    void key;
    tick().then(() => document.querySelector<HTMLElement>('main h1')?.focus());
  });
</script>

{#if !app.verbunden}
  <main class="start">
    <h1 class="h1">Schlomo und Adelheid</h1>
    {#if app.startFehler}
      {@const f = fehlerText(app.startFehler)}
      <div class="err" role="alert">
        <strong style="color:var(--erT)">✕ Die Engine konnte nicht gestartet werden.</strong>
        <p>{f.text} Fehlercode: {f.code}. Ihre Fälle sind unverändert.</p>
        <button class="btn" type="button" onclick={starten}>Erneut versuchen</button>
      </div>
    {:else}
      <div class="cd" style="padding:18px" aria-busy="true" role="status"><div class="sk" style="width:60%"></div><span class="lb">Engine wird gestartet …</span></div>
    {/if}
  </main>
{:else}
  {#key key}
    {@const [a, sid, bereich, extra] = route.teile}
    {#if a === 'faelle'}
      <S01Faelle />
    {:else if a === 'fall' && bereich === 'dokumente'}
      <S02Import {sid} />
    {:else if a === 'fall' && bereich === 'anonymisierung'}
      <S03Anonymisierung {sid} dok={extra} />
    {:else if a === 'fall' && bereich === 'eingabe'}
      <S04Eingabe {sid} />
    {:else if a === 'fall' && bereich === 'pruefung'}
      <S05Pruefung {sid} />
    {:else if a === 'fall' && bereich === 'export'}
      <S06Export {sid} />
    {:else if a === 'fall' && bereich === 'diagnosevergleich'}
      <S12Diagnosevergleich {sid} />
    {:else if a === 'katalog'}
      <S10Katalog />
    {:else if a === 'stilprofil'}
      <S09Stilprofil />
    {:else if a === 'qualitaet'}
      <S11Qualitaet />
    {:else if a === 'intervision' || a === 'supervision'}
      <SRubberduck {sid} modus={a} />
    {:else if a === 'einstellungen'}
      <S13Einstellungen />
    {:else}
      <Platzhalter teile={route.teile} />
    {/if}
  {/key}
{/if}

<style>
  .start { max-width: 640px; margin: 80px auto; padding: 0 16px; display: flex; flex-direction: column; gap: 20px; }
</style>
