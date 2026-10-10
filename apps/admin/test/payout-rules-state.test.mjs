import assert from 'node:assert/strict';
import test from 'node:test';

import {
  changePayoutCredits,
  countPayoutLengths,
  defaultMinimum,
  isSuperGameTriggerSymbol,
  payoutLengthLabel,
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
  superGameTriggerCount: null,
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

test('TASK-0931: a trigger symbol is paid per count on the board, 2..rows*columns', () => {
  const mumia = {
    ...symbol,
    isWildcard: true,
    name: 'Mumia',
    superGameTriggerCount: 3,
  };
  const existing = [
    {
      id: 'p3',
      isActive: true,
      matchLength: 3,
      payoutCredits: 20,
      symbolId: 'symbol',
    },
    {
      id: 'p4',
      isActive: true,
      matchLength: 4,
      payoutCredits: 200,
      symbolId: 'symbol',
    },
    {
      id: 'p5',
      isActive: true,
      matchLength: 5,
      payoutCredits: 2000,
      symbolId: 'symbol',
    },
    {
      id: 'p9',
      isActive: false,
      matchLength: 9,
      payoutCredits: 1,
      symbolId: 'symbol',
    },
  ];
  const draft = payoutConfigurationToDraft(
    mumia,
    {
      isActive: true,
      minimumMatchLength: 3,
      rulesVersionId: 'r',
      symbolId: 'symbol',
    },
    existing,
    5,
  );

  assert.equal(isSuperGameTriggerSymbol(mumia), true);
  assert.equal(isSuperGameTriggerSymbol(symbol), false);
  assert.deepEqual(
    countPayoutLengths(3, 5),
    [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
  );
  assert.equal(payoutLengthLabel(mumia, 3), '3 sztuk na planszy');
  assert.equal(payoutLengthLabel(symbol, 3), '3 kolejnych symboli');
  // The existing 3/4/5 -> 20/200/2000 stay and the minimum is not shown.
  assert.equal(draft.minimumMatchLength, '');
  assert.deepEqual(draft.credits, { 3: '20', 4: '200', 5: '2000' });

  assert.deepEqual(validatePayoutConfiguration(mumia, draft, 5, 3), {
    valid: true,
    value: {
      archiveUnlistedPayouts: true,
      isActive: true,
      minimumMatchLength: null,
      payouts: [
        { matchLength: 3, payoutCredits: 20 },
        { matchLength: 4, payoutCredits: 200 },
        { matchLength: 5, payoutCredits: 2000 },
      ],
    },
  });
  const withCountTwelve = changePayoutCredits(draft, 12, '5000');
  assert.equal(
    validatePayoutConfiguration(mumia, withCountTwelve, 5, 3).value.payouts.at(
      -1,
    ).matchLength,
    12,
  );
  assert.equal(
    validatePayoutConfiguration(
      mumia,
      changePayoutCredits(draft, 5, '100'),
      5,
      3,
    ).valid,
    false,
  );
  assert.equal(
    validatePayoutConfiguration(mumia, changePayoutCredits(draft, 2, 'x'), 5, 3)
      .valid,
    false,
  );
});

test('TASK-0931: a Wild without the trigger role still has no payouts', () => {
  const wild = { ...symbol, isWildcard: true, superGameTriggerCount: null };

  assert.deepEqual(
    validatePayoutConfiguration(
      wild,
      { credits: { 3: '100' }, isActive: true, minimumMatchLength: '' },
      5,
      3,
    ),
    {
      valid: true,
      value: { isActive: true, minimumMatchLength: null, payouts: [] },
    },
  );
});
