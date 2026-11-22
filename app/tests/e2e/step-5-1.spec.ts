// Task 5: proposals of /verbessern in Screen 11; a bad proposal is rejected by the evals and cannot be taken; a good
// one becomes a new version; rollback creates a new version and deletes nothing.
import { expect, test } from '@playwright/test';
import { axe, claude, engine, themes } from './hilfen';

test('Lernschleife: Vorschläge, Eval, Übernehmen, Rollback', async ({ page }) => {
  await page.goto('/#/einstellungen');
  await engine(page, 'einstellungen_speichern', { einstellungen: { schema_version: '1', verbindung: 'desktop', qualifikationen: ['schulpsychologin'], darstellung: 'system' } });
  expect(claude('verbessern', 'schlecht').trim()).toBe('eval_abgelehnt');
  expect(claude('verbessern', 'gut').trim()).toBe('eval_bestanden');
  await page.goto('/#/qualitaet');
  await expect(page.getByText('/verbessern', { exact: true })).toBeVisible();
  const schlecht = page.getByRole('article').filter({ hasText: 'als festgestellt formulieren' });
  await expect(schlecht.getByText('✕ Empfehlung statt Feststellung')).toBeVisible();
  await expect(schlecht.getByRole('button', { name: 'Übernehmen' })).toHaveAttribute('aria-disabled', 'true');
  await themes(page, (t) => axe(page, `11 vorschlaege ${t}`));
  await schlecht.getByRole('button', { name: 'Übernehmen' }).dispatchEvent('click'); // nothing happens
  expect((await engine(page, 'konfiguration_laden')).result.lernbausteine).toBeNull();
  await schlecht.getByRole('button', { name: 'Verwerfen' }).click();
  await expect(page.getByText('Vorschlag verworfen.')).toBeVisible();

  const gut = page.getByRole('article').filter({ hasText: 'in Klammern erklären' });
  await expect(gut.getByRole('button', { name: 'Übernehmen' })).toHaveAttribute('aria-disabled', 'true'); // LLM part first
  await gut.getByLabel(/Der LLM-Teil der Evals lief/).check();
  await gut.getByRole('button', { name: 'Bestätigen' }).click();
  await expect(gut.getByText(/LLM-Teil der Evals bestätigt/)).toBeVisible();
  await gut.getByRole('button', { name: 'Übernehmen' }).click();
  await expect(page.getByText('Übernommen als Version 1 der Lernbausteine.')).toBeVisible();
  expect(claude('verbessern', 'gut2').trim()).toBe('eval_bestanden');
  await page.reload();
  const gut2 = page.getByRole('article').filter({ hasText: 'Kurze Hauptsätze' });
  await gut2.getByLabel(/Der LLM-Teil der Evals lief/).check();
  await gut2.getByRole('button', { name: 'Bestätigen' }).click();
  await gut2.getByRole('button', { name: 'Übernehmen' }).click();
  await expect(page.getByText('Übernommen als Version 2 der Lernbausteine.')).toBeVisible();
  await page.getByRole('button', { name: 'Auf Version 1 zurück' }).click();
  await expect(page.getByText('Version 3', { exact: false }).first()).toBeVisible();
  const k = (await engine(page, 'konfiguration_laden')).result;
  expect(k.lernbausteine.version).toBe('3');
  expect(k.lernbausteine.bausteine.map((b: any) => b.text)).toEqual(['[synthetisch] Fachbegriffe beim ersten Vorkommen in Klammern erklären.']);
  expect(k.versionen.lernbausteine).toEqual(['1', '2']);
  await themes(page, (t) => axe(page, `11 nach rollback ${t}`));
});
