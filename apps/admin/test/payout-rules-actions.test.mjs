import assert from 'node:assert/strict';
import test from 'node:test';

import { savePayoutConfiguration } from '../src/features/rules/payout-rules-actions.ts';

const rulesVersionId = '11111111-1111-4111-8111-111111111111';
const symbolId = '22222222-2222-4222-8222-222222222222';
const configuration = {
  isActive: true,
  minimumMatchLength: 3,
  rulesVersionId,
  symbolId,
};

function createClient(overrides = {}) {
  return {
    createPayoutRule: async (_rulesId, body) => ({
      data: {
        id: `created-${body.matchLength}`,
        isActive: true,
        rulesVersionId,
        ...body,
      },
    }),
    listPayoutRules: async () => ({ data: [] }),
    listRulesVersionSymbols: async () => ({ data: [] }),
    listSymbols: async () => ({ data: [] }),
    updatePayoutRule: async (_rulesId, payoutRuleId, body) => ({
      data: {
        id: payoutRuleId,
        isActive: true,
        matchLength: 3,
        payoutCredits: body.payoutCredits,
        rulesVersionId,
        symbolId,
      },
    }),
    updateRulesVersionSymbol: async () => ({ data: configuration }),
    ...overrides,
  };
}

test('saves minimum before creating every required payout', async () => {
  const calls = [];
  const result = await savePayoutConfiguration(
    createClient({
      createPayoutRule: async (_rulesId, body) => {
        calls.push(`payout-${body.matchLength}`);
        return {
          data: {
            id: `created-${body.matchLength}`,
            isActive: true,
            rulesVersionId,
            ...body,
          },
        };
      },
      updateRulesVersionSymbol: async (_rulesId, _symbolId, body) => {
        calls.push('minimum');
        return { data: { ...configuration, ...body } };
      },
    }),
    rulesVersionId,
    symbolId,
    [],
    {
      isActive: true,
      minimumMatchLength: 3,
      payouts: [
        { matchLength: 3, payoutCredits: 10 },
        { matchLength: 4, payoutCredits: 25 },
        { matchLength: 5, payoutCredits: 100 },
      ],
    },
  );

  assert.deepEqual(calls, ['minimum', 'payout-3', 'payout-4', 'payout-5']);
  assert.equal(result.ok, true);
  assert.equal(result.payoutRules.length, 3);
});

test('reactivates an existing length instead of creating a duplicate', async () => {
  let updateRequest;
  const existing = {
    id: 'payout-3',
    isActive: false,
    matchLength: 3,
    payoutCredits: 5,
    rulesVersionId,
    symbolId,
  };
  const result = await savePayoutConfiguration(
    createClient({
      createPayoutRule: async () => {
        throw new Error('must not create');
      },
      updatePayoutRule: async (_rulesId, payoutRuleId, body) => {
        updateRequest = { body, payoutRuleId };
        return { data: { ...existing, ...body } };
      },
    }),
    rulesVersionId,
    symbolId,
    [existing],
    {
      isActive: true,
      minimumMatchLength: 3,
      payouts: [{ matchLength: 3, payoutCredits: 10 }],
    },
  );

  assert.deepEqual(updateRequest, {
    body: { isActive: true, payoutCredits: 10 },
    payoutRuleId: 'payout-3',
  });
  assert.equal(result.ok, true);
});

test('TASK-0931: saving trigger count payouts archives the counts left empty', async () => {
  const calls = [];
  const existing = [
    { id: 'p3', isActive: true, matchLength: 3, payoutCredits: 20, symbolId },
    { id: 'p4', isActive: true, matchLength: 4, payoutCredits: 200, symbolId },
    {
      id: 'p5',
      isActive: false,
      matchLength: 5,
      payoutCredits: 2000,
      symbolId,
    },
  ];
  const result = await savePayoutConfiguration(
    createClient({
      updateRulesVersionSymbol: async (_rulesId, _symbolId, body) => {
        calls.push(['symbol', body]);
        return { data: { ...configuration, minimumMatchLength: null } };
      },
      updatePayoutRule: async (_rulesId, payoutRuleId, body) => {
        calls.push(['update', payoutRuleId, body]);
        return {
          data: {
            ...existing.find((item) => item.id === payoutRuleId),
            ...body,
            rulesVersionId,
          },
        };
      },
      createPayoutRule: async (_rulesId, body) => {
        calls.push(['create', body.matchLength]);
        return { data: { id: 'p8', isActive: true, rulesVersionId, ...body } };
      },
    }),
    rulesVersionId,
    symbolId,
    existing,
    {
      archiveUnlistedPayouts: true,
      isActive: true,
      minimumMatchLength: null,
      payouts: [
        { matchLength: 3, payoutCredits: 20 },
        { matchLength: 8, payoutCredits: 500 },
      ],
    },
  );

  assert.equal(result.ok, true);
  assert.deepEqual(calls, [
    ['symbol', { isActive: true, minimumMatchLength: null }],
    ['update', 'p3', { isActive: true, payoutCredits: 20 }],
    ['create', 8],
    // Count 4 was cleared in the form; the already inactive 5 is untouched.
    ['update', 'p4', { isActive: false }],
  ]);
  assert.deepEqual(
    result.payoutRules.map((item) => [item.matchLength, item.isActive]),
    [
      [3, true],
      [8, true],
      [4, false],
    ],
  );
});
