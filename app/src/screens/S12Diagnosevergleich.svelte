<script lang="ts">
  // Screen 12: blind comparison. Step 1 the psychologist's own diagnosis (stays on this device, never goes to Claude);
  // step 2 only then the proposals of the engine and of Claude side by side. Only with Q1; never in the report.
  import { anonVonSession } from '../lib/anon';
  import { hatQ1 } from '../lib/app.svelte';
  import AppShell from '../lib/components/AppShell.svelte';
  import ClaudeHandoff from '../lib/components/ClaudeHandoff.svelte';
  import Zustand from '../lib/components/Zustand.svelte';
  import { call, EngineFehler } from '../lib/engine/client';
  import { fehlerText } from '../lib/engine/fehler';
  import { ladeFall, type Fall } from '../lib/fall';
  import { href } from '../lib/router.svelte';

  let { sid }: { sid: string } = $props();
  let fall = $state<Fall | null>(null);
  let vergleich = $state<any>(null);
  let uebersicht = $state<any>(null);
  let laden = $state(true);
  let fehler = $state<unknown>(null);
  let gesperrtQ1 = $state(false);
  let intern = $state({ text: '', icd10_code: '', schweregrad: '' });
  let notiz = $state('');
  let aktionFehler = $state<string | null>(null);
  let gespeichert = $state('');
  let funde = $state<{ text: string; sicher: boolean }[]>([]);

  async function vergleichLaden() {
    try {
      vergleich = await call('diagnosevergleich_laden', { session_id: sid });
      notiz = vergleich.vergleich.notiz ?? '';
    } catch (e) {
      if (e instanceof EngineFehler && e.code === 'E_BLOCKIERT') vergleich = null; // no own diagnosis yet: stay blind
      else if (e instanceof EngineFehler && e.code === 'E_Q1') gesperrtQ1 = true;
      else throw e;
    }
  }
  async function laden_() {
    laden = true;
    fehler = null;
    try {
      fall = await ladeFall(sid);
      gesperrtQ1 = !hatQ1();
      if (!gesperrtQ1 && fall.gutachten_input) await vergleichLaden();
      uebersicht = (await call('diagnosevergleich_uebersicht')).uebersicht;
    } catch (e) {
      fehler = e;
    } finally {
      laden = false;
    }
  }
  laden_();

  async function internSpeichern(e: SubmitEvent) {
    e.preventDefault();
    aktionFehler = null;
    const d: any = { text: intern.text };
    if (intern.icd10_code.trim()) d.icd10_code = intern.icd10_code.trim().toUpperCase();
    if (intern.schweregrad) d.schweregrad = intern.schweregrad;
    try {
      const r = await call('interne_diagnose_speichern', { session_id: sid, interne_diagnose: d });
      if (!r.gespeichert) { funde = r.funde; return; }
      funde = [];
      await vergleichLaden();
      uebersicht = (await call('diagnosevergleich_uebersicht')).uebersicht;
    } catch (err) {
      aktionFehler = fehlerText(err).code === 'E_SCHEMA' ? 'Nicht gespeichert: Der ICD-10-Code hat die Form A00 oder A00.0.' : fehlerText(err).text;
    }
  }
  async function notizSpeichern() {
    aktionFehler = null;
    gespeichert = '';
    try {
      const r = await call('vergleich_notiz_speichern', { session_id: sid, notiz });
      if (!r.gespeichert) { funde = r.funde; return; }
      funde = [];
      gespeichert = 'Notiz gespeichert.';
    } catch (e) { aktionFehler = fehlerText(e).text; }
  }
  const claudeStand = async () => ((await call('diagnosevergleich_laden', { session_id: sid })).claude ? 1 : 0);
  const VGL: Record<string, [string, string]> = { gleich: ['ok', '✓ gleich wie Ihre'], abweichend: ['wn', '◆ abweichend'], nicht_vergleichbar: ['na', '? nicht vergleichbar'] };
  const SCHWERE = ['leicht', 'mittelgradig', 'schwer', 'schwerst', 'keiner'];
</script>

<AppShell aktiv="faelle" anonStatus={fall ? anonVonSession(fall.session) : { stufe: 'nicht_geprueft' }} bereich={fall?.session.bezeichnung ?? 'Fall'}
          titel="Diagnosevergleich" fall={fall ? { session_id: sid, bereich: 'diagnosevergleich', modus: fall.session.modus } : undefined}>
  <Zustand {laden} {fehler} erneut={laden_} ladenText="Vorschläge werden geladen …">
    <p class="lb" style="margin:0">Nur mit der Qualifikation Klinische Psychologin. Erscheint nie im Gutachten.</p>
    {#if funde.length}
      <div class="warn" role="alert"><strong style="color:var(--wnT)">! Mögliche identifizierende Angaben. Nicht gespeichert.</strong> {funde.map((f) => f.text).join(', ')}. Bitte neutral formulieren.</div>
    {/if}
    {#if gesperrtQ1}
      <div class="warn" role="status"><strong style="color:var(--wnT)">! Gesperrt.</strong> Im Profil oder in der Eingabe dieses Falls ist keine Qualifikation Klinische Psychologin hinterlegt. <a href={href('einstellungen')}>Zu den Einstellungen</a></div>
    {:else if !fall?.gutachten_input}
      <div class="empty"><h2 class="h2" style="color:var(--tx)">Noch keine Eingabe</h2><div>Der Vergleich braucht die gespeicherte Eingabe des Falls.</div><a class="btn p" href={href('fall', sid, 'eingabe')}>Zur Eingabe</a></div>
    {:else if !vergleich}
      <form class="cd box" onsubmit={internSpeichern} aria-labelledby="h-s1">
        <h2 class="h3" id="h-s1">Schritt 1 · Ihre interne Diagnose</h2>
        <span class="lb">Bleibt auf diesem Gerät, geht nie an Claude. Nach dem ersten Vergleich nicht mehr änderbar.</span>
        <label class="lb" for="id-text">Diagnose</label><textarea class="in" id="id-text" required maxlength="2000" bind:value={intern.text}></textarea>
        <div class="grid">
          <div><label class="lb" for="id-code">ICD-10-Code (optional)</label><input class="in" id="id-code" bind:value={intern.icd10_code} placeholder="A00.0"></div>
          <div><label class="lb" for="id-sg">Schweregrad (optional)</label><select class="in" id="id-sg" bind:value={intern.schweregrad}><option value="">keine Angabe</option>{#each SCHWERE as s (s)}<option value={s}>{s}</option>{/each}</select></div>
        </div>
        <p class="lb" style="margin:0">Die Vorschläge werden erst sichtbar, nachdem Sie Ihre Diagnose eingetragen haben. So beeinflussen sie Ihr Urteil nicht.</p>
        <button class="btn p" type="submit">Interne Diagnose speichern</button>
        {#if aktionFehler}<div class="err" role="alert">✕ {aktionFehler}</div>{/if}
      </form>
      <div class="empty" data-testid="blind"><h2 class="h2" style="color:var(--tx)">Noch kein Vergleich</h2><div>Tragen Sie zuerst Ihre interne Diagnose ein. Danach sehen Sie die Vorschläge von Engine und Claude daneben.</div></div>
    {:else}
      <section class="cd box" aria-labelledby="h-s1b"><h2 class="h3" id="h-s1b">✓ Schritt 1 · Ihre interne Diagnose</h2>
        <div>{vergleich.interne_diagnose.text}{vergleich.interne_diagnose.icd10_code ? ` · ${vergleich.interne_diagnose.icd10_code}` : ''}{vergleich.interne_diagnose.schweregrad ? ` · ${vergleich.interne_diagnose.schweregrad}` : ''}</div></section>
      <section aria-labelledby="h-s2" class="stack">
        <h2 class="h3" id="h-s2">Schritt 2 · Vorschläge zum Vergleich</h2>
        <div class="zwei">
          <article class="cd box" aria-label="Vorschlag der Engine">
            <div class="row"><span class="pl na">Vorschlag · Engine</span><span class="pl {VGL[vergleich.vergleich.engine][0]}">{VGL[vergleich.vergleich.engine][1]}</span></div>
            <div>{vergleich.engine.icd10_code ?? 'kein ICD-Code'} · Kriterien: {vergleich.engine.kriterien === 'erfuellt' ? 'erfüllt' : vergleich.engine.kriterien === 'nicht_erfuellt' ? 'nicht erfüllt' : 'nicht prüfbar'}</div>
            {#if vergleich.engine.schweregrad_vorschlag}<div class="lb">Schweregrad (grob orientierend): {vergleich.engine.schweregrad_vorschlag}</div>{/if}
            <div class="lb">{vergleich.engine.hinweis}</div>
          </article>
          <article class="cd box" aria-label="Vorschlag von Claude">
            {#if vergleich.claude}
              <div class="row"><span class="pl ai">KI-Vorschlag · Claude</span><span class="pl {VGL[vergleich.vergleich.claude][0]}">{VGL[vergleich.vergleich.claude][1]}</span></div>
              <div>{vergleich.claude.icd10_code ?? 'kein ICD-Code'}</div>
              {#each vergleich.claude.begruendung ?? [] as b, i (i)}<div class="lb">{b.text} ({b.quellen.join(', ')})</div>{/each}
              <div class="lb">{vergleich.claude.hinweis}</div>
            {:else}
              <ClaudeHandoff {sid} art="diagnosevorschlag" titel="Diagnosevorschlag von Claude" befehl="Subagent diagnosevorschlag mit session_id: {sid}"
                             hinweis="Eigenes Gespräch ohne Entwurf und ohne Ihre interne Diagnose." stand={claudeStand} onuebernommen={vergleichLaden} />
            {/if}
          </article>
        </div>
        <label class="lb" for="notiz">Ihre Notiz zur Abweichung (bleibt lokal)</label><textarea class="in" id="notiz" maxlength="2000" bind:value={notiz}></textarea>
        <div class="row"><button class="btn" type="button" onclick={notizSpeichern}>Notiz speichern</button><span role="status">{gespeichert}</span></div>
        {#if aktionFehler}<div class="err" role="alert">✕ {aktionFehler}</div>{/if}
      </section>
    {/if}
    {#if uebersicht && !gesperrtQ1}
      <section class="cd box" aria-labelledby="h-ueb"><h2 class="h3" id="h-ueb">Übereinstimmung über alle Fälle</h2>
        <div class="row"><span class="pl na">Engine gleich: {uebersicht.engine.gleich}</span><span class="pl na">Engine abweichend: {uebersicht.engine.abweichend}</span>
          <span class="pl na">Claude gleich: {uebersicht.claude.gleich}</span><span class="pl na">Claude abweichend: {uebersicht.claude.abweichend}</span></div>
        <span class="lb">Diese Zahlen fließen nie in Lernvorschläge.</span></section>
    {/if}
  </Zustand>
</AppShell>

<style>
  .box { padding: 16px; display: flex; flex-direction: column; gap: 10px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
  .zwei { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; }
</style>
