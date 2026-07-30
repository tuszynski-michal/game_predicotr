import assert from 'node:assert/strict';
import test from 'node:test';

import {
  archiveSymbol,
  saveSymbol,
} from '../src/features/symbols/symbol-catalog-actions.ts';

const gameId = '11111111-1111-4111-8111-111111111111';
const savedSymbol = {
  code: 'S1',
  displayOrder: 10,
  gameId,
  id: '22222222-2222-4222-8222-222222222222',
  imagePath: 'symbols/game-1/s1.png',
  isWildcard: false,
  mobileCode: 1,
  name: 'Symbol 1',
  status: 'active',
};
const draft = {
  code: 'S1',
  displayOrder: 10,
  imagePath: 'symbols/game-1/s1.png',
  isWildcard: false,
  mobileCode: 1,
  name: 'Symbol 1',
  status: 'active',
};

function createClient(overrides = {}) {
  return {
    archiveSymbol: async () => ({ data: undefined }),
    createSymbol: async () => ({ data: savedSymbol }),
    listGames: async () => ({ data: [] }),
    listSymbols: async () => ({ data: [] }),
    updateSymbol: async () => ({ data: savedSymbol }),
    ...overrides,
  };
}

test('creates a symbol with the complete typed contract', async () => {
  let receivedGameId;
  let request;
  const result = await saveSymbol(
    createClient({
      createSymbol: async (currentGameId, body) => {
        receivedGameId = currentGameId;
        request = body;
        return { data: savedSymbol };
      },
    }),
    gameId,
    { mode: 'create' },
    draft,
  );

  assert.equal(receivedGameId, gameId);
  assert.deepEqual(request, {
    code: 'S1',
    displayOrder: 10,
    imagePath: 'symbols/game-1/s1.png',
    isWildcard: false,
    mobileCode: 1,
    name: 'Symbol 1',
    status: 'active',
  });
  assert.deepEqual(result, { ok: true, symbol: savedSymbol });
});

test('updates mutable fields without sending stable code or mobileCode', async () => {
  let receivedGameId;
  let receivedSymbolId;
  let request;
  const result = await saveSymbol(
    createClient({
      updateSymbol: async (currentGameId, symbolId, body) => {
        receivedGameId = currentGameId;
        receivedSymbolId = symbolId;
        request = body;
        return {
          data: { ...savedSymbol, imagePath: null, isWildcard: true },
        };
      },
    }),
    gameId,
    { mode: 'edit', symbolId: savedSymbol.id },
    { ...draft, imagePath: null, isWildcard: true },
  );

  assert.equal(receivedGameId, gameId);
  assert.equal(receivedSymbolId, savedSymbol.id);
  assert.deepEqual(request, {
    displayOrder: 10,
    imagePath: null,
    isWildcard: true,
    name: 'Symbol 1',
    status: 'active',
  });
  assert.equal(result.ok, true);
});

test('archives through the typed boundary and preserves API errors', async () => {
  let archivedGameId;
  let archivedSymbolId;
  const success = await archiveSymbol(
    createClient({
      archiveSymbol: async (currentGameId, symbolId) => {
        archivedGameId = currentGameId;
        archivedSymbolId = symbolId;
        return { data: undefined };
      },
    }),
    gameId,
    savedSymbol.id,
  );
  const failure = await archiveSymbol(
    createClient({
      archiveSymbol: async () => ({
        error: {
          code: 'SYMBOL_NOT_FOUND',
          details: {},
          message: 'Symbol not found.',
        },
      }),
    }),
    gameId,
    savedSymbol.id,
  );

  assert.equal(archivedGameId, gameId);
  assert.equal(archivedSymbolId, savedSymbol.id);
  assert.deepEqual(success, { ok: true });
  assert.deepEqual(failure, {
    error: 'Symbol not found. (SYMBOL_NOT_FOUND)',
    ok: false,
  });
});
