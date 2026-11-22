<script lang="ts">
  // Screen 04: input by template sections (gutachten-input.schema.json). Dates only in memory (DateToAge), categories
  // and text blocks only from the engine (CategoryCell, LockedBlock), rule check right after saving (RuleCheckBar).
  import { anonVonSession } from '../lib/anon';
  import { app, hatQ1 } from '../lib/app.svelte';
  import AppShell from '../lib/components/AppShell.svelte';
  import RuleCheckBar from '../lib/components/RuleCheckBar.svelte';
  import Zustand from '../lib/components/Zustand.svelte';
  import { call } from '../lib/engine/client';
  import { fehlerText } from '../lib/engine/fehler';
  import { ladeFall, type Fall } from '../lib/fall';
  import { GUTACHTENTYP } from '../lib/kategorien';
  import { href } from '../lib/router.svelte';

  let { sid }: { sid: string } = $props();
  let fall = $state<Fall | null>(null);
  let kontext = $state<any>(null);
  let laden = $state(true);
  let fehler = $state<unknown>(null);
  let gi = $state<any>(null);
  // transient, never stored (DateToAge): only the age J;M and derived values go into the input
  let datum = $state({ geburt: '', test: '', schulbeginn: '' });
  let funde = $state<{ feld: string; text: string; kategorie: string; sicher: boolean }[]>([]);
  let speicherFehler = $state<{ text: string; grund: string | null; code: string } | null>(null);
  let gespeichert = $state(false);
  let datumFehler = $state<string | null>(null);

  function leer(typ: string) {
    const T = () => ({ text: '' });
    return {
      schema_version: '3', session_id: sid, gutachtentyp: typ, verfasserin: { qualifikationen: [] },
      vorstellungsgrund: T(), schullaufbahn: { schulstufe: 1, jahr_der_schulpflicht: 1, verlauf: '' }, vorbefunde: [],
      anamnese: [], verhaltensbeobachtung: T(), testergebnisse: [],
      ...(typ === 'spf' ? { leistungsproben: { deutsch: { lesen: T(), schreiben: T() }, mathematik: T() }, foerderung_und_umfeld: T() } : {}),
      adaptives_verhalten: { befragte_rollen: [], text: '' },
      drei_quellen: { klinischer_eindruck: 'fehlt', intelligenztest: 'fehlt', befragung_adaptives_verhalten: 'fehlt' },
      erstsprache_deutsch: true, alter: null, empfehlung: { text: '', ...(typ === 'spf' ? { spf_empfohlen: false } : {}) },
    };
  }

  async function laden_() {
    laden = true;
    fehler = null;
    try {
      fall = await ladeFall(sid);
      kontext = await call('eingabe_kontext', { session_id: sid });
      gi = fall.gutachten_input ? structuredClone(fall.gutachten_input) : leer(fall.session.gutachtentyp!);
    } catch (e) {
      fehler = e;
    } finally {
      laden = false;
    }
  }
  laden_();

  const katalog = $derived<any[]>(kontext?.testkatalog ?? []);
  const eintrag = (id: string | null) => katalog.find((e) => e.id === id);
  const diagnoseErlaubt = $derived(['lrs', 'rechenstoerung'].includes(gi?.gutachtentyp) && hatQ1());

  async function alterBerechnen() {
    datumFehler = null;
    if (!datum.geburt || !datum.test) return;
    try {
      gi.alter = (await call('alter_berechnen', { geburtsdatum: datum.geburt, testdatum: datum.test })).alter;
      for (const t of gi.testergebnisse) await normen(t);
      if (!gi.erstsprache_deutsch && datum.schulbeginn) await schulbesuch();
    } catch (e) {
      datumFehler = fehlerText(e).text;
    }
  }
  async function schulbesuch() {
    if (!datum.schulbeginn || !datum.test) return;
    try {
      gi.schulbesuch_oesterreich_monate = (await call('schulbesuch_berechnen', { schulbeginn_oesterreich: datum.schulbeginn, testdatum: datum.test })).schulbesuch_oesterreich_monate;
    } catch (e) {
      datumFehler = fehlerText(e).text;
    }
  }
  async function normen(t: any) {
    if (!t.testkatalog_id || !gi.alter || !datum.test) return;
    const r = await call('normwerte_ableiten', { testkatalog_id: t.testkatalog_id, alter: gi.alter, testdatum: datum.test });
    if (r.normen_alter_jahre !== undefined) t.normen_alter_jahre = r.normen_alter_jahre;
    if (r.normgruppe) t.normgruppe = r.normgruppe; else delete t.normgruppe;
  }

  function verfahrenHinzufuegen() {
    const n = gi.testergebnisse.length + 1;
    gi.testergebnisse.push({ testergebnis_id: `t${n}`, verfahren: '', testkatalog_id: null, einzeltestung: true, werte: [] });
  }
  async function verfahrenWaehlen(t: any, id: string) {
    const e = eintrag(id);
    t.testkatalog_id = e?.id ?? null;
    t.verfahren = e?.name ?? '';
    t.einzeltestung = e?.einzeltestung ?? true;
    t.werte = (e?.indizes ?? []).flatMap((i: any) => [
      { ebene: 'index', kennung: i.kennung, wert: null, skala: i.skala },
      ...(i.subtests ?? []).map((s: any) => ({ ebene: 'subtest', kennung: s.kennung, wert: null, skala: s.skala })),
    ]);
    await normen(t);
  }
  const zahl = (v: unknown) => (v === '' || v === null || v === undefined ? undefined : Number(v));

  function bereinigt() {
    // empty optional numbers and value rows without a value are left out; nothing is guessed
    const g = $state.snapshot(gi);
    g.verfasserin = { qualifikationen: [...(app.einstellungen?.qualifikationen ?? [])] };
    if (!g.vorlage_id && kontext?.vorlage?.vorlage_id) g.vorlage_id = kontext.vorlage.vorlage_id;
    if (!g.vorlage_id) delete g.vorlage_id;
    g.testergebnisse = g.testergebnisse.map((t: any) => {
      const o: any = { ...t, werte: t.werte.filter((w: any) => zahl(w.wert) !== undefined).map((w: any) => ({ ...w, wert: zahl(w.wert) })) };
      for (const k of ['gesamt_iq', 'ki_untergrenze', 'ki_obergrenze', 'ki_niveau', 'normen_alter_jahre']) {
        if (zahl(o[k]) === undefined) delete o[k]; else o[k] = zahl(o[k]);
      }
      if (!o.normen_begruendung) delete o.normen_begruendung;
      return o;
    });
    g.schullaufbahn.schulstufe = Number(g.schullaufbahn.schulstufe);
    g.schullaufbahn.jahr_der_schulpflicht = Number(g.schullaufbahn.jahr_der_schulpflicht);
    g.anamnese = g.anamnese.map((a: any, i: number) => ({ ...a, quelle_id: `q${i + 1}` }));
    if (g.erstsprache_deutsch) delete g.schulbesuch_oesterreich_monate;
    if (!diagnoseErlaubt || !g.gutachten_diagnose?.text) delete g.gutachten_diagnose;
    else if (!g.gutachten_diagnose.icd10_code) delete g.gutachten_diagnose.icd10_code;
    for (const k of ['staerken', 'foerdermassnahmen']) if (!g.empfehlung[k]) delete g.empfehlung[k];
    return g;
  }

  async function speichern(unsichereBestaetigt = false) {
    speicherFehler = null;
    gespeichert = false;
    if (!gi.alter) {
      speicherFehler = { text: 'Bitte Geburts- und Testdatum eingeben, damit das Alter berechnet wird.', grund: null, code: 'E_SCHEMA' };
      return;
    }
    try {
      const r = await call('eingabe_speichern', { session_id: sid, gutachten_input: bereinigt(), ...(unsichereBestaetigt ? { unsichere_bestaetigt: true } : {}) });
      if (!r.gespeichert) { funde = r.funde; return; }
      funde = [];
      gespeichert = true;
      kontext = await call('eingabe_kontext', { session_id: sid });
      fall = await ladeFall(sid);
    } catch (e) {
      speicherFehler = fehlerText(e);
    }
  }
  const nurUnsicher = $derived(funde.length > 0 && funde.every((f) => !f.sicher));
  const kategorie = (i: number, j: number) => kontext?.kategorien?.find((k: any) => k.wert_quelle === `/testergebnisse/${i}/werte/${j}`);
  const QUELLE = [['dokumentiert', 'Dokumentiert'], ['fehlt', 'Fehlt'], ['nicht_anwendbar', 'Nicht anwendbar']] as const;
</script>

<AppShell aktiv="faelle" anonStatus={fall ? anonVonSession(fall.session) : { stufe: 'nicht_geprueft' }}
          bereich="{fall?.session.bezeichnung ?? 'Fall'} · {GUTACHTENTYP[fall?.session.gutachtentyp ?? 'spf']}"
          titel="Gutachten-Eingabe" fall={fall ? { session_id: sid, bereich: 'eingabe', modus: fall.session.modus } : undefined}>
  <Zustand {laden} {fehler} erneut={laden_} ladenText="Eingabe wird geladen …">
    {#snippet warnung()}
      {#if !katalog.length}
        <div class="warn" role="status"><strong style="color:var(--wnT)">! Ihr Testkatalog ist leer.</strong> Verfahren können erst gewählt werden, wenn sie mit Quelle und Normgruppen im Testkatalog stehen. <a href={href('katalog')}>Testkatalog öffnen</a></div>
      {/if}
      {#if gi && !gi.erstsprache_deutsch}
        <div class="warn" role="status"><strong style="color:var(--wnT)">! Erstsprache nicht Deutsch.</strong> Sind Sprachstand und Lerngelegenheit im Text beschrieben? Der Elefant prüft das vor dem Export.</div>
      {/if}
    {/snippet}
    {#if gi}
      <RuleCheckBar ergebnis={kontext?.regelergebnis} regeln={kontext?.regeln ?? {}} regelwerkVersion={kontext?.regelwerk_version} q1={hatQ1()} />
      <form class="stack" onsubmit={(e) => { e.preventDefault(); speichern(); }}>
        <section class="cd box" aria-labelledby="h-alter">
          <h2 class="h3" id="h-alter">Alter und Schullaufbahn</h2>
          <div class="grid">
            <div><label class="lb" for="geb">Geburtsdatum</label><input class="in" id="geb" type="date" bind:value={datum.geburt} onchange={alterBerechnen}></div>
            <div><label class="lb" for="tdat">Testdatum</label><input class="in" id="tdat" type="date" bind:value={datum.test} onchange={alterBerechnen}></div>
            <div class="cd wert"><div class="lb">Alter bei Testung</div><div data-testid="alter">{gi.alter ? `${gi.alter.jahre};${gi.alter.monate}` : 'noch nicht berechnet'}</div></div>
            <div><label class="lb" for="stufe">Schulstufe</label><input class="in" id="stufe" type="number" min="0" max="13" required bind:value={gi.schullaufbahn.schulstufe}></div>
            <div><label class="lb" for="pflicht">Jahr der Schulpflicht</label><input class="in" id="pflicht" type="number" min="1" max="12" required bind:value={gi.schullaufbahn.jahr_der_schulpflicht}></div>
          </div>
          <span class="lb">Geburts- und Testdatum werden nur zur Berechnung genutzt und nicht gespeichert. Gespeichert wird nur das Alter J;M.</span>
          {#if datumFehler}<div class="err" role="alert">✕ {datumFehler}</div>{/if}
          <label class="lb" for="verlauf">Schullaufbahn, Verlauf</label><textarea class="in" id="verlauf" bind:value={gi.schullaufbahn.verlauf}></textarea>
          <label class="row"><input type="checkbox" bind:checked={gi.erstsprache_deutsch}> Erstsprache Deutsch</label>
          {#if !gi.erstsprache_deutsch}
            <div class="grid">
              <div><label class="lb" for="sbeg">Schulbeginn in Österreich (nur zur Berechnung)</label><input class="in" id="sbeg" type="date" bind:value={datum.schulbeginn} onchange={schulbesuch}></div>
              <div class="cd wert"><div class="lb">Schulbesuch in Österreich</div><div>{gi.schulbesuch_oesterreich_monate ?? '–'} Monate</div></div>
            </div>
          {/if}
        </section>

        {#if (kontext?.vorlagen ?? []).length > 1}
          <section class="cd box" aria-labelledby="h-vl"><h2 class="h3" id="h-vl">Vorlage</h2>
            <label class="lb" for="vl">Vorlage für diesen Fall</label>
            <select class="in" id="vl" style="max-width:320px" bind:value={gi.vorlage_id}><option value={undefined}>Bitte wählen</option>
              {#each kontext.vorlagen as v (v.vorlage_id)}<option value={v.vorlage_id}>{v.vorlage_id} · Version {v.version}</option>{/each}</select></section>
        {:else if !(kontext?.vorlagen ?? []).length}
          <div class="warn" role="status"><strong style="color:var(--wnT)">! Keine Vorlage für diesen Gutachtentyp.</strong> Ohne Vorlage gibt es keinen Entwurf und keinen Export. <a href={href('katalog')}>Vorlage importieren</a></div>
        {/if}
        <section class="cd box" aria-labelledby="h-vg"><h2 class="h3" id="h-vg">Vorstellungsgrund</h2>
          <label class="lb" for="vg">Fragestellung und Anlass</label><textarea class="in" id="vg" bind:value={gi.vorstellungsgrund.text}></textarea></section>

        <section class="cd box" aria-labelledby="h-vb"><h2 class="h3" id="h-vb">Vorbefunde</h2>
          {#each gi.vorbefunde as v, i (i)}
            <div class="grid"><div><label class="lb" for="vbr-{i}">Quelle als Rolle</label><input class="in" id="vbr-{i}" bind:value={v.quelle_rolle}></div>
              <div style="grid-column:span 2"><label class="lb" for="vbt-{i}">Inhalt</label><textarea class="in" id="vbt-{i}" bind:value={v.text}></textarea></div></div>
            <button class="btn s g" type="button" onclick={() => gi.vorbefunde.splice(i, 1)}>Vorbefund {i + 1} entfernen</button>
          {/each}
          <button class="btn s" type="button" onclick={() => gi.vorbefunde.push({ quelle_rolle: '', text: '' })}>+ Vorbefund</button></section>

        <section class="cd box" aria-labelledby="h-an"><h2 class="h3" id="h-an">Anamnese</h2>
          {#each gi.anamnese as a, i (i)}
            <div class="grid">
              <div><label class="lb" for="ane-{i}">Erhoben mit</label><input class="in" id="ane-{i}" bind:value={a.erhoben_mit} placeholder="z. B. die Mutter"></div>
              <div><label class="lb" for="ana-{i}">Art</label><select class="in" id="ana-{i}" bind:value={a.art}>
                <option value="gespraech">Gespräch</option><option value="bericht">Bericht</option><option value="vorbefund">Vorbefund</option><option value="fragebogen">Fragebogen</option><option value="sonstiges">Sonstiges</option></select></div>
              <label class="row"><input type="checkbox" bind:checked={a.uebersetzungshilfe}> Übersetzungshilfe anwesend</label>
            </div>
            <label class="lb" for="ant-{i}">Inhalt der Quelle {i + 1}</label><textarea class="in" id="ant-{i}" bind:value={a.text}></textarea>
            <button class="btn s g" type="button" onclick={() => gi.anamnese.splice(i, 1)}>Quelle {i + 1} entfernen</button>
          {/each}
          <button class="btn s" type="button" onclick={() => gi.anamnese.push({ quelle_id: '', erhoben_mit: '', art: 'gespraech', uebersetzungshilfe: false, text: '' })}>+ Quelle</button></section>

        <section class="cd box" aria-labelledby="h-beob"><h2 class="h3" id="h-beob">Verhaltensbeobachtung</h2>
          <label class="lb" for="beob">Beobachtung in der Testsituation</label><textarea class="in" id="beob" bind:value={gi.verhaltensbeobachtung.text}></textarea></section>

        <section class="cd box" aria-labelledby="h-test"><h2 class="h3" id="h-test">Testergebnisse</h2>
          {#each gi.testergebnisse as t, i (t.testergebnis_id)}
            {@const e = eintrag(t.testkatalog_id)}
            <div class="cd sub">
              <div class="grid">
                <div><label class="lb" for="tv-{i}">Verfahren aus dem Katalog</label>
                  <select class="in" id="tv-{i}" value={t.testkatalog_id ?? ''} onchange={(ev) => verfahrenWaehlen(t, ev.currentTarget.value)}>
                    <option value="">Bitte wählen</option>{#each katalog as k (k.id)}<option value={k.id}>{k.name}{k.status === 'entwurf' ? ' (Entwurf)' : ''}</option>{/each}</select></div>
                <div><label class="lb" for="iq-{i}">Gesamt-IQ</label><input class="in" id="iq-{i}" type="number" bind:value={t.gesamt_iq}></div>
                <div><label class="lb" for="ug-{i}">Konfidenzintervall, Untergrenze</label><input class="in" id="ug-{i}" type="number" bind:value={t.ki_untergrenze}></div>
                <div><label class="lb" for="og-{i}">Konfidenzintervall, Obergrenze</label><input class="in" id="og-{i}" type="number" bind:value={t.ki_obergrenze}></div>
                <div><label class="lb" for="ni-{i}">Konfidenzniveau</label><select class="in" id="ni-{i}" bind:value={t.ki_niveau}>
                  <option value={undefined}>keine Angabe</option>{#each e?.konfidenzniveaus ?? [] as n (n)}<option value={n}>{Math.round(n * 100)} %</option>{/each}</select></div>
                <label class="row"><input type="checkbox" bind:checked={t.einzeltestung}> Einzeltestung</label>
              </div>
              <div class="lb">Normgruppe laut Katalog: {t.normgruppe ? `${t.normgruppe.von.jahre};${t.normgruppe.von.monate} bis ${t.normgruppe.bis.jahre};${t.normgruppe.bis.monate}` : 'nicht abgeleitet'}{t.normen_alter_jahre !== undefined ? ` · Normen ${t.normen_alter_jahre} Jahre alt` : ''}</div>
              {#if kontext?.bausteine?.find((b: any) => b.testkatalog_id === t.testkatalog_id)}
                {@const b = kontext.bausteine.find((b: any) => b.testkatalog_id === t.testkatalog_id)}
                <div class="cd locked" data-testid="baustein"><div class="lb">Gesperrter Baustein · Verfahrensbeschreibung aus Ihrem Testkatalog</div><div class="doc">{b.text}</div><div class="lb">{b.zitat}</div></div>
              {/if}
              {#if t.werte.length}
                <div class="tbx"><table class="t"><caption class="sr">Werte {t.verfahren}</caption>
                  <thead><tr><th scope="col">Ebene</th><th scope="col">Kennung</th><th scope="col">Wert</th><th scope="col">Skala</th><th scope="col">Kategorie (abgeleitet)</th></tr></thead>
                  <tbody>{#each t.werte as w, j (j)}
                    {@const k = kategorie(i, gi.testergebnisse[i].werte.filter((x: any, xi: number) => xi < j && zahl(x.wert) !== undefined).length)}
                    <tr><td>{w.ebene === 'index' ? 'Index' : 'Subtest'}</td><td>{w.kennung}</td>
                      <td><input class="in" style="max-width:100px" type="number" aria-label="Wert {w.kennung}" bind:value={w.wert}></td><td>{w.skala}</td>
                      <td>{#if zahl(w.wert) === undefined}<span class="mu">–</span>{:else if k?.kategorie}<span class="pl na">aus Kategorienskala</span> {k.kategorie}{:else if k}<span class="pl wn">! Kategorie nicht ableitbar</span>{:else}<span class="mu">nach dem Speichern</span>{/if}</td></tr>
                  {/each}</tbody></table></div>
                <span class="lb">Die Kategorie ist nicht editierbar. Ohne passenden Bereich in der Kategorienskala bleibt sie eine markierte Lücke.</span>
              {/if}
              {#if t.normen_alter_jahre !== undefined && t.normen_alter_jahre > 10}
                <label class="lb" for="nb-{i}">Begründung für das Verfahren trotz älterer Normen (Regel c, erscheint im Gutachten)</label><textarea class="in" id="nb-{i}" bind:value={t.normen_begruendung}></textarea>
              {/if}
              <button class="btn s g" type="button" onclick={() => gi.testergebnisse.splice(i, 1)}>Verfahren {i + 1} entfernen</button>
            </div>
          {/each}
          <button class="btn s" type="button" disabled={!katalog.length} onclick={verfahrenHinzufuegen}>+ Verfahren hinzufügen</button></section>

        {#if gi.gutachtentyp === 'spf'}
          <section class="cd box" aria-labelledby="h-lp"><h2 class="h3" id="h-lp">Leistungsproben</h2>
            <label class="lb" for="lpl">Deutsch: Lesen</label><textarea class="in" id="lpl" bind:value={gi.leistungsproben.deutsch.lesen.text}></textarea>
            <label class="lb" for="lps">Deutsch: Schreiben</label><textarea class="in" id="lps" bind:value={gi.leistungsproben.deutsch.schreiben.text}></textarea>
            <label class="lb" for="lpm">Mathematik</label><textarea class="in" id="lpm" bind:value={gi.leistungsproben.mathematik.text}></textarea></section>
          <section class="cd box" aria-labelledby="h-fu"><h2 class="h3" id="h-fu">Förderung und Umfeld</h2>
            <label class="lb" for="fu">Bisherige Förderung und Umfeld</label><textarea class="in" id="fu" bind:value={gi.foerderung_und_umfeld.text}></textarea></section>
        {/if}

        <section class="cd box" aria-labelledby="h-adap"><h2 class="h3" id="h-adap">Adaptives Verhalten</h2>
          <label class="lb" for="adr">Befragte Rollen (durch Komma getrennt)</label>
          <input class="in" id="adr" value={gi.adaptives_verhalten.befragte_rollen.join(', ')}
                 onchange={(e) => (gi.adaptives_verhalten.befragte_rollen = e.currentTarget.value.split(',').map((x) => x.trim()).filter(Boolean))}>
          <label class="lb" for="adt">Verfahren und Ergebnis oder begründete Einschätzung</label><textarea class="in" id="adt" bind:value={gi.adaptives_verhalten.text}></textarea></section>

        <section class="cd box" aria-labelledby="h-q"><h2 class="h3" id="h-q">Quellenlage</h2>
          <div class="grid">
            {#each [['klinischer_eindruck', 'Klinischer Eindruck'], ['intelligenztest', 'Intelligenztest'], ['befragung_adaptives_verhalten', 'Befragung adaptives Verhalten']] as [k, l] (k)}
              <div><label class="lb" for="q-{k}">{l}</label><select class="in" id="q-{k}" bind:value={gi.drei_quellen[k]}>{#each QUELLE as [v, t] (v)}<option value={v}>{t}</option>{/each}</select></div>
            {/each}
          </div></section>

        <section class="cd box" aria-labelledby="h-emp"><h2 class="h3" id="h-emp">Empfehlung</h2>
          <label class="lb" for="emp">Empfehlung</label><textarea class="in" id="emp" bind:value={gi.empfehlung.text}></textarea>
          <label class="lb" for="st">Stärken</label><textarea class="in" id="st" bind:value={gi.empfehlung.staerken}></textarea>
          <label class="lb" for="fm">Fördermaßnahmen</label><textarea class="in" id="fm" bind:value={gi.empfehlung.foerdermassnahmen}></textarea>
          {#if gi.gutachtentyp === 'spf'}<label class="row"><input type="checkbox" bind:checked={gi.empfehlung.spf_empfohlen}> Sonderpädagogischer Förderbedarf wird empfohlen (die zuständige Behörde entscheidet)</label>{/if}
        </section>

        {#if ['lrs', 'rechenstoerung'].includes(gi.gutachtentyp)}
          <section class="cd box" aria-labelledby="h-dia"><h2 class="h3" id="h-dia">Diagnose im Gutachten</h2>
            {#if diagnoseErlaubt}
              {#if !gi.gutachten_diagnose}<button class="btn s" type="button" onclick={() => (gi.gutachten_diagnose = { text: '', icd10_code: '' })}>+ Diagnose eintragen</button>
              {:else}
                <label class="lb" for="dt">Diagnose</label><textarea class="in" id="dt" bind:value={gi.gutachten_diagnose.text}></textarea>
                <label class="lb" for="dc">ICD-10-Code (optional)</label><input class="in" id="dc" style="max-width:200px" bind:value={gi.gutachten_diagnose.icd10_code}>
              {/if}
            {:else}
              <div class="cd locked">Gesperrt: Diagnosefelder sind nur mit der Qualifikation „Klinische Psychologin“ freigeschaltet (<a href={href('einstellungen')}>Einstellungen</a>).</div>
            {/if}</section>
        {/if}

        {#if funde.length}
          <div class="warn" role="alert">
            <strong style="color:var(--wnT)">! Mögliche identifizierende Angaben im Freitext. Nicht gespeichert.</strong>
            <ul>{#each funde as f (f.feld + f.text)}<li>{f.text} ({f.sicher ? 'sicher, bitte ändern' : 'unsicher'})</li>{/each}</ul>
            {#if nurUnsicher}<button class="btn" type="button" onclick={() => speichern(true)}>Geprüft, trotzdem speichern</button>{/if}
          </div>
        {/if}
        {#if speicherFehler}
          <div class="err" role="alert"><strong style="color:var(--erT)">✕ {speicherFehler.text}</strong>{#if speicherFehler.grund} ({speicherFehler.grund}){/if} Ihre Eingaben in dieser Maske bleiben erhalten.
            {#if speicherFehler.grund === 'Namensliste fehlt'}<a href={href('fall', sid, 'dokumente')}>Bekannte Namen setzen</a>{/if}</div>
        {/if}
        <div class="row"><button class="btn p" type="submit">Eingabe speichern und Regeln prüfen</button>
          <span role="status">{gespeichert ? 'Gespeichert.' : ''}</span>
          {#if fall?.gutachten_input}<a class="btn" href={href('fall', sid, 'pruefung')}>Weiter zu Entwurf und Prüfung</a>{/if}</div>
      </form>
    {/if}
  </Zustand>
</AppShell>

<style>
  .box { padding: 16px; display: flex; flex-direction: column; gap: 10px; }
  .sub { padding: 12px; display: flex; flex-direction: column; gap: 10px; background: var(--bg); }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; align-items: end; }
  .wert { padding: 8px 12px; }
  .locked { padding: 10px 12px; background: var(--sf2); display: flex; flex-direction: column; gap: 4px; }
  ul { margin: 6px 0; padding-left: 18px; }
</style>
