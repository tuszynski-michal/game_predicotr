import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createSymbolReviewWorkspaceState,
  symbolReviewBufferedPages,
  symbolReviewBufferedPageCount,
  symbolReviewWorkspaceReducer,
} from '../src/features/symbol-reviews/symbol-review-state.ts';

const filters = {
  gameId: 'game-1',
  state: 'all',
  symbolId: 'symbol-1',
};

function page(id, { nextCursor = null, previousCursor = null } = {}) {
  return {
    catalogRevision: 1,
    counts: { allCount: 180, approvedCount: 90, pendingCount: 90 },
    items: [{ id }],
    nextCursor,
    previousCursor,
  };
}

test('keeps only the current page and its immediate neighbours in memory', () => {
  const first = page('first', { nextCursor: 'after-first' });
  const second = page('second', {
    nextCursor: 'after-second',
    previousCursor: 'before-second',
  });
  const third = page('third', { previousCursor: 'before-third' });
  let state = createSymbolReviewWorkspaceState(filters);

  state = symbolReviewWorkspaceReducer(state, {
    page: first,
    type: 'initial_page_loaded',
  });
  state = symbolReviewWorkspaceReducer(state, {
    page: second,
    type: 'next_page_prefetched',
  });
  state = symbolReviewWorkspaceReducer(state, {
    page: second,
    type: 'next_page_loaded',
  });
  state = symbolReviewWorkspaceReducer(state, {
    page: third,
    type: 'next_page_prefetched',
  });

  assert.equal(state.pages.previous?.items[0]?.id, 'first');
  assert.equal(state.pages.current?.items[0]?.id, 'second');
  assert.equal(state.pages.next?.items[0]?.id, 'third');
  assert.equal(symbolReviewBufferedPageCount(state), 3);
});

test('streams forward and backward without retaining distant pages', () => {
  const first = page('first', { nextCursor: 'after-first' });
  const second = page('second', {
    nextCursor: 'after-second',
    previousCursor: 'before-second',
  });
  const third = page('third', {
    nextCursor: 'after-third',
    previousCursor: 'before-third',
  });
  let state = createSymbolReviewWorkspaceState(filters);
  state = symbolReviewWorkspaceReducer(state, {
    page: first,
    type: 'initial_page_loaded',
  });
  state = symbolReviewWorkspaceReducer(state, {
    page: second,
    type: 'next_page_loaded',
  });
  state = symbolReviewWorkspaceReducer(state, {
    page: third,
    type: 'next_page_loaded',
  });

  assert.deepEqual(
    symbolReviewBufferedPages(state).map((value) => value.items[0]?.id),
    ['second', 'third'],
  );
  assert.ok(symbolReviewBufferedPageCount(state) <= 3);

  state = symbolReviewWorkspaceReducer(state, {
    page: second,
    type: 'previous_page_loaded',
  });
  assert.deepEqual(
    symbolReviewBufferedPages(state).map((value) => value.items[0]?.id),
    ['second', 'third'],
  );
});

test('moves backwards through the cached neighbour and discards distant pages', () => {
  const first = page('first', { nextCursor: 'after-first' });
  const second = page('second', { previousCursor: 'before-second' });
  let state = createSymbolReviewWorkspaceState(filters);

  state = symbolReviewWorkspaceReducer(state, {
    page: first,
    type: 'initial_page_loaded',
  });
  state = symbolReviewWorkspaceReducer(state, {
    page: second,
    type: 'next_page_loaded',
  });
  state = symbolReviewWorkspaceReducer(state, {
    page: first,
    type: 'previous_page_loaded',
  });

  assert.equal(state.pages.current?.items[0]?.id, 'first');
  assert.equal(state.pages.next?.items[0]?.id, 'second');
  assert.equal(state.pages.previous, null);
  assert.equal(symbolReviewBufferedPageCount(state), 2);
});

test('changing game, symbol or review state clears every cached page', () => {
  let state = createSymbolReviewWorkspaceState(filters);
  state = symbolReviewWorkspaceReducer(state, {
    page: page('first', { nextCursor: 'after-first' }),
    type: 'initial_page_loaded',
  });
  state = symbolReviewWorkspaceReducer(state, {
    page: page('second'),
    type: 'next_page_prefetched',
  });
  state = symbolReviewWorkspaceReducer(state, {
    filters: { ...filters, state: 'pending', symbolId: 'symbol-2' },
    type: 'filters_changed',
  });

  assert.deepEqual(state.filters, {
    gameId: 'game-1',
    state: 'pending',
    symbolId: 'symbol-2',
  });
  assert.equal(symbolReviewBufferedPageCount(state), 0);
});
