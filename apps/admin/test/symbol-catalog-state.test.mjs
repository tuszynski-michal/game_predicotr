import assert from 'node:assert/strict';
import test from 'node:test';

import {
  markSymbolArchived,
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
  imagePath: 'symbols/game-1/s1.png',
  isWildcard: false,
  mobileCode: 1,
  name: 'Symbol 1',
  status: 'active',
};

test('validates and normalizes all symbol contract fields', () => {
  assert.deepEqual(
    validateSymbolDraft({
      code: ' S1 ',
      displayOrder: ' 10 ',
      imagePath: ' symbols/game-1/s1.png ',
      isWildcard: false,
      mobileCode: ' 1 ',
      name: ' Symbol 1 ',
      status: 'active',
    }),
    {
      valid: true,
      value: {
        code: 'S1',
        displayOrder: 10,
        imagePath: 'symbols/game-1/s1.png',
        isWildcard: false,
        mobileCode: 1,
        name: 'Symbol 1',
        status: 'active',
      },
    },
  );
  assert.equal(symbolToDraft(symbol).mobileCode, '1');
});

test('rejects invalid mobile codes, display order and stable code', () => {
  const base = {
    code: 'S1',
    displayOrder: '0',
    imagePath: '',
    isWildcard: false,
    mobileCode: '1',
    name: 'Symbol 1',
    status: 'active',
  };

  assert.equal(validateSymbolDraft({ ...base, mobileCode: '0' }).valid, false);
  assert.equal(
    validateSymbolDraft({ ...base, mobileCode: '1.5' }).valid,
    false,
  );
  assert.equal(
    validateSymbolDraft({ ...base, displayOrder: '-1' }).valid,
    false,
  );
  assert.equal(validateSymbolDraft({ ...base, code: 'bad code' }).valid, false);
});

test('accepts an empty image path and rejects unsafe local paths', () => {
  const base = {
    code: 'S1',
    displayOrder: '0',
    imagePath: '',
    isWildcard: false,
    mobileCode: '1',
    name: 'Symbol 1',
    status: 'active',
  };

  const empty = validateSymbolDraft(base);
  assert.equal(empty.valid, true);
  assert.equal(empty.valid ? empty.value.imagePath : 'failure', null);
  for (const imagePath of [
    '../s1.png',
    'symbols/../s1.png',
    String.raw`C:\symbols\s1.png`,
    '/symbols/s1.png',
  ]) {
    assert.equal(validateSymbolDraft({ ...base, imagePath }).valid, false);
  }
});

test('keeps the current game or chooses the first non-archived game', () => {
  const archived = { ...game, id: 'archived', status: 'archived' };
  const active = { ...game, id: 'active' };

  assert.equal(selectGameId([archived, active], null), 'active');
  assert.equal(selectGameId([archived, active], 'archived'), 'archived');
  assert.equal(selectGameId([], 'missing'), null);
});

test('upserts in canonical order and archives without removing records', () => {
  const later = {
    ...symbol,
    code: 'S2',
    displayOrder: 20,
    id: 'later',
    mobileCode: 2,
  };
  const earlier = {
    ...symbol,
    code: 'WILD',
    displayOrder: 5,
    id: 'earlier',
    isWildcard: true,
    mobileCode: 12,
  };
  const inserted = upsertSymbol([later], earlier);
  const renamed = { ...earlier, name: 'Wildcard' };
  const updated = upsertSymbol(inserted, renamed);
  const archived = markSymbolArchived(updated, earlier.id);

  assert.deepEqual(
    inserted.map((item) => item.id),
    ['earlier', 'later'],
  );
  assert.equal(updated[0].name, 'Wildcard');
  assert.equal(archived.length, 2);
  assert.equal(archived[0].status, 'archived');
  assert.equal(updated[0].status, 'active');
});
