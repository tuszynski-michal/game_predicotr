import assert from 'node:assert/strict';
import test from 'node:test';

import {
  APPROXIMATE_WIN_CHART_LABEL_LAYOUT,
  APPROXIMATE_WIN_PIN_LIMIT,
  APPROXIMATE_WIN_RANGE_DEFAULT,
  APPROXIMATE_WIN_RANGE_MAX,
  approximateWinAxisTicks,
  approximateWinChartPoints,
  approximateWinExtremes,
  approximateWinPointKey,
  approximateWinRequestKey,
  filterApproximateWinRows,
  formatApproximateWinCredits,
  layoutApproximateWinPinLabels,
  moveApproximateWinHighlight,
  parseApproximateWinRange,
  shouldRequestApproximateWin,
  toggleApproximateWinPinnedPoint,
  visibleApproximateWinResult,
} from '../src/board-search-approximate-win-state.ts';

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

function assertRoundTicks(ticks, minimum, maximum) {
  assert.ok(ticks.length >= 2);
  assert.ok(ticks[0] <= minimum, `first tick ${ticks[0]} > ${minimum}`);
  assert.ok(ticks.at(-1) >= maximum, `last tick ${ticks.at(-1)} < ${maximum}`);
  const step = ticks[1] - ticks[0];
  const magnitude = 10 ** Math.floor(Math.log10(step));
  assert.ok(
    [1, 2, 5, 10].some((factor) => Math.abs(step - factor * magnitude) < 1e-9),
    `step ${step} is not 1/2/5 x 10^n`,
  );
  for (let index = 1; index < ticks.length; index += 1) {
    assert.ok(Math.abs(ticks[index] - ticks[index - 1] - step) < 1e-9);
  }
}

test('approximateWinAxisTicks returns round ticks enclosing the range', () => {
  assert.deepEqual(
    approximateWinAxisTicks(-2500, 0),
    [-2500, -2000, -1500, -1000, -500, 0],
  );
  const wide = approximateWinAxisTicks(-120, 9800);
  assertRoundTicks(wide, -120, 9800);
  assert.deepEqual(wide, [-2000, 0, 2000, 4000, 6000, 8000, 10000]);
  assertRoundTicks(approximateWinAxisTicks(-7, 3), -7, 3);
  assertRoundTicks(approximateWinAxisTicks(0, 2500, 6), 0, 2500);
  assert.equal(approximateWinAxisTicks(0, 2500, 6)[0], 0);
});

test('approximateWinAxisTicks widens a degenerate range symmetrically', () => {
  const zero = approximateWinAxisTicks(0, 0);
  assertRoundTicks(zero, -1, 1);
  assert.ok(zero.includes(0));
  const five = approximateWinAxisTicks(5, 5);
  assertRoundTicks(five, 0, 10);
  assert.ok(five.every((tick) => !Object.is(tick, -0)));
});

const pinPoint = (spinNumber, kind = 'payout') => ({
  cumulativeBalanceCredits: spinNumber * 10,
  kind,
  spinNumber,
});

test('toggleApproximateWinPinnedPoint pins, unpins and keeps spin order', () => {
  let state = toggleApproximateWinPinnedPoint([], pinPoint(30));
  state = toggleApproximateWinPinnedPoint(state.pins, pinPoint(10));
  assert.deepEqual(
    state.pins.map((point) => point.spinNumber),
    [10, 30],
  );
  assert.equal(state.limitReached, false);
  state = toggleApproximateWinPinnedPoint(state.pins, pinPoint(30));
  assert.deepEqual(
    state.pins.map((point) => point.spinNumber),
    [10],
  );
  assert.notEqual(
    approximateWinPointKey(pinPoint(5, 'payout')),
    approximateWinPointKey(pinPoint(5, 'end')),
  );
});

test('toggleApproximateWinPinnedPoint refuses a pin beyond the limit without dropping one', () => {
  assert.equal(APPROXIMATE_WIN_PIN_LIMIT, 8);
  let pins = [];
  for (let spin = 1; spin <= 8; spin += 1) {
    pins = toggleApproximateWinPinnedPoint(pins, pinPoint(spin)).pins;
  }
  const refused = toggleApproximateWinPinnedPoint(pins, pinPoint(99));
  assert.equal(refused.limitReached, true);
  assert.equal(refused.pins, pins);
  const unpinned = toggleApproximateWinPinnedPoint(pins, pinPoint(3));
  assert.equal(unpinned.limitReached, false);
  assert.equal(unpinned.pins.length, 7);
});

// The chart's real label geometry, so the layout is tested at its width.
const layoutOptions = APPROXIMATE_WIN_CHART_LABEL_LAYOUT;
const labelWidth = layoutOptions.labelWidth;

function assertNoOverlap(placements, width = labelWidth, gap = 4) {
  for (const a of placements) {
    assert.ok(
      a.x - width / 2 >= layoutOptions.minX - 1e-9 &&
        a.x + width / 2 <= layoutOptions.maxX + 1e-9,
    );
    for (const b of placements) {
      if (a === b || a.row !== b.row) continue;
      assert.ok(
        Math.abs(a.x - b.x) >= width + gap - 1e-9,
        `labels ${a.key} and ${b.key} overlap in row ${a.row}`,
      );
    }
  }
}

test('layoutApproximateWinPinLabels stacks labels of the same point into rows', () => {
  const placements = layoutApproximateWinPinLabels(
    [
      { key: 'a', x: 400 },
      { key: 'b', x: 400 },
    ],
    layoutOptions,
  );
  assert.deepEqual(
    placements.map((placement) => [placement.key, placement.row, placement.x]),
    [
      ['a', 0, 400],
      ['b', 1, 400],
    ],
  );
  assertNoOverlap(placements);
});

test('layoutApproximateWinPinLabels keeps an edge label inside the chart', () => {
  const [placement] = layoutApproximateWinPinLabels(
    [{ key: 'edge', x: 795 }],
    layoutOptions,
  );
  assert.equal(placement.x, layoutOptions.maxX - labelWidth / 2);
  assert.equal(placement.pointX, 795);
});

test('layoutApproximateWinPinLabels fits nine labels of one point without overlap', () => {
  const labels = Array.from({ length: 9 }, (_, index) => ({
    key: `p${index}`,
    x: 400,
  }));
  const placements = layoutApproximateWinPinLabels(labels, layoutOptions);
  assert.equal(placements.length, 9);
  assertNoOverlap(placements);
  assert.ok(placements.some((placement) => placement.x !== placement.pointX));
});

test('layoutApproximateWinPinLabels places a hover label around reserved pins', () => {
  const pins = layoutApproximateWinPinLabels(
    Array.from({ length: 8 }, (_, index) => ({ key: `p${index}`, x: 790 })),
    layoutOptions,
  );
  const [hover] = layoutApproximateWinPinLabels([{ key: 'h', x: 790 }], {
    ...layoutOptions,
    reserved: pins,
  });
  assertNoOverlap([...pins, hover]);
  assert.deepEqual(
    pins,
    layoutApproximateWinPinLabels(
      Array.from({ length: 8 }, (_, index) => ({ key: `p${index}`, x: 790 })),
      layoutOptions,
    ),
  );
});

test('layoutApproximateWinPinLabels fits clustered pins at the chart label width', () => {
  // Regression (TASK-0774): with three rows the pin at 658 overlapped.
  const pins = layoutApproximateWinPinLabels(
    [198, 217, 246, 507, 537, 556, 657, 658].map((x, index) => ({
      key: `p${index}`,
      x,
    })),
    layoutOptions,
  );
  assertNoOverlap(pins);
  const [hover] = layoutApproximateWinPinLabels([{ key: 'h', x: 600 }], {
    ...layoutOptions,
    reserved: pins,
  });
  assertNoOverlap([...pins, hover]);
});

test('layoutApproximateWinPinLabels never overlaps eight pins and a hover label', () => {
  // Deterministic pseudo-random pin sets across the whole chart.
  let seed = 7;
  const random = () => {
    seed = (seed * 48271) % 2147483647;
    return seed / 2147483647;
  };
  for (let trial = 0; trial < 3000; trial += 1) {
    const pins = layoutApproximateWinPinLabels(
      Array.from({ length: 8 }, (_, index) => ({
        key: `p${index}`,
        x: 72 + random() * 710,
      })),
      layoutOptions,
    );
    const [hover] = layoutApproximateWinPinLabels(
      [{ key: 'h', x: 72 + random() * 710 }],
      { ...layoutOptions, reserved: pins },
    );
    assertNoOverlap([...pins, hover]);
  }
});

test('moveApproximateWinHighlight skips drop points and stops at the ends', () => {
  const points = approximateWinChartPoints(
    [
      {
        boardStatus: 'accepted',
        cumulativeBalanceCredits: 50,
        cumulativeCostCredits: 50,
        cumulativePayoutCredits: 100,
        payoutCredits: 100,
        payoutKind: 'exact',
        sequenceNumber: 7,
        spinNumber: 5,
      },
    ],
    { balanceCredits: 0, spinNumber: 10 },
  );
  const keys = (point) =>
    point === null ? null : approximateWinPointKey(point);
  assert.equal(keys(moveApproximateWinHighlight(points, null, 1)), 'start:0');
  assert.equal(keys(moveApproximateWinHighlight(points, null, -1)), 'end:10');
  assert.equal(
    keys(moveApproximateWinHighlight(points, 'start:0', 1)),
    'payout:5',
  );
  assert.equal(
    keys(moveApproximateWinHighlight(points, 'payout:5', 1)),
    'end:10',
  );
  assert.equal(
    keys(moveApproximateWinHighlight(points, 'end:10', 1)),
    'end:10',
  );
  assert.equal(
    keys(moveApproximateWinHighlight(points, 'start:0', -1)),
    'start:0',
  );
  assert.equal(moveApproximateWinHighlight([], null, 1), null);
});

test('layoutApproximateWinPinLabels never overlaps labels at fractional positions', () => {
  const toX = (spin) => 72 + (spin / 2500) * 710;
  const sameX = layoutApproximateWinPinLabels(
    Array.from({ length: 9 }, (_, index) => ({
      key: `p${index}`,
      x: 72 + (1234 / 10000) * 710,
    })),
    layoutOptions,
  );
  assertNoOverlap(sameX);
  // Deterministic pseudo-random clusters: 8 pins plus a hover label.
  let seed = 7;
  const random = () => {
    seed = (seed * 1103515245 + 12345) % 2147483648;
    return seed / 2147483648;
  };
  for (let run = 0; run < 2000; run += 1) {
    const centre = random() * 2500;
    const pins = layoutApproximateWinPinLabels(
      Array.from({ length: 8 }, (_, index) => ({
        key: `p${index}`,
        x: toX(Math.min(2500, centre + random() * 60)),
      })),
      layoutOptions,
    );
    const hover = layoutApproximateWinPinLabels(
      [{ key: 'h', x: toX(Math.min(2500, centre + random() * 60)) }],
      { ...layoutOptions, reserved: pins },
    );
    assertNoOverlap([...pins, ...hover]);
  }
});

test('approximateWinAxisTicks can keep a whole-number step and rejects unusable ranges', () => {
  assert.deepEqual(
    approximateWinAxisTicks(0, 3, 6, { integerStep: true }),
    [0, 1, 2, 3],
  );
  assert.deepEqual(
    approximateWinAxisTicks(0, 1, 6, { integerStep: true }),
    [0, 1],
  );
  assert.deepEqual(approximateWinAxisTicks(0, Number.NaN), []);
  assert.deepEqual(approximateWinAxisTicks(0, Number.POSITIVE_INFINITY), []);
  const ticks = approximateWinAxisTicks(1e300, 1e300 + 1);
  assert.ok(ticks.length >= 2 && ticks.length <= 1001);
});

test('the maximum stake is the deepest trough from a zero start', async () => {
  const { approximateWinMaximumStake } =
    await import('../src/board-search-approximate-win-state.ts');
  const row = (spinNumber, payoutCredits, cumulativeBalanceCredits) => ({
    cumulativeBalanceCredits,
    payoutCredits,
    spinNumber,
  });
  // Spin cost 100: paid 300 by spin 3, payout 500 there (+200), then the
  // balance falls to -300 before spin 8's payout of 100 (-200) and the
  // range ends at -400: the end of the range is the deepest point.
  assert.deepEqual(
    approximateWinMaximumStake({
      evaluatedSpinCount: 10,
      rows: [row(3, 500, 200), row(8, 100, -200)],
      rules: { spinCost: 100 },
      summary: { balanceCredits: -400 },
    }),
    { credits: 400, spinNumber: 10 },
  );
  // A payout on the first spin still needs that spin paid first.
  assert.deepEqual(
    approximateWinMaximumStake({
      evaluatedSpinCount: 3,
      rows: [row(1, 1000, 900)],
      rules: { spinCost: 100 },
      summary: { balanceCredits: 700 },
    }),
    { credits: 100, spinNumber: 1 },
  );
  // Without payouts everything paid in is the stake.
  assert.deepEqual(
    approximateWinMaximumStake({
      evaluatedSpinCount: 4,
      rows: [],
      rules: { spinCost: 25 },
      summary: { balanceCredits: -100 },
    }),
    { credits: 100, spinNumber: 4 },
  );
  // The trough before a payout beats a milder end balance.
  assert.deepEqual(
    approximateWinMaximumStake({
      evaluatedSpinCount: 10,
      rows: [row(6, 900, 300), row(9, 100, 100)],
      rules: { spinCost: 100 },
      summary: { balanceCredits: 0 },
    }),
    { credits: 600, spinNumber: 6 },
  );
  // An equal trough later (end balance -600 again) keeps the earlier spin.
  assert.deepEqual(
    approximateWinMaximumStake({
      evaluatedSpinCount: 12,
      rows: [row(6, 900, 300), row(9, 100, 100)],
      rules: { spinCost: 100 },
      summary: { balanceCredits: -600 },
    }),
    { credits: 600, spinNumber: 6 },
  );
  assert.equal(
    approximateWinMaximumStake({
      evaluatedSpinCount: 0,
      rows: [],
      rules: { spinCost: 100 },
      summary: { balanceCredits: 0 },
    }),
    null,
  );
});

test('the stake to a chart point is the deepest trough up to that point', async () => {
  const { approximateWinStakeToPoint } =
    await import('../src/board-search-approximate-win-state.ts');
  const row = (spinNumber, payoutCredits, cumulativeBalanceCredits) => ({
    cumulativeBalanceCredits,
    payoutCredits,
    spinNumber,
  });
  // Spin cost 100: -300 before the payout at spin 3 (+200 after), -300
  // before the payout at spin 8 (-200 after), -600 before spin 12 (+900).
  const rows = [row(3, 500, 200), row(8, 100, -200), row(12, 1500, 900)];
  const at = (spinNumber, cumulativeBalanceCredits) =>
    approximateWinStakeToPoint(rows, 100, {
      cumulativeBalanceCredits,
      spinNumber,
    });
  // Only the troughs up to the point count, not the deeper one after it.
  assert.equal(at(3, 200), 300);
  assert.equal(at(8, -200), 300);
  assert.equal(at(12, 900), 600);
  // An end point below every earlier trough is its own lowest balance.
  assert.equal(at(20, 100), 600);
  assert.equal(
    approximateWinStakeToPoint(rows.slice(0, 2), 100, {
      cumulativeBalanceCredits: -400,
      spinNumber: 10,
    }),
    400,
  );
  // A payout on the first spin still needs that spin paid first.
  assert.equal(
    approximateWinStakeToPoint([row(1, 1000, 900)], 100, {
      cumulativeBalanceCredits: 900,
      spinNumber: 1,
    }),
    100,
  );
});
