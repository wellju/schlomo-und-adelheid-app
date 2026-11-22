import { defineConfig } from '@playwright/test';

// Smoke test of the built Tauri app (CI only: Smart App Control blocks the build on the development device).
export default defineConfig({ testDir: 'tests/tauri', workers: 1, timeout: 180_000, expect: { timeout: 60_000 } });
