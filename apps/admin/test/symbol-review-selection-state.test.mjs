import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createEmptySymbolReviewSelection,
  createSymbolReviewFilterSelection,
  isSymbolReviewItemSelected,
  selectVisibleSymbolReviewItems,
  selectedSymbolReviewCount,
  toggleSymbolReviewItem,
} from '../src/features/symbol-reviews/symbol-review-selection-state.ts';

const filters = { gameId: 'game-1', state: 'all', symbolId: 'symbol-1' };
const counts = { allCount: 3, approvedCount: 2, pendingCount: 1 };
const page = {
  catalogRevision: 9,
  counts,
  items: [],
  nextCursor: null,
  previousCursor: null,
};

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

test('keeps explicit checksum-bound selections across pages', () => {
  const first = item('cell-1', 1);
  const second = item('cell-2', 2);
  let selection = createEmptySymbolReviewSelection();

  selection = toggleSymbolReviewItem(selection, first).selection;
  selection = selectVisibleSymbolReviewItems(selection, [second]).selection;

  assert.equal(selectedSymbolReviewCount(selection, counts), 2);
  assert.equal(isSymbolReviewItemSelected(selection, first), true);
  assert.equal(
    selection.targetsById['cell-1'].expectedCropSampleId,
    'b'.repeat(64),
  );
  assert.equal(
    selection.targetsById['cell-2'].expectedCropChecksumSha256,
    'a'.repeat(64),
  );
});

test('selecting every filtered result uses exclusions instead of materializing all ids', () => {
  const first = item('cell-1');
  const selection = createSymbolReviewFilterSelection(filters, page);
  assert.notEqual(selection, null);
  const deselected = toggleSymbolReviewItem(selection, first).selection;
  const restored = selectVisibleSymbolReviewItems(deselected, [
    first,
  ]).selection;

  assert.equal(selectedSymbolReviewCount(deselected, counts), 2);
  assert.equal(isSymbolReviewItemSelected(deselected, first), false);
  assert.equal(selectedSymbolReviewCount(restored, counts), 3);
  assert.deepEqual(restored.excludedCellReviewIds, []);
});
