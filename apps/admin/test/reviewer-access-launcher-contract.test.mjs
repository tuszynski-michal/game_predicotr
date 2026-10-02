import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const launcherPath = new URL(
  '../src/features/reviewer-access/reviewer-access-launcher.tsx',
  import.meta.url,
);

test('launcher exposes only the import-scoped local grid review control', async () => {
  const source = await readFile(launcherPath, 'utf8');

  assert.match(source, /buildPreparedLocalReviewUrl/);
  assert.match(source, /prepareLocalReviewerWindow/);
  assert.match(source, /startLocalReviewerProcess/);
  assert.match(source, /navigatePreparedLocalReviewerWindow/);
  assert.match(source, /Otwórz lokalnie/);
  assert.doesNotMatch(source, /openOnlineReviewer/);
  assert.doesNotMatch(source, /openLocalReviewer/);
  assert.doesNotMatch(source, /loadReviewerWork/);
  assert.doesNotMatch(source, /heartbeatReviewerWork/);
  assert.doesNotMatch(source, /closeReviewerWork/);
  assert.doesNotMatch(source, /Utwórz link online/);
  assert.doesNotMatch(source, /Zatrzymaj udostępnianie/);
  assert.doesNotMatch(source, /Zakończ pracę lokalną/);
  assert.doesNotMatch(source, /Aktywne prace/);
  assert.doesNotMatch(source, /activeOnlineCount/);
  assert.doesNotMatch(source, /maximumOnlineCount/);
  assert.doesNotMatch(source, /assignmentId/);
  assert.doesNotMatch(source, /accessCode/);
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
  assert.match(source, /Geometria plansz ze stron 3×3/);
  // D-462: one correction queue instead of validation and correction views.
  assert.match(source, /Korekta cięcia siatki/);
  assert.match(source, /Plansze do korekty cięcia siatki/);
  assert.match(source, /view: 'correction'/);
  assert.doesNotMatch(source, /do walidacji|Zatwierdzanie cięcia siatki/);
  assert.match(
    source,
    /hasReviewerWork\(gridReviewCounts, deferredGeometryCounts\)/,
  );
  assert.doesNotMatch(source, /hasVirtualGridAssets/);
  assert.match(source, /reviewReadyImports/);
  assert.match(source, /reviewableGames/);
  assert.doesNotMatch(source, /stopReviewerIngress/);
  assert.doesNotMatch(source, /revokeReviewerSession/);
  assert.doesNotMatch(source, /leaseToken/);
  assert.doesNotMatch(source, /game\.status === 'active'/);
});

test('local launch starts the process and retries the final scoped URL without creating an assignment', async () => {
  const source = await readFile(launcherPath, 'utf8');
  const launchStart = source.indexOf('function launchLocalReviewer()');
  const launchEnd = source.indexOf('\n\n  return (', launchStart);
  const launchSource = source.slice(launchStart, launchEnd);

  assert.match(launchSource, /buildPreparedLocalReviewUrl/);
  assert.match(launchSource, /prepareLocalReviewerWindow/);
  assert.match(launchSource, /startLocalReviewerProcess\(api\)/);
  assert.match(launchSource, /setLocalReviewUrl\(reviewUrl\)/);
  assert.match(launchSource, /Przeglądarka zablokowała nowe okno/);
  assert.match(launchSource, /navigatePreparedLocalReviewerWindow/);
  assert.match(launchSource, /closePreparedLocalReviewerWindow/);
  assert.doesNotMatch(launchSource, /openLocalReviewer/);
  assert.doesNotMatch(launchSource, /refreshOverview/);
  assert.doesNotMatch(launchSource, /about:blank/);
  assert.ok(
    launchSource.indexOf('prepareLocalReviewerWindow') <
      launchSource.indexOf('startLocalReviewerProcess'),
  );
  assert.ok(
    launchSource.indexOf('startLocalReviewerProcess') <
      launchSource.indexOf('navigatePreparedLocalReviewerWindow'),
  );
});
