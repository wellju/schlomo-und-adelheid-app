// Step 4.2: synthetic case up to the released anonymisation; uncertain findings block the release.
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { axe, engine, fault, synthDateien, themes } from './hilfen';

let dir: string;
test.beforeAll(() => { dir = synthDateien(); });

async function einrichten(page: Page) {
  await page.goto('/#/einstellungen');
  await engine(page, 'einstellungen_speichern', { einstellungen: { schema_version: '1', verbindung: 'desktop', qualifikationen: ['schulpsychologin'], darstellung: 'system' } });
}

test('Fallliste: leer, laden, fehler, anlegen mit Gutachtentyp', async ({ page }) => {
  await einrichten(page);
  await page.goto('/#/faelle');
  await expect(page.getByRole('heading', { name: 'Noch keine Fälle' })).toBeVisible();
  await themes(page, (t) => axe(page, `01 leer ${t}`));
  await fault(page, 'sitzungen_auflisten', { delay_ms: 2500 });
  await page.reload();
  await expect(page.getByRole('status', { name: 'Fälle werden geladen …' })).toBeVisible();
  await themes(page, (t) => axe(page, `01 laden ${t}`));
  await fault(page, 'sitzungen_auflisten', { code: 'E_INTERN' });
  await page.reload();
  await expect(page.getByRole('alert')).toContainText('E_INTERN');
  await themes(page, (t) => axe(page, `01 fehler ${t}`));
  await fault(page, 'sitzungen_auflisten', null);
  await page.reload();
  await page.getByLabel('Neutrale Bezeichnung').fill('Fall S. Q.');
  await page.getByRole('button', { name: '+ Anlegen' }).click();
  await expect(page.getByRole('alert')).toContainText('Bezeichnung');
  await page.getByLabel('Gutachtentyp').selectOption('emotional_soziale_entwicklung');
  await expect(page.getByLabel('Gutachtentyp')).toContainText('Entwurf und Export gesperrt');
  await page.getByLabel('Gutachtentyp').selectOption('spf');
  await page.getByLabel('Neutrale Bezeichnung').fill('Fall 15');
  await page.getByRole('button', { name: '+ Anlegen' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Dokumente importieren' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Noch keine Dokumente' })).toBeVisible();
  await themes(page, (t) => axe(page, `02 leer ${t}`));
  const fallUrl = page.url();
  await fault(page, 'sitzung_laden', { delay_ms: 2500 });
  await page.reload();
  await expect(page.getByRole('status', { name: 'Dokumente werden geladen …' })).toBeVisible();
  await themes(page, (t) => axe(page, `02 laden ${t}`));
  await page.goto(fallUrl.replace('/dokumente', '/anonymisierung'));
  await expect(page.getByRole('status', { name: 'Dokument wird geladen …' })).toBeVisible();
  await themes(page, (t) => axe(page, `03 laden ${t}`));
  await fault(page, 'sitzung_laden', { code: 'E_BLOCKIERT', grund: 'konflikt' });
  await page.reload();
  await expect(page.getByRole('alert')).toContainText('Gleichzeitig in Claude geändert');
  await themes(page, (t) => axe(page, `03 fehler ${t}`));
  await fault(page, 'sitzung_laden', null);
  await page.goto('/#/faelle');
  await expect(page.getByRole('link', { name: 'Fall 15' })).toBeVisible();
  await themes(page, (t) => axe(page, `01 normal ${t}`));
});

test('Import, Erkennung, unsicherer Fund sperrt, Freigabe', async ({ page }) => {
  await einrichten(page);
  const r = await engine(page, 'sitzung_anlegen', { bezeichnung: 'Fall 16', modus: 'gutachten', gutachtentyp: 'spf' });
  const sid = r.result.session.session_id;
  await page.goto(`/#/fall/${sid}/dokumente`);
  await page.getByRole('textbox', { name: 'Name 1' }).fill('Synthia Quastberger');
  await page.getByRole('button', { name: 'Namen übernehmen' }).click();
  await expect(page.getByText('Namen gesetzt.')).toBeVisible();
  // wrong format: error, nothing lost
  await page.getByLabel('Quelle als Rolle').fill('Notiz');
  await page.getByLabel(/Datei importieren: Pfad/).fill(path.join(dir, 'falsch.txt'));
  await page.getByRole('button', { name: 'Datei importieren' }).click();
  await expect(page.getByRole('alert')).toContainText('E_DATEITYP');
  await themes(page, (t) => axe(page, `02 fehler ${t}`));
  await page.getByLabel('Quelle als Rolle').fill('Bericht der Klassenlehrerin');
  await page.getByLabel(/Datei importieren: Pfad/).fill(path.join(dir, 'bericht.docx'));
  await page.getByRole('button', { name: 'Datei importieren' }).click();
  await expect(page.getByText('Bericht der Klassenlehrerin')).toBeVisible();
  await themes(page, (t) => axe(page, `02 normal ${t}`));
  await page.getByRole('link', { name: 'Anonymisieren' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Anonymisierung' })).toBeVisible();
  await page.getByRole('button', { name: 'Erkennung starten' }).click();
  await expect(page.getByRole('heading', { name: /Funde \(/ })).toBeVisible();
  await themes(page, (t) => axe(page, `03 normal ${t}`));

  // a known name can never be kept
  const kind = page.getByRole('listitem').filter({ hasText: 'Synthia Quastberger' }).first();
  await expect(kind.getByRole('button', { name: /Behalten/ })).toBeDisabled();
  // manual redaction by keyboard
  await page.getByLabel('Text', { exact: true }).fill('zweite Stufe');
  await page.getByLabel('Ersetzen durch').fill('[Schulstufe]');
  await page.locator('form').getByRole('button', { name: 'Schwärzen' }).click();
  await expect(page.getByRole('listitem').filter({ hasText: 'manuell' }).first()).toBeVisible();

  const sperre = page.getByRole('list', { name: 'Noch gesperrt' });
  await expect(sperre).toContainText('Bestätigung der Durchsicht fehlt');
  const offen = page.getByText('✕ unsicher · Entscheidung nötig');
  const anzahlOffen = await offen.count();
  expect(anzahlOffen, 'der synthetische Text braucht mindestens einen unsicheren Fund').toBeGreaterThan(0);
  await expect(page.getByRole('status').filter({ hasText: 'Erkennung unsicher' })).toBeVisible();
  await themes(page, (t) => axe(page, `03 warnung ${t}`));
  await page.getByLabel('Ich habe den ganzen Text').check();
  await expect(sperre).toContainText('offen (unsicher)');
  const gesperrt = page.getByRole('button', { name: 'Weitergabe gesperrt' });
  await expect(gesperrt).toHaveAttribute('aria-disabled', 'true');
  await gesperrt.dispatchEvent('click'); // a click anyway changes nothing: the lock lives in the logic
  await expect(page.getByRole('heading', { level: 1, name: 'Anonymisierung' })).toBeVisible(); // nothing released
  const dokId = (await engine(page, 'sitzung_laden', { session_id: sid })).result.session.dokumente[0].dok_id;
  const engineSagt = await engine(page, 'anonymisierung_freigeben', { session_id: sid, dok_id: dokId, geprueft_bestaetigt: true });
  expect(engineSagt.fehler.code).toBe('E_ANONYMISIERUNG_OFFEN');
  for (let rest = anzahlOffen; rest > 0; rest--) {
    await page.getByRole('listitem').filter({ has: page.getByText('✕ unsicher · Entscheidung nötig') }).first()
      .getByRole('button', { name: 'Verallgemeinern' }).click();
    await expect(offen).toHaveCount(rest - 1);
  }
  await expect(offen).toHaveCount(0);
  await page.getByRole('button', { name: 'Schwärzung bestätigen' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Dokumente importieren' })).toBeVisible();
  await expect(page.getByText('✓ Schwärzung bestätigt').first()).toBeVisible();
  const fall = await engine(page, 'sitzung_laden', { session_id: sid });
  const text = fall.result.session.dokumente[0].text_anonymisiert as string;
  expect(text).not.toContain('Quastberger');
  expect(text).not.toContain('Brombeerstrauch');
  expect(text).not.toContain('zweite Stufe');
  expect(text).not.toContain('Wendelin');
  expect(text).toContain('[das Kind]');
  await page.goto(`/#/fall/${sid}/anonymisierung`);
  await expect(page.getByRole('heading', { name: 'Nichts zu anonymisieren' })).toBeVisible();
  await themes(page, (t) => axe(page, `03 leer ${t}`));
});
