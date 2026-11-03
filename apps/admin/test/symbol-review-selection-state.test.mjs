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
  selectSymbolReviewRange,
} from '../src/features/symbol-reviews/symbol-review-selection-state.ts';
import { inclusiveSelectionRange } from '../src/features/symbol-reviews/selection-range.ts';

test('range uses full 2500-row page, both directions, skips locked, absent anchor falls back', () => {
  const items = Array.from({ length: 2500 }, (_, i) => item(String(i)));
  const range = (from, to) =>
    inclusiveSelectionRange(
      items,
      from,
      to,
      (entry) => entry.id,
      (entry) => entry.id === '1200',
    );
  assert.deepEqual(range('0', '2499'), range('2499', '0'));
  assert.equal(range('0', '2499').length, 2499);
  assert.equal(range(null, '1'), null);
  assert.equal(range('missing', '1'), null);
  const selected = toggleSymbolReviewItem(
    createEmptySymbolReviewSelection(),
    items[0],
  ).selection;
  const added = selectSymbolReviewRange(selected, range('0', '2499'));
  assert.equal(selectedSymbolReviewCount(added.selection), 2499);
  assert.equal(isSymbolReviewItemSelected(added.selection, items[0]), true);
});

test('range cap is atomic and all_matching only removes range exclusions', () => {
  const full = selectVisibleSymbolReviewItems(
    createEmptySymbolReviewSelection(),
    Array.from({ length: 9999 }, (_, i) => item(String(i))),
  ).selection;
  const result = selectSymbolReviewRange(full, [item('new-1'), item('new-2')]);
  assert.equal(result.selection, full);
  assert.equal(result.rejectedCount, 2);
  const all = {
    kind: 'all_matching_filter',
    snapshot: { matchedCount: 20000 },
    excludedIds: new Set(['a', 'b', 'c']),
  };
  const restored = selectSymbolReviewRange(all, [item('b')]).selection;
  assert.deepEqual([...restored.excludedIds], ['a', 'c']);
  assert.deepEqual([...all.excludedIds], ['a', 'b', 'c']);
});

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

test('accumulates explicit selections from successive keyset pages', () => {
  const firstPage = [item('cell-1', 1), item('cell-2', 2)];
  const secondPage = [item('cell-3', 3), item('cell-4', 4)];

  const afterFirstPage = selectVisibleSymbolReviewItems(
    createEmptySymbolReviewSelection(),
    firstPage,
  ).selection;
  const afterSecondPage = selectVisibleSymbolReviewItems(
    afterFirstPage,
    secondPage,
  ).selection;

  assert.equal(afterSecondPage.kind, 'explicit');
  assert.equal(selectedSymbolReviewCount(afterSecondPage), 4);
  for (const itemOnEitherPage of [...firstPage, ...secondPage]) {
    assert.equal(
      isSymbolReviewItemSelected(afterSecondPage, itemOnEitherPage),
      true,
    );
  }
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
