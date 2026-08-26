import assert from 'node:assert/strict';
import test from 'node:test';

import {
  deleteSymbol,
  saveSymbol,
} from '../src/features/symbols/symbol-catalog-actions.ts';

const gameId = '11111111-1111-4111-8111-111111111111';
const savedSymbol = {
  code: 'LEMON',
  displayOrder: 1,
  gameId,
  id: '22222222-2222-4222-8222-222222222222',
  imagePath: null,
  isWildcard: false,
  mobileCode: 1,
  name: 'Lemon',
  nameEn: null,
  namePl: null,
  status: 'active',
};
const draft = { isWildcard: false, name: 'Lemon' };

function createClient(overrides = {}) {
  return {
    createSymbol: async () => ({ data: savedSymbol }),
    deleteSymbol: async () => ({ data: undefined }),
    listGames: async () => ({ data: [] }),
    listSymbols: async () => ({ data: [] }),
    symbolImageAssetUrl: () => '',
    updateSymbol: async () => ({ data: savedSymbol }),
    ...overrides,
  };
}

test('creates a manual symbol with only its name and joker flag', async () => {
  let request;
  const result = await saveSymbol(
    createClient({
      createSymbol: async (_currentGameId, body) => {
        request = body;
        return { data: savedSymbol };
      },
    }),
    gameId,
    { mode: 'create' },
    draft,
  );

  assert.deepEqual(request, draft);
  assert.deepEqual(result, { ok: true, symbol: savedSymbol });
});

test('edits only name and joker flag without changing stable identity', async () => {
  let request;
  const result = await saveSymbol(
    createClient({
      updateSymbol: async (_currentGameId, _symbolId, body) => {
        request = body;
        return { data: { ...savedSymbol, isWildcard: true } };
      },
    }),
    gameId,
    { mode: 'edit', symbolId: savedSymbol.id },
    { isWildcard: true, name: 'Lemon' },
  );

  assert.deepEqual(request, { isWildcard: true, name: 'Lemon' });
  assert.equal(result.ok, true);
});

test('deletes through the typed boundary and preserves API errors', async () => {
  let deletedGameId;
  let deletedSymbolId;
  const success = await deleteSymbol(
    createClient({
      deleteSymbol: async (currentGameId, symbolId) => {
        deletedGameId = currentGameId;
        deletedSymbolId = symbolId;
        return { data: undefined };
      },
    }),
    gameId,
    savedSymbol.id,
  );
  const failure = await deleteSymbol(
    createClient({
      deleteSymbol: async () => ({
        error: {
          code: 'SYMBOL_DELETE_BLOCKED',
          details: { rules: 1 },
          message: 'Symbol is still used.',
        },
      }),
    }),
    gameId,
    savedSymbol.id,
  );

  assert.equal(deletedGameId, gameId);
  assert.equal(deletedSymbolId, savedSymbol.id);
  assert.deepEqual(success, { ok: true });
  assert.deepEqual(failure, {
    error: 'Symbol is still used. (SYMBOL_DELETE_BLOCKED)',
    ok: false,
  });
});
