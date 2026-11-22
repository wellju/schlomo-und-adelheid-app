// Step 4.5: synthetic intervision and supervision over ClaudeHandoff, warning and hint banner visible, key question
// confirmed before the end; style profile released in the app; quality overview from learning signals.
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { axe, claude, engine, fault, synthDateien, themes } from './hilfen';

async function einstellungen(page: Page, verbindung: 'desktop' | 'browser') {
  await page.goto('/#/einstellungen');
  await engine(page, 'einstellungen_speichern', { einstellungen: { schema_version: '1', verbindung, qualifikationen: ['schulpsychologin'], darstellung: 'system' } });
  await page.reload();
}
const sitzung = async (page: Page, modus: string, name: string) =>
  (await engine(page, 'sitzung_anlegen', { bezeichnung: name, modus })).result.session.session_id as string;

test('Intervision im Desktop-Modus: Warnhinweis, Hinweisbanner, Prüfungen, Schlüsselfrage bestätigen', async ({ page }) => {
  await einstellungen(page, 'desktop');
  const sid = await sitzung(page, 'intervision', 'Intervision 71');
  await page.goto(`/#/intervision/${sid}`);
  await expect(page.getByTestId('warnhinweis')).toContainText('Nur anonymisierte Vignetten');
  await expect(page.getByRole('heading', { name: 'Noch keine Sitzung' })).toBeVisible();
  await expect(page.getByText(`/intervision ${sid}`)).toBeVisible();
  await themes(page, (t) => axe(page, `07 leer ${t}`));
  await page.getByRole('button', { name: 'Übergeben und warten' }).click();
  claude('intervision', sid);
  await expect(page.getByRole('list', { name: 'Phasen' }).getByText('6 Abschluss · aktuell')).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId('hinweisbanner').first()).toContainText('MA 11');
  await expect(page.getByTestId('hinweisbanner').first()).toContainText('Die Sitzung läuft weiter.');
  await expect(page.getByRole('region', { name: 'Schlüsselfrage' })).toContainText('Wie gewinne ich die Eltern?');
  await expect(page.getByRole('article', { name: /Annahme ohne Beleg/ })).toBeVisible();
  await themes(page, (t) => axe(page, `07 normal ${t}`));
  const beenden = page.getByRole('button', { name: 'Sitzung beenden' });
  await expect(beenden).toHaveAttribute('aria-disabled', 'true'); // not before the key question is confirmed
  await page.getByLabel(/Die Schlüsselfrage und die Mitnahme stimmen/).check();
  await beenden.click();
  await expect(page.getByText('✓ Sitzung beendet.')).toBeVisible();
  const fall = (await engine(page, 'sitzung_laden', { session_id: sid })).result;
  expect(fall.protokolle.at(-1).phase).toBe('beendet');
  expect(fall.protokolle.at(-1).pruefbefunde.length).toBe(1);
});

test('Supervision im Browser-Modus: ein Protokoll, Goldfisch, Ende; ohne Hinweise keine Sitzung', async ({ page }) => {
  await einstellungen(page, 'browser');
  const sid = await sitzung(page, 'supervision', 'Supervision 72');
  await page.goto(`/#/supervision/${sid}`);
  await expect(page.getByRole('heading', { level: 1, name: 'Rubberduck Supervision' })).toBeVisible();
  const paket = (n: string) => path.join(process.env.SCHLOMO_DEV_BASIS!, `${sid}-${n}.json`);
  async function uebergabe(region: RegExp, n: string) {
    const r = page.getByRole('region', { name: region });
    await r.getByLabel('Speicherort des Pakets: Pfad (nur Entwicklung)').fill(paket(n));
    await r.getByRole('button', { name: 'Paket speichern' }).click();
    await expect(r.getByText('Paket gespeichert')).toBeVisible();
    await r.getByLabel('Antwort von Claude (Text oder Datei)').fill(claude('antwort', sid, paket(n)));
    await r.getByRole('button', { name: 'Antwort einfügen' }).click();
  }
  await uebergabe(/Sitzung in Claude führen/, 'sitzung');
  await expect(page.getByRole('list', { name: 'Phasen' }).getByText('5 Abschluss · aktuell')).toBeVisible();
  await expect(page.getByTestId('hinweisbanner').first()).toBeVisible();
  await expect(page.getByRole('region', { name: 'Anliegen' })).toContainText('unter Druck');
  await themes(page, (t) => axe(page, `08 normal ${t}`));
  await page.getByLabel(/Das Anliegen und die Mitnahme stimmen/).check();
  await page.getByRole('button', { name: 'Sitzung beenden' }).dispatchEvent('click');
  expect((await engine(page, 'protokoll_beenden', { session_id: sid })).fehler.grund).toBe('pruefung_fehlt');
  await uebergabe(/Prüfung Goldfisch/, 'goldfisch');
  await expect(page.getByRole('region', { name: /Prüfung Goldfisch/ })).toHaveCount(0);
  await page.getByRole('button', { name: 'Sitzung beenden' }).click();
  await expect(page.getByText('✓ Sitzung beendet.')).toBeVisible();
  expect((await engine(page, 'sitzung_laden', { session_id: sid })).result.lernsignale ?? []).toEqual([]);

  // without the hint wordings no session starts
  await fault(page, 'rubberduck_vorgaben', { delay_ms: 2500 });
  const sid2 = await sitzung(page, 'intervision', 'Intervision 73');
  await page.goto(`/#/intervision/${sid2}`);
  await expect(page.getByRole('status', { name: 'Sitzung wird geladen …' })).toBeVisible();
  await themes(page, (t) => axe(page, `07 laden ${t}`));
  await fault(page, 'rubberduck_vorgaben', null);
  await page.reload();
  await expect(page.getByText('Im Browser-Modus sind alle Berater ein Modell')).toBeVisible();
  await fault(page, 'sitzung_laden', { code: 'E_INTERN' });
  await page.reload();
  await expect(page.getByRole('alert')).toContainText('E_INTERN');
  await themes(page, (t) => axe(page, `07 fehler ${t}`));
  await fault(page, 'sitzung_laden', null);
});

test('Stilprofil: Probegutachten, Entwurf von Claude, Freigabe; Qualität aus Lernsignalen', async ({ page }) => {
  await einstellungen(page, 'desktop');
  await page.goto('/#/stilprofil');
  await expect(page.getByRole('heading', { name: 'Noch kein Stilprofil' })).toBeVisible();
  await themes(page, (t) => axe(page, `09 leer ${t}`));
  // a released sample report in its own session
  const dir = synthDateien();
  const s = (await engine(page, 'sitzung_anlegen', { bezeichnung: 'Probegutachten 1', modus: 'gutachten', gutachtentyp: 'spf' })).result.session.session_id;
  await engine(page, 'bekannte_namen_setzen', { session_id: s, namen: [] });
  const dok = (await engine(page, 'dokument_importieren', { session_id: s, pfad: path.join(dir, 'bericht.docx'), quelle_rolle: 'Probegutachten' })).result.dok_id;
  const funde = (await engine(page, 'erkennung_ausfuehren', { session_id: s, dok_id: dok })).result.funde;
  for (const f of funde.filter((x: any) => x.status === 'offen')) await engine(page, 'schwaerzung_entscheiden', { session_id: s, dok_id: dok, fund_id: f.fund_id, entscheidung: 'uebernehmen' });
  expect((await engine(page, 'anonymisierung_freigeben', { session_id: s, dok_id: dok, geprueft_bestaetigt: true })).ok).toBe(true);
  await page.reload();
  await expect(page.getByText(`/stil-lernen ${s}`)).toBeVisible();
  await page.getByRole('button', { name: 'Übergeben und warten' }).click();
  claude('stilprofil', s);
  await expect(page.getByRole('heading', { name: /Erkannte Stilmerkmale · Version v1/ })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText('Entwurf', { exact: true })).toBeVisible();
  await themes(page, (t) => axe(page, `09 normal ${t}`));
  await page.getByRole('button', { name: 'Version v1 freigeben' }).click();
  await expect(page.getByText('Version v1 freigegeben und aktiv.')).toBeVisible();
  expect((await engine(page, 'stilprofile_laden')).result.aktiv).toBe('v1');

  await page.goto('/#/qualitaet');
  await expect(page.getByRole('heading', { level: 1, name: 'Lernen und Qualität' })).toBeVisible();
  await expect(page.getByText(/Wenig Datengrundlage\.|Noch keine Lernsignale/).first()).toBeVisible(); // depends on earlier specs
  await themes(page, (t) => axe(page, `11 ${t}`));
  await fault(page, 'lernsignale_uebersicht', { code: 'E_INTERN' });
  await page.reload();
  await expect(page.getByRole('alert')).toContainText('E_INTERN');
  await themes(page, (t) => axe(page, `11 fehler ${t}`));
  await fault(page, 'lernsignale_uebersicht', { delay_ms: 2500 });
  await page.reload();
  await expect(page.getByRole('status', { name: 'Kennzahlen werden berechnet …' })).toBeVisible();
  await themes(page, (t) => axe(page, `11 laden ${t}`));
  await fault(page, 'lernsignale_uebersicht', null);
});
