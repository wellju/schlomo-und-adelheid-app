// Built app with bundled engine: starts, version handshake succeeds, Screen 13 without axe violations.
// WebView2 opens a debugging port on request (WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS), Playwright attaches over CDP.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { chromium, expect, test } from '@playwright/test';
import { axe } from '../e2e/hilfen';

test('App startet mit Engine', async () => {
  const exe = process.env.SCHLOMO_APP_EXE;
  expect(exe, 'SCHLOMO_APP_EXE fehlt: ohne installierte App ist der Lauf rot, nie übersprungen (EGM C7)').toBeTruthy();
  const basis = fs.mkdtempSync(path.join(fs.realpathSync.native(os.tmpdir()), 'schlomo-tauri-'));
  const t0 = Date.now();
  const proc = spawn(exe!, [], {
    cwd: path.dirname(exe!),
    env: { ...process.env, WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: '--remote-debugging-port=9333 --remote-allow-origins=*',
           SCHLOMO_DATA_DIR: path.join(basis, 'daten'), SCHLOMO_WISSENSBASIS: path.join(basis, 'wissen') },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let ende: string | null = null;
  proc.on('exit', (code, signal) => { ende = `beendet mit ${code ?? signal}`; });
  proc.on('error', (e) => { ende = `Startfehler ${e.message}`; });
  proc.stderr?.on('data', (d) => process.stderr.write(d));
  try {
    let browser;
    for (let i = 0; i < 90 && !browser && !ende; i++) {
      browser = await chromium.connectOverCDP('http://127.0.0.1:9333', { timeout: 5000 }).catch(() => undefined);
      if (!browser) await new Promise((r) => setTimeout(r, 1000));
    }
    expect(ende, 'die App hat sich vor dem Anhängen beendet').toBeNull();
    expect(browser, 'WebView2 nicht erreichbar').toBeTruthy();
    const page = browser!.contexts()[0].pages()[0];
    await page.evaluate(() => { location.hash = '#/einstellungen'; });
    await expect(page.getByRole('heading', { name: 'Noch nicht eingerichtet' })).toBeVisible();
    console.log(`Start bis Handshake: ${Date.now() - t0} ms`);
    await page.getByRole('button', { name: 'Einrichten' }).click();
    await expect(page.getByRole('heading', { level: 1, name: 'Verbindung und Profil' })).toBeVisible();
    await axe(page, '13 in der Tauri-App');
    await browser!.close();
  } finally {
    proc.kill();
  }
});
