import assert from 'node:assert/strict';
import test from 'node:test';

import {
  archiveGameIdentity,
  restoreGameIdentity,
  saveGameIdentity,
} from '../src/features/games/game-catalog-actions.ts';

const savedGame = {
  code: 'game-1',
  createdAt: '2026-07-26T10:00:00Z',
  id: '11111111-1111-4111-8111-111111111111',
  name: 'Game 1',
  status: 'active',
  updatedAt: '2026-07-26T10:00:00Z',
};

function createClient(overrides = {}) {
  return {
    archiveGame: async () => ({ data: undefined }),
    createGame: async () => ({ data: savedGame }),
    listGames: async () => ({ data: [] }),
    updateGame: async () => ({ data: savedGame }),
    ...overrides,
  };
}

test('creates a game with its stable code through the typed client boundary', async () => {
  let request;
  const client = createClient({
    createGame: async (body) => {
      request = body;
      return { data: savedGame };
    },
  });

  const result = await saveGameIdentity(
    client,
    { mode: 'create' },
    { code: 'game-1', name: 'Game 1', status: 'active' },
  );

  assert.deepEqual(request, {
    code: 'game-1',
    name: 'Game 1',
    status: 'active',
  });
  assert.deepEqual(result, { game: savedGame, ok: true });
});

test('edits only mutable game identity fields and never sends the stable code', async () => {
  let gameId;
  let request;
  const client = createClient({
    updateGame: async (receivedGameId, body) => {
      gameId = receivedGameId;
      request = body;
      return { data: { ...savedGame, name: 'Renamed', status: 'draft' } };
    },
  });

  const result = await saveGameIdentity(
    client,
    { gameId: savedGame.id, mode: 'edit' },
    { code: 'attempted-change', name: 'Renamed', status: 'draft' },
  );

  assert.equal(gameId, savedGame.id);
  assert.deepEqual(request, { name: 'Renamed', status: 'draft' });
  assert.equal(result.ok, true);
});

test('archives by identifier and preserves a stable API error for the UI', async () => {
  let archivedGameId;
  const success = await archiveGameIdentity(
    createClient({
      archiveGame: async (gameId) => {
        archivedGameId = gameId;
        return { data: undefined };
      },
    }),
    savedGame.id,
  );
  const failure = await archiveGameIdentity(
    createClient({
      archiveGame: async () => ({
        error: {
          code: 'GAME_NOT_FOUND',
          details: {},
          message: 'Game not found.',
        },
      }),
    }),
    savedGame.id,
  );

  assert.equal(archivedGameId, savedGame.id);
  assert.deepEqual(success, { ok: true });
  assert.deepEqual(failure, {
    error: 'Game not found. (GAME_NOT_FOUND)',
    ok: false,
  });
});

test('restores an archived game as a draft without changing its identity', async () => {
  let gameId;
  let request;
  const archivedGame = { ...savedGame, status: 'archived' };
  const restoredGame = { ...savedGame, status: 'draft' };
  const result = await restoreGameIdentity(
    createClient({
      updateGame: async (receivedGameId, body) => {
        gameId = receivedGameId;
        request = body;
        return { data: restoredGame };
      },
    }),
    archivedGame,
  );

  assert.equal(gameId, savedGame.id);
  assert.deepEqual(request, { name: savedGame.name, status: 'draft' });
  assert.deepEqual(result, { game: restoredGame, ok: true });
});
