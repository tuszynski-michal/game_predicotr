import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const launcherPath = new URL(
  '../src/features/reviewer-access/reviewer-access-launcher.tsx',
  import.meta.url,
);

test('launcher exposes explicit online start and stop controls', async () => {
  const source = await readFile(launcherPath, 'utf8');

  assert.match(source, /publishReviewerSession/);
  assert.match(source, /stopReviewerPublishing/);
  assert.match(source, /Utwórz link i wystaw online/);
  assert.match(source, /Zatrzymaj udostępnianie/);
  assert.match(source, /session\?\.sessionId/);
  assert.match(source, /listOperationalImageReviewItems/);
  assert.match(source, /Przejdź do Import layoutów/);
  assert.match(source, /reviewCounts\?\.total === 0/);
  assert.match(source, /reviewReadyImports/);
});
