import fs from 'node:fs';
import path from 'node:path';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vite';
import { engineBridge } from './dev/bridge';

const REPO = path.resolve(import.meta.dirname, '..');

// Versions the app expects from `status` (docs/ui-api.md, E_VERSION): taken from the same repo the engine is built from.
function expected() {
  const init = fs.readFileSync(path.join(REPO, 'engine', 'src', 'schlomo_engine', '__init__.py'), 'utf8');
  const engine_version = /__version__ = "([^"]+)"/.exec(init)![1];
  const schema_versionen: Record<string, string> = {};
  for (const f of fs.readdirSync(path.join(REPO, 'contracts')).filter((f) => f.endsWith('.schema.json')).sort()) {
    const s = JSON.parse(fs.readFileSync(path.join(REPO, 'contracts', f), 'utf8'));
    schema_versionen[f.replace('.schema.json', '')] = s.properties?.schema_version?.const ?? '';
  }
  return { engine_version, schema_versionen };
}

export default defineConfig({
  plugins: [svelte(), engineBridge()],
  define: { __ERWARTET__: JSON.stringify(expected()) },
  clearScreen: false,
  server: { host: '127.0.0.1', port: 5174, strictPort: true },
  build: { target: 'es2022' },
});
