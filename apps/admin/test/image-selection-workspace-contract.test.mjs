import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const workspaceSource = await readFile(
  new URL(
    '../src/features/image-selection/image-selection-workspace.tsx',
    import.meta.url,
  ),
  'utf8',
);
const catalogSource = await readFile(
  new URL('../src/features/catalog/catalog-workspace.tsx', import.meta.url),
  'utf8',
);
const styleSource = await readFile(
  new URL('../src/app/globals.css', import.meta.url),
  'utf8',
);
const manualModalSource = await readFile(
  new URL(
    '../src/features/image-selection/manual-image-selection-modal.tsx',
    import.meta.url,
  ),
  'utf8',
);
const jobMonitorSource = await readFile(
  new URL('../src/features/jobs/job-monitor.tsx', import.meta.url),
  'utf8',
);

test('uses a browser-native directory picker directly from the owner action', () => {
  assert.match(workspaceSource, /folderInputRef\.current\?\.click\(\)/);
  assert.match(workspaceSource, /node\.webkitdirectory = true/);
  assert.match(workspaceSource, /type="file"/);
  assert.match(workspaceSource, /multiple/);
  assert.doesNotMatch(workspaceSource, /FileReader|arrayBuffer\(/);
});

test('shows bounded upload recovery with file and byte progress', () => {
  assert.match(workspaceSource, /progress\.uploadedFiles/);
  assert.match(workspaceSource, /progress\.uploadedBytes/);
  assert.match(workspaceSource, /Ponów brakujące pliki/);
  assert.match(workspaceSource, /Anuluj staging/);
  assert.match(workspaceSource, /MAX_IMAGE_SELECTION_FILES = 100_000/);
  assert.match(workspaceSource, /preparingFolder/);
  assert.match(workspaceSource, /waitForBrowserPaint\(\)/);
  assert.match(workspaceSource, /Analizowanie plików w folderze/);
  assert.match(styleSource, /\.imageSelectionSpinner/);
});

test('polls an active run with bounded duration and abortable requests', () => {
  assert.match(workspaceSource, /RUN_POLL_INTERVAL_MS = 2_000/);
  assert.match(workspaceSource, /RUN_POLL_REQUEST_TIMEOUT_MS = 10_000/);
  assert.match(workspaceSource, /RUN_POLL_MAX_DURATION_MS = 45 \* 60 \* 1_000/);
  assert.match(workspaceSource, /isPollableRunStatus\(activeRunStatus\)/);
  assert.match(
    workspaceSource,
    /getImageSelectionWithTimeout\(api, activeRunId\)/,
  );
  assert.match(workspaceSource, /new AbortController\(\)/);
  assert.match(workspaceSource, /window\.clearTimeout\(timerId\)/);
  assert.match(
    workspaceSource,
    /status === 'created' \|\| status === 'processing'/,
  );
});

test('reruns the current selector from immutable uploaded staging', () => {
  assert.match(workspaceSource, /api\.rerunImageSelection\(run\.id\)/);
  assert.match(
    workspaceSource,
    /Wznowiono selekcję od ostatniego trwałego checkpointu/,
  );
  assert.match(workspaceSource, /Przelicz ponownie załadowane zdjęcia/);
  assert.match(workspaceSource, /Ponowny upload nie był potrzebny/);
  assert.match(
    workspaceSource,
    /window\.localStorage\.setItem\(storageKey\(gameId\), result\.data\.run\.id\)/,
  );
  assert.match(workspaceSource, /run\.selectorFingerprint\.slice\(0, 12\)/);
});

test('isolates image selection state by active game and keeps four tiles responsive', () => {
  assert.match(catalogSource, /key=\{activeGame\.id\}/);
  assert.match(catalogSource, /gameId=\{activeGame\.id\}/);
  assert.match(
    styleSource,
    /grid-template-columns: repeat\(4, minmax\(0, 1fr\)\)/,
  );
  assert.match(
    styleSource,
    /grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/,
  );
  assert.match(styleSource, /\.imageSelectionWorkspace\s*\{[^}]*min-width: 0/s);
});

test('hands a verified output to the explicit import step without starting it', () => {
  assert.match(workspaceSource, /handoffImageSelection\(run\.id\)/);
  assert.match(workspaceSource, /Przekaż do Importu layoutów/);
  assert.match(workspaceSource, /run\.outputManifestSha256 === null/);
  assert.match(catalogSource, /section: 'imports'/);
  assert.match(catalogSource, /initialHandoff=/);
});

test('manual fallback uses one JPEG, bounded navigation and idempotent approval', () => {
  assert.match(manualModalSource, /accept="\.jpg,\.jpeg,image\/jpeg"/);
  assert.doesNotMatch(manualModalSource, /multiple/);
  assert.match(manualModalSource, /event\.key === 'ArrowLeft'/);
  assert.match(manualModalSource, /event\.key === 'ArrowRight'/);
  assert.match(manualModalSource, /event\.key === 'Enter' && !event\.repeat/);
  assert.match(manualModalSource, /approvalInFlightRef/);
  assert.match(manualModalSource, /idempotencyKey/);
  assert.match(manualModalSource, /continueImageSelectionWithoutImage/);
  assert.match(manualModalSource, /Brak zdjęcia dla layoutów/);
  assert.match(manualModalSource, /Dodaj opcjonalne zdjęcie/);
  assert.match(manualModalSource, /Zakres layoutów nierozpoznany/);
  assert.match(manualModalSource, /listImageSelectionGroupCandidates/);
  assert.match(manualModalSource, /pliki kandydatów/);
  assert.match(workspaceSource, /manualGroups\.length > 0/);
  assert.match(manualModalSource, /manualSelectionCandidateGallery/);
  assert.match(manualModalSource, /candidateFileUrl/);
  assert.match(workspaceSource, /listImageSelections/);
  assert.match(workspaceSource, /imageSelectionHistory/);
  assert.match(workspaceSource, /Pominięte grupy-duplikaty/);
  assert.match(workspaceSource, /refreshRunAfterManualApproval\(activeRunId\)/);
  assert.match(workspaceSource, /setRun\(result\.data\)/);
  assert.match(
    manualModalSource,
    /event\.key === 'ArrowRight'[^}]*navigate\(1\)/s,
  );
});

test('manual fallback exposes compact accessible controls and visible focus', () => {
  assert.match(manualModalSource, /aria-modal="true"/);
  assert.match(manualModalSource, /role="dialog"/);
  assert.match(manualModalSource, /Poprzedni wyjątek/);
  assert.match(manualModalSource, /Następny wyjątek/);
  assert.match(manualModalSource, /Początek zakresu/);
  assert.match(manualModalSource, /Koniec zakresu/);
  assert.match(styleSource, /\.manualSelectionDialog:focus-visible/);
  assert.match(
    styleSource,
    /max-height: calc\(100vh - 32px\)[^}]*overflow: hidden/s,
  );
});

test('job monitor exposes bounded image-selection counters and separate timings', () => {
  assert.match(jobMonitorSource, /job\.progress\.imageSelection/);
  assert.match(jobMonitorSource, /imageSelectionProgress\?\.groups/);
  assert.match(jobMonitorSource, /imageSelectionProgress\?\.selected/);
  assert.match(jobMonitorSource, /imageSelectionProgress\?\.manual/);
  assert.match(jobMonitorSource, /imageSelectionProgress\?\.errors/);
  assert.match(jobMonitorSource, /imageSelectionProgress\.verifications/);
  assert.match(
    jobMonitorSource,
    /imageSelectionProgress\.uploadDurationSeconds/,
  );
  assert.match(
    jobMonitorSource,
    /imageSelectionProgress\.processingDurationSeconds/,
  );
});

test('image selection workspace shows live progress and final aggregates', () => {
  assert.match(workspaceSource, /jobStatusLabel\(run\.job\.status\)/);
  assert.match(workspaceSource, /jobStageLabel\(run\.job\.progress\.stage\)/);
  assert.match(workspaceSource, /jobProgressLabel\(run\.job\)/);
  assert.match(workspaceSource, /jobProgressPercent\(run\.job\)/);
  assert.match(workspaceSource, /selectionProgress\?\.groups/);
  assert.match(workspaceSource, /selectionProgress\?\.selected/);
  assert.match(workspaceSource, /selectionProgress\?\.manual/);
  assert.match(workspaceSource, /Roboczo bez numerów/);
  assert.match(workspaceSource, /To licznik tymczasowy/);
  assert.match(workspaceSource, /Nierozpoznane zestawy/);
  assert.match(workspaceSource, /selectionProgress\?\.skipped/);
  assert.match(workspaceSource, /selectionProgress\?\.errors/);
  assert.match(workspaceSource, /selectionProgress\?\.verifications/);
  assert.match(workspaceSource, /uploadDurationSeconds/);
  assert.match(workspaceSource, /processingDurationSeconds/);
  assert.match(workspaceSource, /Szczegóły techniczne/);
  assert.match(styleSource, /\.imageSelectionRunProgress progress/);
});
