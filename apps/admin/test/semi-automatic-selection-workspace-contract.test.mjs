import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const workspaceSource = await readFile(
  new URL(
    '../src/features/semi-automatic-image-selection/semi-automatic-selection-workspace.tsx',
    import.meta.url,
  ),
  'utf8',
);
const actionsSource = await readFile(
  new URL(
    '../src/features/semi-automatic-image-selection/semi-automatic-selection-actions.ts',
    import.meta.url,
  ),
  'utf8',
);
const reviewSource = await readFile(
  new URL(
    '../src/features/semi-automatic-image-selection/semi-automatic-selection-review.ts',
    import.meta.url,
  ),
  'utf8',
);
const reviewWorkspaceSource = await readFile(
  new URL(
    '../src/features/semi-automatic-image-selection/semi-automatic-selection-review-workspace.tsx',
    import.meta.url,
  ),
  'utf8',
);
const v7ReviewWorkspaceSource = await readFile(
  new URL(
    '../src/features/semi-automatic-image-selection/v7-selection-review-workspace.tsx',
    import.meta.url,
  ),
  'utf8',
);
const catalogSource = await readFile(
  new URL('../src/features/catalog/catalog-workspace.tsx', import.meta.url),
  'utf8',
);
const navigationSource = await readFile(
  new URL('../src/features/catalog/admin-navigation-state.ts', import.meta.url),
  'utf8',
);
const styleSource = await readFile(
  new URL('../src/app/globals.css', import.meta.url),
  'utf8',
);

test('adds a standalone semi-automatic workspace rather than a game section', () => {
  assert.match(catalogSource, /id: 'semi-automatic-image-selection'/);
  assert.match(catalogSource, /<SemiAutomaticSelectionWorkspace/);
  assert.match(navigationSource, /'semi-automatic-image-selection'/);
  assert.match(workspaceSource, /Niezależnie od gry · lokalnie/);
  assert.doesNotMatch(workspaceSource, /gameId=/);
});

test('configures the direct local source through capabilities and range bounds', () => {
  assert.match(
    workspaceSource,
    /getSemiAutomaticImageSelectionCapabilities\(\)/,
  );
  assert.match(workspaceSource, /capabilities\.v7\.startEnabled/);
  assert.match(workspaceSource, /Pierwszy zakres w nagraniu/);
  assert.match(workspaceSource, /Ostatni zakres w nagraniu/);
  assert.match(workspaceSource, /Kolejność numeracji/);
  assert.match(workspaceSource, /Tryb pracy/);
  assert.match(workspaceSource, /Styl obramowania/);
  assert.match(workspaceSource, /V7 czeka na odbiór/);
  assert.match(workspaceSource, /deriveV7OutputDirectory/);
  assert.match(workspaceSource, /fullRangeSize/);
  assert.match(workspaceSource, /Wybierz katalog źródłowy/);
  assert.match(workspaceSource, /Sprawdzanie dostępności/);
});

test('builds only the V7 request for a new run and keeps legacy payload separate', () => {
  assert.match(workspaceSource, /createV7SelectionFromLocalSource/);
  assert.match(actionsSource, /createV7SelectionPayload/);
  assert.match(actionsSource, /mode: 'selection'/);
  assert.match(
    workspaceSource,
    /V7 jest zablokowane: \{capabilities\.v7\.reason\}/,
  );
});

test('starts selection from a metadata manifest without creating browser staging', () => {
  assert.match(actionsSource, /selectSemiAutomaticImageSelectionSourceFolder/);
  assert.match(actionsSource, /selectionToken: input\.source\.selectionToken/);
  assert.match(actionsSource, /listSemiAutomaticImageSelectionSources/);
  assert.match(workspaceSource, /createV7SelectionFromLocalSource/);
  assert.match(workspaceSource, /Źródła nie będą kopiowane do stagingu/);
  assert.doesNotMatch(workspaceSource, /createBrowserImageSelection/);
  assert.doesNotMatch(workspaceSource, /uploadBrowserImageSelectionFile/);
  assert.doesNotMatch(workspaceSource, /Ponów brakujące pliki/);
  assert.doesNotMatch(workspaceSource, /Anuluj staging/);
});

test('polls one active run and hands terminal analysis to the review workspace', () => {
  assert.match(workspaceSource, /POLL_INTERVAL_MS = 2_000/);
  assert.match(workspaceSource, /POLL_MAX_DURATION_MS = 45 \* 60 \* 1_000/);
  assert.match(workspaceSource, /window\.setTimeout\(\(\) => void poll\(\)/);
  assert.match(workspaceSource, /Wstrzymaj po checkpointcie/);
  assert.match(workspaceSource, /Wznów analizę/);
  assert.match(workspaceSource, /Anuluj run/);
  assert.match(workspaceSource, /<SemiAutomaticSelectionReviewWorkspace/);
  assert.match(workspaceSource, /run\.workflowMode !== 'v7_selection'/);
  assert.match(workspaceSource, /pickSemiAutomaticOutputDirectory/);
  assert.match(workspaceSource, /Wskaż katalog wyniku historycznego/);
  assert.match(workspaceSource, /<V7SelectionReviewWorkspace/);
  assert.match(workspaceSource, /loadSemiAutomaticReviewSourceFiles/);
});

test('keeps scan, sequence and exact neighbour preview cursors durable and separate', async () => {
  const storageSource = await readFile(
    new URL(
      '../src/features/semi-automatic-image-selection/semi-automatic-selection-output-storage.ts',
      import.meta.url,
    ),
    'utf8',
  );
  assert.match(storageSource, /scanSourceIndex/);
  assert.match(storageSource, /sequenceExpectedIndex/);
  assert.match(storageSource, /viewSourceIndex/);
  assert.match(
    storageSource,
    /outputDirectory: SemiAutomaticOutputDirectoryHandle \| null/,
  );
  assert.match(
    storageSource,
    /sequenceExpectedIndex:\s*value\.sequenceExpectedIndex \?\? value\.activeExpectedIndex/,
  );
  assert.match(v7ReviewWorkspaceSource, /PODGLĄD SĄSIADÓW V7/);
  assert.match(v7ReviewWorkspaceSource, /viewSourceIndex: sourceIndex/);
  assert.match(v7ReviewWorkspaceSource, /const persistView = useCallback/);
  assert.match(v7ReviewWorkspaceSource, /scrollLeft: view\.scrollLeft/);
  assert.match(
    v7ReviewWorkspaceSource,
    /useManualImageViewer\([\s\S]*persistView/,
  );
  assert.match(
    workspaceSource,
    /const \[restoreComplete, setRestoreComplete\]/,
  );
  assert.match(
    workspaceSource,
    /run\.workflowMode === 'v7_selection' &&\s*restoreComplete/,
  );
  assert.match(
    v7ReviewWorkspaceSource,
    /podgląd nie zmienia reprezentanta ani[\s\S]*kursora sekwencji/,
  );
});

test('reviews a complete range snapshot and locks source editing to one target range', () => {
  assert.match(reviewSource, /loadAllSemiAutomaticSelectionRanges/);
  assert.match(reviewSource, /afterExpectedIndex/);
  assert.match(reviewSource, /item\.expectedIndex !== ranges\.length/);
  assert.match(reviewSource, /manualEditSourceStartIndex/);
  assert.match(reviewSource, /sourceIndex \+ 1/);
  assert.match(reviewSource, /replaceOwnedOutputBytes/);
  assert.match(reviewSource, /sourceIndex: source\.sourceIndex/);
  assert.match(reviewWorkspaceSource, /REVIEW MODE/);
  assert.match(reviewWorkspaceSource, /EDIT SOURCE MODE/);
  assert.match(reviewWorkspaceSource, /<ManualImageViewer/);
  assert.match(reviewWorkspaceSource, /initialUi\?\.zoomPercent/);
  assert.match(reviewWorkspaceSource, /viewer\.imageViewportRef\.current/);
  assert.match(reviewWorkspaceSource, /isFormInteractionTarget/);
  assert.match(reviewWorkspaceSource, /event\.key === 'Enter'/);
  assert.match(reviewWorkspaceSource, /Zatwierdź i zapisz/);
  assert.match(
    reviewWorkspaceSource,
    /prepareSemiAutomaticSelectionOutputReview/,
  );
  assert.doesNotMatch(
    reviewWorkspaceSource,
    /synchronizeSemiAutomaticSelectionOutput/,
  );
  assert.match(reviewWorkspaceSource, /event\.key\.toLowerCase\(\) === 'f'/);
  assert.match(reviewWorkspaceSource, /event\.key === 'Escape'/);
  assert.match(reviewWorkspaceSource, /Luka — wybierz zdjęcie/);
});

test('uses the established Admin visual system with responsive run progress', () => {
  assert.match(styleSource, /\.semiAutomaticSelectionWorkspace/);
  assert.match(styleSource, /\.semiAutomaticSelectionRunProgress progress/);
  assert.match(styleSource, /\.semiAutomaticSelectionRun dl/);
  assert.match(
    styleSource,
    /@media \(max-width: 860px\)[\s\S]*semiAutomaticSelectionRunBody/,
  );
});
