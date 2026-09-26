import { createClient } from '@hey-api/openapi-ts';
import { mkdtemp, readdir, readFile, rm } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { assertSameGeneratedEntries } from '../../admin-api-client/scripts/generated-client-drift.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const check = process.argv.includes('--check');
const output = check
  ? await mkdtemp(join(tmpdir(), 'vision-lab-client-'))
  : join(root, 'src/generated');
async function inventory(path, prefix = '') {
  const files = new Map();
  for (const entry of await readdir(path, { withFileTypes: true })) {
    if (entry.isDirectory())
      for (const [key, value] of await inventory(
        join(path, entry.name),
        `${prefix}${entry.name}/`,
      ))
        files.set(key, value);
    else
      files.set(
        `${prefix}${entry.name}`,
        await readFile(join(path, entry.name), 'utf8'),
      );
  }
  return files;
}
try {
  await createClient({
    input: join(root, 'openapi/openapi.json'),
    output: { path: output, tsConfigPath: join(root, 'tsconfig.json') },
  });
  if (check)
    assertSameGeneratedEntries(
      await inventory(join(root, 'src/generated')),
      await inventory(output),
    );
} finally {
  if (check) await rm(output, { recursive: true, force: true });
}
