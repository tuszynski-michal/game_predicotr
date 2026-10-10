import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
  INCOMPLETE_IMAGE_STATES,
  errorCodeOf,
  formatPercent,
  formatSequenceNumbers,
  geometryGapCounts,
  geometryGateReasonLabel,
  geometryImageStateLabel,
  geometryPositionLabel,
  geometryScopeImportId,
  geometrySectionState,
  lowQualityErrorMessage,
  parseLowQualityThresholds,
} from '../src/features/imports/geometry-completeness-state.ts';

const sectionSource = readFileSync(
  new URL(
    '../src/features/imports/geometry-completeness-section.tsx',
    import.meta.url,
  ),
  'utf8',
);
const panelSource = readFileSync(
  new URL(
    '../src/features/imports/image-folder-import-panel.tsx',
    import.meta.url,
  ),
  'utf8',
);
const launcherSource = readFileSync(
  new URL(
    '../src/features/reviewer-access/reviewer-access-launcher.tsx',
    import.meta.url,
  ),
  'utf8',
);

const base = {
  error: null,
  hasStaleData: false,
  incompleteImages: 0,
  loading: false,
  totalImages: 0,
};

test('section state: loading wins, then error without stale data', () => {
  assert.equal(geometrySectionState({ ...base, loading: true }), 'loading');
  assert.equal(
    geometrySectionState({ ...base, error: 'boom', totalImages: 5 }),
    'error',
  );
  assert.equal(
    geometrySectionState({
      ...base,
      error: 'boom',
      hasStaleData: true,
      incompleteImages: 1,
      totalImages: 5,
    }),
    'incomplete',
  );
});

test('section state: empty game, all complete and incomplete lists', () => {
  assert.equal(geometrySectionState(base), 'no-images');
  assert.equal(
    geometrySectionState({ ...base, totalImages: 10 }),
    'all-complete',
  );
  assert.equal(
    geometrySectionState({ ...base, incompleteImages: 3, totalImages: 10 }),
    'incomplete',
  );
});

test('every image and position state has a Polish label', () => {
  for (const state of [...INCOMPLETE_IMAGE_STATES, 'superseded']) {
    assert.notEqual(geometryImageStateLabel(state), state);
  }
  assert.equal(geometryImageStateLabel('complete'), 'Kompletne');
  assert.equal(geometryImageStateLabel('import_failed'), 'Import nieudany');
  assert.equal(
    geometryImageStateLabel('superseded'),
    'Zastąpione nowszym importem',
  );
  assert.match(geometryPositionLabel('superseded', null), /^Zastąpiona/);
  assert.equal(geometryImageStateLabel('future_state'), 'future_state');
  assert.equal(geometryPositionLabel('missing', null), 'Brak siatki');
  assert.equal(
    geometryPositionLabel('deferred', 'residual_too_high'),
    'Siatka odroczona (zbyt duży błąd dopasowania)',
  );
  assert.equal(
    geometryPositionLabel('deferred', 'new_reason'),
    'Siatka odroczona (new_reason)',
  );
});

test('the incomplete states never include superseded images', () => {
  assert.deepEqual(
    [...INCOMPLETE_IMAGE_STATES],
    [
      'incomplete_missing',
      'incomplete_partial',
      'incomplete_uncertain',
      'import_failed',
      'no_source_geometry',
    ],
  );
  assert.ok(!INCOMPLETE_IMAGE_STATES.includes('superseded'));
});

test('heading counters split real gaps from unconfirmed grids (TASK-0964)', () => {
  // Mumie: 4 real gaps, 51 541 automatic grids without manual approval.
  assert.deepEqual(
    geometryGapCounts({
      importFailed: 0,
      incompleteMissing: 1,
      incompletePartial: 1,
      incompleteUncertain: 51_541,
      noSourceGeometry: 2,
    }),
    { realGaps: 4, unconfirmed: 51_541 },
  );
  assert.deepEqual(
    geometryGapCounts({
      importFailed: 3,
      incompleteMissing: 0,
      incompletePartial: 0,
      incompleteUncertain: 0,
      noSourceGeometry: 0,
    }),
    { realGaps: 3, unconfirmed: 0 },
  );
});

test('low-quality thresholds default to 80 % and 5 cells and convert percent to a fraction', () => {
  assert.deepEqual(parseLowQualityThresholds('80', '5'), {
    maxConfidence: 0.8,
    minCells: 5,
    ok: true,
  });
  assert.deepEqual(parseLowQualityThresholds(' 62,5 ', ' 3 '), {
    maxConfidence: 0.625,
    minCells: 3,
    ok: true,
  });
  assert.deepEqual(parseLowQualityThresholds('0', '15'), {
    maxConfidence: 0,
    minCells: 15,
    ok: true,
  });
  assert.deepEqual(parseLowQualityThresholds('100', '1'), {
    maxConfidence: 1,
    minCells: 1,
    ok: true,
  });
});

test('low-quality thresholds reject out-of-range or malformed input', () => {
  for (const [percent, cells] of [
    ['', '5'],
    ['abc', '5'],
    ['-1', '5'],
    ['100.5', '5'],
    ['80', ''],
    ['80', '0'],
    ['80', '16'],
    ['80', '2.5'],
    ['80', '-3'],
  ]) {
    const result = parseLowQualityThresholds(percent, cells);
    assert.equal(result.ok, false, `${percent}/${cells}`);
    assert.equal(typeof result.error, 'string');
  }
});

test('low-quality errors map the timeout code to an operator hint', () => {
  assert.match(
    lowQualityErrorMessage('IMAGE_GEOMETRY_LOW_QUALITY_TIMEOUT'),
    /Zawęź/,
  );
  assert.equal(
    lowQualityErrorMessage(null),
    'Nie udało się sprawdzić jakości symboli.',
  );
  assert.equal(errorCodeOf({ code: 'X', message: 'm' }), 'X');
  assert.equal(errorCodeOf({ message: 'm' }), null);
  assert.equal(errorCodeOf(null), null);
  assert.equal(formatPercent(0.8), '80%');
  assert.equal(formatPercent(0.625), '62,5%');
});

test('scope resolves to an import id only for a known selected import', () => {
  const imports = [{ id: 'job-1', label: 'Import 1' }];
  assert.equal(geometryScopeImportId('game', 'job-1', imports), undefined);
  assert.equal(geometryScopeImportId('import', 'job-1', imports), 'job-1');
  assert.equal(geometryScopeImportId('import', 'gone', imports), undefined);
  assert.equal(geometryScopeImportId('import', '', imports), undefined);
});

test('grid diagnostics belong to correction while missing boards stay in import', () => {
  assert.doesNotMatch(panelSource, /GeometryCompletenessSection/);
  assert.match(panelSource, /<MissingBoardsSection/);
  assert.match(launcherSource, /<GeometryCompletenessSection/);
  assert.match(launcherSource, /key=\{gameId\}/);
  assert.match(launcherSource, /importActive=\{jobs\.some/);
  assert.match(sectionSource, /Diagnostyka siatek zdjęć/);
  assert.match(
    sectionSource,
    /W V3\s+poprawne\s+pełne\s+siatki\s+są\s+cięte\s+automatycznie/,
  );
});

test('the section no longer lists photos, previews grids or edits gate exceptions (TASK-0964)', () => {
  assert.doesNotMatch(sectionSource, /GeometryImageItem/);
  assert.doesNotMatch(sectionSource, /GeometryGateControls/);
  assert.doesNotMatch(sectionSource, /listIncompleteGeometryImages/);
  assert.doesNotMatch(sectionSource, /getImageGeometryCompletenessSourceAsset/);
  assert.doesNotMatch(sectionSource, /setSourceImageGeometryException/);
  assert.doesNotMatch(sectionSource, /withdrawSourceImageGeometryException/);
  assert.doesNotMatch(sectionSource, /Dopuść wyjątkiem/);
  assert.doesNotMatch(sectionSource, /<svg|<polygon/);
  assert.doesNotMatch(sectionSource, /reviewer-local-start/);
  assert.doesNotMatch(sectionSource, /reviewer-local-window/);
  assert.match(sectionSource, /Otwórz braki w Reviewerze/);
  assert.match(sectionSource, /onClick=\{onOpenReviewer\}/);
  assert.match(sectionSource, /realnymi brakami/);
  assert.match(sectionSource, /z niepotwierdzoną siatką/);
});

test('whole-image gate copy does not claim that every V3 crop is unavailable', () => {
  assert.match(
    geometryGateReasonLabel('SOURCE_IMAGE_GEOMETRY_INCOMPLETE'),
    /w V3 poprawne pełne siatki mogą być już dostępne/,
  );
});

test('the section uses the generated-client wrappers and runs the quality query only on demand', () => {
  assert.match(sectionSource, /api\.getImageGeometryCompleteness/);
  assert.match(sectionSource, /api\.getImageGeometryLowQualityBoards/);
  // the quality query is a button handler, never part of loading or polling
  const loadReports = sectionSource.slice(
    sectionSource.indexOf('const loadReports'),
    sectionSource.indexOf('// Only the counters are polled'),
  );
  assert.doesNotMatch(loadReports, /getImageGeometryLowQualityBoards/);
  assert.match(sectionSource, /onClick=\{\(\) => void run\(\)\}/);
  // polling is gated by an active import and only refreshes the counters
  assert.match(sectionSource, /if \(!importActive\) return;/);
  assert.match(sectionSource, /loadReports\(\{ silent: true \}\)/);
});

test('the import report lists replaced and skipped sequences (D-543)', () => {
  assert.equal(formatSequenceNumbers([], 0), '—');
  assert.equal(formatSequenceNumbers([100, 101], 2), '#100, #101');
  assert.equal(formatSequenceNumbers([100, 104], 5), '#100, #104 i jeszcze 3');
  assert.match(sectionSource, /<dt>Zastąpione sekwencje<\/dt>/);
  assert.match(sectionSource, /<dt>Pominięte — sekwencja ma właściciela<\/dt>/);
  assert.match(sectionSource, /importReport\?\.sequenceOwnership \?\? null/);
});
