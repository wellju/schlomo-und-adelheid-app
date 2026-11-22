<script lang="ts">
  // Category scale: ranges per scale with label and mandatory source; the psychologist enters the limits herself.
  import { call } from '../../lib/engine/client';
  import { fehlerText } from '../../lib/engine/fehler';
  import { naechsteVersion } from '../../lib/version';
  import VersionList from '../../lib/components/VersionList.svelte';
  let { skala, versionen, ongeaendert }: { skala: any | null; versionen: string[]; ongeaendert: () => void } = $props();
  const leer = () => ({ skala: 'iq', von: null as number | null, bis: null as number | null, bezeichnung: '', quelle: '', status: 'entwurf', herkunft: 'psychologin' });
  let neu = $state(leer());
  let fehler = $state<string | null>(null);
  let gespeichert = $state('');

  async function speichern(eintraege: any[]) {
    fehler = null;
    gespeichert = '';
    const dok = { schema_version: skala?.schema_version ?? '2', version: naechsteVersion(skala?.version ?? '0', versionen), eintraege };
    try {
      const r = await call<{ version: string }>('katalog_speichern', { name: 'kategorienskala', dokument: dok });
      gespeichert = `Gespeichert als Version ${r.version}.`;
      neu = leer();
      ongeaendert();
    } catch (e) {
      const f = fehlerText(e);
      fehler = f.code === 'E_SCHEMA' ? 'Nicht gespeichert: Jeder Bereich braucht Skala, Grenzen, Bezeichnung und eine Quelle; Bereiche derselben Skala dürfen sich nicht überschneiden.' : f.text;
    }
  }
  function hinzufuegen(e: SubmitEvent) {
    e.preventDefault();
    if (!neu.quelle.trim()) { fehler = 'Pflichtfeld Quelle fehlt. Ohne Quelle wird kein Bereich gespeichert.'; return; }
    speichern([...(skala?.eintraege ?? []), { ...neu, von: Number(neu.von), bis: Number(neu.bis) }]);
  }
  const SKALA: Record<string, string> = { iq: 'IQ', wertpunkte: 'Wertpunkte', t: 'T-Werte', pr: 'Prozentränge' };
</script>

<section class="stack" aria-label="Kategorienskala">
  {#if !skala?.eintraege?.length}
    <div class="empty"><h3 class="h2" style="color:var(--tx)">Kategorienskala · leer</h3><div>Die Grenzen tragen Sie selbst ein: je Skala Bereich, Bezeichnung und Quelle.</div></div>
  {:else}
    <div class="cd tbx"><table class="t"><caption class="sr">Kategorienskala Version {skala.version}</caption>
      <thead><tr><th scope="col">Skala</th><th scope="col">Von</th><th scope="col">Bis</th><th scope="col">Bezeichnung</th><th scope="col">Quelle</th><th scope="col">Status</th><th scope="col">Aktion</th></tr></thead>
      <tbody>{#each skala.eintraege as e, i (i)}
        <tr><td>{SKALA[e.skala]}</td><td>{e.von}</td><td>{e.bis}</td><td>{e.bezeichnung}</td><td>{e.quelle}</td>
          <td><span class="pl {e.status === 'freigegeben' ? 'ok' : 'na'}">{e.status === 'freigegeben' ? '✓ Freigegeben' : 'Entwurf'}</span></td>
          <td><div class="row">
            {#if e.status !== 'freigegeben'}<button class="btn s" type="button" onclick={() => speichern(skala.eintraege.map((x: any, j: number) => (j === i ? { ...x, status: 'freigegeben' } : x)))}>Freigeben<span class="sr"> {e.bezeichnung}</span></button>{/if}
            <button class="btn s g" type="button" onclick={() => speichern(skala.eintraege.filter((_: any, j: number) => j !== i))}>Entfernen<span class="sr"> {e.bezeichnung}</span></button></div></td></tr>
      {/each}</tbody></table></div>
  {/if}
  <form class="cd box" onsubmit={hinzufuegen} aria-labelledby="h-neu-ber">
    <h3 class="h3" id="h-neu-ber">Bereich eintragen</h3>
    <div class="grid">
      <div><label class="lb" for="ks-skala">Skala</label><select class="in" id="ks-skala" bind:value={neu.skala}>{#each Object.entries(SKALA) as [k, l] (k)}<option value={k}>{l}</option>{/each}</select></div>
      <div><label class="lb" for="ks-von">Von</label><input class="in" id="ks-von" type="number" required bind:value={neu.von}></div>
      <div><label class="lb" for="ks-bis">Bis</label><input class="in" id="ks-bis" type="number" required bind:value={neu.bis}></div>
      <div><label class="lb" for="ks-bez">Bezeichnung</label><input class="in" id="ks-bez" required bind:value={neu.bezeichnung}></div>
      <div><label class="lb" for="ks-q">Quelle *</label><input class="in" id="ks-q" bind:value={neu.quelle} placeholder="Manual, Seite"></div>
    </div>
    <button class="btn p" type="submit">+ Bereich speichern</button>
    <div role="status">{gespeichert}</div>
    {#if fehler}<div class="err" role="alert">✕ {fehler} Ihre Eingabe bleibt im Formular erhalten.</div>{/if}
  </form>
  {#if skala}<VersionList name="kategorienskala" aktiv={skala.version} {versionen} {ongeaendert} />{/if}
</section>

<style>
  .box { padding: 16px; display: flex; flex-direction: column; gap: 10px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; align-items: end; }
</style>
