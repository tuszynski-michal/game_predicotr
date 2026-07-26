import { mkdir, mkdtemp, readFile, readdir, rm } from 'node:fs/promises';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

import { generateAdminApiClient, generatedDirectory } from './generation.mjs';

const currentDirectory = generatedDirectory;
const toolingDirectory = fileURLToPath(
  new URL('../../../.tooling/', import.meta.url),
);
await mkdir(toolingDirectory, { recursive: true });
const temporaryDirectory = await mkdtemp(
  join(toolingDirectory, 'openapi-check-'),
);

async function filesByRelativePath(directory) {
  const result = new Map();

  async function visit(current) {
    const entries = await readdir(current, { withFileTypes: true });
    for (const entry of entries) {
      const path = join(current, entry.name);
      if (entry.isDirectory()) {
        await visit(path);
      } else {
        result.set(
          relative(directory, path).replaceAll('\\', '/'),
          await readFile(path, 'utf8'),
        );
      }
    }
  }

  await visit(directory);
  return result;
}

try {
  await generateAdminApiClient(temporaryDirectory);

  const current = await filesByRelativePath(currentDirectory);
  const expected = await filesByRelativePath(temporaryDirectory);

  assertSameEntries(current, expected);
  console.log('Generated Admin API client is current.');
} finally {
  await rm(temporaryDirectory, { recursive: true, force: true });
}

function assertSameEntries(current, expected) {
  const currentKeys = [...current.keys()].sort();
  const expectedKeys = [...expected.keys()].sort();

  if (JSON.stringify(currentKeys) !== JSON.stringify(expectedKeys)) {
    throw new Error(
      'Generated Admin API file set is stale. Run: npm run openapi:generate',
    );
  }

  for (const path of expectedKeys) {
    if (current.get(path) !== expected.get(path)) {
      const currentContent = current.get(path) ?? '';
      const expectedContent = expected.get(path) ?? '';
      const firstDifference = [...expectedContent].findIndex(
        (character, index) => character !== currentContent[index],
      );
      throw new Error(
        `Generated Admin API file is stale: ${path} at character ${firstDifference}. ` +
          'Run: npm run openapi:generate',
      );
    }
  }
}
