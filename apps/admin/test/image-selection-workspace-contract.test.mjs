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

test('does not export a historical run into a folder reserved for a new upload', () => {
  const chooseOutputFolderSource = workspaceSource.slice(
    workspaceSource.indexOf('async function chooseOutputFolder()'),
    workspaceSource.indexOf('async function cancelUpload()'),
  );
  const startUploadSource = workspaceSource.slice(
    workspaceSource.indexOf('async function startUpload('),
    workspaceSource.indexOf('async function chooseFolder('),
  );

  assert.match(
    chooseOutputFolderSource,
    /pendingOutputDirectoryRef\.current = directory/,
  );
  assert.doesNotMatch(
    chooseOutputFolderSource,
    /outputDirectoryBindingRef\.current|outputDirectoryStore\.save/,
  );
  assert.match(
    startUploadSource,
    /if \(!result\.ok\)[\s\S]*outputDirectoryBindingRef\.current = \{[\s\S]*runId: result\.created\.run\.id/,
  );
  assert.match(
    workspaceSource,
    /outputDirectoryBindingRef\.current\?\.runId !== activeRunId/,
  );
  assert.match(
    workspaceSource,
    /if \(outputBinding\?\.runId !== activeRunId\)/,
  );
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
  assert.match(
    workspaceSource,
    /api\.rerunImageSelection\(run\.id, \{\s*firstSequenceNumber:/,
  );
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
  assert.match(
    workspaceSource,
    /formatSelectorVersion\(run\.selectorVersion\)/,
  );
  assert.match(workspaceSource, /fast-image-selector-/);
});

test('history hides cancelled, failed and incomplete terminal runs', () => {
  assert.match(
    workspaceSource,
    /visibleImageSelectionRuns\(result\.data\.items\)/,
  );
  assert.match(workspaceSource, /isVisibleImageSelectionRun\(result\.data\)/);
  assert.match(
    workspaceSource,
    /window\.localStorage\.removeItem\(storageKey\(gameId\)\)/,
  );
});

test('history labels identify a process by short date, engine and sequence range', () => {
  assert.match(workspaceSource, /year: '2-digit'/);
  assert.match(workspaceSource, /run\.sequenceRangeStart/);
  assert.match(workspaceSource, /run\.sequenceRangeEnd/);
  assert.match(workspaceSource, /`seq \$\{run\.sequenceRangeStart/);
  assert.doesNotMatch(
    workspaceSource,
    /return `\$\{created\} · \$\{formatSelectorVersion\(run\.selectorVersion\)\} · \$\{jobStatusLabel/,
  );
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
  assert.match(workspaceSource, /Przekaż do Importu plansz/);
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
  assert.match(manualModalSource, /Brak zdjęcia dla plansz/);
  assert.match(manualModalSource, /Dodaj opcjonalne zdjęcie/);
  assert.match(manualModalSource, /Zakres plansz nierozpoznany/);
  assert.match(manualModalSource, /listImageSelectionGroupCandidates/);
  assert.match(manualModalSource, /pliki kandydatów/);
  assert.match(workspaceSource, /manualGroups\.length > 0/);
  assert.match(manualModalSource, /manualSelectionCandidateGallery/);
  assert.match(manualModalSource, /candidateFileUrl/);
  assert.match(
    manualModalSource,
    /\/api\/v1\/admin\/image-selections\/\$\{encodeURIComponent\(runId\)\}/,
  );
  assert.doesNotMatch(
    manualModalSource,
    /\$\{apiBaseUrl\.replace\([^\n]+\}\/admin\/image-selections/,
  );
  assert.match(workspaceSource, /listImageSelections/);
  assert.match(workspaceSource, /imageSelectionHistory/);
  assert.match(workspaceSource, /Pominięte grupy-duplikaty/);
  assert.match(workspaceSource, /refreshRunAfterManualApproval\(activeRunId\)/);
  assert.match(workspaceSource, /setRun\(result\.data\)/);
  assert.match(
    manualModalSource,
    /event\.key === 'ArrowRight'[^}]*approveCurrent\(\)/s,
  );
  assert.match(manualModalSource, /defaultManualCandidateIndex/);
  assert.match(manualModalSource, /nextUnresolvedManualIndex/);
  assert.match(manualModalSource, /Wybrane: \{decisionCounts\.selected\}/);
  assert.match(manualModalSource, /discardDuplicateImageSelectionGroup/);
  assert.match(manualModalSource, /Odrzuć jako duplikat/);
  assert.match(manualModalSource, /IMAGE_SELECTION_RANGE_CONFLICT/);
  assert.match(manualModalSource, /Odrzuć duplikat i dalej/);
  assert.match(manualModalSource, /duplicateRangeConflict\.idempotencyKey/);
  assert.match(manualModalSource, /skipped_existing_range/);
  assert.match(
    workspaceSource,
    /groups\.filter\(\(group\) => group\.id !== updated\.id\)/,
  );
  assert.match(workspaceSource, /bindOutputDirectoryForReview\(run\.id\)/);
  assert.match(workspaceSource, /restoreOutputDirectory/);
  const bindingSource = workspaceSource.slice(
    workspaceSource.indexOf('async function bindOutputDirectoryForReview('),
    workspaceSource.indexOf('async function openAutomaticVerification()'),
  );
  assert.doesNotMatch(bindingSource, /saveFinalizedImageSelectionGroups/);
  assert.doesNotMatch(bindingSource, /loadImageSelectionGroupsAfter/);
  assert.match(workspaceSource, /progressiveSaveEnabledRef\.current = false/);
  assert.match(manualModalSource, /const outputError = await onGroupUpdated/);
  assert.match(manualModalSource, /plik nie trafił do folderu/);
  assert.match(
    manualModalSource,
    /Poczekaj, aż galeria wybierze domyślne zdjęcie/,
  );
});

test('separates image choice from range choice and supports reversible rejection', () => {
  assert.match(workspaceSource, /Wybierz zdjęcie/);
  assert.match(workspaceSource, /Ustal grupę/);
  assert.match(workspaceSource, /mode="range"/);
  assert.match(workspaceSource, /mode="rejected"/);
  assert.match(manualModalSource, /confirmImageSelectionGroupRange/);
  assert.match(manualModalSource, /candidateId: draftForApproval\.candidateId/);
  assert.match(manualModalSource, /rangeStart \+ 8/);
  assert.match(manualModalSource, /Koniec zakresu \(opcjonalnie\)/);
  assert.doesNotMatch(
    manualModalSource,
    /disabled=\{rangeMode \|\| rejectedMode\}/,
  );
  assert.match(manualModalSource, /rejectImageSelectionReviewGroup/);
  assert.match(manualModalSource, /restoreRejectedImageSelectionGroup/);
  assert.match(manualModalSource, /Odrzuć grupę/);
  assert.match(manualModalSource, /Przywróć do kolejki/);
});

test('manual fallback exposes compact accessible controls and visible focus', () => {
  assert.match(manualModalSource, /aria-modal="true"/);
  assert.match(manualModalSource, /role="dialog"/);
  assert.match(manualModalSource, /Poprzedni wyjątek/);
  assert.match(manualModalSource, /Zatwierdź i przejdź do następnego wyjątku/);
  assert.match(manualModalSource, /Początek zakresu/);
  assert.match(manualModalSource, /Koniec zakresu/);
  assert.match(styleSource, /\.manualSelectionDialog:focus-visible/);
  assert.match(
    styleSource,
    /max-height: calc\(100vh - 32px\)[^}]*overflow: hidden/s,
  );
});

test('manual gallery scrolls and opens a fullscreen preview with one zoom level', () => {
  assert.match(manualModalSource, /manualSelectionCandidateGallerySummary/);
  assert.match(manualModalSource, /przewiń listę, aby zobaczyć wszystkie/);
  assert.match(manualModalSource, /tabIndex=\{0\}/);
  assert.match(manualModalSource, /manualSelectionFullscreenOverlay/);
  assert.match(manualModalSource, /Otwórz pełny podgląd zdjęcia/);
  assert.match(manualModalSource, /previewZoomed \? 'Dopasuj' : 'Powiększ'/);
  assert.match(manualModalSource, /Zamknij pełny podgląd/);
  assert.match(
    styleSource,
    /\.manualSelectionCandidateGallery\s*\{[^}]*overflow-y: auto[^}]*scrollbar-gutter: stable/s,
  );
  assert.match(styleSource, /\.manualSelectionFullscreenPreviewZoomed/);
});

test('automatically selected groups can be inspected without mutating the run', () => {
  assert.match(
    workspaceSource,
    /loadAutomaticallySelectedImageSelectionGroups/,
  );
  assert.match(workspaceSource, /Weryfikuj wybory algorytmu/);
  assert.match(workspaceSource, /mode="automatic-verification"/);
  assert.match(manualModalSource, /mode === 'automatic-verification'/);
  assert.match(manualModalSource, /Wybór algorytmu/);
  assert.match(manualModalSource, /Ten tryb niczego nie zmienia w jobie/);
  assert.match(
    manualModalSource,
    /if \(verificationMode\) navigate\(1\);\s*else void approveCurrent\(\);/,
  );
  assert.match(styleSource, /\.manualSelectionCandidateAlgorithm/);
  assert.match(styleSource, /\.manualSelectionAlgorithmBadge/);
});

test('range audit distinguishes OCR suggestions from strong positional proof', () => {
  assert.match(manualModalSource, /RangeProofSummary/);
  assert.match(manualModalSource, /Mocny dowód OCR/);
  assert.match(manualModalSource, /Sugestia OCR do kontroli/);
  assert.match(manualModalSource, /rangeLabelObservations/);
  assert.match(manualModalSource, /suggestedRangeStart/);
  assert.match(manualModalSource, /poz\. \$\{item\.positionIndex \+ 1\}/);
  assert.match(styleSource, /\.manualSelectionRangeProof/);
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
  assert.match(workspaceSource, /Wybrane grupy/);
  assert.match(workspaceSource, /Do wyboru zdjęcia/);
  assert.match(workspaceSource, /Do ustalenia zakresu/);
  assert.match(workspaceSource, /osobna kolejka nierozpoznanych zakresów/);
  assert.match(workspaceSource, /selectionProgress\?\.skipped/);
  assert.match(workspaceSource, /selectionProgress\?\.errors/);
  assert.match(workspaceSource, /selectionProgress\?\.verifications/);
  assert.match(workspaceSource, /uploadDurationSeconds/);
  assert.match(workspaceSource, /processingDurationSeconds/);
  assert.match(workspaceSource, /Szczegóły techniczne/);
  assert.match(styleSource, /\.imageSelectionRunProgress progress/);
});
