import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createEmptySymbolReviewSelection,
  createAllMatchingFilterSymbolReviewSelection,
  isSymbolReviewItemSelected,
  MAX_EXPLICIT_SYMBOL_REVIEW_SELECTION,
  selectVisibleSymbolReviewItems,
  selectedSymbolReviewCount,
  toggleSymbolReviewItem,
} from '../src/features/symbol-reviews/symbol-review-selection-state.ts';

function item(id, sequenceNumber = 1) {
  return {
    assignedSymbolCode: 'cherry',
    assignedSymbolId: 'symbol-1',
    assignedSymbolName: 'Cherry',
    boardStatus: 'pending',
    cellIndex: 0,
    columnIndex: 0,
    cropChecksumSha256: 'a'.repeat(64),
    cropSampleId: 'b'.repeat(64),
    geometryRevision: 0,
    hasGridIssue: false,
    id,
    importJobId: 'import-1',
    predictionSymbolCode: 'cherry',
    recognizedBoardId: 'board-1',
    reviewItemId: 'review-1',
    reviewState: 'pending',
    revision: 2,
    rowIndex: 0,
    sequenceNumber,
  };
}

test('selects only explicit items from the current page', () => {
  const first = item('cell-1', 1);
  const second = item('cell-2', 2);
  let selection = createEmptySymbolReviewSelection();

  selection = toggleSymbolReviewItem(selection, first).selection;
  selection = selectVisibleSymbolReviewItems(selection, [second]).selection;

  assert.equal(MAX_EXPLICIT_SYMBOL_REVIEW_SELECTION, 10_000);
  assert.equal(selectedSymbolReviewCount(selection), 2);
  assert.equal(isSymbolReviewItemSelected(selection, first), true);
  assert.equal(
    selection.targetsById['cell-1'].expectedCropSampleId,
    'b'.repeat(64),
  );
  assert.equal(
    selection.targetsById['cell-2'].expectedCropChecksumSha256,
    'a'.repeat(64),
  );
  assert.equal(selection.kind, 'explicit');
});

test('page-local selection never exceeds ten thousand exact targets', () => {
  const items = Array.from({ length: 10_001 }, (_, index) =>
    item(`cell-${index}`, index),
  );
  const result = selectVisibleSymbolReviewItems(
    createEmptySymbolReviewSelection(),
    items,
  );

  assert.equal(selectedSymbolReviewCount(result.selection), 10_000);
  assert.equal(result.rejectedCount, 1);
});

test('all-filter selection keeps only exclusions locally', () => {
  const first = item('cell-1', 1);
  const second = item('cell-2', 2);
  let selection = createAllMatchingFilterSymbolReviewSelection({
    catalogRevision: 7,
    gameId: 'game-1',
    matchedCount: 25_000,
    maxConfidence: 0.8,
    minConfidence: 0.5,
    state: 'pending',
    symbolId: 'symbol-1',
  });

  selection = toggleSymbolReviewItem(selection, first).selection;
  assert.equal(selection.kind, 'all_matching_filter');
  assert.equal(isSymbolReviewItemSelected(selection, first), false);
  assert.equal(isSymbolReviewItemSelected(selection, second), true);
  assert.equal(selectedSymbolReviewCount(selection), 24_999);
  assert.equal(selection.excludedIds.size, 1);
});
