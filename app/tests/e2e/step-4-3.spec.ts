// Step 4.3: synthetic case end to end in desktop mode up to the DOCX, browser mode with valid and invalid answers.
import fs from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { axe, claude, engine, fault, themes } from './hilfen';

async function einstellungen(page: Page, verbindung: 'desktop' | 'browser') {
  await page.goto('/#/einstellungen');
  await engine(page, 'einstellungen_speichern', { einstellungen: { schema_version: '1', verbindung, qualifikationen: ['schulpsychologin'], darstellung: 'system' } });
  await page.reload(); // the app reads the settings at start
}

async function fallMitEingabe(page: Page, name: string) {
  const sid = (await engine(page, 'sitzung_anlegen', { bezeichnung: name, modus: 'gutachten', gutachtentyp: 'spf' })).result.session.session_id;
  await engine(page, 'bekannte_namen_setzen', { session_id: sid, namen: [] });
  await page.goto(`/#/fall/${sid}/eingabe`);
  await expect(page.getByRole('heading', { level: 1, name: 'Gutachten-Eingabe' })).toBeVisible();
  await page.getByLabel('Geburtsdatum').fill('2018-01-10');
  await page.getByLabel('Testdatum').fill('2026-05-20');
  await page.getByLabel('Testdatum').blur();
  await expect(page.getByTestId('alter')).toHaveText('8;4');
  await page.getByLabel('Schulstufe').fill('2');
  await page.getByLabel('Jahr der Schulpflicht').fill('2');
  await page.getByLabel('Fragestellung und Anlass').fill('[synthetisch] Langsame Lernfortschritte.');
  await page.getByLabel('Beobachtung in der Testsituation').fill('[synthetisch] Ruhig und kooperativ.');
  await page.getByRole('button', { name: '+ Verfahren hinzufügen' }).click();
  await page.getByLabel('Verfahren aus dem Katalog').selectOption('iq-test-a');
  await page.getByLabel('Gesamt-IQ').fill('62');
  await page.getByLabel('Konfidenzintervall, Untergrenze').fill('57');
  await page.getByLabel('Konfidenzintervall, Obergrenze').fill('68');
  await page.getByLabel('Konfidenzniveau').selectOption({ label: '95 %' });
  await page.getByLabel('Wert I1').fill('62');
  await page.getByLabel('Deutsch: Lesen').fill('[synthetisch] Lesen auf Niveau der ersten Stufe.');
  await page.getByLabel('Deutsch: Schreiben').fill('[synthetisch] Schreiben lautgetreu.');
  await page.getByLabel('Mathematik', { exact: true }).fill('[synthetisch] Zahlenraum bis 20.');
  await page.getByLabel('Bisherige Förderung und Umfeld').fill('[synthetisch] Förderstunden seit der ersten Stufe.');
  await page.getByLabel('Befragte Rollen (durch Komma getrennt)').fill('die Klassenlehrerin');
  await page.getByLabel('Verfahren und Ergebnis oder begründete Einschätzung').fill('[synthetisch] Befragung der Klassenlehrerin.');
  for (const q of ['Klinischer Eindruck', 'Intelligenztest', 'Befragung adaptives Verhalten']) await page.getByLabel(q).selectOption('dokumentiert');
  await page.getByRole('textbox', { name: 'Empfehlung', exact: true }).fill('[synthetisch] Ein sonderpädagogischer Förderbedarf wird empfohlen.');
  await page.getByLabel(/Sonderpädagogischer Förderbedarf wird empfohlen/).check();
  await page.getByRole('button', { name: 'Eingabe speichern und Regeln prüfen' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Gespeichert.' })).toBeVisible();
  return sid;
}

test('Desktop-Modus: Eingabe, Übergabe, Befunde, DOCX', async ({ page }) => {
  await einstellungen(page, 'desktop');
  claude('vorlage');
  const sid = await fallMitEingabe(page, 'Fall 41');
  // rules and derived values come from the engine
  await expect(page.getByRole('button', { name: /spf_s1/ })).toBeVisible();
  await expect(page.getByTestId('baustein')).toContainText('Baustein A');
  await expect(page.getByText('aus Kategorienskala')).toBeVisible();
  await page.getByRole('button', { name: /normen_alter/ }).click();
  await expect(page.getByText('Begründung fehlt')).toBeVisible();
  await expect(page.getByLabel(/Begründung für das Verfahren trotz älterer Normen/)).toBeVisible();
  await themes(page, (t) => axe(page, `04 normal ${t}`));
  // free text with a name: the engine refuses to save
  await engine(page, 'bekannte_namen_setzen', { session_id: sid, namen: [{ text: 'Synthia Quastberger', rolle: 'das Kind' }] });
  await page.getByLabel('Fragestellung und Anlass').fill('[synthetisch] Synthia Quastberger lernt langsam.');
  await page.getByRole('button', { name: 'Eingabe speichern und Regeln prüfen' }).click();
  await expect(page.getByRole('alert')).toContainText('Nicht gespeichert');
  await themes(page, (t) => axe(page, `04 warnung ${t}`));
  await page.getByLabel('Fragestellung und Anlass').fill('[synthetisch] Langsame Lernfortschritte.');
  await page.getByRole('button', { name: 'Eingabe speichern und Regeln prüfen' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Gespeichert.' })).toBeVisible();

  await page.getByRole('link', { name: 'Weiter zu Entwurf und Prüfung' }).click();
  await expect(page.getByRole('heading', { name: 'Noch kein Entwurf' })).toBeVisible();
  await expect(page.getByText(`/gutachten ${sid}`)).toBeVisible();
  await themes(page, (t) => axe(page, `05 leer ${t}`));
  await page.getByRole('button', { name: 'Übergeben und warten' }).click();
  await expect(page.getByText('◷ Wartet auf Ergebnis')).toBeVisible();
  await themes(page, (t) => axe(page, `05 wartet ${t}`));
  claude('codetab', sid); // the Code-Tab writes draft and findings through the MCP tools
  await expect(page.getByText('✓ Übernommen')).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Elefant · 1' })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText('Lücke: keine Anamnese eingegeben')).toBeVisible();
  await page.getByRole('button', { name: /Vorgestellt wegen langsamer/ }).click();
  await expect(page.getByText('/vorstellungsgrund', { exact: true })).toBeVisible();
  await themes(page, (t) => axe(page, `05 normal ${t}`));
  await page.getByRole('article', { name: /Befund elefant/ }).getByRole('button', { name: 'Annehmen' }).click();
  await page.getByRole('tab', { name: 'Stil · 1' }).click();
  await page.getByRole('article', { name: /Befund stil/ }).getByRole('button', { name: 'Verwerfen' }).click();
  await expect(page.getByText('✕ Verworfen')).toBeVisible();
  const fall = (await engine(page, 'sitzung_laden', { session_id: sid })).result;
  expect(fall.lernsignale.map((l: any) => [l.art, l.bereich, l.herkunft])).toEqual([
    ['befund_angenommen', 'pruefverhalten', 'gutachten'], ['befund_verworfen', 'sprache', 'gutachten']]);

  // edit a paragraph: new draft version and a learning signal text_geaendert
  await page.getByRole('button', { name: 'Bearbeiten Absatz a1' }).click();
  await page.getByLabel(/Absatz bearbeiten/).fill('[synthetisch] Vorgestellt wegen deutlich langsamer Lernfortschritte.');
  await page.getByRole('button', { name: 'Absatz speichern' }).click();
  await expect(page.getByText('Version 2')).toBeVisible();
  const nachher = (await engine(page, 'sitzung_laden', { session_id: sid })).result;
  expect(nachher.lernsignale.at(-1).art).toBe('text_geaendert');

  await page.getByRole('link', { name: 'Weiter zum Export' }).click();
  await expect(page.getByRole('article', { name: 'Vorschau im Layout der Vorlage' })).toContainText('deutlich langsamer');
  await themes(page, (t) => axe(page, `06 normal ${t}`));
  const ziel = path.join(process.env.SCHLOMO_DEV_BASIS!, 'Gutachten Fall 41.docx');
  await page.getByLabel('Zieldatei: Pfad (nur Entwicklung)').fill(ziel);
  await page.getByRole('button', { name: 'DOCX exportieren' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Exportiert: Entwurf Version 2' })).toBeVisible();
  expect(fs.statSync(ziel).size).toBeGreaterThan(1000);
  await page.getByRole('button', { name: 'DOCX exportieren' }).click(); // never over an existing file
  await expect(page.getByRole('alert')).toContainText('gibt es schon');
  await themes(page, (t) => axe(page, `06 fehler ${t}`));
});

test('Browser-Modus: Pakete in fester Reihenfolge, ungültige Antwort, Sperren', async ({ page }) => {
  await einstellungen(page, 'browser');
  claude('vorlage');
  const sid = await fallMitEingabe(page, 'Fall 42');
  await page.goto(`/#/fall/${sid}/pruefung`);
  await expect(page.getByRole('list', { name: 'Reihenfolge der Übergaben' })).toBeVisible();
  const paket = (n: string) => path.join(process.env.SCHLOMO_DEV_BASIS!, `${sid}-${n}.json`);
  async function uebergabe(n: string, antwort?: string) {
    await page.getByLabel('Speicherort des Pakets: Pfad (nur Entwicklung)').fill(paket(n));
    await page.getByRole('button', { name: 'Paket speichern' }).click();
    await expect(page.getByText('Paket gespeichert')).toBeVisible();
    await page.getByLabel('Antwort von Claude (Text oder Datei)').fill(antwort ?? claude('antwort', sid, paket(n)));
    await page.getByRole('button', { name: 'Antwort einfügen' }).click();
  }
  // an answer to a different package is refused with its reason
  await uebergabe('fremd', '```json\n{"schema_version":"2","paket_id":"p-00000000","typ":"gutachten-output","daten":{}}\n```');
  await expect(page.getByRole('alert')).toContainText('Antwort ungültig');
  await themes(page, (t) => axe(page, `05 ungueltig ${t}`));
  await uebergabe('entwurf');
  await expect(page.getByText('Version 1')).toBeVisible();
  await expect(page.getByRole('button', { name: /2 Stilprüfung/ })).toHaveAttribute('aria-current', 'step');
  // no released style profile: the engine has no style package, the screen offers to go on without it
  await page.getByLabel('Speicherort des Pakets: Pfad (nur Entwicklung)').fill(paket('stil'));
  await page.getByRole('button', { name: 'Paket speichern' }).click();
  await expect(page.getByRole('alert')).toContainText('kein freigegebenes Stilprofil');
  await themes(page, (t) => axe(page, `05 ohne stilprofil ${t}`));
  await page.getByRole('button', { name: 'Ohne Stilprüfung weiter' }).click();
  await uebergabe('goldfisch');
  await expect(page.getByRole('region', { name: /Übergabe an Claude: Elefant/ })).toBeVisible();
  await uebergabe('elefant');
  await expect(page.getByText('✓ Übernommen')).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Elefant · 1' })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Goldfisch · 1' })).toBeVisible();
  // locks: loading and engine errors in the preview, no template means no export
  await fault(page, 'export_vorschau', { delay_ms: 2500 });
  await page.goto(`/#/fall/${sid}/export`);
  await expect(page.getByRole('status', { name: 'Vorschau wird erstellt …' })).toBeVisible();
  await themes(page, (t) => axe(page, `06 laden ${t}`));
  await fault(page, 'export_vorschau', null);
  await page.reload();
  await expect(page.getByRole('button', { name: /DOCX exportieren|Export gesperrt/ })).toBeVisible();
  await themes(page, (t) => axe(page, `06 normal browser ${t}`));
});

test('Gesperrt ohne bestätigte Anonymisierung, Eingabe lädt und meldet Fehler', async ({ page }) => {
  await einstellungen(page, 'desktop');
  const sid = (await engine(page, 'sitzung_anlegen', { bezeichnung: 'Fall 43', modus: 'gutachten', gutachtentyp: 'spf' })).result.session.session_id;
  await page.goto(`/#/fall/${sid}/pruefung`);
  await expect(page.getByText('Übergabe gesperrt.')).toBeVisible();
  await themes(page, (t) => axe(page, `05 warnung ${t}`));
  await page.goto(`/#/fall/${sid}/export`);
  await expect(page.getByRole('heading', { name: 'Noch kein Entwurf' })).toBeVisible();
  await themes(page, (t) => axe(page, `06 leer ${t}`));
  await fault(page, 'eingabe_kontext', { delay_ms: 2500 });
  await page.goto(`/#/fall/${sid}/eingabe`);
  await expect(page.getByRole('status', { name: 'Eingabe wird geladen …' })).toBeVisible();
  await themes(page, (t) => axe(page, `04 laden ${t}`));
  await fault(page, 'eingabe_kontext', { code: 'E_INTERN' });
  await page.reload();
  await expect(page.getByRole('alert')).toContainText('E_INTERN');
  await themes(page, (t) => axe(page, `04 fehler ${t}`));
  await fault(page, 'eingabe_kontext', null);
  await fault(page, 'sitzung_laden', { code: 'E_INTERN' });
  await page.goto(`/#/fall/${sid}/pruefung`);
  await expect(page.getByRole('alert')).toContainText('E_INTERN');
  await themes(page, (t) => axe(page, `05 fehler ${t}`));
  await fault(page, 'sitzung_laden', null);
});
