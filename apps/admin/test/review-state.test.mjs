import assert from 'node:assert/strict';
import test from 'node:test';

import {
  adjacentReviewItemId,
  formatReviewConfidence,
  orderReviewItems,
  reviewAssetUrl,
  reviewCell,
  reviewStatusLabel,
} from '../src/features/reviews/review-state.ts';

function item(id, rank) {
  return {
    createdAt: '2026-07-29T10:00:00Z',
    id,
    resolvedAt: null,
    resolvedBy: null,
    resolvedValue: null,
    reviewBatchId: 'batch-1',
    snapshot: {
      cells: Array.from({ length: 15 }, (_, cellIndex) => ({
        alternatives: [{ confidence: 0.8, symbolCode: 'star' }],
        cellIndex,
        columnIndex: cellIndex % 5,
        confidence: 0.8,
        cropRelativePath: `cells/${cellIndex}.png`,
        entropy: 0.2,
        observationId: `${cellIndex}`.padStart(64, '0'),
        predictedSymbolCode: 'star',
        rowIndex: Math.floor(cellIndex / 5),
        sampleId: `${cellIndex + 1}`.padStart(64, '0'),
      })),
      selectionRank: rank,
      sequenceNumber: rank * 10,
    },
    status: 'pending',
  };
}

test('orders the immutable queue by selection rank without mutating input', () => {
  const input = [item('third', 3), item('first', 1), item('second', 2)];
  const ordered = orderReviewItems(input);

  assert.deepEqual(
    ordered.map((value) => value.id),
    ['first', 'second', 'third'],
  );
  assert.deepEqual(
    input.map((value) => value.id),
    ['third', 'first', 'second'],
  );
  assert.equal(adjacentReviewItemId(ordered, 'second', -1), 'first');
  assert.equal(adjacentReviewItemId(ordered, 'second', 1), 'third');
  assert.equal(adjacentReviewItemId(ordered, 'third', 1), null);
});

test('maps status, confidence and row-major cells to explicit text', () => {
  const current = item('item-1', 1);

  assert.equal(reviewStatusLabel('pending'), 'Oczekuje na decyzję');
  assert.equal(reviewStatusLabel('accepted'), 'Zaakceptowany');
  assert.match(formatReviewConfidence(0.873), /87[,.]3%/);
  assert.equal(reviewCell(current, 14)?.columnIndex, 4);
  assert.equal(reviewCell(current, 14)?.rowIndex, 2);
  assert.equal(reviewCell(current, 15), null);
});

test('builds only item-scoped loopback asset URLs with bounded cell indexes', () => {
  assert.equal(
    reviewAssetUrl('http://127.0.0.1:8000', 'item/unsafe', 'board'),
    'http://127.0.0.1:8000/api/v1/admin/review-items/item%2Funsafe/assets/board',
  );
  assert.equal(
    reviewAssetUrl('http://127.0.0.1:8000/', 'item-1', 'cell', 14),
    'http://127.0.0.1:8000/api/v1/admin/review-items/item-1/assets/cells/14',
  );
  assert.throws(
    () => reviewAssetUrl('http://127.0.0.1:8000', 'item-1', 'cell', 15),
    RangeError,
  );
});
