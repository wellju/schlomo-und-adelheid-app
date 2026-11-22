// Step 4.1: app starts with the real engine (handshake), Screen 13 in all states, axe without violations.
import { expect, test } from '@playwright/test';
import { axe, engine, fault, themes } from './hilfen';

test('Handshake und Einrichtung, Einstellungen bleiben nach Neustart', async ({ page }) => {
  await page.goto('/#/einstellungen');
  await expect(page.getByRole('heading', { name: 'Noch nicht eingerichtet' })).toBeVisible();
  await themes(page, (t) => axe(page, `13 leer ${t}`));
  await page.getByRole('button', { name: 'Einrichten' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Verbindung und Profil' })).toBeVisible();
  await expect(page.getByTestId('warn-q1')).toBeVisible();
  await themes(page, (t) => axe(page, `13 warnung ${t}`));
  await page.getByLabel('Claude im Browser').check();
  await page.getByLabel('Klinische Psychologin').check();
  await expect(page.getByTestId('warn-q1')).toHaveCount(0);
  await themes(page, (t) => axe(page, `13 normal ${t}`));
  await page.reload();
  await expect(page.getByLabel('Claude im Browser')).toBeChecked();
  await expect(page.getByLabel('Klinische Psychologin')).toBeChecked();
  const r = await engine(page, 'einstellungen_laden');
  expect(r.result.einstellungen.qualifikationen).toEqual(['klinische_psychologin']);
});

test('Laden und Fehler', async ({ page }) => {
  await page.goto('/#/faelle');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await fault(page, 'sitzungen_auflisten', { delay_ms: 3000 });
  await page.goto('/#/einstellungen');
  await expect(page.getByRole('status', { name: 'Wird geladen …' })).toBeVisible();
  await themes(page, (t) => axe(page, `13 laden ${t}`));
  await fault(page, 'sitzungen_auflisten', { code: 'E_INTERN' });
  await page.reload();
  await expect(page.getByRole('alert')).toContainText('Fehlercode: E_INTERN');
  await themes(page, (t) => axe(page, `13 fehler ${t}`));
  await fault(page, 'sitzungen_auflisten', null);
  await page.getByRole('button', { name: 'Erneut versuchen' }).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('Versionsabweichung zeigt E_VERSION', async ({ page }) => {
  await page.goto('/#/einstellungen');
  await fault(page, 'status', { code: 'E_VERSION' });
  await page.reload();
  await expect(page.getByRole('alert')).toContainText('E_VERSION');
  await fault(page, 'status', null);
});
