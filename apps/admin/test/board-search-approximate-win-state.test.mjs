import assert from 'node:assert/strict';
import test from 'node:test';

import {
  APPROXIMATE_WIN_RANGE_DEFAULT,
  APPROXIMATE_WIN_RANGE_MAX,
  approximateWinChartPoints,
  approximateWinExtremes,
  approximateWinRequestKey,
  filterApproximateWinRows,
  formatApproximateWinCredits,
  parseApproximateWinRange,
  shouldRequestApproximateWin,
  visibleApproximateWinResult,
} from '../src/features/board-search/board-search-approximate-win-state.ts';

test('parseApproximateWinRange accepts a positive integer within the ceiling', () => {
  assert.equal(APPROXIMATE_WIN_RANGE_DEFAULT, 2500);
  assert.deepEqual(parseApproximateWinRange('1'), { ok: true, value: 1 });
  assert.deepEqual(
    parseApproximateWinRange(String(APPROXIMATE_WIN_RANGE_DEFAULT)),
    {
      ok: true,
      value: APPROXIMATE_WIN_RANGE_DEFAULT,
    },
  );
  assert.deepEqual(
    parseApproximateWinRange(String(APPROXIMATE_WIN_RANGE_MAX)),
    {
      ok: true,
      value: APPROXIMATE_WIN_RANGE_MAX,
    },
  );
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
  const base = {
    gameId: 'game-1',
    resultIdentity: 'operational_review:37:' + 'a'.repeat(64),
    spinCount: 1000,
  };
  const key = approximateWinRequestKey(base);
  assert.notEqual(key, approximateWinRequestKey({ ...base, gameId: 'game-2' }));
  assert.notEqual(
    key,
    approximateWinRequestKey({
      ...base,
      resultIdentity: 'operational_review:38:' + 'a'.repeat(64),
    }),
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
    shouldRequestApproximateWin({
      isOpen: true,
      requestKey: key,
      state: { key, kind: 'loading' },
    }),
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
      state: {
        key: previousKey,
        kind: 'ready',
        result: /** @type {any} */ ({}),
      },
    }),
    true,
  );
});

test('shouldRequestApproximateWin keeps a ready result while the same key stays open', () => {
  const key = 'game-1|id|1000';
  assert.equal(
    shouldRequestApproximateWin({
      isOpen: true,
      requestKey: key,
      state: {
        key,
        kind: 'ready',
        result: /** @type {any} */ ({ evaluatedSpinCount: 1000 }),
      },
    }),
    false,
  );
});

test('visibleApproximateWinResult only shows a ready result matching the current key', () => {
  const key = 'game-1|id|1000';
  const result = /** @type {any} */ ({ evaluatedSpinCount: 1000 });
  assert.equal(
    visibleApproximateWinResult({ key, kind: 'ready', result }, key),
    result,
  );
  assert.equal(
    visibleApproximateWinResult({ key, kind: 'ready', result }, 'other-key'),
    null,
  );
  assert.equal(
    visibleApproximateWinResult({ key, kind: 'ready', result }, null),
    null,
  );
  assert.equal(visibleApproximateWinResult({ kind: 'idle' }, key), null);
  assert.equal(
    visibleApproximateWinResult({ key, kind: 'loading' }, key),
    null,
  );
  assert.equal(
    visibleApproximateWinResult({ key, kind: 'error', message: 'x' }, key),
    null,
  );
});

function row(sequenceNumber, cumulativeBalanceCredits = sequenceNumber * 10) {
  return /** @type {any} */ ({
    boardStatus: 'accepted',
    cumulativeBalanceCredits,
    cumulativeCostCredits: 0,
    cumulativePayoutCredits: 0,
    payoutCredits: 1,
    payoutKind: 'exact',
    sequenceNumber,
    spinNumber: sequenceNumber,
  });
}

test('approximateWinChartPoints draws the drop before each payout and ends at the last spin', () => {
  const payout = (spinNumber, balance, payoutCredits) => ({
    ...row(spinNumber, balance),
    payoutCredits,
  });
  assert.deepEqual(
    approximateWinChartPoints([payout(4, -50, 30), payout(12, 175, 385)], {
      balanceCredits: 95,
      spinNumber: 20,
    }),
    [
      { cumulativeBalanceCredits: 0, kind: 'start', spinNumber: 0 },
      { cumulativeBalanceCredits: -80, kind: 'before_payout', spinNumber: 4 },
      { cumulativeBalanceCredits: -50, kind: 'payout', spinNumber: 4 },
      { cumulativeBalanceCredits: -210, kind: 'before_payout', spinNumber: 12 },
      { cumulativeBalanceCredits: 175, kind: 'payout', spinNumber: 12 },
      { cumulativeBalanceCredits: 95, kind: 'end', spinNumber: 20 },
    ],
  );
  // A range that ends on a payout adds no separate end point.
  assert.equal(
    approximateWinChartPoints([payout(4, -50, 30)], {
      balanceCredits: -50,
      spinNumber: 4,
    }).at(-1).kind,
    'payout',
  );
});

test('approximateWinExtremes handles large inputs without spreading arguments', () => {
  const values = Array.from({ length: 200_001 }, (_, index) => index - 100_000);
  assert.deepEqual(approximateWinExtremes(values), {
    maximum: 100_000,
    minimum: -100_000,
  });
  assert.deepEqual(approximateWinExtremes([]), { maximum: 0, minimum: 0 });
});

test('filterApproximateWinRows keeps only payouts at or above the local threshold', () => {
  assert.deepEqual(
    filterApproximateWinRows([row(1), { ...row(2), payoutCredits: 50 }], 50),
    [{ ...row(2), payoutCredits: 50 }],
  );
});

test('formatApproximateWinCredits formats with Polish grouping', () => {
  assert.equal(
    formatApproximateWinCredits(20000),
    (20000).toLocaleString('pl-PL'),
  );
  assert.equal(
    formatApproximateWinCredits(-2000),
    (-2000).toLocaleString('pl-PL'),
  );
});
