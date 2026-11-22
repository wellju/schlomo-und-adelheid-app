// Step 4.4: entries without a source are refused; proposals appear only after the internal diagnosis.
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { axe, claude, engine, fault, themes } from './hilfen';

async function einstellungen(page: Page, qualifikationen: string[]) {
  await page.goto('/#/einstellungen');
  await engine(page, 'einstellungen_speichern', { einstellungen: { schema_version: '1', verbindung: 'desktop', qualifikationen, darstellung: 'system' } });
  await page.reload();
}

test('Katalog: Quellenpflicht, Versionen, Rollback, Vorlagenimport', async ({ page }) => {
  await einstellungen(page, ['schulpsychologin']);
  await page.goto('/#/katalog');
  await expect(page.getByRole('heading', { level: 1, name: 'Testkatalog und Regelwerk' })).toBeVisible();
  await expect(page.getByRole('table', { name: /Testkatalog Version syn-1/ })).toBeVisible();
  await themes(page, (t) => axe(page, `10 testkatalog ${t}`));
  // edit a procedure and empty its source: refused, nothing saved
  await page.getByRole('button', { name: 'Bearbeiten Synthetischer Intelligenztest A' }).click();
  await page.getByLabel('Quelle *: Manual').fill('');
  await page.getByRole('button', { name: 'Verfahren speichern' }).click();
  await expect(page.getByRole('alert')).toContainText('Pflichtfeld Quelle fehlt');
  await themes(page, (t) => axe(page, `10 testkatalog fehler ${t}`));
  const vorher = await engine(page, 'konfiguration_laden');
  expect(vorher.result.testkatalog.version).toBe('syn-1');
  await page.getByLabel('Quelle *: Manual').fill('[synthetisch] Manual A');
  await page.getByRole('button', { name: 'Verfahren speichern' }).click();
  await expect(page.getByText('Gespeichert als Version syn-2.')).toBeVisible();
  // the engine refuses an empty source even when the app is bypassed
  const doc = structuredClone(vorher.result.testkatalog);
  doc.version = 'syn-9';
  doc.eintraege[0].quelle = { manual: ' ', seite: '1' };
  expect((await engine(page, 'katalog_speichern', { name: 'testkatalog', dokument: doc })).fehler.code).toBe('E_SCHEMA');

  await page.getByRole('tab', { name: 'Kategorienskala' }).click();
  await page.getByLabel('Von').fill('170');
  await page.getByLabel('Bis').fill('180');
  await page.getByLabel('Bezeichnung').fill('Kategorie Z');
  await page.getByRole('button', { name: '+ Bereich speichern' }).click();
  await expect(page.getByRole('alert')).toContainText('Pflichtfeld Quelle fehlt');
  await page.getByLabel('Quelle *').fill('[synthetisch] Quelle Z');
  await page.getByRole('button', { name: '+ Bereich speichern' }).click();
  await expect(page.getByText('Gespeichert als Version syn-2.')).toBeVisible();
  await expect(page.getByRole('cell', { name: 'Kategorie Z', exact: true })).toBeVisible();
  await themes(page, (t) => axe(page, `10 kategorienskala ${t}`));
  await page.getByRole('button', { name: 'Auf Version syn-1 zurück' }).click();
  await expect(page.getByRole('table', { name: /Kategorienskala Version syn-3/ })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'Kategorie Z', exact: true })).toHaveCount(0);

  await page.getByRole('tab', { name: 'Regelwerk' }).click();
  await expect(page.getByRole('cell', { name: 'spf_s1', exact: true })).toBeVisible();
  await themes(page, (t) => axe(page, `10 regelwerk ${t}`));

  await page.getByRole('tab', { name: 'Vorlagen' }).click();
  await expect(page.getByRole('heading', { name: 'Vorlage importieren' })).toBeVisible();
  await themes(page, (t) => axe(page, `10 vorlagen ${t}`));
  claude('vorlagedatei');
  await page.getByLabel(/Vorlage importieren: Pfad/).fill(path.join(process.env.SCHLOMO_DEV_BASIS!, 'Neue Vorlage.docx'));
  await page.getByRole('button', { name: 'Vorlage importieren' }).click();
  await expect(page.getByRole('heading', { name: /Zuordnung: Neue_Vorlage.docx/ })).toBeVisible();
  await page.getByLabel('Kennung der Vorlage').fill('spf-neu');
  await page.getByLabel('Vorstellungsgrund').selectOption('Vorstellungsgrund');
  await page.getByLabel('Name des Kindes').selectOption({ index: 1 });
  await themes(page, (t) => axe(page, `10 zuordnung ${t}`));
  await page.getByRole('button', { name: 'Zuordnung speichern' }).click();
  await expect(page.getByText('Vorlage spf-neu zugeordnet.')).toBeVisible();
  await expect(page.getByRole('cell', { name: 'spf-neu', exact: true })).toBeVisible();
  // importing the same file again never overwrites
  await page.getByLabel(/Vorlage importieren: Pfad/).fill(path.join(process.env.SCHLOMO_DEV_BASIS!, 'Neue Vorlage.docx'));
  await page.getByRole('button', { name: 'Vorlage importieren' }).click();
  await expect(page.getByRole('alert')).toContainText('nie überschrieben');

  await fault(page, 'konfiguration_laden', { delay_ms: 2500 });
  await page.reload();
  await expect(page.getByRole('status', { name: 'Katalog wird geladen …' })).toBeVisible();
  await themes(page, (t) => axe(page, `10 laden ${t}`));
  await fault(page, 'konfiguration_laden', null);
});

test('Diagnosevergleich: gesperrt ohne Q1, blind bis zur internen Diagnose', async ({ page }) => {
  await einstellungen(page, ['schulpsychologin']);
  const sid = (await engine(page, 'sitzung_anlegen', { bezeichnung: 'Fall 52', modus: 'gutachten', gutachtentyp: 'spf' })).result.session.session_id;
  await engine(page, 'bekannte_namen_setzen', { session_id: sid, namen: [] });
  await page.goto(`/#/fall/${sid}/diagnosevergleich`);
  await expect(page.getByText('Gesperrt.')).toBeVisible();
  await themes(page, (t) => axe(page, `12 gesperrt ${t}`));

  await einstellungen(page, ['schulpsychologin', 'klinische_psychologin']);
  claude('eingabe', sid); // synthetic input with Q1
  await page.goto(`/#/fall/${sid}/diagnosevergleich`);
  await expect(page.getByRole('heading', { name: 'Schritt 1 · Ihre interne Diagnose' })).toBeVisible();
  await expect(page.getByTestId('blind')).toBeVisible();
  await expect(page.getByRole('article', { name: 'Vorschlag der Engine' })).toHaveCount(0);
  await themes(page, (t) => axe(page, `12 leer ${t}`));
  await page.getByLabel('Diagnose', { exact: true }).fill('[synthetisch] interne Einschätzung');
  await page.getByLabel('ICD-10-Code (optional)').fill('f70');
  await page.getByRole('button', { name: 'Interne Diagnose speichern' }).click();
  await expect(page.getByRole('article', { name: 'Vorschlag der Engine' })).toBeVisible();
  await expect(page.getByText(/Subagent diagnosevorschlag mit session_id/)).toBeVisible();
  // the internal diagnosis is in no package for Claude
  const paket = await engine(page, 'erzeuge_paket', { session_id: sid, art: 'diagnosevorschlag' });
  expect(JSON.stringify(paket.result.fallpaket)).not.toContain('interne Einschätzung');
  await page.getByRole('button', { name: 'Übergeben und warten' }).click();
  claude('diagnose', sid);
  await expect(page.getByText('KI-Vorschlag · Claude')).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole('article', { name: 'Vorschlag von Claude' })).toContainText('abweichend');
  await page.getByLabel(/Ihre Notiz zur Abweichung/).fill('[synthetisch] Notiz');
  await page.getByRole('button', { name: 'Notiz speichern' }).click();
  await expect(page.getByText('Notiz gespeichert.')).toBeVisible();
  await page.reload();
  await expect(page.getByText('Claude abweichend: 1')).toBeVisible();
  await themes(page, (t) => axe(page, `12 normal ${t}`));
  // locked after the first comparison
  expect((await engine(page, 'interne_diagnose_speichern', { session_id: sid, interne_diagnose: { text: 'neu' } })).fehler.code).toBe('E_BLOCKIERT');
  // sitzung_laden never returns the internal diagnosis
  expect(JSON.stringify((await engine(page, 'sitzung_laden', { session_id: sid })).result)).not.toContain('interne Einschätzung');
  await fault(page, 'diagnosevergleich_laden', { code: 'E_INTERN' });
  await page.reload();
  await expect(page.getByRole('alert')).toContainText('E_INTERN');
  await themes(page, (t) => axe(page, `12 fehler ${t}`));
  await fault(page, 'diagnosevergleich_laden', null);
});
