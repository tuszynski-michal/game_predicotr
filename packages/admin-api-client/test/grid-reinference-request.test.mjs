import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('grid reinference preserves exact commands, game scope and confirmation targets', async () => {
  const requests = [];
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requests.push({
        path: new URL(request.url),
        method: request.method,
        headers: request.headers,
        body: request.method === 'GET' ? null : await request.json(),
      });
      return Response.json({ operationId: 'operation' });
    },
  });
  const game = '11111111-1111-4111-8111-111111111111';
  const operation = '22222222-2222-4222-8222-222222222222';
  const key = '33333333-3333-4333-8333-333333333333';
  const base = `/api/v1/admin/image-review-items/grid-reinference/${game}`;
  const command = {
    idempotencyKey: key,
    expectedRevision: 2,
    manifestSha256: 'a'.repeat(64),
  };
  await api.prepareGridReinference(game, { idempotencyKey: key });
  await api.getGridReinference(game, operation);
  await api.getGridReinferenceTargets(game, operation, 'bound-cursor', 25);
  await api.freezeGridReinference(game, operation, command);
  await api.acknowledgeGridReinferencePilot(game, operation, {
    idempotencyKey: key,
    expectedRevision: 3,
    pilotOperationId: game,
    pilotReportSha256: 'b'.repeat(64),
  });
  await api.startGridReinference(game, operation, {
    ...command,
    expectedRevision: 4,
    broadScopeConfirmed: true,
  });
  await api.resumeGridReinference(game, operation, {
    idempotencyKey: key,
    expectedRevision: 5,
    expectedPhase: 'infer',
  });
  await api.cancelGridReinference(game, operation, {
    idempotencyKey: key,
    expectedRevision: 6,
  });
  assert.deepEqual(
    requests.map((item) => item.path.pathname),
    [
      `${base}/prepare`,
      `${base}/operations/${operation}`,
      `${base}/operations/${operation}/targets`,
      ...['freeze', 'pilot-ack', 'start', 'resume', 'cancel'].map(
        (action) => `${base}/operations/${operation}/${action}`,
      ),
    ],
  );
  assert.deepEqual(requests[3].body, command);
  assert.equal(requests[2].path.searchParams.get('cursor'), 'bound-cursor');
  assert.equal(requests[2].path.searchParams.get('limit'), '25');
  assert.equal(requests[5].body.broadScopeConfirmed, true);
  assert.equal(requests[6].body.expectedPhase, 'infer');
});

test('grid operation history uses bounded game-scoped GET and generated statistics response', async () => {
  const requests = [];
  const response = {
    items: [
      {
        operationId: 'operation',
        statsPolicy: null,
        scopeStats: null,
        effectStats: null,
      },
    ],
    nextCursor: 'next',
  };
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requests.push({ url: new URL(request.url), method: request.method });
      return Response.json(response);
    },
  });
  const result = await api.listGridReinferenceOperations('game', {
    cursor: 'bound-cursor',
    limit: 50,
    compatibleWithOperationId: 'broad-operation',
  });
  assert.equal(requests[0].method, 'GET');
  assert.equal(
    requests[0].url.pathname,
    '/api/v1/admin/image-review-items/grid-reinference/game/operations',
  );
  assert.equal(requests[0].url.searchParams.get('limit'), '50');
  assert.equal(requests[0].url.searchParams.get('cursor'), 'bound-cursor');
  assert.equal(
    requests[0].url.searchParams.get('compatible_with_operation_id'),
    'broad-operation',
  );
  assert.deepEqual(result.data, response);
});
