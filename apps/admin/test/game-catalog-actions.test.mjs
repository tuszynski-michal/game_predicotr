import assert from 'node:assert/strict';
import test from 'node:test';

import {
  archiveGameIdentity,
  loadGridEngineProfiles,
  restoreGameIdentity,
  saveGameIdentity,
} from '../src/features/games/game-catalog-actions.ts';

const savedGame = {
  code: 'game-1',
  createdAt: '2026-07-26T10:00:00Z',
  id: '11111111-1111-4111-8111-111111111111',
  expectedLayoutCount: 500000,
  name: 'Game 1',
  shapeGeometryConfiguration: 'requires_clarification',
  status: 'active',
  updatedAt: '2026-07-26T10:00:00Z',
};

function createClient(overrides = {}) {
  return {
    archiveGame: async () => ({ data: undefined }),
    createGame: async () => ({ data: savedGame }),
    getGame: async () => ({ data: savedGame }),
    listGames: async () => ({ data: [] }),
    listGridEngineProfiles: async () => ({ data: [] }),
    updateGame: async () => ({ data: savedGame }),
    ...overrides,
  };
}

test('creates a game with a grid engine profile as its page format', async () => {
  let request;
  const mumieGame = {
    ...savedGame,
    shapeGeometryConfiguration: 'grid_profile_mumie_v1',
  };
  const client = createClient({
    createGame: async (body) => {
      request = body;
      return { data: mumieGame };
    },
  });

  const result = await saveGameIdentity(
    client,
    { mode: 'create' },
    {
      code: 'mumie',
      expectedLayoutCount: '500000',
      name: 'Mumie',
      shapeGeometryConfiguration: 'grid_profile_mumie_v1',
      status: 'draft',
    },
  );

  assert.equal(request.shapeGeometryConfiguration, 'grid_profile_mumie_v1');
  assert.deepEqual(result, { game: mumieGame, ok: true });
});

test('loads grid engine profiles and reports a failure without throwing', async () => {
  const profile = { configuration: 'grid_profile_777_v2', status: 'missing' };
  assert.deepEqual(
    await loadGridEngineProfiles(
      createClient({
        listGridEngineProfiles: async () => ({ data: [profile] }),
      }),
    ),
    { ok: true, profiles: [profile] },
  );
  const failed = await loadGridEngineProfiles(
    createClient({
      listGridEngineProfiles: async () => ({
        error: { code: 'X', details: {}, message: 'broken' },
      }),
    }),
  );
  assert.equal(failed.ok, false);
  assert.match(failed.error, /broken/);
  const offline = await loadGridEngineProfiles(
    createClient({
      listGridEngineProfiles: async () => {
        throw new Error('socket');
      },
    }),
  );
  assert.equal(offline.ok, false);
  assert.match(offline.error, /modele silnika siatek/);
});

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
    {
      code: 'game-1',
      expectedLayoutCount: '500000',
      name: 'Game 1',
      shapeGeometryConfiguration: 'framed_full_page_v2',
      status: 'active',
    },
  );

  assert.deepEqual(request, {
    code: 'game-1',
    expectedLayoutCount: 500000,
    name: 'Game 1',
    shapeGeometryConfiguration: 'framed_full_page_v2',
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
    {
      code: 'attempted-change',
      expectedLayoutCount: '250',
      name: 'Renamed',
      shapeGeometryConfiguration: 'requires_clarification',
      status: 'draft',
    },
  );

  assert.equal(gameId, savedGame.id);
  assert.deepEqual(request, {
    expectedLayoutCount: 250,
    name: 'Renamed',
    shapeGeometryConfiguration: 'requires_clarification',
    status: 'draft',
  });
  assert.equal(result.ok, true);
});

test('reconciles an edit when the server saved it but the mutation response was lost', async () => {
  const editedGame = {
    ...savedGame,
    expectedLayoutCount: 750000,
    name: 'Game 1 edited',
    status: 'draft',
  };
  const result = await saveGameIdentity(
    createClient({
      getGame: async () => ({ data: editedGame }),
      updateGame: async () => ({ data: undefined }),
    }),
    { gameId: savedGame.id, mode: 'edit' },
    {
      code: savedGame.code,
      expectedLayoutCount: '750000',
      name: 'Game 1 edited',
      shapeGeometryConfiguration: 'requires_clarification',
      status: 'draft',
    },
  );

  assert.deepEqual(result, { game: editedGame, ok: true });
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
  assert.deepEqual(request, {
    expectedLayoutCount: 500000,
    name: savedGame.name,
    status: 'draft',
  });
  assert.deepEqual(result, { game: restoredGame, ok: true });
});
