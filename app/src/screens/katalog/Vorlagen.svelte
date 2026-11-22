<script lang="ts">
  // Templates: import a DOCX into wissensbasis/vorlagen/ (never overwritten), then the mapping dialog: headings to
  // report sections, header labels to placeholders. The engine checks that every heading and label exists.
  import DateiWahl from '../../lib/components/DateiWahl.svelte';
  import { call } from '../../lib/engine/client';
  import { fehlerText } from '../../lib/engine/fehler';
  import { GUTACHTENTYP } from '../../lib/kategorien';
  let { vorlagen, ongeaendert }: { vorlagen: any[]; ongeaendert: () => void } = $props();

  const ABSCHNITTE = [['vorstellungsgrund', 'Vorstellungsgrund'], ['schullaufbahn', 'Schullaufbahn'], ['vorbefunde', 'Vorbefunde'],
    ['anamnese', 'Anamnese'], ['verhaltensbeobachtung', 'Verhaltensbeobachtung'], ['testbefunde', 'Testbefunde'],
    ['leistungsproben', 'Leistungsproben'], ['diagnose', 'Diagnose (nicht bei SPF)'], ['empfehlung', 'Empfehlung']] as const;
  const PLATZHALTER = [['name_kind', 'Name des Kindes'], ['geburtsdatum', 'Geburtsdatum'], ['klasse', 'Klasse'], ['schultyp', 'Schultyp'],
    ['bezirk', 'Bezirk'], ['schuladresse', 'Schuladresse'], ['wohnadresse', 'Wohnadresse'], ['geschaeftszahl', 'Geschäftszahl'],
    ['ort_datum', 'Ort und Datum'], ['signatur', 'Unterschrift']] as const;
  let importiert = $state<{ datei: string; titel: string[]; kopf_beschriftungen: string[] } | null>(null);
  let zuordnung = $state({ vorlage_id: '', gutachtentyp: 'spf', abschnitte: {} as Record<string, string>, kopf: {} as Record<string, string> });
  let fehler = $state<string | null>(null);
  let meldung = $state('');

  async function importieren(pfad: string) {
    fehler = null;
    meldung = '';
    try {
      importiert = await call('vorlage_importieren', { pfad });
      zuordnung = { vorlage_id: '', gutachtentyp: 'spf', abschnitte: {}, kopf: {} };
    } catch (e) {
      const f = fehlerText(e);
      fehler = f.code === 'E_BLOCKIERT' ? 'Eine Vorlage mit diesem Dateinamen gibt es schon; sie wird nie überschrieben. Bitte die Datei umbenennen.' : f.text;
    }
  }

  async function zuordnen(e: SubmitEvent) {
    e.preventDefault();
    fehler = null;
    const vorlage = {
      schema_version: '1', vorlage_id: zuordnung.vorlage_id, version: '1', gutachtentyp: zuordnung.gutachtentyp, datei: importiert!.datei,
      abschnitte: ABSCHNITTE.map(([id]) => ({ abschnitt_id: id, ueberschrift: zuordnung.abschnitte[id] ?? '' })).filter((a) => a.ueberschrift),
      kopffelder: PLATZHALTER.map(([p]) => ({ platzhalter: p, bezeichnung: zuordnung.kopf[p] ?? '' })).filter((k) => k.bezeichnung),
      status: 'entwurf',
    };
    try {
      await call('vorlage_zuordnen', { vorlage });
      meldung = `Vorlage ${vorlage.vorlage_id} zugeordnet.`;
      importiert = null;
      ongeaendert();
    } catch (err) {
      const f = fehlerText(err);
      fehler = { E_ABSCHNITT_FEHLT: 'Eine gewählte Überschrift steht nicht in der Vorlage.', E_KOPFFELD_FEHLT: 'Eine gewählte Kopf-Beschriftung steht nicht in der Vorlage.',
        E_SCHEMA: 'Kennung (klein, ohne Leerzeichen) und mindestens ein Abschnitt sind nötig.' }[f.code] ?? f.text;
    }
  }
</script>

<section class="stack" aria-label="Vorlagen">
  <div class="cd box">
    <h3 class="h3">Vorlage importieren</h3>
    <p class="lb" style="margin:0">Eigene DOCX-Vorlagen. Danach ordnen Sie Überschriften den Abschnitten und Kopf-Beschriftungen den Platzhaltern zu. Vorlagen bleiben auf diesem Gerät.</p>
    <DateiWahl id="vorlage-pfad" label="Vorlage importieren" endungen={['docx']} onwahl={importieren} />
    <div role="status">{meldung}</div>
  </div>
  {#if importiert}
    <form class="cd box" onsubmit={zuordnen} aria-labelledby="h-zu">
      <h3 class="h3" id="h-zu">Zuordnung: {importiert.datei}</h3>
      <div class="grid">
        <div><label class="lb" for="zu-id">Kennung der Vorlage</label><input class="in" id="zu-id" required pattern="[a-z0-9\-]+" bind:value={zuordnung.vorlage_id} placeholder="z. B. spf-2026"></div>
        <div><label class="lb" for="zu-typ">Gutachtentyp</label><select class="in" id="zu-typ" bind:value={zuordnung.gutachtentyp}>{#each Object.entries(GUTACHTENTYP) as [k, l] (k)}<option value={k}>{l}</option>{/each}</select></div>
      </div>
      <fieldset class="grid"><legend class="h3">Abschnitte</legend>
        {#each ABSCHNITTE as [id, l] (id)}
          {#if !(id === 'diagnose' && zuordnung.gutachtentyp === 'spf')}
            <div><label class="lb" for="zu-a-{id}">{l}</label>
              <select class="in" id="zu-a-{id}" bind:value={zuordnung.abschnitte[id]}><option value="">nicht in dieser Vorlage</option>{#each importiert.titel as t (t)}<option value={t}>{t}</option>{/each}</select></div>
          {/if}
        {/each}
      </fieldset>
      <fieldset class="grid"><legend class="h3">Kopffelder (bleiben Platzhalter, Sie setzen sie im Dokument ein)</legend>
        {#each PLATZHALTER as [p, l] (p)}
          <div><label class="lb" for="zu-k-{p}">{l}</label>
            <select class="in" id="zu-k-{p}" bind:value={zuordnung.kopf[p]}><option value="">nicht im Kopf</option>{#each importiert.kopf_beschriftungen as k (k)}<option value={k}>{k}</option>{/each}</select></div>
        {/each}
      </fieldset>
      <div class="row"><button class="btn p" type="submit">Zuordnung speichern</button><button class="btn g" type="button" onclick={() => (importiert = null)}>Abbrechen</button></div>
    </form>
  {/if}
  {#if fehler}<div class="err" role="alert">✕ {fehler}</div>{/if}
  {#if vorlagen.length}
    <div class="cd tbx"><table class="t"><caption class="sr">Zugeordnete Vorlagen</caption>
      <thead><tr><th scope="col">Kennung</th><th scope="col">Gutachtentyp</th><th scope="col">Abschnitte</th><th scope="col">Kopffelder</th><th scope="col">Status</th></tr></thead>
      <tbody>{#each vorlagen as v (v.vorlage_id)}<tr><td>{v.vorlage_id}</td><td>{GUTACHTENTYP[v.gutachtentyp]}</td><td>{v.abschnitte.length}</td><td>{v.kopffelder.length}</td>
        <td><span class="pl na">{v.status === 'freigegeben' ? '✓ Freigegeben' : 'Entwurf'}</span></td></tr>{/each}</tbody></table></div>
  {:else}
    <div class="empty"><h3 class="h2" style="color:var(--tx)">Noch keine Vorlage</h3><div>Ohne zugeordnete Vorlage gibt es keinen Entwurf und keinen Export.</div></div>
  {/if}
</section>

<style>
  .box { padding: 16px; display: flex; flex-direction: column; gap: 10px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; align-items: end; }
  legend { grid-column: 1 / -1; margin-bottom: 4px; }
</style>
