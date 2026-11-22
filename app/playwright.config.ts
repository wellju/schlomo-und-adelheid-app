import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { defineConfig } from '@playwright/test';

// Fresh synthetic data folder per run, outside the repo and in long form (docs/naechste-session.md).
// set once in the main process; workers inherit it, so the test helpers and the bridge share one folder
process.env.SCHLOMO_DEV_BASIS ??= path.join(fs.realpathSync.native(os.tmpdir()), `schlomo-e2e-${Date.now()}`);
const basis = process.env.SCHLOMO_DEV_BASIS;

export default defineConfig({
  testDir: 'tests/e2e',
  workers: 1,
  timeout: 240_000,
  expect: { timeout: 15_000 },
  use: { baseURL: 'http://127.0.0.1:5174', channel: 'msedge', locale: 'de-AT' },
  webServer: {
    command: 'npx vite --port 5174',
    url: 'http://127.0.0.1:5174',
    reuseExistingServer: false,
    timeout: 120_000,
    env: { SCHLOMO_DEV_BASIS: basis },
  },
});
