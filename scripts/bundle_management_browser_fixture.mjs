import { build } from 'esbuild';
import { resolve } from 'node:path';
await build({
  entryPoints: ['artifacts/management-panel-browser/browser/fixture.tsx'],
  bundle: true,
  platform: 'browser',
  format: 'iife',
  outfile: 'artifacts/management-panel-browser/browser/fixture.js',
  jsx: 'automatic',
  alias: {
    react: resolve('apps/reviewer/node_modules/react'),
    'react-dom': resolve('apps/reviewer/node_modules/react-dom'),
  },
  define: { 'process.env.NODE_ENV': '"production"' },
});
