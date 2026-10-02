import assert from 'node:assert/strict';
import test from 'node:test';

import {
  applySymbolDisplayOrderChanges,
  planSymbolReorder,
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
};

test('validates only the manually entered name and joker flag', () => {
  assert.deepEqual(
    validateSymbolDraft({ isWildcard: true, name: '  Wild  ' }),
    { valid: true, value: { isWildcard: true, name: 'Wild' } },
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
  });
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
