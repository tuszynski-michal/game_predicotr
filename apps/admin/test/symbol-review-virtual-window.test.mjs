import assert from 'node:assert/strict';
import test from 'node:test';

import {
  MAX_SYMBOL_REVIEW_ATLAS_CELLS,
  boundedVirtualPreviewItems,
  shouldApplyVirtualPreviewResult,
  symbolReviewVirtualWindow,
} from '../src/features/symbol-reviews/symbol-review-virtual-window.ts';

test('keeps rendered card windows bounded for 500, 1000 and 10000 metadata items', () => {
  for (const itemCount of [500, 1_000, 10_000]) {
    const window = symbolReviewVirtualWindow(itemCount, 10, 20, 8);
    assert.ok(window.startIndex >= 0);
    assert.ok(window.endIndexExclusive <= itemCount);
    assert.ok(window.endIndexExclusive - window.startIndex <= 120);
  }
});

test('limits one virtual preview atlas to 100 visible cells', () => {
  const items = Array.from({ length: 180 }, (_, index) => ({
    id: `cell-${index}`,
  }));
  assert.equal(MAX_SYMBOL_REVIEW_ATLAS_CELLS, 100);
  assert.equal(boundedVirtualPreviewItems(items).length, 100);
});

test('ignores a late preview response after viewport or filter cancellation', () => {
  assert.equal(shouldApplyVirtualPreviewResult(4, 4), true);
  assert.equal(shouldApplyVirtualPreviewResult(4, 5), false);
});
