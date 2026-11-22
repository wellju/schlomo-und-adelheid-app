// Test helpers: axe check (WCAG 2.1 AA) and fault injection through the development bridge. Synthetic data only.
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import AxeBuilder from '@axe-core/playwright';
import { expect, type Page } from '@playwright/test';

export async function axe(page: Page, wo: string) {
  const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
  expect(r.violations.map((v) => `${wo}: ${v.id} ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`)).toEqual([]);
}

async function bridge(page: Page, pfad: string, body: object) {
  const token = await page.locator('meta[name="schlomo-dev-token"]').getAttribute('content');
  const r = await page.request.post(`/__engine${pfad}`, { headers: { 'x-schlomo-token': token! }, data: body });
  expect(r.ok()).toBeTruthy();
}

export const fault = (page: Page, fn: string, f: { code?: string; grund?: string; delay_ms?: number } | null) =>
  bridge(page, '/fault', { fn, fault: f });

/** Call the engine directly, e.g. to prepare synthetic sessions. */
export async function engine(page: Page, fn: string, args: object = {}) {
  const token = await page.locator('meta[name="schlomo-dev-token"]').getAttribute('content');
  const r = await page.request.post('/__engine', { headers: { 'x-schlomo-token': token! }, data: { fn, args } });
  const msg = JSON.parse((await r.text()).trim().split('\n').pop()!);
  return msg;
}

/** Every theme: light, dark and system with a dark preference. */
export async function themes(page: Page, check: (name: string) => Promise<void>) {
  for (const t of ['hell', 'dunkel'] as const) {
    await page.evaluate((x) => { document.documentElement.dataset.theme = x; }, t);
    await check(t);
  }
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.evaluate(() => { document.documentElement.dataset.theme = 'system'; });
  await check('system dunkel');
  await page.emulateMedia({ colorScheme: 'light' });
}

/** Synthetic files written by the engine's Python (python-docx), into a fresh temp folder. */
export function synthDateien(): string {
  const dir = fs.mkdtempSync(path.join(fs.realpathSync.native(os.tmpdir()), 'schlomo-synth-'));
  const repo = path.resolve(import.meta.dirname, '..', '..', '..');
  const win = path.join(repo, 'engine', '.venv', 'Scripts', 'python.exe');
  const py = fs.existsSync(win) ? win : path.join(repo, 'engine', '.venv', 'bin', 'python');
  execFileSync(py, ['-I', path.join(import.meta.dirname, 'synth', 'dateien.py'), dir]);
  return dir;
}

/** Stand-in for Claude (synth/fall.py) on the bridge's data folder. */
export function claude(...args: string[]): string {
  const repo = path.resolve(import.meta.dirname, '..', '..', '..');
  const win = path.join(repo, 'engine', '.venv', 'Scripts', 'python.exe');
  const py = fs.existsSync(win) ? win : path.join(repo, 'engine', '.venv', 'bin', 'python');
  const basis = process.env.SCHLOMO_DEV_BASIS!;
  return execFileSync(py, ['-I', path.join(import.meta.dirname, 'synth', 'fall.py'), args[0], basis, ...args.slice(1)],
    { encoding: 'utf8', env: { ...process.env, PYTHONIOENCODING: 'utf-8', SCHLOMO_SPACY_MODEL: 'de_core_news_md' } });
}
