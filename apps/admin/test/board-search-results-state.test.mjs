import assert from 'node:assert/strict';
import test from 'node:test';

import {
  activeBoardSearchResult,
  BOARD_SEARCH_LIMIT_MAX,
  boardSearchNeighbourIndexes,
  boardSearchResultIdentity,
  computeBoardCropTransform,
  createBoardSearchResultsState,
  moveBoardSearchResult,
  parseBoardCropQuad,
  parseBoardSearchLimit,
  reconcileBoardSearchResultsState,
} from '../src/features/board-search/board-search-results-state.ts';

const results = [
  { reviewItemId: 'one', sequenceNumber: 10 },
  { reviewItemId: 'two', sequenceNumber: 19 },
  { reviewItemId: 'three', sequenceNumber: 28 },
];

function fullResult(overrides) {
  return {
    assetMode: 'operational_review',
    boardChecksumSha256: 'a'.repeat(64),
    importJobId: 'job',
    recognizedBoardId: 'board',
    reviewItemId: 'review',
    score: {
      alternativeMatchCount: 0,
      exactMatchCount: 1,
      mismatchCount: 0,
      score: 50,
      unknownCount: 0,
      weightedAlternativeScore: 0,
    },
    sequenceNumber: 1,
    status: 'pending',
    ...overrides,
  };
}

test('moves one board result at a time without wrapping at either boundary', () => {
  let state = createBoardSearchResultsState(results);
  state = moveBoardSearchResult(state, 1);
  state = moveBoardSearchResult(state, 1);
  state = moveBoardSearchResult(state, 1);

  assert.equal(activeBoardSearchResult(state)?.reviewItemId, 'three');
  assert.equal(state.activeIndex, 2);

  state = moveBoardSearchResult(state, -1);
  assert.equal(activeBoardSearchResult(state)?.reviewItemId, 'two');
});

test('prefetches only existing immediate neighbours and tolerates an empty result set', () => {
  assert.deepEqual(
    boardSearchNeighbourIndexes(createBoardSearchResultsState(results)),
    [1],
  );
  assert.deepEqual(
    boardSearchNeighbourIndexes(
      moveBoardSearchResult(createBoardSearchResultsState(results), 1),
    ),
    [0, 2],
  );
  assert.equal(
    activeBoardSearchResult(createBoardSearchResultsState([])),
    null,
  );
  assert.deepEqual(
    boardSearchNeighbourIndexes(createBoardSearchResultsState([])),
    [],
  );
});

test('parseBoardSearchLimit accepts a positive integer within the technical limit', () => {
  assert.deepEqual(parseBoardSearchLimit('5'), { ok: true, value: 5 });
  assert.deepEqual(parseBoardSearchLimit('1'), { ok: true, value: 1 });
  assert.deepEqual(parseBoardSearchLimit(String(BOARD_SEARCH_LIMIT_MAX)), {
    ok: true,
    value: BOARD_SEARCH_LIMIT_MAX,
  });
  assert.deepEqual(parseBoardSearchLimit(' 10 '), { ok: true, value: 10 });
});

test('parseBoardSearchLimit rejects zero, negative, fractional, out-of-range and empty input', () => {
  assert.equal(parseBoardSearchLimit('0').ok, false);
  assert.equal(parseBoardSearchLimit('-1').ok, false);
  assert.equal(parseBoardSearchLimit('1.5').ok, false);
  assert.equal(
    parseBoardSearchLimit(String(BOARD_SEARCH_LIMIT_MAX + 1)).ok,
    false,
  );
  assert.equal(parseBoardSearchLimit('').ok, false);
  assert.equal(parseBoardSearchLimit('   ').ok, false);
  assert.equal(parseBoardSearchLimit('abc').ok, false);
});

test('boardSearchResultIdentity is stable across ranking position', () => {
  const a = fullResult({ sequenceNumber: 37 });
  const b = fullResult({ sequenceNumber: 37 });
  assert.equal(boardSearchResultIdentity(a), boardSearchResultIdentity(b));

  const differentChecksum = fullResult({
    boardChecksumSha256: 'b'.repeat(64),
    sequenceNumber: 37,
  });
  assert.notEqual(
    boardSearchResultIdentity(a),
    boardSearchResultIdentity(differentChecksum),
  );
});

test('reconcileBoardSearchResultsState keeps the previously selected board when it is still present', () => {
  const first = [
    fullResult({ sequenceNumber: 10 }),
    fullResult({ sequenceNumber: 19 }),
    fullResult({ sequenceNumber: 28 }),
  ];
  let state = createBoardSearchResultsState(first);
  state = moveBoardSearchResult(state, 1); // now on sequence 19

  const second = [
    fullResult({ sequenceNumber: 19 }),
    fullResult({ sequenceNumber: 28 }),
  ];
  const reconciled = reconcileBoardSearchResultsState(state, second);
  assert.equal(reconciled.activeIndex, 0);
  assert.equal(activeBoardSearchResult(reconciled)?.sequenceNumber, 19);
});

test('reconcileBoardSearchResultsState falls back to the first result when the selection drops out', () => {
  const first = [
    fullResult({ sequenceNumber: 10 }),
    fullResult({ sequenceNumber: 19 }),
  ];
  let state = createBoardSearchResultsState(first);
  state = moveBoardSearchResult(state, 1); // now on sequence 19

  const second = [fullResult({ sequenceNumber: 41 })];
  const reconciled = reconcileBoardSearchResultsState(state, second);
  assert.equal(reconciled.activeIndex, 0);
  assert.equal(activeBoardSearchResult(reconciled)?.sequenceNumber, 41);
});

test('reconcileBoardSearchResultsState resets to index 0 for an empty previous selection', () => {
  const empty = createBoardSearchResultsState([]);
  const reconciled = reconcileBoardSearchResultsState(empty, [
    fullResult({ sequenceNumber: 1 }),
  ]);
  assert.equal(reconciled.activeIndex, 0);
});

// --- parseBoardCropQuad --------------------------------------------------

function quad(points) {
  return points.map(([x, y]) => ({ x, y }));
}

test('parseBoardCropQuad extracts a valid sourceQuad', () => {
  const points = quad([
    [10, 20],
    [110, 20],
    [110, 80],
    [10, 80],
  ]);
  assert.deepEqual(parseBoardCropQuad({ sourceQuad: points }), points);
});

test('parseBoardCropQuad falls back to quad when sourceQuad is absent', () => {
  const points = quad([
    [0, 0],
    [50, 0],
    [50, 50],
    [0, 50],
  ]);
  assert.deepEqual(parseBoardCropQuad({ quad: points }), points);
});

test('parseBoardCropQuad returns null for anything that is not exactly a 4-point numeric quad', () => {
  assert.equal(parseBoardCropQuad(null), null);
  assert.equal(parseBoardCropQuad(undefined), null);
  assert.equal(parseBoardCropQuad('not an object'), null);
  assert.equal(parseBoardCropQuad({}), null);
  assert.equal(
    parseBoardCropQuad({ sourceQuad: quad([[0, 0], [1, 1], [2, 2]]) }),
    null,
  );
  assert.equal(
    parseBoardCropQuad({ sourceQuad: [{ x: 0 }, { x: 1 }, { x: 2 }, { x: 3 }] }),
    null,
  );
  assert.equal(
    parseBoardCropQuad({
      sourceQuad: [
        { x: 'nope', y: 0 },
        { x: 1, y: 1 },
        { x: 2, y: 2 },
        { x: 3, y: 3 },
      ],
    }),
    null,
  );
  assert.equal(
    parseBoardCropQuad({ sourceQuad: [null, null, null, null] }),
    null,
  );
});

// --- computeBoardCropTransform --------------------------------------------

test('computeBoardCropTransform pads the bounding box proportionally without distortion', () => {
  // A 100x60 board at (10, 20) inside a 1000x600 source image.
  const points = quad([
    [10, 20],
    [110, 20],
    [110, 80],
    [10, 80],
  ]);
  const transform = computeBoardCropTransform(points, 1000, 600);
  assert.ok(transform !== null);
  // padding = 20% of 100 = 20 horizontally, 20% of 60 = 12 vertically
  const paddedWidth = 100 + 2 * 20;
  const paddedHeight = 60 + 2 * 12;
  const cropX = 10 - 20;
  const cropY = 20 - 12;
  assert.equal(transform.aspectRatioWidth, paddedWidth);
  assert.equal(transform.aspectRatioHeight, paddedHeight);
  assert.equal(transform.imageWidthPercent, (1000 / paddedWidth) * 100);
  assert.equal(transform.imageHeightPercent, (600 / paddedHeight) * 100);
  assert.equal(transform.imageLeftPercent, (-cropX / paddedWidth) * 100);
  assert.equal(transform.imageTopPercent, (-cropY / paddedHeight) * 100);
});

test('computeBoardCropTransform returns null for a degenerate quad or non-positive image size', () => {
  const zeroWidth = quad([
    [10, 10],
    [10, 10],
    [10, 80],
    [10, 80],
  ]);
  assert.equal(computeBoardCropTransform(zeroWidth, 1000, 600), null);

  const validPoints = quad([
    [0, 0],
    [10, 0],
    [10, 10],
    [0, 10],
  ]);
  assert.equal(computeBoardCropTransform(validPoints, 0, 600), null);
  assert.equal(computeBoardCropTransform(validPoints, 1000, -1), null);
  assert.equal(computeBoardCropTransform(validPoints.slice(0, 3), 1000, 600), null);
});
