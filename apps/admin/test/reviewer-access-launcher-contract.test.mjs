import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const launcherPath = new URL(
  '../src/features/reviewer-access/reviewer-access-launcher.tsx',
  import.meta.url,
);

test('launcher exposes import-scoped local and independent online controls', async () => {
  const source = await readFile(launcherPath, 'utf8');

  assert.match(source, /openOnlineReviewer/);
  assert.match(source, /openLocalReviewer/);
  assert.match(source, /loadReviewerWork/);
  assert.match(source, /heartbeatReviewerWork/);
  assert.match(source, /closeReviewerWork/);
  assert.match(source, /Otwórz lokalnie/);
  assert.match(source, /Utwórz link online/);
  assert.match(source, /Zatrzymaj udostępnianie/);
  assert.match(source, /Aktywne prace/);
  assert.match(source, /activeOnlineCount/);
  assert.match(source, /maximumOnlineCount/);
  assert.match(source, /assignmentId/);
  assert.match(source, /listOperationalImageReviewItems/);
  assert.match(source, /Przejdź do Import layoutów/);
  assert.match(source, /reviewCounts\?\.total === 0/);
  assert.match(source, /reviewReadyImports/);
  assert.match(source, /reviewableGames/);
  assert.doesNotMatch(source, /stopReviewerIngress/);
  assert.doesNotMatch(source, /revokeReviewerSession/);
  assert.doesNotMatch(source, /leaseToken/);
  assert.doesNotMatch(source, /game\.status === 'active'/);
});
