import assert from 'node:assert/strict';
import test from 'node:test';

import {
  countGamesByStatus,
  filterGamesByStatus,
  GAME_STATUS_FILTERS,
  markGameArchived,
  upsertGame,
  validateGameDraft,
} from '../src/features/games/game-catalog-state.ts';
import { apiErrorMessage } from '../src/features/catalog/catalog-api-error.ts';

const game = {
  code: 'game-1',
  createdAt: '2026-07-26T10:00:00Z',
  id: '11111111-1111-4111-8111-111111111111',
  name: 'Game 1',
  status: 'active',
  updatedAt: '2026-07-26T10:00:00Z',
};

test('offers exactly the three accepted status filters', () => {
  assert.deepEqual(GAME_STATUS_FILTERS, ['active', 'draft', 'archived']);
});

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

test('filters games by exactly one status and preserves catalog order', () => {
  const draft = { ...game, id: 'game-2', name: 'Draft', status: 'draft' };
  const archived = {
    ...game,
    id: 'game-3',
    name: 'Archived',
    status: 'archived',
  };
  const secondActive = { ...game, id: 'game-4', name: 'Second active' };
  const games = [game, draft, archived, secondActive];

  assert.deepEqual(filterGamesByStatus(games, 'active'), [game, secondActive]);
  assert.deepEqual(filterGamesByStatus(games, 'draft'), [draft]);
  assert.deepEqual(filterGamesByStatus(games, 'archived'), [archived]);
  assert.deepEqual(games, [game, draft, archived, secondActive]);
});

test('counts every game status for filter badges', () => {
  assert.deepEqual(
    countGamesByStatus([
      game,
      { ...game, id: 'game-2', status: 'active' },
      { ...game, id: 'game-3', status: 'draft' },
      { ...game, id: 'game-4', status: 'archived' },
    ]),
    { active: 2, archived: 1, draft: 1 },
  );
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
