import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import {
  approximateWinStakeToPoint,
  approximateWinMachineCashAtPoint,
} from '../src/board-search-approximate-win-state.ts';

const cases = JSON.parse(
  readFileSync(
    new URL(
      '../../domain-fixtures/management-pin-metric-cases.json',
      import.meta.url,
    ),
    'utf8',
  ),
);

// Zero and unavailable pins are backend/caller states. These cases exercise
// the real existing numerical helpers, without substituting constant results.
for (const fixture of cases.filter(
  (item) => item.spin > 0 && item.required !== null,
)) {
  test(`shared management pin metrics: ${fixture.name}`, () => {
    const point = {
      spinNumber: fixture.spin,
      cumulativeBalanceCredits: fixture.net,
    };
    const required = approximateWinStakeToPoint(
      fixture.rows,
      fixture.spinCost,
      point,
    );
    const cash = approximateWinMachineCashAtPoint(
      fixture.rows,
      fixture.spinCost,
      point,
    );
    assert.equal(required, fixture.required);
    assert.equal(cash, fixture.cash);
  });
}
