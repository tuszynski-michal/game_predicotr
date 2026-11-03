import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { createAdminApiClient } from '../src/index.ts';

test('generated wrapper transmits replacement selection and entry working/restore requests', async () => {
  const request = JSON.parse(
    readFileSync(
      new URL('./fixtures/source-replacement-request-v1.json', import.meta.url),
      'utf8',
    ),
  );
  const entryId = request.entries[0].entryId;
  const selection = {
    request,
    selectedEntryIds: [entryId],
    files: [
      {
        entryId,
        fileName: 'seq_1-9.jpg',
        checksumSha256: 'a'.repeat(64),
        rangeStart: 1,
        rangeEnd: 9,
        operationId: 'committed',
      },
    ],
  };
  const sent = [];
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (input) => {
      sent.push({
        path: new URL(input.url).pathname,
        method: input.method,
        body: input.method === 'GET' ? null : await input.json(),
      });
      return Response.json({});
    },
  });
  await api.createBrowserImageSelection({
    displayName: 'ready',
    gameId: request.gameId,
    expectedFileCount: 1,
    expectedTotalBytes: 100,
    idempotencyKey: 'stable',
    replacementSelection: selection,
  });
  await api.previewReadyBrowserImageImport('upload', {
    gameId: request.gameId,
    replacementSelection: selection,
  });
  await api.startReadyBrowserImageImport('upload', {
    gameId: request.gameId,
    manifestChecksumSha256: 'b'.repeat(64),
    preflightChecksumSha256: 'c'.repeat(64),
    replacementSelection: selection,
  });
  await api.getSourceReplacementWorking(
    request.gameId,
    request.batchId,
    entryId,
  );
  const command = {
    batchId: request.batchId,
    entryId,
    expectedRevision: 4,
    idempotencyKey: 'restore',
    confirmed: true,
    actor: 'local-admin',
    readability: [
      { cellId: 'cell', identity: 'identity', revision: 2, readable: true },
    ],
  };
  await api.restoreSourceReplacementEntry(request.gameId, command);
  for (const call of sent.slice(0, 3))
    assert.deepEqual(call.body.replacementSelection, selection);
  assert.equal(sent[3].method, 'GET');
  assert.equal(
    sent[3].path,
    `/api/v1/admin/games/${request.gameId}/board-sources/${request.batchId}/entries/${entryId}/working`,
  );
  assert.equal(sent[4].method, 'POST');
  assert.match(sent[4].path, /\/restore$/);
  assert.deepEqual(sent[4].body, command);
});
