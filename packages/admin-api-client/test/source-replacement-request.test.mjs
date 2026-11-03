import assert from 'node:assert/strict';
import test from 'node:test';
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
