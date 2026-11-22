<script lang="ts">
  // Screen 09: style profile from released, locally anonymised sample reports. The result of Claude is always a
  // draft; only the psychologist releases it. Sample reports are documents with the source role "Probegutachten".
  import { anonUebersicht, type AnonStatus } from '../lib/anon';
  import AppShell from '../lib/components/AppShell.svelte';
  import ClaudeHandoff from '../lib/components/ClaudeHandoff.svelte';
  import Zustand from '../lib/components/Zustand.svelte';
  import { call } from '../lib/engine/client';
  import { fehlerText } from '../lib/engine/fehler';
  import { gehe, href } from '../lib/router.svelte';

  let daten = $state<{ stilprofile: any[]; aktiv: string | null } | null>(null);
  let sessions = $state<any[]>([]);
  let anon = $state<AnonStatus>({ stufe: 'uebersicht', gesperrt: 0 });
  let laden = $state(true);
  let fehler = $state<unknown>(null);
  let gewaehlt = $state<string | null>(null);
  let sid = $state('');
  let aktionFehler = $state<string | null>(null);
  let meldung = $state('');

  async function laden_(still = false) {
    if (!still) { laden = true; fehler = null; }
    try {
      daten = await call('stilprofile_laden');
      sessions = (await call<{ sessions: any[] }>('sitzungen_auflisten')).sessions;
      anon = anonUebersicht(sessions);
      gewaehlt ??= daten!.stilprofile[0]?.version ?? null;
      sid ||= probeSitzungen[0]?.session_id ?? '';
    } catch (e) {
      if (!still) fehler = e;
    } finally {
      laden = false;
    }
  }
  laden_();

  const probe = (s: any) => s.dokumente.filter((d: any) => d.quelle_rolle === 'Probegutachten');
  const probeSitzungen = $derived(sessions.filter((s) => probe(s).length));
  const sitzung = $derived(sessions.find((s) => s.session_id === sid));
  const ungeschwaerzt = $derived(sitzung ? probe(sitzung).filter((d: any) => d.freigabe.status !== 'freigegeben').length : 0);
  const profil = $derived(daten?.stilprofile.find((p) => p.version === gewaehlt) ?? null);
  const stand = async () => (await call<{ stilprofile: any[] }>('stilprofile_laden')).stilprofile.length;

  async function probeSitzungAnlegen() {
    try {
      const r = await call<{ session: any }>('sitzung_anlegen', { bezeichnung: `Probegutachten ${probeSitzungen.length + 1}`, modus: 'gutachten', gutachtentyp: 'spf' });
      gehe('fall', r.session.session_id, 'dokumente');
    } catch (e) { aktionFehler = fehlerText(e).text; }
  }
  async function freigeben(v: string) {
    aktionFehler = null;
    try { await call('stilprofil_freigeben', { version: v }); meldung = `Version ${v} freigegeben und aktiv.`; await laden_(true); }
    catch (e) { aktionFehler = `Freigabe fehlgeschlagen: ${fehlerText(e).text}`; }
  }
</script>

<AppShell aktiv="stilprofil" anonStatus={anon} bereich="Wissen" titel="Stilprofil">
  <Zustand {laden} {fehler} erneut={() => laden_()} ladenText="Stilprofile werden geladen …">
    <section class="cd box" aria-labelledby="h-probe"><h2 class="h3" id="h-probe">Probegutachten</h2>
      <p class="lb" style="margin:0">Nur freigegebene, lokal anonymisierte Probegutachten. Importieren Sie sie in einer eigenen Sitzung mit der Quelle als Rolle „Probegutachten“ und bestätigen Sie die Schwärzung.</p>
      {#if probeSitzungen.length}
        <div style="max-width:360px"><label class="lb" for="ps">Sitzung mit Probegutachten</label>
          <select class="in" id="ps" bind:value={sid}>{#each probeSitzungen as s (s.session_id)}<option value={s.session_id}>{s.bezeichnung} · {probe(s).length} Probegutachten</option>{/each}</select></div>
        {#if ungeschwaerzt}<div class="warn" role="status"><strong style="color:var(--wnT)">! {ungeschwaerzt} Probegutachten nicht geschwärzt.</strong> Sie werden nicht analysiert, bis die Schwärzung bestätigt ist. <a href={href('fall', sid, 'anonymisierung')}>Schwärzen</a></div>{/if}
      {/if}
      <div class="row"><button class="btn" type="button" onclick={probeSitzungAnlegen}>Probegutachten hinzufügen</button>
        {#if sid}<a class="btn g" href={href('fall', sid, 'dokumente')}>Zu den Dokumenten</a>{/if}</div>
    </section>
    {#if sid}
      <ClaudeHandoff {sid} art="stil_lernen" titel="Stilprofil analysieren" befehl="/stil-lernen {sid}" {stand}
                     hinweis="Das Ergebnis ist immer ein Entwurf mit Belegzitaten; freigeben können nur Sie." onuebernommen={() => { gewaehlt = null; laden_(true); }} />
    {/if}
    {#if !daten?.stilprofile.length}
      <div class="empty"><h2 class="h2" style="color:var(--tx)">Noch kein Stilprofil</h2><div>Fügen Sie eigene, bereits geschwärzte Gutachten hinzu. Erkannte Stilmerkmale werden mit Belegzitaten angezeigt und erst nach Ihrer Freigabe verwendet.</div></div>
    {:else}
      <section class="cd box" aria-labelledby="h-vers"><h2 class="h3" id="h-vers">Versionen</h2>
        <ul class="liste">{#each daten.stilprofile as p (p.version)}
          <li class="row"><button class="btn s" type="button" aria-pressed={gewaehlt === p.version} onclick={() => (gewaehlt = p.version)}>Version {p.version}</button>
            <span class="pl {p.status === 'freigegeben' ? 'ok' : 'na'}">{p.status === 'freigegeben' ? '✓ Freigegeben' : 'Entwurf'}</span>
            {#if daten.aktiv === p.version}<span class="pl ai">aktiv</span>{/if}<span class="lb">{p.anzahl_probegutachten} Probegutachten</span></li>{/each}</ul>
      </section>
      {#if profil}
        <section class="cd box" aria-labelledby="h-merk"><div class="row"><h2 class="h3" id="h-merk">Erkannte Stilmerkmale · Version {profil.version}</h2><span class="pl ai">KI-Analyse</span></div>
          {#each profil.merkmale as m (m.merkmal_id)}
            <article class="cd merkmal"><strong>{m.beschreibung}</strong><span class="lb">{m.kategorie}</span>
              {#each m.belegzitate ?? [] as z, i (i)}<div class="doc lb">„{z.text}“ · {z.probe_id}</div>{/each}</article>
          {/each}
          <h3 class="h3">Formulierungsbeispiele</h3>
          {#each profil.formulierungsbeispiele as f, i (i)}<div class="doc">{f.abschnitt_id}: {f.text}</div>{/each}
          {#if profil.status !== 'freigegeben'}<button class="btn p" type="button" style="align-self:flex-start" onclick={() => freigeben(profil.version)}>Version {profil.version} freigeben</button>{/if}
        </section>
      {/if}
    {/if}
    <div role="status">{meldung}</div>
    {#if aktionFehler}<div class="err" role="alert">✕ {aktionFehler} Das aktive Profil bleibt unverändert.</div>{/if}
  </Zustand>
</AppShell>

<style>
  .box { padding: 16px; display: flex; flex-direction: column; gap: 10px; }
  .liste { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
  .merkmal { padding: 10px 12px; display: flex; flex-direction: column; gap: 4px; background: var(--bg); }
</style>
