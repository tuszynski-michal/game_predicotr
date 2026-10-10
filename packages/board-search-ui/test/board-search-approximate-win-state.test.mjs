import assert from 'node:assert/strict';
import test from 'node:test';

import {
  APPROXIMATE_WIN_CHART_LABEL,
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
  layoutApproximateWinPointLabels,
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
  assert.equal(APPROXIMATE_WIN_PIN_LIMIT, 6);
  let pins = [];
  for (let spin = 1; spin <= 6; spin += 1) {
    pins = toggleApproximateWinPinnedPoint(pins, pinPoint(spin)).pins;
  }
  const refused = toggleApproximateWinPinnedPoint(pins, pinPoint(99));
  assert.equal(refused.limitReached, true);
  assert.equal(refused.pins, pins);
  const unpinned = toggleApproximateWinPinnedPoint(pins, pinPoint(3));
  assert.equal(unpinned.limitReached, false);
  assert.equal(unpinned.pins.length, 5);
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

test('cash on the machine is the stake put in plus the net cash', async () => {
  const { approximateWinMachineCashAtPoint } =
    await import('../src/board-search-approximate-win-state.ts');
  const row = (spinNumber, payoutCredits, cumulativeBalanceCredits) => ({
    cumulativeBalanceCredits,
    payoutCredits,
    spinNumber,
  });
  const rows = [row(3, 500, 200), row(8, 100, -200)];
  const at = (spinNumber, cumulativeBalanceCredits) =>
    approximateWinMachineCashAtPoint(rows, 100, {
      cumulativeBalanceCredits,
      spinNumber,
    });
  // Stake 300 to reach spin 3, net +200: 500 on the machine.
  assert.equal(at(3, 200), 500);
  // Stake 300, net -200: 100 left on the machine.
  assert.equal(at(8, -200), 100);
  // At the deepest point everything put in is gone.
  assert.equal(at(12, -600), 0);
});

// The chart's real label geometry and plot area (TASK-0786).
const labelLayout = {
  area: { maxX: 782, maxY: 350, minX: 74, minY: 12 },
  height: APPROXIMATE_WIN_CHART_LABEL.height,
  width: APPROXIMATE_WIN_CHART_LABEL.width,
};

function assertLabelsFit(placements, { allowOverlap = false } = {}) {
  const { area, height, width } = labelLayout;
  for (const a of placements) {
    assert.ok(a.left >= area.minX - 1e-9 && a.left + width <= area.maxX + 1e-9);
    assert.ok(a.top >= area.minY - 1e-9 && a.top + height <= area.maxY + 1e-9);
    if (allowOverlap) continue;
    for (const b of placements) {
      if (a === b) continue;
      const apart =
        Math.abs(a.left - b.left) >= width + 4 - 1e-9 ||
        Math.abs(a.top - b.top) >= height + 4 - 1e-9;
      assert.ok(apart, `labels ${a.key} and ${b.key} overlap`);
    }
  }
}

test('layoutApproximateWinPointLabels puts a label beside its point, on the plot', () => {
  const [placement] = layoutApproximateWinPointLabels(
    [{ key: 'a', x: 400, y: 180 }],
    labelLayout,
  );
  assertLabelsFit([placement]);
  assert.equal(placement.pointX, 400);
  assert.equal(placement.pointY, 180);
  // Near the point, but never on top of it.
  const { height, width } = labelLayout;
  const covers =
    400 > placement.left &&
    400 < placement.left + width &&
    180 > placement.top &&
    180 < placement.top + height;
  assert.equal(covers, false);
  assert.ok(
    Math.hypot(
      placement.left + width / 2 - 400,
      placement.top + height / 2 - 180,
    ) < 200,
  );
});

test('layoutApproximateWinPointLabels keeps corner points inside the plot', () => {
  const placements = layoutApproximateWinPointLabels(
    [
      { key: 'tl', x: 74, y: 12 },
      { key: 'tr', x: 782, y: 12 },
      { key: 'bl', x: 74, y: 350 },
      { key: 'br', x: 782, y: 350 },
    ],
    labelLayout,
  );
  assertLabelsFit(placements);
});

test('layoutApproximateWinPointLabels steers clear of the series line when there is room', () => {
  // A flat line through the middle: the label goes above or below it.
  const obstacles = Array.from({ length: 60 }, (_, index) => ({
    x: 74 + index * 12,
    y: 180,
  }));
  const [placement] = layoutApproximateWinPointLabels(
    [{ key: 'a', x: 400, y: 180 }],
    { ...labelLayout, obstacles },
  );
  const { height } = labelLayout;
  assert.ok(placement.top + height < 180 || placement.top > 180);
});

test('layoutApproximateWinPointLabels never overlaps six pins and a hover label', () => {
  let seed = 7;
  const random = () => {
    seed = (seed * 48271) % 2147483647;
    return seed / 2147483647;
  };
  const anywhere = () => ({ x: 74 + random() * 708, y: 12 + random() * 338 });
  for (let trial = 0; trial < 1500; trial += 1) {
    // Half of the trials cluster the points, as pins on one peak do.
    const centre = anywhere();
    const near = () => ({
      x: Math.min(782, centre.x + random() * 30),
      y: Math.min(350, centre.y + random() * 30),
    });
    const pick = trial % 2 === 0 ? anywhere : near;
    const pins = layoutApproximateWinPointLabels(
      Array.from({ length: 6 }, (_, index) => ({
        key: `p${index}`,
        ...pick(),
      })),
      labelLayout,
    );
    const [hover] = layoutApproximateWinPointLabels([{ key: 'h', ...pick() }], {
      ...labelLayout,
      reserved: pins,
    });
    assertLabelsFit([...pins, hover]);
  }
});
