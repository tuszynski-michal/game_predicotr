import assert from 'node:assert/strict';
import test from 'node:test';

import {
  activeBoardSearchResult,
  boardSearchNeighbourIndexes,
  createBoardSearchResultsState,
  moveBoardSearchResult,
} from '../src/features/board-search/board-search-results-state.ts';

const results = [
  { reviewItemId: 'one', sequenceNumber: 10 },
  { reviewItemId: 'two', sequenceNumber: 19 },
  { reviewItemId: 'three', sequenceNumber: 28 },
];

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
