import assert from 'node:assert/strict';
import test from 'node:test';

import {
  applySymbolDisplayOrderChanges,
  canEditSuperGameTrigger,
  EMPTY_SYMBOL_DRAFT,
  parseSuperGameTriggerCount,
  planSymbolReorder,
  SUPER_GAME_TRIGGER_COUNT_OPTIONS,
  superGameTriggerCountLabel,
  selectGameId,
  symbolToDraft,
  upsertSymbol,
  validateSymbolDraft,
} from '../src/features/symbols/symbol-catalog-state.ts';

const game = {
  code: 'game-1',
  createdAt: '2026-07-26T10:00:00Z',
  id: '11111111-1111-4111-8111-111111111111',
  name: 'Game 1',
  status: 'active',
  updatedAt: '2026-07-26T10:00:00Z',
};
const symbol = {
  code: 'S1',
  displayOrder: 10,
  gameId: game.id,
  id: '22222222-2222-4222-8222-222222222222',
  imagePath: null,
  isWildcard: false,
  mobileCode: 1,
  name: 'Symbol 1',
  nameEn: null,
  namePl: null,
  status: 'active',
  superGameTriggerCount: null,
};

test('validates only the manually entered name, Wild flag and trigger role', () => {
  assert.deepEqual(
    validateSymbolDraft({
      isWildcard: true,
      name: '  Wild  ',
      superGameTriggerCount: 4,
      triggersSuperGame: false,
    }),
    {
      valid: true,
      value: { isWildcard: true, name: 'Wild', superGameTriggerCount: null },
    },
  );
  assert.deepEqual(
    validateSymbolDraft({
      isWildcard: true,
      name: 'Mumia',
      superGameTriggerCount: 3,
      triggersSuperGame: true,
    }),
    {
      valid: true,
      value: { isWildcard: true, name: 'Mumia', superGameTriggerCount: 3 },
    },
  );
  assert.equal(
    validateSymbolDraft({ isWildcard: false, name: '  ' }).valid,
    false,
  );
  assert.equal(
    validateSymbolDraft({ isWildcard: false, name: 'x'.repeat(201) }).valid,
    false,
  );
});

test('keeps stable identity out of the editable draft', () => {
  assert.deepEqual(symbolToDraft(symbol), {
    isWildcard: false,
    name: 'Symbol 1',
    superGameTriggerCount: 3,
    triggersSuperGame: false,
  });
  assert.deepEqual(
    symbolToDraft({ ...symbol, isWildcard: true, superGameTriggerCount: 5 }),
    {
      isWildcard: true,
      name: 'Symbol 1',
      superGameTriggerCount: 5,
      triggersSuperGame: true,
    },
  );
});

test('keeps the current game or chooses the first non-archived game', () => {
  const archived = { ...game, id: 'archived', status: 'archived' };
  const active = { ...game, id: 'active' };

  assert.equal(selectGameId([archived, active], null), 'active');
  assert.equal(selectGameId([archived, active], 'archived'), 'archived');
  assert.equal(selectGameId([], 'missing'), null);
});

test('upserts symbols in their server-assigned canonical order', () => {
  const later = { ...symbol, displayOrder: 20, id: 'later', mobileCode: 2 };
  const earlier = {
    ...symbol,
    displayOrder: 5,
    id: 'earlier',
    isWildcard: true,
    mobileCode: 12,
  };
  const inserted = upsertSymbol([later], earlier);
  const renamed = { ...earlier, name: 'Wildcard' };

  assert.deepEqual(
    inserted.map((item) => item.id),
    ['earlier', 'later'],
  );
  assert.equal(upsertSymbol(inserted, renamed)[0].name, 'Wildcard');
});

function orderedSymbol(id, displayOrder, mobileCode) {
  return { ...symbol, displayOrder, id, mobileCode };
}

test('moving a symbol up swaps it with the previous one and renumbers', () => {
  const symbols = [
    orderedSymbol('a', 0, 1),
    orderedSymbol('star', 6, 7),
    orderedSymbol('seven', 7, 8),
  ];

  assert.deepEqual(planSymbolReorder(symbols, 'seven', 'up'), [
    { displayOrder: 1, symbolId: 'seven' },
    { displayOrder: 2, symbolId: 'star' },
  ]);
  assert.deepEqual(planSymbolReorder(symbols, 'a', 'down'), [
    { displayOrder: 0, symbolId: 'star' },
    { displayOrder: 1, symbolId: 'a' },
    { displayOrder: 2, symbolId: 'seven' },
  ]);
});

test('reorder resolves ties by mobile code and skips unchanged symbols', () => {
  const symbols = [
    orderedSymbol('c', 1, 3),
    orderedSymbol('a', 0, 1),
    orderedSymbol('b', 1, 2),
  ];

  assert.deepEqual(planSymbolReorder(symbols, 'c', 'up'), [
    { displayOrder: 2, symbolId: 'b' },
  ]);
});

test('reorder at the list edges or for an unknown symbol changes nothing', () => {
  const symbols = [orderedSymbol('a', 0, 1), orderedSymbol('b', 1, 2)];

  assert.deepEqual(planSymbolReorder(symbols, 'a', 'up'), []);
  assert.deepEqual(planSymbolReorder(symbols, 'b', 'down'), []);
  assert.deepEqual(planSymbolReorder(symbols, 'missing', 'up'), []);
});

test('saved displayOrder changes re-sort the local catalog list', () => {
  const symbols = [
    orderedSymbol('a', 0, 1),
    orderedSymbol('star', 1, 7),
    orderedSymbol('seven', 2, 8),
  ];
  const changes = planSymbolReorder(symbols, 'seven', 'up');

  assert.deepEqual(
    applySymbolDisplayOrderChanges(symbols, changes).map((item) => [
      item.id,
      item.displayOrder,
    ]),
    [
      ['a', 0],
      ['seven', 1],
      ['star', 2],
    ],
  );
});

test('TASK-0931: trigger role offers three, four or five symbols and needs a super game kind', () => {
  assert.deepEqual(
    SUPER_GAME_TRIGGER_COUNT_OPTIONS.map((option) => [
      option.value,
      option.label,
    ]),
    [
      [3, 'Trzy symbole'],
      [4, 'Cztery symbole'],
      [5, 'Pięć symboli'],
    ],
  );
  assert.equal(superGameTriggerCountLabel(4), 'Cztery symbole');
  assert.equal(parseSuperGameTriggerCount('5'), 5);
  assert.equal(parseSuperGameTriggerCount('9'), 3);
  assert.equal(EMPTY_SYMBOL_DRAFT.triggersSuperGame, false);

  const noKind = { superGameKind: 'none' };
  const wildSuperSpins = { superGameKind: 'wild_super_spins' };
  assert.equal(canEditSuperGameTrigger(noKind, EMPTY_SYMBOL_DRAFT), false);
  assert.equal(canEditSuperGameTrigger(null, EMPTY_SYMBOL_DRAFT), false);
  assert.equal(
    canEditSuperGameTrigger(wildSuperSpins, EMPTY_SYMBOL_DRAFT),
    true,
  );
  // A saved role can always be removed.
  assert.equal(
    canEditSuperGameTrigger(noKind, { triggersSuperGame: true }),
    true,
  );
});
