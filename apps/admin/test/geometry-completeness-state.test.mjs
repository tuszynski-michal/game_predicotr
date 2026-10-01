import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
  INCOMPLETE_IMAGE_STATES,
  LISTED_IMAGE_STATES,
  errorCodeOf,
  formatPercent,
  geometryImageStateLabel,
  geometryImportErrorLabel,
  geometryPositionLabel,
  geometryPositionTone,
  geometryScopeImportId,
  geometrySectionState,
  geometrySourceStatusLabel,
  lowQualityErrorMessage,
  parseLowQualityThresholds,
  quadCentre,
  quadSvgPoints,
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
  for (const state of LISTED_IMAGE_STATES) {
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
  assert.equal(geometrySourceStatusLabel('processing'), 'w przetwarzaniu');
});

test('the default list holds the states that need attention; superseded is a filter of its own', () => {
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
  assert.deepEqual(
    [...LISTED_IMAGE_STATES],
    [...INCOMPLETE_IMAGE_STATES, 'superseded'],
  );
});

test('import errors keep their code and gain a Polish meaning when it is known', () => {
  assert.equal(
    geometryImportErrorLabel('IMAGE_STAGE_EXECUTION_FAILED'),
    'etap przetwarzania zakończył się błędem (IMAGE_STAGE_EXECUTION_FAILED)',
  );
  assert.match(
    geometryImportErrorLabel('IMAGE_STAGE_RESULT_INVALID'),
    /IMAGE_STAGE_RESULT_INVALID/,
  );
  assert.match(
    geometryImportErrorLabel('IMAGE_VIRTUAL_CELL_SOURCE_SUPPORT_INCOMPLETE'),
    /IMAGE_VIRTUAL_CELL_SOURCE_SUPPORT_INCOMPLETE/,
  );
  assert.equal(geometryImportErrorLabel('SOMETHING_NEW'), 'SOMETHING_NEW');
});

test('positions without a grid are marked danger, uncertain ones warning', () => {
  assert.equal(geometryPositionTone('ok'), 'ok');
  assert.equal(geometryPositionTone('superseded'), 'muted');
  assert.equal(geometryPositionTone('uncertain'), 'warning');
  assert.equal(geometryPositionTone('partial'), 'warning');
  assert.equal(geometryPositionTone('missing'), 'danger');
  assert.equal(geometryPositionTone('deferred'), 'danger');
});

test('quad helpers accept four finite points only', () => {
  const quad = [
    { x: 0, y: 0 },
    { x: 10, y: 0 },
    { x: 10, y: 20 },
    { x: 0, y: 20 },
  ];
  assert.equal(quadSvgPoints(quad), '0,0 10,0 10,20 0,20');
  assert.deepEqual(quadCentre(quad), { x: 5, y: 10 });
  assert.equal(quadSvgPoints(null), null);
  assert.equal(quadSvgPoints(undefined), null);
  assert.equal(quadSvgPoints(quad.slice(0, 3)), null);
  assert.equal(
    quadSvgPoints([...quad.slice(0, 3), { x: Number.NaN, y: 1 }]),
    null,
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

test('the panel mounts the section next to the missing-boards section', () => {
  assert.match(panelSource, /<GeometryCompletenessSection/);
  assert.ok(
    panelSource.indexOf('<MissingBoardsSection') <
      panelSource.indexOf('<GeometryCompletenessSection'),
  );
  assert.match(panelSource, /importActive=\{jobs\.some/);
});

test('the section uses the generated-client wrappers and runs the quality query only on demand', () => {
  assert.match(sectionSource, /api\.getImageGeometryCompleteness/);
  assert.match(sectionSource, /api\.listIncompleteGeometryImages/);
  assert.match(sectionSource, /api\.getImageGeometryLowQualityBoards/);
  // the preview is keyed by the source image, so every image has one (TASK-0808)
  assert.match(sectionSource, /api\.getImageGeometryCompletenessSourceAsset/);
  assert.doesNotMatch(sectionSource, /previewReviewItemId/);
  assert.doesNotMatch(sectionSource, /getOperationalImageReviewSourceAsset/);
  // the quality query is a button handler, never part of loading or polling
  const loadReports = sectionSource.slice(
    sectionSource.indexOf('const loadReports'),
    sectionSource.indexOf('const loadImages'),
  );
  assert.doesNotMatch(loadReports, /getImageGeometryLowQualityBoards/);
  assert.match(sectionSource, /onClick=\{\(\) => void run\(\)\}/);
  // polling is gated by an active import and only refreshes the counters
  assert.match(sectionSource, /if \(!importActive\) return;/);
  assert.match(sectionSource, /loadReports\(\{ silent: true \}\)/);
});
