import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { createAdminApiClient } from '../src/index.ts';

test('exact source mode, durable key/revision and GET exports stay in board-sources', async () => {
  const sent = [];
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      sent.push({
        path: new URL(request.url).pathname,
        method: request.method,
        body: request.method === 'GET' ? null : await request.json(),
      });
      return Response.json({ mode: 'replace_preserve_history' });
    },
  });
  const scope = {
    mode: 'replace_preserve_history',
    sourceIds: ['exact-source'],
  };
  const command = {
    ...scope,
    expectedRevision: 0,
    previewToken: 'a'.repeat(64),
    idempotencyKey: 'key',
  };
  await api.previewSourceReplacement('game', scope);
  await api.planSourceReplacement('game', command);
  await api.planSourceReplacement('game', command);
  await api.getSourceReplacementBatch('game', 'batch');
  assert.deepEqual(sent[0].body, scope);
  assert.deepEqual(sent[1].body, sent[2].body);
  assert.equal(sent[1].method, 'POST');
  assert.equal(sent[1].path, '/api/v1/admin/games/game/board-sources');
  assert.equal(sent[3].method, 'GET');
  assert.match(
    api.exportSourceReplacementUrl('game', 'batch', 'csv'),
    /board-sources\/batch\/export\?format=csv$/,
  );
});

test('retirement uses exact command and typed selected-gap export from the configured server', async () => {
  const fixture = JSON.parse(
    readFileSync(
      new URL('./fixtures/source-replacement-request-v1.json', import.meta.url),
      'utf8',
    ),
  );
  const sent = [];
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      sent.push({
        url: request.url,
        method: request.method,
        body: request.method === 'GET' ? null : await request.json(),
      });
      if (request.method === 'GET') return Response.json(fixture);
      return Response.json(
        request.method === 'POST'
          ? { action: 'retire' }
          : { phase: 'gap_open' },
      );
    },
  });
  const preview = {
    mode: 'replace_preserve_history',
    action: 'retire',
    batchId: fixture.batchId,
    entryId: fixture.entries[0].entryId,
    expectedRevision: 1,
  };
  await api.previewSourceRetirement(fixture.gameId, preview);
  const command = {
    ...preview,
    idempotencyKey: 'key',
    confirmed: true,
    previewToken: 'a'.repeat(64),
  };
  await api.executeSourceRetirement(fixture.gameId, command);
  await api.executeSourceRetirement(fixture.gameId, command);
  const exported = await api.exportSourceReplacementRequest(
    fixture.gameId,
    fixture.batchId,
    [fixture.entries[0].entryId],
  );
  assert.equal(sent[0].method, 'POST');
  assert.deepEqual(sent[0].body, preview);
  assert.equal(sent[1].method, 'DELETE');
  assert.deepEqual(sent[1].body, sent[2].body);
  assert.equal(
    new URL(sent[3].url).searchParams.get('entryIds'),
    fixture.entries[0].entryId,
  );
  assert.deepEqual(exported.data, fixture);
  assert.equal(fixture.schemaVersion, 'source-replacement-request-v1');
  assert.equal(fixture.allowedRanges[0].entryId, fixture.entries[0].entryId);
});
