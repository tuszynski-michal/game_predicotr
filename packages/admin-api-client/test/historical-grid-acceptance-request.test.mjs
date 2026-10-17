import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('historical acceptance keeps game scope, confirmation, cursor and transport identities', async () => {
  const requests = [];
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requests.push({
        method: request.method,
        url: new URL(request.url),
        body: request.method === 'GET' ? null : await request.json(),
      });
      return Response.json({
        operationId: 'operation',
        statusOnly: true,
        materializesNewCells: false,
      });
    },
  });
  const game = '11111111-1111-4111-8111-111111111111';
  const operation = '22222222-2222-4222-8222-222222222222';
  const key = '33333333-3333-4333-8333-333333333333';
  await api.createHistoricalGridAcceptance(game, { idempotencyKey: key });
  await api.previewHistoricalGridAcceptanceNext(game, operation, {
    expectedCursor: 8,
  });
  await api.confirmHistoricalGridAcceptance(game, operation, {
    idempotencyKey: key,
    confirmed: true,
  });
  await api.runHistoricalGridAcceptanceNext(game, operation, {
    idempotencyKey: key,
    expectedCursor: 5,
  });
  await api.getHistoricalGridAcceptance(game, operation, 25);
  const base = `/api/v1/admin/image-review-items/geometry-completeness/${game}/historical-acceptance`;
  assert.deepEqual(
    requests.map((item) => item.url.pathname),
    [
      base,
      `${base}/${operation}/preview-next`,
      `${base}/${operation}/confirm`,
      `${base}/${operation}/run-next`,
      `${base}/${operation}`,
    ],
  );
  assert.deepEqual(
    requests.map((item) => item.method),
    ['POST', 'POST', 'POST', 'POST', 'GET'],
  );
  assert.deepEqual(requests[2].body, { idempotencyKey: key, confirmed: true });
  assert.deepEqual(requests[3].body, {
    idempotencyKey: key,
    expectedCursor: 5,
  });
  assert.equal(requests[4].url.searchParams.get('afterOrdinal'), '25');
});
