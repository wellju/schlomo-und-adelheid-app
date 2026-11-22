<script lang="ts">
  // Test catalogue: procedures with age range, norm type and year, norm groups, confidence levels, reliabilities,
  // indices with subtests, the fixed description block, and a mandatory source (manual and page).
  import { call } from '../../lib/engine/client';
  import { fehlerText } from '../../lib/engine/fehler';
  import { naechsteVersion } from '../../lib/version';
  import VersionList from '../../lib/components/VersionList.svelte';
  let { katalog, versionen, ongeaendert }: { katalog: any | null; versionen: string[]; ongeaendert: () => void } = $props();

  const Q = () => ({ manual: '', seite: '' });
  const A = (j = 0, m = 0) => ({ jahre: j, monate: m });
  function leer() {
    return { id: '', name: '', verfahrensversion: '', art: 'intelligenztest', altersbereich: { von: A(6), bis: A(16, 11) }, normart: 'alter',
      normjahr: null as number | null, normgruppen: [] as any[], konfidenzniveaus: [0.95], einzeltestung: true, mehrdimensional: false,
      messbereich: { iq_min: null as number | null, iq_max: null as number | null, quelle: Q() },
      innere_konsistenz: { wert: null as number | null, quelle: Q() }, retest: { wert: null as number | null, quelle: Q() },
      indizes: [] as any[], beschreibungsbaustein: { text: '', zitat: '' }, quelle: Q(), status: 'entwurf', befuellt_von: 'psychologin' };
  }
  let form = $state<any>(null);
  let alteId = $state<string | null>(null);
  let fehler = $state<string | null>(null);
  let gespeichert = $state('');
  const ohneQuelle = $derived((katalog?.eintraege ?? []).filter((e: any) => !e.quelle?.manual?.trim() || !e.quelle?.seite?.trim()));

  function bereinigen(f: any) {
    const o = structuredClone($state.snapshot(f));
    o.normjahr = Number(o.normjahr);
    for (const k of ['innere_konsistenz', 'retest']) if (o[k].wert === null || o[k].wert === '') delete o[k]; else o[k].wert = Number(o[k].wert);
    if (o.art !== 'intelligenztest' && (o.messbereich.iq_min === null || o.messbereich.iq_min === '')) delete o.messbereich;
    else { o.messbereich.iq_min = Number(o.messbereich.iq_min); o.messbereich.iq_max = Number(o.messbereich.iq_max); }
    if (!o.verfahrensversion) delete o.verfahrensversion;
    o.konfidenzniveaus = o.konfidenzniveaus.map(Number);
    return o;
  }

  async function speichern(eintraege: any[]) {
    fehler = null;
    gespeichert = '';
    const dok = { schema_version: katalog?.schema_version ?? '3', version: naechsteVersion(katalog?.version ?? '0', versionen), eintraege };
    try {
      const r = await call<{ version: string }>('katalog_speichern', { name: 'testkatalog', dokument: dok });
      gespeichert = `Gespeichert als Version ${r.version}.`;
      form = null;
      ongeaendert();
    } catch (e) {
      const f = fehlerText(e);
      fehler = f.code === 'E_SCHEMA'
        ? 'Nicht gespeichert: Pflichtfelder fehlen oder sind leer. Jede Quelle braucht Manual und Seite, Intelligenztests Konfidenzniveaus und Messbereich.'
        : f.text;
    }
  }
  function absenden(e: SubmitEvent) {
    e.preventDefault();
    const o = bereinigen(form);
    if (!o.quelle.manual.trim() || !o.quelle.seite.trim()) { fehler = 'Pflichtfeld Quelle fehlt: Manual und Seite angeben.'; return; }
    const rest = (katalog?.eintraege ?? []).filter((x: any) => x.id !== alteId);
    speichern([...rest, o]);
  }
  const ART: Record<string, string> = { intelligenztest: 'Intelligenztest', adaptives_verhalten: 'Adaptives Verhalten', leistungstest: 'Leistungstest', sprachstand: 'Sprachstand', sonstiges: 'Sonstiges' };
  const mon = (a: any) => `${a.jahre};${a.monate}`;
</script>

<section class="stack" aria-label="Testkatalog">
  {#if ohneQuelle.length}
    <div class="warn" role="status"><strong style="color:var(--wnT)">! {ohneQuelle.length} {ohneQuelle.length === 1 ? 'Eintrag' : 'Einträge'} ohne Quelle.</strong> {ohneQuelle.map((e: any) => e.name).join(', ')} kann nicht gespeichert werden, solange das Pflichtfeld Quelle leer ist.</div>
  {/if}
  {#if !katalog?.eintraege?.length}
    <div class="empty"><h3 class="h2" style="color:var(--tx)">Ihr Testkatalog ist leer</h3><div>Tragen Sie die Verfahren ein, die Sie verwenden: Name und Version, Normgruppen, Konfidenzniveaus und die Quelle, etwa Manual und Seite.</div></div>
  {:else}
    <div class="cd tbx"><table class="t"><caption class="sr">Testkatalog Version {katalog.version}</caption>
      <thead><tr><th scope="col">Verfahren</th><th scope="col">Art</th><th scope="col">Normgruppen</th><th scope="col">Normjahr</th><th scope="col">Konfidenzniveaus</th><th scope="col">Quelle *</th><th scope="col">Status</th><th scope="col">Aktion</th></tr></thead>
      <tbody>{#each katalog.eintraege as e (e.id)}
        <tr><td><strong>{e.name}</strong>{e.verfahrensversion ? ` · ${e.verfahrensversion}` : ''}</td><td>{ART[e.art]}</td>
          <td>{(e.normgruppen ?? []).map((g: any) => `${mon(g.von)} bis ${mon(g.bis)}`).join(', ') || '–'}</td><td>{e.normjahr}</td>
          <td>{(e.konfidenzniveaus ?? []).map((n: number) => `${Math.round(n * 100)} %`).join(', ') || '–'}</td>
          <td>{e.quelle?.manual ? `${e.quelle.manual}, S. ${e.quelle.seite}` : '✕ Pflichtfeld fehlt'}</td>
          <td><span class="pl {e.status === 'freigegeben' ? 'ok' : 'na'}">{e.status === 'freigegeben' ? '✓ Freigegeben' : 'Entwurf'}</span></td>
          <td><div class="row"><button class="btn s" type="button" onclick={() => { form = structuredClone($state.snapshot(e)); form.messbereich ??= { iq_min: null, iq_max: null, quelle: Q() }; form.innere_konsistenz ??= { wert: null, quelle: Q() }; form.retest ??= { wert: null, quelle: Q() }; alteId = e.id; }}>Bearbeiten<span class="sr"> {e.name}</span></button>
            {#if e.status !== 'freigegeben'}<button class="btn s" type="button" onclick={() => speichern(katalog.eintraege.map((x: any) => (x.id === e.id ? { ...x, status: 'freigegeben' } : x)))}>Freigeben<span class="sr"> {e.name}</span></button>{/if}</div></td></tr>
      {/each}</tbody></table></div>
  {/if}
  {#if !form}
    <button class="btn p" type="button" style="align-self:flex-start" onclick={() => { form = leer(); alteId = null; }}>+ Verfahren eintragen</button>
  {:else}
    <form class="cd box" onsubmit={absenden} aria-labelledby="h-vf">
      <h3 class="h3" id="h-vf">{alteId ? 'Verfahren bearbeiten' : 'Verfahren eintragen'}</h3>
      <div class="grid">
        <div><label class="lb" for="tk-id">Kennung (klein, ohne Leerzeichen)</label><input class="in" id="tk-id" required pattern="[a-z0-9\-]+" bind:value={form.id}></div>
        <div><label class="lb" for="tk-name">Name</label><input class="in" id="tk-name" required bind:value={form.name}></div>
        <div><label class="lb" for="tk-ver">Version des Verfahrens</label><input class="in" id="tk-ver" bind:value={form.verfahrensversion}></div>
        <div><label class="lb" for="tk-art">Art</label><select class="in" id="tk-art" bind:value={form.art}>{#each Object.entries(ART) as [k, l] (k)}<option value={k}>{l}</option>{/each}</select></div>
        <div><label class="lb" for="tk-na">Normart</label><select class="in" id="tk-na" bind:value={form.normart}><option value="alter">Alter</option><option value="klasse">Klasse</option></select></div>
        <div><label class="lb" for="tk-nj">Normjahr laut Manual</label><input class="in" id="tk-nj" type="number" required bind:value={form.normjahr}></div>
        <div><label class="lb" for="tk-ab-vj">Altersbereich von (Jahre)</label><input class="in" id="tk-ab-vj" type="number" min="0" bind:value={form.altersbereich.von.jahre}></div>
        <div><label class="lb" for="tk-ab-bj">Altersbereich bis (Jahre)</label><input class="in" id="tk-ab-bj" type="number" min="0" bind:value={form.altersbereich.bis.jahre}></div>
        <div><label class="lb" for="tk-kn">Konfidenzniveaus in % (durch Komma)</label><input class="in" id="tk-kn" value={form.konfidenzniveaus.map((n: number) => Math.round(n * 100)).join(', ')}
          onchange={(e) => (form.konfidenzniveaus = e.currentTarget.value.split(',').map((x) => Number(x.trim()) / 100).filter((x) => x > 0 && x < 1))}></div>
        <label class="row"><input type="checkbox" bind:checked={form.einzeltestung}> Einzeltestung</label>
        <label class="row"><input type="checkbox" bind:checked={form.mehrdimensional}> Mehrdimensional</label>
      </div>
      <fieldset class="stack-s"><legend class="h3">Normgruppen (J;M)</legend>
        {#each form.normgruppen as g, i (i)}
          <div class="row">
            {#each [['von', 'von'], ['bis', 'bis']] as [k, l] (k)}
              <label class="lb">{l} Jahre <input class="in kurz" type="number" min="0" bind:value={g[k].jahre}></label>
              <label class="lb">Monate <input class="in kurz" type="number" min="0" max="11" bind:value={g[k].monate}></label>
            {/each}
            <button class="btn s g" type="button" onclick={() => form.normgruppen.splice(i, 1)}>Normgruppe {i + 1} entfernen</button>
          </div>
        {/each}
        <button class="btn s" type="button" style="align-self:flex-start" onclick={() => form.normgruppen.push({ von: A(), bis: A() })}>+ Normgruppe</button>
      </fieldset>
      <fieldset class="stack-s"><legend class="h3">Indizes und Subtests</legend>
        {#each form.indizes as ix, i (i)}
          <div class="cd sub">
            <div class="grid">
              <div><label class="lb" for="ix-k-{i}">Index {i + 1}: Kennung</label><input class="in" id="ix-k-{i}" required bind:value={ix.kennung}></div>
              <div><label class="lb" for="ix-b-{i}">Bezeichnung</label><input class="in" id="ix-b-{i}" required bind:value={ix.bezeichnung}></div>
              <div><label class="lb" for="ix-s-{i}">Skala</label><select class="in" id="ix-s-{i}" bind:value={ix.skala}><option value="iq">IQ</option><option value="wertpunkte">Wertpunkte</option><option value="t">T-Werte</option><option value="pr">Prozentränge</option></select></div>
            </div>
            {#each ix.subtests as st, j (j)}
              <div class="grid">
                <div><label class="lb" for="st-k-{i}-{j}">Subtest {j + 1}: Kennung</label><input class="in" id="st-k-{i}-{j}" required bind:value={st.kennung}></div>
                <div><label class="lb" for="st-b-{i}-{j}">Bezeichnung</label><input class="in" id="st-b-{i}-{j}" required bind:value={st.bezeichnung}></div>
                <div><label class="lb" for="st-i-{i}-{j}">Inhalte</label><input class="in" id="st-i-{i}-{j}" bind:value={st.inhalte_text}></div>
              </div>
            {/each}
            <div class="row"><button class="btn s" type="button" onclick={() => ix.subtests.push({ kennung: '', bezeichnung: '', skala: 'wertpunkte', inhalte_text: '' })}>+ Subtest</button>
              <button class="btn s g" type="button" onclick={() => form.indizes.splice(i, 1)}>Index {i + 1} entfernen</button></div>
          </div>
        {/each}
        <button class="btn s" type="button" style="align-self:flex-start" onclick={() => form.indizes.push({ kennung: '', bezeichnung: '', skala: 'iq', subtests: [] })}>+ Index</button>
      </fieldset>
      {#if form.art === 'intelligenztest'}
        <div class="grid">
          <div><label class="lb" for="mb-min">Messbereich IQ von</label><input class="in" id="mb-min" type="number" bind:value={form.messbereich.iq_min}></div>
          <div><label class="lb" for="mb-max">Messbereich IQ bis</label><input class="in" id="mb-max" type="number" bind:value={form.messbereich.iq_max}></div>
          <div><label class="lb" for="mb-qm">Quelle Messbereich: Manual</label><input class="in" id="mb-qm" bind:value={form.messbereich.quelle.manual}></div>
          <div><label class="lb" for="mb-qs">Seite</label><input class="in" id="mb-qs" bind:value={form.messbereich.quelle.seite}></div>
        </div>
      {/if}
      <div class="grid">
        {#each [['innere_konsistenz', 'Innere Konsistenz'], ['retest', 'Retest-Reliabilität']] as [k, l] (k)}
          <div><label class="lb" for="rel-{k}">{l} (0 bis 1, optional)</label><input class="in" id="rel-{k}" type="number" step="0.01" min="0" max="1" bind:value={form[k].wert}></div>
          <div><label class="lb" for="rel-{k}-m">Quelle {l}: Manual</label><input class="in" id="rel-{k}-m" bind:value={form[k].quelle.manual}></div>
          <div><label class="lb" for="rel-{k}-s">Seite</label><input class="in" id="rel-{k}-s" bind:value={form[k].quelle.seite}></div>
        {/each}
      </div>
      <label class="lb" for="bb-t">Beschreibungsbaustein (fester Text aus Ihrer Vorlage, wird nie verändert)</label><textarea class="in" id="bb-t" required bind:value={form.beschreibungsbaustein.text}></textarea>
      <label class="lb" for="bb-z">Zitat des Bausteins</label><input class="in" id="bb-z" required bind:value={form.beschreibungsbaustein.zitat}>
      <div class="grid">
        <div><label class="lb" for="q-m">Quelle *: Manual</label><input class="in" id="q-m" bind:value={form.quelle.manual}></div>
        <div><label class="lb" for="q-s">Quelle *: Seite</label><input class="in" id="q-s" bind:value={form.quelle.seite}></div>
      </div>
      <div class="row"><button class="btn p" type="submit">Verfahren speichern</button><button class="btn g" type="button" onclick={() => (form = null)}>Abbrechen</button></div>
    </form>
  {/if}
  <div role="status">{gespeichert}</div>
  {#if fehler}<div class="err" role="alert">✕ {fehler} Ihre Eingabe bleibt im Formular erhalten.</div>{/if}
  {#if katalog}<VersionList name="testkatalog" aktiv={katalog.version} {versionen} {ongeaendert} />{/if}
</section>

<style>
  .box { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
  .sub { padding: 12px; background: var(--bg); display: flex; flex-direction: column; gap: 8px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; align-items: end; }
  .stack-s { display: flex; flex-direction: column; gap: 8px; }
  .kurz { width: 80px; }
</style>
