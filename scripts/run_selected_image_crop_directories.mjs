import { promises as fs } from 'node:fs';
import path from 'node:path';
import { processCropDirectory } from './lib/selected-crop-durable-runner.mjs';
import { SELECTED_IMAGE_AUTO_CROP_POLICY } from '../packages/manual-image-selection-core/src/auto-crop.ts';
import { CROP_V11_POLICY } from '../packages/manual-image-selection-core/src/auto-crop-v11.ts';
import { CROP_V11_RELEASE_ENABLED } from '../packages/manual-image-selection-core/src/crop-preparation.ts';
const [
  parentArg,
  fromArg = '1',
  throughArg = '1',
  policy = SELECTED_IMAGE_AUTO_CROP_POLICY,
] = process.argv.slice(2);
if (!parentArg)
  throw new Error('Usage: <parent> <from-index> <through-index> [policy]');
if (policy === CROP_V11_POLICY && !CROP_V11_RELEASE_ENABLED)
  throw new Error('CROP_V11_ACCEPTANCE_REQUIRED');
const from = Number(fromArg),
  through = Number(throughArg);
if (
  !Number.isSafeInteger(from) ||
  !Number.isSafeInteger(through) ||
  from < 1 ||
  through < from
)
  throw new Error('CROP_RUN_RANGE_INVALID');
const parent = path.resolve(parentArg);
const dirs = (await fs.readdir(parent, { withFileTypes: true }))
  .filter(
    (e) =>
      e.isDirectory() &&
      !e.isSymbolicLink() &&
      !e.name.endsWith(' cut') &&
      /^\\s*\\d+/.test(e.name),
  )
  .sort(
    (a, b) =>
      parseInt(a.name) - parseInt(b.name) || a.name.localeCompare(b.name),
  );
if (through > dirs.length) throw new Error('CROP_RUN_RANGE_INCOMPLETE');
for (let index = from - 1; index < through; index++) {
  const dir = dirs[index];
  console.log('Start ' + (index + 1) + ': ' + dir.name);
  const result = await processCropDirectory(
    path.join(parent, dir.name),
    policy,
    {
      onProgress: (p) => {
        if (p.completed % 25 === 0) console.log(JSON.stringify(p));
      },
    },
  );
  console.log(JSON.stringify({ directory: dir.name, ...result }));
  if (result.failures.length) process.exitCode = 1;
}
