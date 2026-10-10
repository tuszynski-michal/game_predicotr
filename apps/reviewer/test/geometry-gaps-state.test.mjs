import assert from 'node:assert/strict';
import test from 'node:test';

import {
  GEOMETRY_GAPS_FILTERS,
  GEOMETRY_GAPS_PAGE_LIMIT,
  GEOMETRY_GAP_STATES_WITHOUT_EDITOR,
  allPartialPositionsHumanApproved,
  geometryGapPositionTarget,
  geometryGapsFilterCount,
  geometryGapsFilterLabel,
  geometryGapsListQuery,
  geometryImageStateLabel,
  geometryImageSummary,
  geometryImageTone,
  geometryImportErrorLabel,
  geometryPositionLabel,
  geometryPositionStateLabel,
  geometryPositionTone,
  geometrySourceStatusLabel,
  quadCentre,
  quadSvgPoints,
  shouldPrefetchNextPage,
  visibleGapImages,
} from '../src/features/operational-reviews/geometry-gaps-state.ts';

const position = (overrides) => ({
  humanApproved: false,
  positionIndex: 0,
  quad: null,
  reasonCode: null,
  recognizedBoardId: null,
  sequenceNumber: 1,
  state: 'ok',
  ...overrides,
});

test('filters are the four real-gap states behind the default "all" (decision 3)', () => {
  assert.deepEqual(GEOMETRY_GAPS_FILTERS, [
    'all',
    'incomplete_missing',
    'incomplete_partial',
    'import_failed',
    'no_source_geometry',
  ]);
  assert.deepEqual(GEOMETRY_GAPS_FILTERS.map(geometryGapsFilterLabel), [
    'Wszystkie braki',
    'Brakuje plansz',
    'Plansza częściowa',
    'Import nieudany',
    'Bez geometrii źródła',
  ]);
  // "Siatka niepotwierdzona" is a counter in the Admin, never a queue here.
  assert.equal(GEOMETRY_GAPS_FILTERS.includes('incomplete_uncertain'), false);
  assert.deepEqual([...GEOMETRY_GAP_STATES_WITHOUT_EDITOR].sort(), [
    'import_failed',
    'no_source_geometry',
  ]);
});

test('the list query sends gapsOnly for "all" and a single imageState otherwise', () => {
  assert.deepEqual(geometryGapsListQuery('g', 'all', null), {
    gameId: 'g',
    gapsOnly: true,
    limit: GEOMETRY_GAPS_PAGE_LIMIT,
  });
  assert.deepEqual(geometryGapsListQuery('g', 'import_failed', 'c2', 10), {
    afterCursor: 'c2',
    gameId: 'g',
    imageState: 'import_failed',
    limit: 10,
  });
  // Never both: the server answers 422 for the pair (TASK-0961).
  const query = geometryGapsListQuery('g', 'incomplete_partial', null);
  assert.equal('gapsOnly' in query, false);
});

test('filter counters come from the completeness report', () => {
  const report = {
    images: {
      complete: 5,
      importFailed: 3,
      incomplete: 51545,
      incompleteMissing: 1,
      incompletePartial: 0,
      incompleteUncertain: 51541,
      noSourceGeometry: 0,
      superseded: 199,
      total: 51749,
    },
  };
  assert.equal(geometryGapsFilterCount(report, 'all'), 4);
  assert.equal(geometryGapsFilterCount(report, 'incomplete_missing'), 1);
  assert.equal(geometryGapsFilterCount(report, 'import_failed'), 3);
  assert.equal(geometryGapsFilterCount(report, 'incomplete_partial'), 0);
  assert.equal(geometryGapsFilterCount(report, 'no_source_geometry'), 0);
});

test('state labels and tones follow the Admin diagnostics', () => {
  assert.equal(geometryImageStateLabel('incomplete_missing'), 'Brakuje plansz');
  assert.equal(geometryImageStateLabel('weird'), 'weird');
  assert.equal(geometryPositionStateLabel('deferred'), 'Siatka odroczona');
  assert.equal(
    geometryPositionLabel('deferred', 'incomplete_lattice'),
    'Siatka odroczona (niepełna siatka)',
  );
  assert.equal(geometryPositionLabel('missing', null), 'Brak siatki');
  assert.equal(
    geometryImportErrorLabel('IMAGE_STAGE_EXECUTION_FAILED'),
    'etap przetwarzania zakończył się błędem (IMAGE_STAGE_EXECUTION_FAILED)',
  );
  assert.equal(geometryImportErrorLabel('X_UNKNOWN'), 'X_UNKNOWN');
  assert.equal(geometrySourceStatusLabel('failed'), 'błąd');
  assert.equal(geometryPositionTone('ok'), 'ok');
  assert.equal(geometryPositionTone('partial'), 'warning');
  assert.equal(geometryPositionTone('missing'), 'danger');
  assert.equal(geometryPositionTone('superseded'), 'muted');
  assert.equal(geometryImageTone('incomplete_partial'), 'warning');
  assert.equal(geometryImageTone('import_failed'), 'danger');
});

test('the image summary shows the range and the expected boards', () => {
  assert.equal(
    geometryImageSummary({
      expectedBoardCount: 9,
      sequenceRangeEnd: 1008,
      sequenceRangeStart: 1000,
    }),
    'numery 1000–1008 · oczekiwane plansze: 9',
  );
  assert.equal(
    geometryImageSummary({
      expectedBoardCount: null,
      sequenceRangeEnd: null,
      sequenceRangeStart: null,
    }),
    'brak geometrii źródła, oczekiwana liczba plansz nieznana',
  );
});

test('quadSvgPoints returns null for anything but four finite points', () => {
  assert.equal(quadSvgPoints(null), null);
  assert.equal(quadSvgPoints(undefined), null);
  assert.equal(quadSvgPoints([{ x: 1, y: 2 }]), null);
  assert.equal(
    quadSvgPoints([
      { x: 1, y: 2 },
      { x: Number.NaN, y: 2 },
      { x: 3, y: 4 },
      { x: 5, y: 6 },
    ]),
    null,
  );
  assert.equal(
    quadSvgPoints([
      { x: 1, y: 2 },
      { x: Number.POSITIVE_INFINITY, y: 2 },
      { x: 3, y: 4 },
      { x: 5, y: 6 },
    ]),
    null,
  );
  assert.equal(
    quadSvgPoints([
      { x: 10, y: 20 },
      { x: 30, y: 20 },
      { x: 30, y: 40 },
      { x: 10, y: 40 },
    ]),
    '10,20 30,20 30,40 10,40',
  );
  assert.deepEqual(
    quadCentre([
      { x: 10, y: 20 },
      { x: 30, y: 20 },
      { x: 30, y: 40 },
      { x: 10, y: 40 },
    ]),
    { x: 20, y: 30 },
  );
});

test('an image whose every partial position is human approved is hidden by default (decision 8)', () => {
  const approved = {
    positions: [
      position({ state: 'ok' }),
      position({ humanApproved: true, positionIndex: 1, state: 'partial' }),
      position({ humanApproved: true, positionIndex: 2, state: 'partial' }),
    ],
  };
  const pending = {
    positions: [
      position({ humanApproved: true, positionIndex: 1, state: 'partial' }),
      position({ humanApproved: false, positionIndex: 2, state: 'partial' }),
    ],
  };
  const missing = { positions: [position({ state: 'missing' })] };
  const empty = { positions: [] };
  assert.equal(allPartialPositionsHumanApproved(approved), true);
  assert.equal(allPartialPositionsHumanApproved(pending), false);
  // Without a partial position the rule never applies.
  assert.equal(allPartialPositionsHumanApproved(missing), false);
  assert.equal(allPartialPositionsHumanApproved(empty), false);
  // A position without the flag (older responses) counts as not approved.
  assert.equal(
    allPartialPositionsHumanApproved({
      positions: [position({ humanApproved: undefined, state: 'partial' })],
    }),
    false,
  );

  const images = [approved, pending, missing];
  assert.deepEqual(visibleGapImages(images, false), [pending, missing]);
  assert.deepEqual(visibleGapImages(images, true), images);
});

test('the next page is fetched when at most three images remain', () => {
  assert.equal(shouldPrefetchNextPage(0, 25, true), false);
  assert.equal(shouldPrefetchNextPage(20, 25, true), false);
  assert.equal(shouldPrefetchNextPage(21, 25, true), true);
  assert.equal(shouldPrefetchNextPage(24, 25, true), true);
  // Everything fetched so far is hidden by the filter: fetch more.
  assert.equal(shouldPrefetchNextPage(0, 0, true), true);
  assert.equal(shouldPrefetchNextPage(24, 25, false), false);
});

test('the editing target is the grid-reviews row of the position: board first, then deferred slot', () => {
  const board = {
    pendingGeometryId: null,
    positionIndex: 3,
    reviewItemId: 'r3',
    slotKind: 'current_review',
  };
  const deferred = {
    pendingGeometryId: 'p3',
    positionIndex: 3,
    reviewItemId: null,
    slotKind: 'deferred_geometry',
  };
  const other = {
    pendingGeometryId: 'p5',
    positionIndex: 5,
    reviewItemId: null,
    slotKind: 'deferred_geometry',
  };
  assert.deepEqual(geometryGapPositionTarget([deferred, board, other], 3), {
    kind: 'reported',
    row: board,
  });
  assert.deepEqual(geometryGapPositionTarget([deferred, other], 3), {
    kind: 'deferred',
    pendingId: 'p3',
    row: deferred,
  });
  // No row for the position: nothing to edit (decision 5).
  assert.equal(geometryGapPositionTarget([board, other], 4), null);
  assert.equal(geometryGapPositionTarget([], 3), null);
  // A board without a review item and a slot without a pending id are not
  // targets either.
  assert.equal(
    geometryGapPositionTarget(
      [
        { ...board, reviewItemId: null },
        { ...deferred, pendingGeometryId: null },
      ],
      3,
    ),
    null,
  );
});
