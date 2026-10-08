import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  DomainValidationError,
  PAYOUT_V3_ALGORITHM_VERSION,
  PAYOUT_V4_ALGORITHM_VERSION,
  evaluatePayout,
  payoutAlgorithmVersion,
} from '../dist/index.js';

// The worker evaluator (services/worker/tests/test_payout.py) executes the
// same fixture; both languages must produce identical results (TASK-0932).
const fixture = JSON.parse(
  await readFile(
    new URL('../../domain-fixtures/payout-golden-cases.json', import.meta.url),
    'utf8',
  ),
);

function inputs(section, testCase) {
  const paylinesById = new Map(
    section.paylines.map((payline) => [payline.id, payline]),
  );
  const omitted = new Set(testCase.omitPayoutRulesForSymbols ?? []);
  return {
    game: section.game,
    cells: testCase.rows.flat(),
    paylines: testCase.paylineIds.map((id) => paylinesById.get(id)),
    payoutSymbols: section.payoutSymbols,
    payoutRules: section.payoutRules.filter(
      (rule) => !omitted.has(rule.symbolMobileCode),
    ),
  };
}

function evaluate({ game, cells, paylines, payoutSymbols, payoutRules }) {
  return evaluatePayout(game, cells, paylines, payoutSymbols, payoutRules);
}

for (const testCase of fixture.cases) {
  test(`payout-v3 golden case ${testCase.id}`, () => {
    const caseInputs = inputs(fixture, testCase);
    const result = evaluate(caseInputs);

    assert.deepEqual(
      { totalPayout: result.totalPayout, matches: result.matches },
      testCase.expected,
    );
    assert.deepEqual(result.countMatches, []);
    assert.equal(
      payoutAlgorithmVersion(caseInputs.game),
      PAYOUT_V3_ALGORITHM_VERSION,
    );
  });
}

const scenario = fixture.wildCountScenario;

for (const testCase of scenario.cases) {
  test(`payout-v4-wild-count golden case ${testCase.id}`, () => {
    const caseInputs = inputs(scenario, testCase);
    const result = evaluate(caseInputs);

    assert.ok(testCase.manualCalculation.length > 0);
    assert.deepEqual(result, testCase.expected);
    assert.equal(
      payoutAlgorithmVersion(caseInputs.game),
      scenario.algorithmVersion,
    );
    assert.equal(scenario.algorithmVersion, PAYOUT_V4_ALGORITHM_VERSION);
  });
}

test('a trigger symbol cannot have a minimum match length', () => {
  const caseInputs = inputs(scenario, scenario.cases[0]);
  assert.throws(
    () =>
      evaluate({
        ...caseInputs,
        payoutSymbols: [
          ...caseInputs.payoutSymbols,
          { symbolMobileCode: 6, minimumMatchLength: 3 },
        ],
      }),
    (error) =>
      error instanceof DomainValidationError &&
      error.code === 'super_game_trigger_payout_symbol',
  );
});

test('count rules outside 2..rows*columns and non-increasing counts are rejected', () => {
  const caseInputs = inputs(scenario, scenario.cases[0]);
  for (const matchLength of [1, 16]) {
    assert.throws(
      () =>
        evaluate({
          ...caseInputs,
          payoutRules: [
            ...caseInputs.payoutRules,
            { symbolMobileCode: 6, matchLength, payoutCredits: 5 },
          ],
        }),
      (error) =>
        error instanceof DomainValidationError &&
        error.code === 'invalid_match_length',
    );
  }
  assert.throws(
    () =>
      evaluate({
        ...caseInputs,
        payoutRules: caseInputs.payoutRules.map((rule) =>
          rule.symbolMobileCode === 6 ? { ...rule, payoutCredits: 20 } : rule,
        ),
      }),
    (error) =>
      error instanceof DomainValidationError &&
      error.code === 'non_increasing_payout',
  );
});
