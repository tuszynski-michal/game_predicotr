import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createSymbolReviewWorkspaceState,
  DEFAULT_SYMBOL_REVIEW_PAGE_SIZE,
  MIN_SYMBOL_REVIEW_PAGE_SIZE,
  symbolReviewPageRange,
  symbolReviewWorkspaceReducer,
} from '../src/features/symbol-reviews/symbol-review-state.ts';

const filters = {
  gameId: 'game-1',
  pageSize: 500,
  state: 'pending',
  symbolId: 'symbol-1',
};

function page(id, { nextCursor = null, previousCursor = null } = {}) {
  return {
    catalogRevision: 1,
    counts: { allCount: 900, approvedCount: 400, pendingCount: 500 },
    items: [{ cellReviewId: id, id }],
    nextCursor,
    previousCursor,
  };
}

test('uses a single bounded configurable page without adjacent data cache', () => {
  assert.equal(DEFAULT_SYMBOL_REVIEW_PAGE_SIZE, 500);
  assert.equal(MIN_SYMBOL_REVIEW_PAGE_SIZE, 1);
  let state = createSymbolReviewWorkspaceState(filters);
  state = symbolReviewWorkspaceReducer(state, {
    page: page('first', { nextCursor: 'after-first' }),
    position: { number: 1 },
    type: 'page_loaded',
  });
  state = symbolReviewWorkspaceReducer(state, {
    page: page('second', { previousCursor: 'before-second' }),
    position: { afterCursor: 'after-first', number: 2 },
    type: 'page_loaded',
  });

  assert.equal(state.currentPage.page.items[0].id, 'second');
  assert.deepEqual(state.currentPage.position, {
    afterCursor: 'after-first',
    number: 2,
  });
  assert.equal('pages' in state, false);
});

test('changing filters and explicit clearing discard the current page', () => {
  let state = createSymbolReviewWorkspaceState(filters);
  state = symbolReviewWorkspaceReducer(state, {
    page: page('first'),
    position: { number: 1 },
    type: 'page_loaded',
  });
  state = symbolReviewWorkspaceReducer(state, { type: 'clear_page' });
  assert.equal(state.currentPage, null);

  state = symbolReviewWorkspaceReducer(state, {
    filters: { ...filters, symbolId: 'symbol-2' },
    type: 'filters_changed',
  });
  assert.deepEqual(state.filters, { ...filters, symbolId: 'symbol-2' });
  assert.equal(state.currentPage, null);
});

test('fresh keyset reload replaces changed rows instead of merging a page cache', () => {
  const position = { afterCursor: 'after-previous-page', number: 2 };
  let state = createSymbolReviewWorkspaceState(filters);
  state = symbolReviewWorkspaceReducer(state, {
    page: { ...page('changed'), items: [{ id: 'changed' }] },
    position,
    type: 'page_loaded',
  });
  state = symbolReviewWorkspaceReducer(state, {
    page: {
      ...page('replacement'),
      items: [{ id: 'replacement' }, { id: 'next' }],
    },
    position,
    type: 'page_loaded',
  });

  assert.deepEqual(
    state.currentPage.page.items.map((item) => item.id),
    ['replacement', 'next'],
  );
  assert.deepEqual(state.currentPage.position, position);
});

test('reports the one-based range represented by the confirmed page size', () => {
  assert.deepEqual(symbolReviewPageRange(1, 500, 500, 1_240), {
    start: 1,
    end: 500,
  });
  assert.deepEqual(symbolReviewPageRange(2, 500, 500, 1_240), {
    start: 501,
    end: 1_000,
  });
  assert.deepEqual(symbolReviewPageRange(3, 240, 500, 1_240), {
    start: 1_001,
    end: 1_240,
  });
  assert.deepEqual(symbolReviewPageRange(3, 20, 100, 220), {
    start: 201,
    end: 220,
  });
  assert.equal(symbolReviewPageRange(1, 0, 100, 0), null);
});
