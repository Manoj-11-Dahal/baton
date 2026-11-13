/**
 * Build script for Agi Super Harness.
 * Builds the renderer with Vite, then the Node core with esbuild.
 * Usage: node scripts/build-node.mjs [--tests]
 */

import { build } from 'vite';
import { build as esbuildBuild } from 'esbuild';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const tests = process.argv.includes('--tests');

async function main() {
  console.log('[build] Building renderer with Vite...');
  await build({
    configFile: path.resolve(root, 'vite.config.mts'),
    build: { outDir: path.resolve(root, 'dist/renderer'), emptyOutDir: true },
  });
  console.log('[build] Renderer built → dist/renderer');

  const entries = tests
    ? ['tests/unit.test.ts']
    : ['src/core/index.ts', 'src/electron/main.ts'];

  const outDir = tests ? path.resolve(root, 'dist/tests') : path.resolve(root, 'dist');

  console.log(`[build] Building Node code with esbuild → ${outDir}...`);
  await esbuildBuild({
    entryPoints: entries.map((e) => path.resolve(root, e)),
    bundle: true,
    platform: 'node',
    format: 'cjs',
    outdir: outDir,
    logLevel: 'info',
    target: 'node22',
    external: ['electron', 'zustand', 'react', 'react-dom'],
  });

  console.log('[build] Done.');
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
