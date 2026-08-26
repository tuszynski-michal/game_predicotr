import assert from 'node:assert/strict';
import test from 'node:test';

import {
  loadSymbolReviewPage,
  loadSymbolReviewSymbols,
} from '../src/features/symbol-reviews/symbol-review-actions.ts';

const gameId = '11111111-1111-4111-8111-111111111111';
const page = {
  catalogRevision: 7,
  counts: { allCount: 3, approvedCount: 2, pendingCount: 1 },
  items: [],
  nextCursor: 'next-page',
  previousCursor: null,
};

function client(overrides = {}) {
  return {
    listGames: async () => ({ data: [] }),
    listSymbolCellReviews: async () => ({ data: page }),
    listSymbols: async () => ({ data: [] }),
    symbolCellReviewAssetUrl: () => '',
    ...overrides,
  };
}

test('loads a bounded, checksum-independent metadata page with its keyset cursor', async () => {
  let request;
  const result = await loadSymbolReviewPage(
    client({
      listSymbolCellReviews: async (options) => {
        request = options;
        return { data: page };
      },
    }),
    {
      afterCursor: 'after-page',
      gameId,
      state: 'pending',
      symbolId: 'unknown',
    },
  );

  assert.deepEqual(request, {
    afterCursor: 'after-page',
    gameId,
    limit: 60,
    state: 'pending',
    symbolId: 'unknown',
  });
  assert.deepEqual(result, { ok: true, page });
});

test('exposes a controlled rebuilding state instead of treating it as an empty page', async () => {
  const result = await loadSymbolReviewPage(
    client({
      listSymbolCellReviews: async () => ({
        error: {
          code: 'SYMBOL_CELL_REVIEW_PROJECTION_INCOMPLETE',
          message: 'Backfill is still running.',
        },
      }),
    }),
    { gameId, state: 'all', symbolId: 'symbol-1' },
  );

  assert.equal(result.ok, false);
  if (!result.ok) {
    assert.equal(result.isProjectionRebuilding, true);
  }
});

test('lists only active symbols in deterministic catalog order', async () => {
  const result = await loadSymbolReviewSymbols(
    client({
      listSymbols: async () => ({
        data: [
          { code: 'Z', displayOrder: 2, id: 'z', status: 'active' },
          { code: 'A', displayOrder: 1, id: 'a', status: 'active' },
          { code: 'OLD', displayOrder: 0, id: 'old', status: 'archived' },
        ],
      }),
    }),
    gameId,
  );

  assert.equal(result.ok, true);
  if (result.ok) {
    assert.deepEqual(
      result.symbols.map((symbol) => symbol.id),
      ['a', 'z'],
    );
  }
});
