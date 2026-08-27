import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createEmptySymbolReviewSelection,
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

test('selects only explicit items from the current five-hundred-item page', () => {
  const first = item('cell-1', 1);
  const second = item('cell-2', 2);
  let selection = createEmptySymbolReviewSelection();

  selection = toggleSymbolReviewItem(selection, first).selection;
  selection = selectVisibleSymbolReviewItems(selection, [second]).selection;

  assert.equal(MAX_EXPLICIT_SYMBOL_REVIEW_SELECTION, 500);
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

test('page-local selection never exceeds five hundred exact targets', () => {
  const items = Array.from({ length: 501 }, (_, index) =>
    item(`cell-${index}`, index),
  );
  const result = selectVisibleSymbolReviewItems(
    createEmptySymbolReviewSelection(),
    items,
  );

  assert.equal(selectedSymbolReviewCount(result.selection), 500);
  assert.equal(result.rejectedCount, 1);
});
