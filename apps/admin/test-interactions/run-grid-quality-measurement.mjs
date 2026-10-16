import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

// Small in-memory fixtures only. This runner never contacts local services.
const cwd = fileURLToPath(new URL('../', import.meta.url));
const result = spawnSync(
  process.execPath,
  [
    '../../node_modules/tsx/dist/cli.mjs',
    '--tsconfig',
    'tsconfig.json',
    '--test',
    'test/grid-quality-measurement.test.mjs',
    'test-interactions/grid-quality-measurement.test.mjs',
  ],
  { cwd, stdio: 'inherit', timeout: 110_000, windowsHide: true },
);
if (result.error) console.error(result.error.message);
process.exitCode = result.status ?? 1;
