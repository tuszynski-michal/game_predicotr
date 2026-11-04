import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

for (const policy of [
  'v3-engine-acceptance-v1',
  'v3-engine-acceptance-v2',
  'v3-engine-acceptance-v3',
]) {
  test(`grid reinference wrapper retains server policy ${policy}`, async () => {
    const api = createAdminApiClient({
      baseUrl: 'http://127.0.0.1:8000',
      fetch: async () =>
        Response.json({ operationId: 'operation', acceptancePolicy: policy }),
    });
    const result = await api.getGridReinference('game', 'operation');
    assert.equal(result.data.acceptancePolicy, policy);
  });
}

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

test('public recognition GET projections retain frozen and current scopes without mutation', async () => {
  const requests = [];
  const current = {
    scope: 'current_game',
    capabilities: {
      boardRows: 3,
      boardColumns: 5,
      pageRows: 3,
      pageColumns: 3,
    },
    evaluation: { state: 'qualified', reasonCodes: [] },
    automatic: {
      state: 'unqualified',
      reasonCodes: ['NEURAL_GRID_CALIBRATION_REQUIRED'],
    },
  };
  const frozen = {
    scope: 'frozen_operation',
    evaluation: { state: 'unqualified', reasonCodes: [] },
    automatic: { state: 'unqualified', reasonCodes: [] },
    reasonCodes: [],
    rescue: {
      state: 'foreign_scope',
      completedAttempts: 0,
      consumedAttempts: 0,
      reasonCodes: ['GRID_RESCUE_SLOT_BINDING_REQUIRED'],
    },
    completeness: { state: 'unavailable', measuredTargets: 0, reasonCodes: [] },
  };
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requests.push(request);
      return Response.json({
        recognitionStatus: request.url.includes('grid-model-assignment')
          ? current
          : frozen,
      });
    },
  });
  assert.deepEqual(
    (await api.getGameGridModelAssignment('game')).data.recognitionStatus,
    current,
  );
  assert.deepEqual(
    (await api.getGridReinference('game', 'operation')).data.recognitionStatus,
    frozen,
  );
  assert.ok(requests.every((request) => request.method === 'GET'));
  current.capabilities = null;
  current.evaluation = current.automatic = {
    state: 'unavailable',
    reasonCodes: ['NEURAL_GRID_STATUS_STORAGE_UNAVAILABLE'],
  };
  assert.deepEqual(
    (await api.getGameGridModelAssignment('game')).data.recognitionStatus,
    current,
  );
});
