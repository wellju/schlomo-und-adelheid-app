<script lang="ts">
  // Screen 13: connection to Claude (ConnectionSetting) and profile of the author (QualificationProfile).
  import { anonUebersicht, type AnonStatus } from '../lib/anon';
  import { app, darstellungSetzen, hatQ1, type Einstellungen } from '../lib/app.svelte';
  import AppShell from '../lib/components/AppShell.svelte';
  import Zustand from '../lib/components/Zustand.svelte';
  import { call } from '../lib/engine/client';
  import { fehlerText } from '../lib/engine/fehler';
  import { ordnerWaehlen, pfadFeld } from '../lib/datei';

  let anon = $state<AnonStatus>({ stufe: 'uebersicht', gesperrt: 0 });
  let laden = $state(true);
  let fehler = $state<unknown>(null);
  let speicherFehler = $state<unknown>(null);
  let gespeichert = $state(false);
  let entwurf = $state<Einstellungen>(structuredClone($state.snapshot(app.einstellungen!)));
  let einrichtung = $state<{ eingerichtet: boolean; arbeitsordner: string | null } | null>(null);
  let ordner = $state('');
  let einrichtFehler = $state<string | null>(null);
  async function einrichten() {
    einrichtFehler = null;
    try {
      const ziel = pfadFeld() ? ordner.trim() : await ordnerWaehlen();
      if (!ziel) return;
      einrichtung = await call('einrichten', { arbeitsordner: ziel });
    } catch (e) {
      const f = fehlerText(e);
      einrichtFehler = f.code === 'E_BLOCKIERT' ? 'Der Ordner muss neu oder leer sein und darf nicht im Datenordner der App liegen.' : f.text;
    }
  }

  async function laden_() {
    laden = true;
    fehler = null;
    try {
      anon = anonUebersicht((await call<{ sessions: any[] }>('sitzungen_auflisten')).sessions);
      einrichtung = await call('einrichten_status');
    } catch (e) {
      fehler = e;
    } finally {
      laden = false;
    }
  }
  laden_();

  async function speichern() {
    speicherFehler = null;
    gespeichert = false;
    try {
      const r = await call<{ einstellungen: Einstellungen }>('einstellungen_speichern', { einstellungen: $state.snapshot(entwurf) });
      app.einstellungen = r.einstellungen;
      app.eingerichtet = true;
      darstellungSetzen(r.einstellungen.darstellung);
      gespeichert = true;
    } catch (e) {
      speicherFehler = e;
      entwurf = structuredClone($state.snapshot(app.einstellungen!));
    }
  }

  const QUALI = [
    ['schulpsychologin', 'Schulpsychologin'], ['klinische_psychologin', 'Klinische Psychologin'],
    ['gesundheitspsychologin', 'Gesundheitspsychologin'],
  ] as const;
  function quali(q: Einstellungen['qualifikationen'][number], an: boolean) {
    entwurf.qualifikationen = an ? [...entwurf.qualifikationen, q] : entwurf.qualifikationen.filter((x) => x !== q);
    speichern();
  }
</script>

<AppShell aktiv="einstellungen" anonStatus={anon} bereich="Einstellungen" titel="Verbindung und Profil">
  <Zustand {laden} {fehler} erneut={laden_} leer={!app.eingerichtet && !gespeichert} leerTitel="Noch nicht eingerichtet"
           leerText="Wählen Sie, wie Sie mit Claude arbeiten, und Ihre Qualifikation. Die Auswahl gilt für alle Fälle.">
    {#snippet leerAktion()}<button class="btn p" type="button" onclick={speichern}>Einrichten</button>{/snippet}
    {#snippet warnung()}
      {#if app.einstellungenBeschaedigt}
        <div class="warn" role="status"><strong style="color:var(--wnT)">! Die gespeicherten Einstellungen waren beschädigt.</strong> Es gelten die Vorgaben, bis Sie neu speichern.</div>
      {/if}
      {#if speicherFehler}
        <div class="err" role="alert"><strong style="color:var(--erT)">✕ Einstellungen nicht gespeichert.</strong> Ihre bisherigen Einstellungen gelten weiter.</div>
      {/if}
      {#if einrichtung && !einrichtung.eingerichtet && entwurf.verbindung === 'desktop'}
        <div class="warn" role="status" data-testid="warn-arbeitsordner"><strong style="color:var(--wnT)">! Arbeitsordner für Claude Desktop fehlt.</strong> Ohne ihn erreicht der Code-Tab die Engine nicht. Bitte unten einrichten oder die Verbindung auf Browser stellen.</div>
      {/if}
      {#if !hatQ1()}
        <div class="warn" role="status" data-testid="warn-q1"><strong style="color:var(--wnT)">! Ohne „Klinische Psychologin“</strong> sind Diagnosefelder und der Diagnosevergleich gesperrt.</div>
      {/if}
    {/snippet}
    <section class="cd box" aria-labelledby="h-verb">
      <h2 class="h2" id="h-verb">Verbindung zu Claude</h2>
      <div role="radiogroup" aria-labelledby="h-verb" class="wahl">
        <label class="cd opt" class:sel={entwurf.verbindung === 'desktop'}>
          <input type="radio" name="verb" value="desktop" bind:group={entwurf.verbindung} onchange={speichern}>
          <span><strong>Claude Desktop (Code-Tab)</strong><br><span class="lb">Direkt verbunden über die lokale Engine. Prüfer laufen als eigene Subagents.</span></span>
        </label>
        <label class="cd opt" class:sel={entwurf.verbindung === 'browser'}>
          <input type="radio" name="verb" value="browser" bind:group={entwurf.verbindung} onchange={speichern}>
          <span><strong>Claude im Browser</strong><br><span class="lb">Übergabe über Pakete zum Hochladen. Jede Prüfung in einem neuen Gespräch.</span></span>
        </label>
      </div>
    </section>
    <section class="cd box" aria-labelledby="h-prof">
      <h2 class="h2" id="h-prof">Profil der Verfasserin</h2>
      <fieldset class="row-q">
        <legend class="lb">Qualifikation</legend>
        {#each QUALI as [q, label] (q)}
          <label class="chk"><input type="checkbox" checked={entwurf.qualifikationen.includes(q)}
                                    onchange={(e) => quali(q, e.currentTarget.checked)}> {label}</label>
        {/each}
      </fieldset>
      <span class="lb">Ohne „Klinische Psychologin“ sind Diagnosefelder und der Diagnosevergleich gesperrt. Namen stehen hier nicht, sie setzen Sie im exportierten Dokument ein.</span>
    </section>
    <section class="cd box" aria-labelledby="h-ao">
      <h2 class="h2" id="h-ao">Arbeitsordner für Claude Desktop</h2>
      {#if einrichtung?.eingerichtet}
        <div><span class="pl ok">✓ Eingerichtet</span> <span class="lb">{einrichtung.arbeitsordner}</span></div>
        <span class="lb">Im Code-Tab diesen Ordner öffnen und den MCP-Server „engine“ beim ersten Start einmal freigeben.</span>
      {:else}
        <span class="lb">Ein neuer, leerer Ordner, etwa in Ihren Dokumenten. Die App legt dort Skills, Prüfer und die Verbindung zur Engine an; Falldaten liegen nie dort.</span>
        {#if pfadFeld()}<label class="lb" for="ao">Ordner: Pfad (nur Entwicklung)</label><input class="in" id="ao" bind:value={ordner}>{/if}
        <button class="btn" type="button" style="align-self:flex-start" onclick={einrichten}>Arbeitsordner einrichten</button>
      {/if}
      {#if einrichtFehler}<div class="err" role="alert">✕ {einrichtFehler}</div>{/if}
    </section>
    <section class="cd box" aria-labelledby="h-dar">
      <h2 class="h2" id="h-dar">Darstellung</h2>
      <label class="lb" for="dar">Farbschema</label>
      <select class="in" id="dar" style="max-width:260px" bind:value={entwurf.darstellung} onchange={speichern}>
        <option value="system">Wie das System</option><option value="hell">Hell</option><option value="dunkel">Dunkel</option>
      </select>
    </section>
    <section class="cd box" aria-labelledby="h-ds">
      <h2 class="h2" id="h-ds">Datenschutz</h2>
      <span style="font-size:13px">Echte Gutachten nie direkt in Claude hochladen, immer zuerst hier importieren und anonymisieren. Gesprächsverläufe im Browser liegen in Ihrem Claude-Konto, Aufbewahrung siehe Anleitung.</span>
    </section>
    <p class="lb" role="status">{gespeichert ? 'Gespeichert.' : ''} Engine {app.engineVersion}</p>
  </Zustand>
</AppShell>

<style>
  .box { padding: 16px 18px; display: flex; flex-direction: column; gap: 10px; }
  .wahl { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
  .opt { padding: 12px 14px; display: flex; gap: 10px; align-items: flex-start; cursor: pointer; }
  .opt.sel { border-color: var(--ac); }
  .row-q { display: flex; gap: 16px; flex-wrap: wrap; }
  .chk { display: flex; gap: 6px; align-items: center; min-height: 40px; }
</style>
