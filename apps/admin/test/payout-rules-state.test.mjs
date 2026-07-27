import assert from 'node:assert/strict';
import test from 'node:test';

import {
  changePayoutCredits,
  defaultMinimum,
  payoutConfigurationToDraft,
  requiredMatchLengths,
  validatePayoutConfiguration,
} from '../src/features/rules/payout-rules-state.ts';

const symbol = {
  code: 'S1',
  displayOrder: 0,
  gameId: 'game',
  id: 'symbol',
  imagePath: null,
  isWildcard: false,
  mobileCode: 1,
  name: 'Symbol 1',
  status: 'active',
};

test('defaults ordinary symbols to three and derives required lengths', () => {
  const draft = payoutConfigurationToDraft(symbol, undefined, [], 5);

  assert.equal(defaultMinimum(5), 3);
  assert.equal(draft.minimumMatchLength, '3');
  assert.deepEqual(requiredMatchLengths(3, 5), [3, 4, 5]);
  assert.equal(defaultMinimum(2), 2);
  assert.equal(defaultMinimum(1), null);
});

test('validates a complete strictly increasing payout matrix', () => {
  let draft = payoutConfigurationToDraft(symbol, undefined, [], 5);
  draft = changePayoutCredits(draft, 3, '10');
  draft = changePayoutCredits(draft, 4, '25');
  draft = changePayoutCredits(draft, 5, '100');

  assert.deepEqual(validatePayoutConfiguration(symbol, draft, 5), {
    valid: true,
    value: {
      isActive: true,
      minimumMatchLength: 3,
      payouts: [
        { matchLength: 3, payoutCredits: 10 },
        { matchLength: 4, payoutCredits: 25 },
        { matchLength: 5, payoutCredits: 100 },
      ],
    },
  });
  assert.equal(
    validatePayoutConfiguration(symbol, changePayoutCredits(draft, 5, '25'), 5)
      .valid,
    false,
  );
  assert.equal(
    validatePayoutConfiguration(symbol, { ...draft, credits: { 3: '10' } }, 5)
      .valid,
    false,
  );
});

test('wildcard always produces null minimum and no payouts', () => {
  assert.deepEqual(
    validatePayoutConfiguration(
      { ...symbol, isWildcard: true },
      {
        credits: { 3: '100' },
        isActive: false,
        minimumMatchLength: '3',
      },
      5,
    ),
    {
      valid: true,
      value: {
        isActive: false,
        minimumMatchLength: null,
        payouts: [],
      },
    },
  );
});
