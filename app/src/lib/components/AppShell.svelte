<script lang="ts">
  // AppShell (Übergabe-Board): navigation, header with the mandatory anonymisation status, optional case tabs.
  import type { Snippet } from 'svelte';
  import type { AnonStatus } from '../anon';
  import { href } from '../router.svelte';
  import AnonStatusBadge from './AnonStatusBadge.svelte';

  type FallReiter = { session_id: string; bereich: string; modus: string };
  let {
    aktiv, anonStatus, bereich, titel, fall, kopf, children, modus = 'normal',
  }: {
    aktiv: string; anonStatus: AnonStatus; bereich: string; titel: string; fall?: FallReiter; kopf?: Snippet;
    children: Snippet; modus?: 'normal' | 'supervision';
  } = $props();

  const NAV = [
    ['faelle', 'Fälle'], ['katalog', 'Testkatalog und Regelwerk'], ['stilprofil', 'Stilprofil'],
    ['qualitaet', 'Lernen und Qualität'], ['einstellungen', 'Einstellungen'],
  ] as const;
  const GUTACHTEN_REITER = [
    ['dokumente', 'Dokumente'], ['anonymisierung', 'Anonymisierung'], ['eingabe', 'Eingabe'], ['pruefung', 'Entwurf und Prüfung'],
    ['export', 'Export'], ['diagnosevergleich', 'Diagnosevergleich'],
  ] as const;
</script>

<div class="shell" class:mode-supervision={modus === 'supervision'}>
  <nav class="side" aria-label="Hauptnavigation">
    <div class="marke"><div class="name">Schlomo und Adelheid</div><div class="lb">Gutachten und Reflexion</div></div>
    {#each NAV as [key, label] (key)}
      <a class="ni" class:on={aktiv === key} href={href(key)} aria-current={aktiv === key ? 'page' : undefined}>{label}</a>
    {/each}
    <div style="flex:1"></div>
    <div class="lb hinweis">KI-Vorschläge werden nie automatisch übernommen.</div>
  </nav>
  <main>
    {#if modus === 'supervision'}<div class="band" aria-hidden="true">Supervision</div>{/if}
    <header class="top">
      <div class="titel"><div class="lb">{bereich}</div><h1 class="h2" tabindex="-1">{titel}</h1></div>
      {@render kopf?.()}
      <AnonStatusBadge status={anonStatus} />
    </header>
    {#if fall && fall.modus === 'gutachten'}
      <nav class="reiter" aria-label="Bereiche des Falls">
        {#each GUTACHTEN_REITER as [key, label] (key)}
          <a class="tb" class:on={fall.bereich === key} href={href('fall', fall.session_id, key)}
             aria-current={fall.bereich === key ? 'page' : undefined}>{label}</a>
        {/each}
      </nav>
    {/if}
    <div class="inhalt">{@render children()}</div>
  </main>
</div>

<style>
  .shell { min-height: 100vh; display: flex; flex-wrap: wrap; }
  .side { flex: 1 1 200px; max-width: 240px; background: var(--sf); border-right: 1px solid var(--bd); padding: 16px 12px; display: flex; flex-direction: column; gap: 2px; }
  .marke { padding: 6px 10px 18px; }
  .name { font-weight: 600; font-size: 15px; }
  .hinweis { padding: 10px; }
  .ni { display: flex; align-items: center; min-height: 40px; padding: 0 10px; border-radius: 6px; color: var(--tx); text-decoration: none; font-weight: 500; }
  .ni:hover { background: var(--sf2); color: var(--tx); }
  .ni.on { background: var(--acS); color: var(--ac); }
  main { flex: 999 1 560px; min-width: 0; display: flex; flex-direction: column; }
  .top { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding: 12px 28px; border-bottom: 1px solid var(--bd); background: var(--sf); }
  .titel { flex: 1 1 300px; min-width: 0; }
  h1:focus { outline: none; }
  .band { background: var(--sv); color: var(--sf); font-weight: 600; font-size: 12px; letter-spacing: .04em; padding: 4px 28px; }
  .reiter { display: flex; flex-wrap: wrap; gap: 4px; padding: 0 28px; border-bottom: 1px solid var(--bd); background: var(--sf); }
  .tb { display: inline-flex; align-items: center; min-height: 44px; padding: 0 12px; color: var(--tx); text-decoration: none; font-weight: 500; border-bottom: 2px solid transparent; }
  .tb.on { color: var(--ac); border-bottom-color: var(--ac); }
  .inhalt { padding: 24px 28px; display: flex; flex-direction: column; gap: 20px; }
  @media (max-width: 719px) {
    .side { max-width: none; border-right: 0; border-bottom: 1px solid var(--bd); flex-direction: row; flex-wrap: wrap; }
    .marke, .hinweis { display: none; }
    .top, .inhalt { padding-left: 16px; padding-right: 16px; }
  }
</style>
