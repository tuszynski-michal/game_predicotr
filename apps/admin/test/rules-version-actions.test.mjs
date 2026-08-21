import assert from 'node:assert/strict';
import test from 'node:test';

import {
  archiveRulesVersion,
  createEditableRulesDraft,
  loadRulesVersionsForGame,
  loadPublicationReadiness,
  publishRulesVersion,
  saveRulesVersion,
} from '../src/features/rules/rules-version-actions.ts';

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
    archiveRulesVersion: async () => ({ data: undefined }),
    archivePayline: async () => ({ data: undefined }),
    createRulesVersion: async () => ({ data: savedRulesVersion }),
    createRulesDraftFromPublished: async () => ({
      data: {
        ...savedRulesVersion,
        id: 'draft-copy',
        status: 'draft',
        version: 2,
      },
    }),
    createPayline: async () => ({ data: undefined }),
    getRulesPublicationReadiness: async () => ({
      data: { issues: [], ready: true, rulesVersionId: savedRulesVersion.id },
    }),
    listGames: async () => ({ data: [] }),
    listPaylines: async () => ({ data: [] }),
    listRulesVersions: async () => ({ data: [] }),
    publishRulesVersion: async () => ({
      data: {
        ...savedRulesVersion,
        publishedAt: '2026-07-27T11:00:00Z',
        status: 'published',
      },
    }),
    updatePayline: async () => ({ data: undefined }),
    updateRulesVersion: async () => ({ data: savedRulesVersion }),
    ...overrides,
  };
}

test('opens one editable draft copied from the published workspace', async () => {
  let receivedId;
  const result = await createEditableRulesDraft(
    createClient({
      createRulesDraftFromPublished: async (rulesVersionId) => {
        receivedId = rulesVersionId;
        return {
          data: {
            ...savedRulesVersion,
            id: 'draft-copy',
            status: 'draft',
            version: 2,
          },
        };
      },
    }),
    savedRulesVersion.id,
  );

  assert.equal(receivedId, savedRulesVersion.id);
  assert.equal(result.ok, true);
  assert.equal(result.rulesVersion?.id, 'draft-copy');
});

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

test('reconciles a created draft when the mutation response is lost', async () => {
  let listCalls = 0;
  const result = await saveRulesVersion(
    createClient({
      createRulesVersion: async () => {
        throw new Error('response lost');
      },
      listRulesVersions: async () => {
        listCalls += 1;
        return { data: [savedRulesVersion] };
      },
    }),
    { gameId, mode: 'create' },
    draft,
    { timeoutMs: 20 },
  );

  assert.equal(listCalls, 1);
  assert.deepEqual(result, {
    ok: true,
    rulesVersion: savedRulesVersion,
  });
});

test('does not mask a stable create error with reconciliation', async () => {
  let listCalls = 0;
  const result = await saveRulesVersion(
    createClient({
      createRulesVersion: async () => ({
        error: {
          code: 'INVALID_RULES_ROWS',
          details: {},
          message: 'Rows are invalid.',
        },
      }),
      listRulesVersions: async () => {
        listCalls += 1;
        return { data: [savedRulesVersion] };
      },
    }),
    { gameId, mode: 'create' },
    draft,
  );

  assert.equal(listCalls, 0);
  assert.deepEqual(result, {
    error: 'Rows are invalid. (INVALID_RULES_ROWS)',
    ok: false,
  });
});

test('bounds a hanging create and reconciliation request', async () => {
  const never = () => new Promise(() => {});
  const startedAt = Date.now();
  const result = await saveRulesVersion(
    createClient({
      createRulesVersion: never,
      listRulesVersions: never,
    }),
    { gameId, mode: 'create' },
    draft,
    { timeoutMs: 5 },
  );

  assert.equal(result.ok, false);
  assert.match(result.error, /Nie udało się potwierdzić zapisu reguł/);
  assert.ok(Date.now() - startedAt < 500);
});

test('bounds loading the rules catalog', async () => {
  const result = await loadRulesVersionsForGame(
    createClient({
      listRulesVersions: () => new Promise(() => {}),
    }),
    gameId,
    { timeoutMs: 5 },
  );

  assert.deepEqual(result, {
    error: 'Lokalne Admin API nie zakończyło pobierania wersji reguł.',
    ok: false,
  });
});

test('loads readiness, publishes and maps archive to local immutable state', async () => {
  const readiness = await loadPublicationReadiness(
    createClient(),
    savedRulesVersion.id,
  );
  const published = await publishRulesVersion(
    createClient(),
    savedRulesVersion.id,
  );
  const archived = await archiveRulesVersion(createClient(), {
    ...savedRulesVersion,
    publishedAt: '2026-07-27T11:00:00Z',
    status: 'published',
  });

  assert.equal(readiness.ok, true);
  assert.equal(readiness.readiness.ready, true);
  assert.equal(published.ok, true);
  assert.equal(published.rulesVersion.status, 'published');
  assert.equal(archived.ok, true);
  assert.equal(archived.rulesVersion.status, 'archived');
  assert.equal(archived.rulesVersion.publishedAt, '2026-07-27T11:00:00Z');
});

test('preserves a stable publication conflict returned by the API', async () => {
  const result = await publishRulesVersion(
    createClient({
      publishRulesVersion: async () => ({
        error: {
          code: 'RULES_VERSION_NOT_READY',
          details: { issues: [] },
          message: 'Rules version has publication blockers.',
        },
      }),
    }),
    savedRulesVersion.id,
  );

  assert.deepEqual(result, {
    error: 'Rules version has publication blockers. (RULES_VERSION_NOT_READY)',
    ok: false,
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
