import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';
test('physical source wrappers use existing preview and confirmed DELETE with exact replay body', async () => {
  const sent = [];
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      sent.push({
        method: request.method,
        path: new URL(request.url).pathname,
        headers: request.headers,
        body: await request.json(),
      });
      return Response.json(
        request.method === 'POST'
          ? { bytesToDelete: 123, fileCount: 1 }
          : {
              phase: 'gap_open',
              purge: { fileStatus: 'pending', deletedBytes: 0 },
            },
      );
    },
  });
  const preview = {
    mode: 'replace_delete_source',
    action: 'purge',
    batchId: 'batch',
    entryId: 'entry',
    expectedRevision: 2,
  };
  const command = {
    ...preview,
    previewToken: 'a'.repeat(64),
    idempotencyKey: 'same-key',
    confirmed: true,
  };
  assert.equal(
    (await api.previewSourcePurge('game', preview)).data.bytesToDelete,
    123,
  );
  assert.equal(
    (await api.executeSourcePurge('game', command)).data.purge.fileStatus,
    'pending',
  );
  await api.executeSourcePurge('game', command);
  assert.equal(sent[0].method, 'POST');
  assert.equal(
    sent[0].path,
    '/api/v1/admin/games/game/board-source-cleanup-preview',
  );
  assert.deepEqual(sent[0].body, preview);
  assert.equal(sent[1].method, 'DELETE');
  assert.equal(sent[1].path, '/api/v1/admin/games/game/board-sources');
  assert.deepEqual(sent[1].body, command);
  assert.deepEqual(sent[2].body, command);
  assert.ok([...sent[1].headers.values()].includes('board-source-ranges:game'));
});
