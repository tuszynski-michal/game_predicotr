import assert from 'node:assert/strict';
import test from 'node:test';

import { createAdminApiClient } from '../src/index.ts';

test('shadow job and result wrappers retain game scope and typed request body', async () => {
  const requests = [];
  const gameId = '11111111-1111-4111-8111-111111111111';
  const requestId = '22222222-2222-4222-8222-222222222222';
  const sourceImageId = '33333333-3333-4333-8333-333333333333';
  const resultId = '44444444-4444-4444-8444-444444444444';
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requests.push({
        url: new URL(request.url),
        method: request.method,
        body: request.method === 'POST' ? await request.clone().json() : null,
      });
      return Response.json({ id: requestId, items: [], nextCursor: null });
    },
  });
  await api.startGridShadowJob({
    gameId,
    requestId,
    sourceImageIds: [sourceImageId],
  });
  await api.listGridShadowResults({
    gameId,
    sourceImageId,
    limit: 1,
    cursor: 'next',
  });
  await api.getGridShadowResult(gameId, resultId);
  assert.equal(requests[0].method, 'POST');
  assert.equal(
    requests[0].url.pathname,
    `/api/v1/admin/games/${gameId}/grid-shadow-jobs`,
  );
  assert.deepEqual(requests[0].body, {
    requestId,
    sourceImageIds: [sourceImageId],
  });
  assert.equal(
    requests[1].url.pathname,
    `/api/v1/admin/games/${gameId}/grid-shadow-results`,
  );
  assert.equal(
    requests[1].url.searchParams.get('sourceImageId'),
    sourceImageId,
  );
  assert.equal(requests[1].url.searchParams.get('cursor'), 'next');
  assert.equal(requests[1].url.searchParams.get('limit'), '1');
  assert.equal(
    requests[2].url.pathname,
    `/api/v1/admin/games/${gameId}/grid-shadow-results/${resultId}`,
  );
});
