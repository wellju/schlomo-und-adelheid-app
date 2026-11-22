// Development bridge (only `vite serve`): starts `engine ui` from engine/.venv and relays the JSON-lines channel of
// docs/ui-api.md over HTTP on 127.0.0.1. Needed because Smart App Control blocks the locally built Tauri shell on the
// development device (docs/task-4-ergebnis.md). Synthetic data only; never part of a production build.
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import type { IncomingMessage, ServerResponse } from 'node:http';
import type { Plugin } from 'vite';

type Msg = { id?: string; ok?: boolean; event?: string; [k: string]: unknown };
type Fault = { code?: string; grund?: string | null; delay_ms?: number };

const REPO = path.resolve(import.meta.dirname, '..', '..');

function devDirs() {
  const base = process.env.SCHLOMO_DEV_BASIS ?? path.join(fs.realpathSync.native(os.tmpdir()), 'schlomo-dev');
  const dirs = { base, data: path.join(base, 'daten'), work: path.join(base, 'arbeit'), wissen: path.join(base, 'wissensbasis'),
    konf: path.join(base, 'konfiguration') };
  // a copy of the synthetic configuration: catalogue care in the app writes there, never into the repo's test fixtures
  if (!fs.existsSync(dirs.konf)) {
    fs.cpSync(process.env.SCHLOMO_DEV_KONFIGURATION ?? path.join(REPO, 'engine', 'tests', 'konfiguration_synthetisch'), dirs.konf, { recursive: true });
  }
  for (const d of Object.values(dirs)) fs.mkdirSync(d, { recursive: true });
  return dirs;
}

function python(): string {
  const win = path.join(REPO, 'engine', '.venv', 'Scripts', 'python.exe');
  return fs.existsSync(win) ? win : path.join(REPO, 'engine', '.venv', 'bin', 'python');
}

async function body(req: IncomingMessage): Promise<any> {
  let raw = '';
  for await (const chunk of req) raw += chunk;
  return JSON.parse(raw || '{}');
}

export function engineBridge(): Plugin {
  const token = randomBytes(24).toString('hex');
  const pending = new Map<string, (m: Msg) => void>();
  const faults = new Map<string, Fault>();
  let proc: ChildProcessWithoutNullStreams | null = null;
  let seq = 0;

  function start() {
    const d = devDirs();
    proc = spawn(python(), ['-m', 'schlomo_engine', 'ui'], {
      cwd: d.work,
      env: {
        ...process.env,
        PYTHONPATH: path.join(REPO, 'engine', 'src'),
        PYTHONIOENCODING: 'utf-8',
        SCHLOMO_DATA_DIR: d.data,
        SCHLOMO_KONFIGURATION: d.konf,
        SCHLOMO_WISSENSBASIS: d.wissen,
        SCHLOMO_VORLAGEN: path.join(d.wissen, 'vorlagen'),
        SCHLOMO_SPACY_MODEL: process.env.SCHLOMO_SPACY_MODEL ?? 'de_core_news_md',
      },
    });
    let buf = '';
    proc.stdout.setEncoding('utf8');
    proc.stdout.on('data', (chunk: string) => {
      buf += chunk;
      let i: number;
      while ((i = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, i);
        buf = buf.slice(i + 1);
        if (!line.trim()) continue;
        let msg: Msg;
        try { msg = JSON.parse(line) as Msg; } catch { continue; } // a broken line never ends the dev server (EGM B7)
        if (msg.id && pending.has(msg.id)) pending.get(msg.id)!(msg);
      }
    });
    proc.stderr.on('data', (c) => process.stderr.write(c)); // log lines carry no content (docs/ui-api.md)
    proc.on('error', () => { proc = null; for (const [id, done] of pending) done({ id, ok: false, fehler: { code: 'E_INTERN', grund: null } }); });
    proc.on('exit', () => {
      proc = null;
      for (const [id, done] of pending) done({ id, ok: false, fehler: { code: 'E_INTERN', grund: null } });
    });
  }

  async function handle(req: IncomingMessage, res: ServerResponse) {
    // only this dev server's own page: same host, and no foreign Origin (EGM C20)
    const host = req.headers.host ?? '';
    const origin = req.headers.origin;
    if (req.method !== 'POST' || req.headers['x-schlomo-token'] !== token || !/^(127\.0\.0\.1|localhost):\d+$/.test(host)
        || (origin && origin !== `http://${host}`)) {
      res.statusCode = 403;
      return res.end();
    }
    const msg = await body(req);
    if (req.url === '/fault') { // test hook: inject a delay or an error for one function
      if (msg.fault) faults.set(msg.fn, msg.fault); else faults.delete(msg.fn);
      return res.end('{}');
    }
    if (req.url === '/reset') { // test hook: stop the engine; the next call starts a fresh one
      proc?.stdin.end();
      proc = null;
      faults.clear();
      return res.end('{}');
    }
    res.setHeader('content-type', 'application/x-ndjson');
    const fault = faults.get(msg.fn);
    if (fault?.delay_ms) await new Promise((r) => setTimeout(r, fault.delay_ms));
    if (fault?.code) return res.end(JSON.stringify({ ok: false, fehler: { code: fault.code, grund: fault.grund ?? null } }) + '\n');
    if (!proc) start();
    const id = `dev-${++seq}`;
    await new Promise<void>((resolve) => {
      pending.set(id, (m) => {
        res.write(JSON.stringify(m) + '\n');
        if (!m.event) {
          pending.delete(id);
          resolve();
        }
      });
      proc!.stdin.write(JSON.stringify({ id, fn: msg.fn, args: msg.args ?? {} }) + '\n');
    });
    res.end();
  }

  return {
    name: 'schlomo-engine-bridge',
    apply: 'serve',
    transformIndexHtml: (html) => html.replace('</head>', `<meta name="schlomo-dev-token" content="${token}">\n</head>`),
    configureServer(server) {
      server.middlewares.use('/__engine', (req, res) => {
        handle(req, res).catch(() => {
          res.statusCode = 500;
          res.end();
        });
      });
      server.httpServer?.on('close', () => proc?.stdin.end());
    },
  };
}
