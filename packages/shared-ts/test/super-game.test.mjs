import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import { WILD_SUPER_SPINS_CODE, evaluateSeriesBoard } from '../dist/index.js';

// The worker evaluation (services/worker/tests/test_super_game_payout.py)
// executes the same fixture section; both languages must agree (TASK-0936).
const fixture = JSON.parse(
  await readFile(
    new URL('../../domain-fixtures/payout-golden-cases.json', import.meta.url),
    'utf8',
  ),
);
const scenario = fixture.wildSuperSpinsScenario;

function evaluate(testCase) {
  return evaluateSeriesBoard(
    scenario.game,
    testCase.rows.flat(),
    scenario.paylines,
    scenario.payoutSymbols,
    scenario.payoutRules,
    testCase.superSymbolMobileCode,
    { generationFresh: testCase.generationFresh ?? true },
  );
}

function serialize(result) {
  const { columns } = scenario.game;
  const evaluatedRows = [];
  for (let start = 0; start < result.evaluatedCells.length; start += columns) {
    evaluatedRows.push(result.evaluatedCells.slice(start, start + columns));
  }
  return {
    totalPayout: result.totalPayout,
    payoutKind: result.payoutKind,
    evaluatedRows,
    expansion: result.expansion,
    matches: result.matches,
    countMatches: result.countMatches,
    retrigger: result.retrigger,
  };
}

function byId(id) {
  const found = scenario.cases.find((testCase) => testCase.id === id);
  assert.ok(found, id);
  return evaluate(found);
}

test('the scenario belongs to the wild_super_spins kind', () => {
  assert.equal(scenario.superGameKind, WILD_SUPER_SPINS_CODE);
});

for (const testCase of scenario.cases) {
  test(`wild_super_spins golden case ${testCase.id}`, () => {
    assert.ok(testCase.manualCalculation.length > 0);
    assert.deepEqual(serialize(evaluate(testCase)), testCase.expected);
  });
}

test('an undefined super symbol is neither a lower nor an upper bound', () => {
  const grows = byId('undefined-super-symbol-is-provisional-and-may-grow');
  const grown = byId('expansion-covers-a-line-win-underneath');
  const shrinks = byId('undefined-super-symbol-is-provisional-and-may-shrink');
  const shrunk = byId('defined-super-symbol-covers-a-larger-win');
  assert.equal(grows.payoutKind, 'provisional');
  assert.equal(shrinks.payoutKind, 'provisional');
  assert.ok(grows.totalPayout < grown.totalPayout);
  assert.ok(shrinks.totalPayout > shrunk.totalPayout);
});

test('an unknown cell in a covered column changes only counts and retrigger', () => {
  const before = byId('two-mumias-and-unknown-cell-in-covered-column');
  const after = byId('two-mumias-unknown-cell-filled-as-mumia');
  assert.deepEqual(before.evaluatedCells, after.evaluatedCells);
  assert.deepEqual(before.matches, after.matches);
  assert.deepEqual(before.expansion, after.expansion);
  assert.deepEqual([before.retrigger, after.retrigger], [false, true]);
  assert.equal(after.totalPayout - before.totalPayout, 20);
});
