import { build } from 'esbuild';
import { mkdir, copyFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { gitBuildInfo } from './release-support.mjs';
const buildInfo = gitBuildInfo(path.resolve('../..'));
await mkdir('dist/renderer', { recursive: true });
await Promise.all([
  build({
    entryPoints: ['src/main.ts'],
    outfile: 'dist/main.cjs',
    bundle: true,
    platform: 'node',
    format: 'cjs',
    external: ['electron'],
    target: 'node24',
  }),
  build({
    entryPoints: ['src/preload.ts'],
    outfile: 'dist/preload.cjs',
    bundle: true,
    platform: 'node',
    format: 'cjs',
    external: ['electron'],
    target: 'node24',
  }),
  build({
    entryPoints: ['src/renderer/index.tsx'],
    outfile: 'dist/renderer/app.js',
    bundle: true,
    platform: 'browser',
    target: 'chrome148',
    minify: true,
    define: { 'process.env.NODE_ENV': '"production"' },
  }),
]);
await copyFile('src/renderer/index.html', 'dist/renderer/index.html');
await writeFile(
  'dist/build-info.json',
  `${JSON.stringify(buildInfo, null, 2)}\n`,
  'utf8',
);
