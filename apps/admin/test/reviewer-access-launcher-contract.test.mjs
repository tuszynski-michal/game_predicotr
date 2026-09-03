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
  assert.match(source, /listImageGridReviews/);
  assert.doesNotMatch(source, /listOperationalImageReviewItems/);
  assert.match(source, /listPendingBoardCellGeometry/);
  assert.match(source, /listReadyBrowserImageSelections/);
  assert.match(source, /readyBoardImportStaging/);
  assert.match(source, /Gotowy staging plansz czeka na uruchomienie importu/);
  assert.match(source, /className="reviewerImportSelect"/);
  assert.match(source, /className="reviewerSelectedImportId"/);
  assert.match(source, /ID: <code>\{selectedJob\.id\}<\/code>/);
  assert.match(source, /Przejdź do Importu plansz/);
  assert.match(source, /gridReviewTotal\(gridReviewCounts\) === 0/);
  assert.match(source, /Do korekty siatki/);
  assert.match(
    source,
    /hasReviewerWork\(gridReviewCounts, deferredGeometryCounts\)/,
  );
  assert.match(source, /hasVirtualGridAssets/);
  assert.match(source, /cropów v0\.10 renderowanych ze źródła/);
  assert.match(source, /reviewReadyImports/);
  assert.match(source, /reviewableGames/);
  assert.doesNotMatch(source, /stopReviewerIngress/);
  assert.doesNotMatch(source, /revokeReviewerSession/);
  assert.doesNotMatch(source, /leaseToken/);
  assert.doesNotMatch(source, /game\.status === 'active'/);
});

test('local launch navigates the prepared window before refreshing assignment state', async () => {
  const source = await readFile(launcherPath, 'utf8');
  const launchStart = source.indexOf('async function launchLocalReviewer()');
  const launchEnd = source.indexOf(
    'async function createOnlineWork()',
    launchStart,
  );
  const launchSource = source.slice(launchStart, launchEnd);
  const navigateAt = launchSource.indexOf(
    'navigatePreparedLocalReviewerWindow',
  );
  const refreshAt = launchSource.indexOf('void refreshOverview(false)');

  assert.notEqual(navigateAt, -1);
  assert.ok(refreshAt > navigateAt);
  assert.doesNotMatch(launchSource, /await refreshOverview\(false\)/);
  assert.doesNotMatch(launchSource, /about:blank/);
  assert.match(launchSource, /closePreparedLocalReviewerWindow/);
  assert.match(launchSource, /setLocalReviewUrl\(reviewUrl\)/);
  assert.match(launchSource, /Nie udało się przekierować przygotowanego okna/);
});
