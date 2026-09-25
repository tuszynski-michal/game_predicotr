import assert from 'node:assert/strict';
import test from 'node:test';

import {
  APPROXIMATE_WIN_RANGE_DEFAULT,
  APPROXIMATE_WIN_RANGE_MAX,
  APPROXIMATE_WIN_ROWS_PAGE_SIZE,
  approximateWinRequestKey,
  formatApproximateWinCredits,
  pageApproximateWinRows,
  parseApproximateWinRange,
  shouldRequestApproximateWin,
  visibleApproximateWinResult,
} from '../src/features/board-search/board-search-approximate-win-state.ts';

test('parseApproximateWinRange accepts a positive integer within the ceiling', () => {
  assert.deepEqual(parseApproximateWinRange('1'), { ok: true, value: 1 });
  assert.deepEqual(parseApproximateWinRange(String(APPROXIMATE_WIN_RANGE_DEFAULT)), {
    ok: true,
    value: APPROXIMATE_WIN_RANGE_DEFAULT,
  });
  assert.deepEqual(parseApproximateWinRange(String(APPROXIMATE_WIN_RANGE_MAX)), {
    ok: true,
    value: APPROXIMATE_WIN_RANGE_MAX,
  });
  assert.deepEqual(parseApproximateWinRange(' 42 '), { ok: true, value: 42 });
});

test('parseApproximateWinRange rejects zero, negative, fractional, out-of-range and empty input', () => {
  assert.equal(parseApproximateWinRange('0').ok, false);
  assert.equal(parseApproximateWinRange('-5').ok, false);
  assert.equal(parseApproximateWinRange('3.5').ok, false);
  assert.equal(
    parseApproximateWinRange(String(APPROXIMATE_WIN_RANGE_MAX + 1)).ok,
    false,
  );
  assert.equal(parseApproximateWinRange('').ok, false);
  assert.equal(parseApproximateWinRange('   ').ok, false);
  assert.equal(parseApproximateWinRange('abc').ok, false);
});

test('approximateWinRequestKey changes the number of results does not affect it (independent parameters)', () => {
  const key = approximateWinRequestKey({
    gameId: 'game-1',
    resultIdentity: 'operational_review:37:' + 'a'.repeat(64),
    spinCount: 1000,
  });
  // The same board/range with a differently-ranked search result (limit
  // change) keeps the same identity string, so the key is unaffected.
  const sameKey = approximateWinRequestKey({
    gameId: 'game-1',
    resultIdentity: 'operational_review:37:' + 'a'.repeat(64),
    spinCount: 1000,
  });
  assert.equal(key, sameKey);
});

test('approximateWinRequestKey differs for a different board, game or range', () => {
  const base = { gameId: 'game-1', resultIdentity: 'operational_review:37:' + 'a'.repeat(64), spinCount: 1000 };
  const key = approximateWinRequestKey(base);
  assert.notEqual(key, approximateWinRequestKey({ ...base, gameId: 'game-2' }));
  assert.notEqual(
    key,
    approximateWinRequestKey({ ...base, resultIdentity: 'operational_review:38:' + 'a'.repeat(64) }),
  );
  assert.notEqual(key, approximateWinRequestKey({ ...base, spinCount: 500 }));
});

test('shouldRequestApproximateWin never fires while collapsed or without a selection', () => {
  assert.equal(
    shouldRequestApproximateWin({
      isOpen: false,
      requestKey: 'game-1|id|1000',
      state: { kind: 'idle' },
    }),
    false,
  );
  assert.equal(
    shouldRequestApproximateWin({
      isOpen: true,
      requestKey: null,
      state: { kind: 'idle' },
    }),
    false,
  );
});

test('shouldRequestApproximateWin fires on first expansion with a valid selection', () => {
  assert.equal(
    shouldRequestApproximateWin({
      isOpen: true,
      requestKey: 'game-1|id|1000',
      state: { kind: 'idle' },
    }),
    true,
  );
});

test('shouldRequestApproximateWin does not refire for an in-flight or already-resolved matching key', () => {
  const key = 'game-1|id|1000';
  assert.equal(
    shouldRequestApproximateWin({ isOpen: true, requestKey: key, state: { key, kind: 'loading' } }),
    false,
  );
  assert.equal(
    shouldRequestApproximateWin({
      isOpen: true,
      requestKey: key,
      state: { key, kind: 'ready', result: /** @type {any} */ ({}) },
    }),
    false,
  );
  assert.equal(
    shouldRequestApproximateWin({
      isOpen: true,
      requestKey: key,
      state: { key, kind: 'error', message: 'boom' },
    }),
    false,
  );
});

test('shouldRequestApproximateWin refires when the selected board or range changes', () => {
  const previousKey = 'game-1|id-a|1000';
  const nextKey = 'game-1|id-b|1000';
  assert.equal(
    shouldRequestApproximateWin({
      isOpen: true,
      requestKey: nextKey,
      state: { key: previousKey, kind: 'ready', result: /** @type {any} */ ({}) },
    }),
    true,
  );
});

test('shouldRequestApproximateWin reuses a ready result on reopen with the same key', () => {
  const key = 'game-1|id|1000';
  assert.equal(
    shouldRequestApproximateWin({
      isOpen: true,
      requestKey: key,
      state: { key, kind: 'ready', result: /** @type {any} */ ({ evaluatedSpinCount: 1000 }) },
    }),
    false,
  );
});

test('visibleApproximateWinResult only shows a ready result matching the current key', () => {
  const key = 'game-1|id|1000';
  const result = /** @type {any} */ ({ evaluatedSpinCount: 1000 });
  assert.equal(visibleApproximateWinResult({ key, kind: 'ready', result }, key), result);
  assert.equal(visibleApproximateWinResult({ key, kind: 'ready', result }, 'other-key'), null);
  assert.equal(visibleApproximateWinResult({ key, kind: 'ready', result }, null), null);
  assert.equal(visibleApproximateWinResult({ kind: 'idle' }, key), null);
  assert.equal(visibleApproximateWinResult({ key, kind: 'loading' }, key), null);
  assert.equal(
    visibleApproximateWinResult({ key, kind: 'error', message: 'x' }, key),
    null,
  );
});

function row(sequenceNumber) {
  return /** @type {any} */ ({
    boardStatus: 'accepted',
    cumulativeBalanceCredits: 0,
    cumulativeCostCredits: 0,
    cumulativePayoutCredits: 0,
    payoutCredits: 1,
    payoutKind: 'exact',
    sequenceNumber,
    spinNumber: sequenceNumber,
  });
}

test('pageApproximateWinRows returns page 1 of an empty result without erroring', () => {
  const page = pageApproximateWinRows([], 1);
  assert.deepEqual(page, { page: 1, pageCount: 1, rows: [], totalRowCount: 0 });
});

test('pageApproximateWinRows splits rows into pages of the fixed page size', () => {
  const rows = Array.from({ length: APPROXIMATE_WIN_ROWS_PAGE_SIZE + 5 }, (_, index) =>
    row(index + 1),
  );
  const first = pageApproximateWinRows(rows, 1);
  assert.equal(first.rows.length, APPROXIMATE_WIN_ROWS_PAGE_SIZE);
  assert.equal(first.pageCount, 2);
  assert.equal(first.totalRowCount, rows.length);
  assert.equal(first.rows[0].sequenceNumber, 1);

  const second = pageApproximateWinRows(rows, 2);
  assert.equal(second.rows.length, 5);
  assert.equal(second.rows[0].sequenceNumber, APPROXIMATE_WIN_ROWS_PAGE_SIZE + 1);
});

test('pageApproximateWinRows clamps an out-of-range requested page', () => {
  const rows = [row(1), row(2)];
  assert.equal(pageApproximateWinRows(rows, 0).page, 1);
  assert.equal(pageApproximateWinRows(rows, 99).page, 1);
});

test('formatApproximateWinCredits formats with Polish grouping', () => {
  assert.equal(formatApproximateWinCredits(20000), (20000).toLocaleString('pl-PL'));
  assert.equal(formatApproximateWinCredits(-2000), (-2000).toLocaleString('pl-PL'));
});
