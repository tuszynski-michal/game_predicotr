import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createSymbolReviewWorkspaceState,
  DEFAULT_SYMBOL_REVIEW_PAGE_SIZE,
  isSymbolReviewPageSize,
  MAX_SYMBOL_REVIEW_CACHED_PAGES,
  MAX_SYMBOL_REVIEW_PAGE_SIZE,
  parseSymbolReviewChangeRange,
  parseSymbolReviewPageNumber,
  SYMBOL_REVIEW_PAGE_SIZES,
  symbolReviewConfidenceRange,
  symbolReviewExtendedFilters,
  symbolReviewFiltersReady,
  symbolReviewIsoToLocalDateTime,
  symbolReviewLocalDateTimeToIso,
  symbolReviewStartOfDayLocal,
  symbolReviewPageRange,
  symbolReviewWorkspaceReducer,
} from '../src/features/symbol-reviews/symbol-review-state.ts';

const filters = {
  confidence: 'all',
  gameId: 'game-1',
  pageSize: 500,
  state: 'pending',
  symbolId: 'symbol-1',
};

test('requires both game and symbol scope before loading review data', () => {
  assert.equal(
    symbolReviewFiltersReady({ ...filters, gameId: null, symbolId: null }),
    false,
  );
  assert.equal(symbolReviewFiltersReady({ ...filters, symbolId: null }), false);
  assert.equal(symbolReviewFiltersReady(filters), true);
  assert.equal(symbolReviewFiltersReady({ ...filters, symbolId: 'all' }), true);
});

function page(id, { nextCursor = null, previousCursor = null } = {}) {
  return {
    catalogRevision: 1,
    counts: { allCount: 900, approvedCount: 400, pendingCount: 500 },
    items: [{ cellReviewId: id, id }],
    nextCursor,
    previousCursor,
  };
}

test('keeps at most three bounded metadata pages around the current keyset page', () => {
  assert.equal(DEFAULT_SYMBOL_REVIEW_PAGE_SIZE, 500);
  assert.equal(MAX_SYMBOL_REVIEW_PAGE_SIZE, 2_500);
  assert.deepEqual(SYMBOL_REVIEW_PAGE_SIZES, [500, 1_000, 2_000, 2_500]);
  assert.equal(isSymbolReviewPageSize(2_500), true);
  assert.equal(isSymbolReviewPageSize(750), false);
  assert.equal(MAX_SYMBOL_REVIEW_CACHED_PAGES, 3);
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
  assert.equal(state.pages.length, 2);

  for (const pageNumber of [3, 4]) {
    state = symbolReviewWorkspaceReducer(state, {
      page: page(`page-${pageNumber}`),
      position: { number: pageNumber },
      type: 'page_prefetched',
    });
  }
  assert.equal(state.pages.length, 3);
  assert.deepEqual(
    state.pages.map((cached) => cached.position.number),
    [1, 2, 3],
  );
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
  assert.deepEqual(
    state.pages[0]?.page.items.map((item) => item.id),
    ['replacement', 'next'],
  );
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
  assert.deepEqual(symbolReviewPageRange(1, 2_500, 2_500, 3_000), {
    start: 1,
    end: 2_500,
  });
  assert.equal(symbolReviewPageRange(1, 0, 100, 0), null);
});

test('accepts only a one-based page number within the known result range', () => {
  assert.equal(parseSymbolReviewPageNumber('1', 12), 1);
  assert.equal(parseSymbolReviewPageNumber('12', 12), 12);
  assert.equal(parseSymbolReviewPageNumber('', 12), null);
  assert.equal(parseSymbolReviewPageNumber('0', 12), null);
  assert.equal(parseSymbolReviewPageNumber('2.5', 12), null);
  assert.equal(parseSymbolReviewPageNumber('13', 12), null);
});

test('maps non-overlapping confidence ranges to the API range snapshot', () => {
  assert.deepEqual(symbolReviewConfidenceRange('all'), {});
  assert.deepEqual(symbolReviewConfidenceRange('exact_100'), {
    maxConfidence: 1,
    minConfidence: 1,
  });
  assert.deepEqual(symbolReviewConfidenceRange('from_80_to_100'), {
    maxConfidence: 0.9999999999999999,
    minConfidence: 0.8,
  });
  assert.deepEqual(symbolReviewConfidenceRange('from_60_to_80'), {
    maxConfidence: 0.7999999999999999,
    minConfidence: 0.6,
  });
  assert.deepEqual(symbolReviewConfidenceRange('below_60'), {
    maxConfidence: 0.5999999999999999,
  });
});

test('extended filters are sent only when set', () => {
  assert.deepEqual(
    symbolReviewExtendedFilters({
      changedFrom: null,
      changedTo: null,
      predictionSource: 'all',
    }),
    {},
  );
  assert.deepEqual(
    symbolReviewExtendedFilters({
      changedFrom: '2026-09-29T22:00:00.000Z',
      changedTo: null,
      predictionSource: 'model',
    }),
    { changedFrom: '2026-09-29T22:00:00.000Z', predictionSource: 'model' },
  );
});

test('change range converts local minutes to inclusive instants', () => {
  const from = symbolReviewLocalDateTimeToIso('2026-09-30T00:00', 'from');
  const to = symbolReviewLocalDateTimeToIso('2026-09-30T23:59', 'to');

  assert.equal(from, new Date(2026, 8, 30, 0, 0).toISOString());
  assert.equal(
    to,
    new Date(2026, 8, 30, 23, 59, 59, 999).toISOString().replace('Z', '999Z'),
  );
  assert.equal(symbolReviewIsoToLocalDateTime(to), '2026-09-30T23:59');
  assert.equal(symbolReviewIsoToLocalDateTime(from), '2026-09-30T00:00');
  assert.equal(symbolReviewIsoToLocalDateTime(null), '');
  assert.equal(symbolReviewLocalDateTimeToIso('2026-09-30', 'from'), null);
  assert.equal(
    symbolReviewLocalDateTimeToIso('2026-09-30T00:00:42', 'from'),
    from,
  );
  assert.equal(
    symbolReviewStartOfDayLocal(new Date(2026, 8, 30, 15, 42)),
    '2026-09-30T00:00',
  );
});

test('change range rejects incomplete and reversed bounds', () => {
  assert.deepEqual(parseSymbolReviewChangeRange('', ''), {
    changedFrom: null,
    changedTo: null,
    ok: true,
  });
  assert.equal(parseSymbolReviewChangeRange('2026-09-30', '').ok, false);
  assert.equal(
    parseSymbolReviewChangeRange('2026-09-30T10:00', '2026-09-30T09:00').ok,
    false,
  );
  const sameMinute = parseSymbolReviewChangeRange(
    '2026-09-30T10:00',
    '2026-09-30T10:00',
  );
  assert.equal(sameMinute.ok, true);
});
