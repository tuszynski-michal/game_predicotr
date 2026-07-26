import assert from 'node:assert/strict';
import test from 'node:test';

import {
  apiErrorMessage,
  markGameArchived,
  upsertGame,
  validateGameDraft,
} from '../src/features/games/game-catalog-state.ts';

const game = {
  code: 'game-1',
  createdAt: '2026-07-26T10:00:00Z',
  id: '11111111-1111-4111-8111-111111111111',
  name: 'Game 1',
  status: 'active',
  updatedAt: '2026-07-26T10:00:00Z',
};

test('validates and normalizes the game identity draft', () => {
  assert.deepEqual(
    validateGameDraft({
      code: ' game-1 ',
      name: ' Game 1 ',
      status: 'draft',
    }),
    {
      valid: true,
      value: {
        code: 'game-1',
        name: 'Game 1',
        status: 'draft',
      },
    },
  );
  assert.deepEqual(
    validateGameDraft({ code: 'game-1', name: '  ', status: 'draft' }),
    {
      error: 'Kod i nazwa gry są wymagane.',
      valid: false,
    },
  );
});

test('inserts a new game and replaces an edited game immutably', () => {
  const initial = [game];
  const second = { ...game, code: 'game-2', id: 'game-2', name: 'Game 2' };
  const inserted = upsertGame(initial, second);
  const edited = { ...game, name: 'Game One', status: 'draft' };
  const updated = upsertGame(inserted, edited);

  assert.deepEqual(inserted, [game, second]);
  assert.deepEqual(updated, [edited, second]);
  assert.deepEqual(initial, [game]);
});

test('archives a game without removing or mutating the original record', () => {
  const initial = [game];
  const archived = markGameArchived(initial, game.id);

  assert.equal(archived.length, 1);
  assert.equal(archived[0].status, 'archived');
  assert.equal(initial[0].status, 'active');
  assert.equal(archived[0].code, game.code);
});

test('presents stable API error text and hides unknown transport details', () => {
  assert.equal(
    apiErrorMessage(
      {
        code: 'GAME_CODE_ALREADY_EXISTS',
        details: {},
        message: 'A game with this code already exists.',
      },
      'Fallback',
    ),
    'A game with this code already exists. (GAME_CODE_ALREADY_EXISTS)',
  );
  assert.equal(
    apiErrorMessage(new Error('socket details'), 'Fallback'),
    'Fallback',
  );
});
