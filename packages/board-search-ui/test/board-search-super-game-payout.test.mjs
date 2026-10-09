import assert from 'node:assert/strict';
import test from 'node:test';

import {
  approximateWinBalancePayout,
  approximateWinChartPoints,
  approximateWinCostAtSpin,
  approximateWinCostSchedule,
  approximateWinMachineCashAtPoint,
  approximateWinPointAtSpin,
  approximateWinStakeToPoint,
} from '../src/board-search-approximate-win-state.ts';
import {
  boardExpandedCells,
  boardExpansionLabel,
  boardLinesConsistency,
} from '../src/board-search-board-lines-state.ts';

// TASK-0936: super game series boards in the approximate win and the modal.

const expansion = {
  columnCount: 3,
  columns: [1, 3, 4],
  linePayoutCredits: 10,
  paylineCount: 5,
  payoutCredits: 50,
  symbolCode: 'K',
};

test('the expansion label reads like the plan example', () => {
  assert.equal(
    boardExpansionLabel(expansion, 'K'),
    'Rozwinięcie K ×3 kolumny → 10 × 5 linii = 50',
  );
  assert.equal(
    boardExpansionLabel(
      {
        ...expansion,
        columnCount: 5,
        linePayoutCredits: 40,
        payoutCredits: 200,
      },
      'K',
    ),
    'Rozwinięcie K ×5 kolumn → 40 × 5 linii = 200',
  );
  assert.equal(
    boardExpansionLabel(expansion, 'K', (credits) => `${credits} kr.`),
    'Rozwinięcie K ×3 kolumny → 10 kr. × 5 linii = 50 kr.',
  );
});

test('expanded cells are whole columns', () => {
  assert.deepEqual(
    [...boardExpandedCells({ expansion })].sort((a, b) => a - b),
    [1, 3, 4, 6, 8, 9, 11, 13, 14],
  );
  assert.equal(boardExpandedCells({ expansion: null }).size, 0);
  assert.equal(boardExpandedCells({}).size, 0);
});

test('the expansion payout explains the board payout together with lines and counts', () => {
  const detail = {
    countMatches: [{ payoutCredits: 20 }],
    expansion,
    matches: [{ payoutCredits: 5 }],
    payoutCredits: 75,
    rules: { rulesVersionId: 'rules-1' },
  };
  assert.deepEqual(boardLinesConsistency(detail, 75, 'rules-1'), {
    kind: 'consistent',
  });
  assert.deepEqual(
    boardLinesConsistency({ ...detail, expansion: null }, 75, 'rules-1'),
    { kind: 'inconsistent', reason: 'lines' },
  );
});

const row = (
  spinNumber,
  payoutCredits,
  cumulativePayoutCredits,
  cost,
  kind,
) => ({
  boardStatus: 'accepted',
  cumulativeBalanceCredits: cumulativePayoutCredits - cost,
  cumulativeCostCredits: cost,
  cumulativePayoutCredits,
  mode: kind === 'base' ? 'base' : 'super',
  payoutCredits,
  payoutKind: kind === 'base' ? 'exact' : kind,
  sequenceNumber: 100 + spinNumber,
  spinCostCredits: kind === 'base' ? 10 : 0,
  spinNumber,
});

test('a provisional payout never moves the balance line', () => {
  const provisional = row(4, 30, 0, 20, 'provisional');
  assert.equal(approximateWinBalancePayout(provisional), 0);
  assert.equal(approximateWinBalancePayout(row(1, 30, 30, 10, 'base')), 30);
  const points = approximateWinChartPoints([provisional]);
  assert.deepEqual(
    points.slice(1).map((point) => point.cumulativeBalanceCredits),
    [-20, -20],
  );
  assert.equal(approximateWinStakeToPoint([provisional], 10, points[2]), 20);
});

// The summary carries the exact free spin ranges (audit TASK-0936 P0-1):
// every chart value and pin uses them, also between payout rows.
test('a chart point after free spins uses the exact free spin ranges', () => {
  // Spins 1..2 cost 10 each, spins 3..6 are free (series), spin 7 costs 10.
  const result = {
    evaluatedSpinCount: 7,
    rows: [row(2, 15, 15, 20, 'base'), row(5, 50, 65, 20, 'exact')],
    rules: { spinCost: 10 },
    summary: {
      balanceCredits: 35,
      superSpinCost: 0,
      superSpinRanges: [{ endSpin: 6, startSpin: 3 }],
    },
  };
  const at = (spin) =>
    approximateWinPointAtSpin(result, spin).cumulativeBalanceCredits;
  assert.equal(at(3), -5);
  assert.equal(at(5), 45);
  assert.equal(at(6), 45);
  assert.equal(at(7), 35);
  assert.equal(
    approximateWinCostAtSpin(approximateWinCostSchedule(result), 7),
    30,
  );
});

test('a series without any positive payout still ends at the summary balance', () => {
  // Spins 1..10, 3..6 free, no payout at all: cost 6 × 10 = 60.
  const result = {
    evaluatedSpinCount: 10,
    rows: [],
    rules: { spinCost: 10 },
    summary: {
      balanceCredits: -60,
      superSpinCost: 0,
      superSpinRanges: [{ endSpin: 6, startSpin: 3 }],
    },
  };
  const at = (spin) =>
    approximateWinPointAtSpin(result, spin).cumulativeBalanceCredits;
  assert.equal(at(10), result.summary.balanceCredits);
  // A pin after the series: spins 1, 2 and 7 paid.
  assert.equal(at(7), -30);
  assert.equal(at(4), -20);
  const points = approximateWinChartPoints(
    result.rows,
    { balanceCredits: -60, spinNumber: 10 },
    approximateWinCostSchedule(result),
  );
  // Corner points keep the free spins flat: 2 → -20, 6 → -20.
  assert.deepEqual(
    points.map((point) => [point.spinNumber, point.cumulativeBalanceCredits]),
    [
      [0, 0],
      [2, -20],
      [6, -20],
      [10, -60],
    ],
  );
});

test('a range starting inside a series needs no stake for a paying free spin', () => {
  // Spins 1..2 are free (the rest of a series), spin 3 costs 100.
  const costs = {
    spinCost: 100,
    superSpinCost: 0,
    superSpinRanges: [{ endSpin: 2, startSpin: 1 }],
  };
  const rows = [
    {
      ...row(1, 50, 50, 0, 'exact'),
      cumulativeBalanceCredits: 50,
      spinCostCredits: 0,
    },
  ];
  const first = { cumulativeBalanceCredits: 50, spinNumber: 1 };
  assert.equal(approximateWinStakeToPoint(rows, costs, first), 0);
  assert.equal(approximateWinMachineCashAtPoint(rows, costs, first), 50);
  // The first paid spin after the series: 50 - 100 = -50 needs 50 in hand.
  const paid = { cumulativeBalanceCredits: -50, spinNumber: 3 };
  assert.equal(approximateWinStakeToPoint(rows, costs, paid), 50);
  assert.equal(approximateWinMachineCashAtPoint(rows, costs, paid), 0);
});

test('without free spins the stake keeps the first spin cost', () => {
  assert.equal(
    approximateWinStakeToPoint([], 20, {
      cumulativeBalanceCredits: 0,
      spinNumber: 0,
    }),
    20,
  );
});

test('without free spins a chart point keeps spin × spin cost', () => {
  const result = {
    evaluatedSpinCount: 7,
    rows: [{ ...row(2, 15, 15, 20, 'base'), mode: undefined }],
    rules: { spinCost: 10 },
    summary: { balanceCredits: -55 },
  };
  assert.equal(
    approximateWinPointAtSpin(result, 7).cumulativeBalanceCredits,
    -55,
  );
  assert.equal(
    approximateWinPointAtSpin(result, 4).cumulativeBalanceCredits,
    -25,
  );
});
