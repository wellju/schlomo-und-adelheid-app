// Step 4.6: first start sets up the working folder for Claude Desktop with this engine.
import fs from 'node:fs';
import path from 'node:path';
import { expect, test } from '@playwright/test';
import { axe, engine, themes } from './hilfen';

test('Arbeitsordner einrichten', async ({ page }) => {
  await page.goto('/#/einstellungen');
  await engine(page, 'einstellungen_speichern', { einstellungen: { schema_version: '1', verbindung: 'desktop', qualifikationen: ['schulpsychologin'], darstellung: 'system' } });
  await page.reload();
  await expect(page.getByTestId('warn-arbeitsordner')).toBeVisible();
  await themes(page, (t) => axe(page, `13 ohne arbeitsordner ${t}`));
  const ziel = path.join(process.env.SCHLOMO_DEV_BASIS!, 'Schlomo Arbeitsordner');
  await page.getByLabel('Ordner: Pfad (nur Entwicklung)').fill(process.env.SCHLOMO_DEV_BASIS!);
  await page.getByRole('button', { name: 'Arbeitsordner einrichten' }).click();
  await expect(page.getByRole('alert')).toContainText('neu oder leer');
  await page.getByLabel('Ordner: Pfad (nur Entwicklung)').fill(ziel);
  await page.getByRole('button', { name: 'Arbeitsordner einrichten' }).click();
  await expect(page.getByText('✓ Eingerichtet')).toBeVisible();
  await expect(page.getByTestId('warn-arbeitsordner')).toHaveCount(0);
  const mcp = JSON.parse(fs.readFileSync(path.join(ziel, '.mcp.json'), 'utf8'));
  expect(mcp.mcpServers.engine.args.at(-1)).toBe('mcp');
  expect(fs.existsSync(path.join(ziel, '.claude', 'skills', 'gutachten', 'SKILL.md'))).toBe(true);
  await themes(page, (t) => axe(page, `13 eingerichtet ${t}`));
});
