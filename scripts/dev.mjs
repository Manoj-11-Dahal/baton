/**
 * Dev script for Agi Super Harness.
 * Starts Vite in dev mode and launches Electron once the renderer is ready.
 * Usage: node scripts/dev.mjs [--web]
 */

import { execSync, spawn } from 'node:child_process';
import { createServer } from 'vite';
import path from 'node:path';

const root = path.resolve(__dirname, '..');
const web = process.argv.includes('--web');

async function main() {
  const server = await createServer({
    configFile: path.resolve(root, 'vite.config.mts'),
    server: { middlewareMode: true, hmr: web },
  });

  await server.listen(5173);
  console.log('[dev] Vite dev server ready on http://127.0.0.1:5173');

  if (web) {
    console.log('[dev] Web mode: open http://127.0.0.1:5173');
    return;
  }

  // Launch Electron pointing at the dev server
  const electron = spawn(require.resolve('electron'), ['.'], {
    cwd: root,
    stdio: 'inherit',
    env: { ...process.env, BATON_DEV: '1', VITE_DEV_SERVER_URL: 'http://127.0.0.1:5173' },
  });

  electron.on('exit', (code) => {
    process.exit(code ?? 0);
  });

  process.on('SIGINT', () => {
    electron.kill('SIGINT');
    server.close();
    process.exit(0);
  });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
