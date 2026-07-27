import assert from 'node:assert/strict';
import test from 'node:test';

import { saveRulesVersion } from '../src/features/rules/rules-version-actions.ts';

const gameId = '11111111-1111-4111-8111-111111111111';
const savedRulesVersion = {
  columns: 5,
  createdAt: '2026-07-27T10:00:00Z',
  gameId,
  id: '22222222-2222-4222-8222-222222222222',
  publishedAt: null,
  rows: 3,
  spinCost: 10,
  status: 'draft',
  version: 1,
};
const draft = { columns: 5, rows: 3, spinCost: 10 };

function createClient(overrides = {}) {
  return {
    archivePayline: async () => ({ data: undefined }),
    createRulesVersion: async () => ({ data: savedRulesVersion }),
    createPayline: async () => ({ data: undefined }),
    listGames: async () => ({ data: [] }),
    listPaylines: async () => ({ data: [] }),
    listRulesVersions: async () => ({ data: [] }),
    updatePayline: async () => ({ data: undefined }),
    updateRulesVersion: async () => ({ data: savedRulesVersion }),
    ...overrides,
  };
}

test('creates a server-numbered rules draft with dimensions and cost only', async () => {
  let receivedGameId;
  let request;
  const result = await saveRulesVersion(
    createClient({
      createRulesVersion: async (currentGameId, body) => {
        receivedGameId = currentGameId;
        request = body;
        return { data: savedRulesVersion };
      },
    }),
    { gameId, mode: 'create' },
    draft,
  );

  assert.equal(receivedGameId, gameId);
  assert.deepEqual(request, { columns: 5, rows: 3, spinCost: 10 });
  assert.equal('version' in request, false);
  assert.equal('status' in request, false);
  assert.deepEqual(result, {
    ok: true,
    rulesVersion: savedRulesVersion,
  });
});

test('updates the selected draft and preserves a stable API error', async () => {
  let receivedId;
  const success = await saveRulesVersion(
    createClient({
      updateRulesVersion: async (rulesVersionId, body) => {
        receivedId = rulesVersionId;
        return {
          data: { ...savedRulesVersion, ...body },
        };
      },
    }),
    { mode: 'edit', rulesVersionId: savedRulesVersion.id },
    { columns: 6, rows: 4, spinCost: 25 },
  );
  const failure = await saveRulesVersion(
    createClient({
      updateRulesVersion: async () => ({
        error: {
          code: 'RULES_VERSION_IMMUTABLE',
          details: {},
          message: 'Only a draft rules version can be changed.',
        },
      }),
    }),
    { mode: 'edit', rulesVersionId: savedRulesVersion.id },
    draft,
  );

  assert.equal(receivedId, savedRulesVersion.id);
  assert.equal(success.ok, true);
  assert.deepEqual(failure, {
    error:
      'Only a draft rules version can be changed. (RULES_VERSION_IMMUTABLE)',
    ok: false,
  });
});
