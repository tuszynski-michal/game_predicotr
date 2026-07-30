import { mkdir, mkdtemp, rename, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { generateAdminApiClient, generatedDirectory } from './generation.mjs';

const toolingDirectory = fileURLToPath(
  new URL('../../../.tooling/', import.meta.url),
);
await mkdir(toolingDirectory, { recursive: true });
const temporaryDirectory = await mkdtemp(
  join(toolingDirectory, 'openapi-generate-'),
);

try {
  await generateAdminApiClient(temporaryDirectory);
  await rm(generatedDirectory, { recursive: true, force: true });
  await rename(temporaryDirectory, generatedDirectory);
} finally {
  await rm(temporaryDirectory, { recursive: true, force: true });
}
