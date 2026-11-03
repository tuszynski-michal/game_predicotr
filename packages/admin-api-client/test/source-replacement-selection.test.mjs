import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('generated selection request and wrapper preserve reservation and history metadata', async () => {
  const gameId = '11111111-1111-4111-8111-111111111111';
  const batchId = '22222222-2222-4222-8222-222222222222';
  const entryId = '33333333-3333-4333-8333-333333333333';
  const payload = {
    gameId,
    sequenceNumber: 7,
    state: 'reserved_gap',
    overrideRevision: 2,
    manualOverrideReviewItemId: null,
    replacementBatchId: batchId,
    replacementEntryId: entryId,
    replacementManifestUrl: `/api/v1/admin/games/${gameId}/board-sources/${batchId}`,
    candidates: [
      {
        reviewItemId: 'old',
        sourceState: 'retired',
        selectable: false,
        selected: false,
      },
    ],
  };
  const calls = [];
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      calls.push([request.method, new URL(request.url).pathname]);
      return Response.json(payload);
    },
  });
  const response = await client.getImageSequenceSourceSelection(gameId, 7);
  assert.deepEqual(calls, [
    ['GET', `/api/v1/admin/image-review-items/sequence-sources/${gameId}/7`],
  ]);
  assert.deepEqual(response.data, payload);
});
