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

test('configures the global upload only through capabilities and range bounds', () => {
  assert.match(
    workspaceSource,
    /getSemiAutomaticImageSelectionCapabilities\(\)/,
  );
  assert.match(workspaceSource, /capabilities\?\.enabled !== true/);
  assert.match(workspaceSource, /Pierwsza plansza/);
  assert.match(workspaceSource, /Ostatnia plansza/);
  assert.match(workspaceSource, /Kolejność numeracji/);
  assert.match(workspaceSource, /fullRangeSize/);
  assert.match(workspaceSource, /Wybierz katalog źródłowy/);
  assert.match(workspaceSource, /Wybierz katalog docelowy/);
  assert.match(workspaceSource, /Sprawdzanie dostępności/);
});

test('uploads JPEGs to the global staging purpose with bounded recovery', () => {
  assert.match(actionsSource, /purpose: 'semi_automatic_selection'/);
  assert.match(actionsSource, /gameId: null/);
  assert.match(actionsSource, /MAX_UPLOAD_CONCURRENCY = 4/);
  assert.match(actionsSource, /MAX_FILE_ATTEMPTS = 3/);
  assert.match(actionsSource, /jpe\?g\$\/iu/);
  assert.match(actionsSource, /createSemiAutomaticImageSelection/);
  assert.match(workspaceSource, /Ponów brakujące pliki/);
  assert.match(workspaceSource, /Anuluj staging/);
  assert.match(workspaceSource, /uploadedFiles/);
  assert.match(workspaceSource, /uploadedBytes/);
});

test('polls one active run and hands terminal analysis to the review workspace', () => {
  assert.match(workspaceSource, /POLL_INTERVAL_MS = 2_000/);
  assert.match(workspaceSource, /POLL_MAX_DURATION_MS = 45 \* 60 \* 1_000/);
  assert.match(workspaceSource, /window\.setTimeout\(\(\) => void poll\(\)/);
  assert.match(workspaceSource, /Wstrzymaj po checkpointcie/);
  assert.match(workspaceSource, /Wznów analizę/);
  assert.match(workspaceSource, /Anuluj run/);
  assert.match(workspaceSource, /<SemiAutomaticSelectionReviewWorkspace/);
  assert.match(workspaceSource, /collectSemiAutomaticSourceFiles/);
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
