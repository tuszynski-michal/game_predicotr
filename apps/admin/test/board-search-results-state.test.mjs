import assert from 'node:assert/strict';
import test from 'node:test';

import {
  activeBoardSearchResult,
  BOARD_SEARCH_LIMIT_MAX,
  boardSearchNeighbourIndexes,
  boardSearchResultIdentity,
  createBoardSearchResultsState,
  moveBoardSearchResult,
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
