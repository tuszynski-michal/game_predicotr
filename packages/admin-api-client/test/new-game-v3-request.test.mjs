import assert from 'node:assert/strict';
import test from 'node:test';

import { createAdminApiClient } from '../src/index.ts';

test('new create and initial transfer use existing generated routes and preserve exact command keys', async () => {
  const requests = [];
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requests.push({
        path: new URL(request.url).pathname,
        method: request.method,
        body: await request.clone().json(),
      });
      return Response.json({});
    },
  });
  const key = '10040000-0000-4000-8000-000000000001';
  const create = {
    idempotencyKey: key,
    code: 'new-v3',
    name: 'New V3',
    gridModel: { mode: 'published', versionId: key },
  };
  await api.createGame(create);
  await api.createGame(create);
  const transfer = {
    idempotencyKey: key,
    expectedRevision: 0,
    versionId: key,
    mode: 'initial_transfer',
  };
  await api.activateGameGridModel(key, transfer);
  assert.deepEqual(
    requests.slice(0, 2).map((request) => request.body),
    [create, create],
  );
  assert.equal('shapeGeometryConfiguration' in requests[0].body, false);
  assert.equal(requests[0].path, '/api/v1/admin/games');
  assert.equal(
    requests[2].path,
    `/api/v1/admin/games/${key}/grid-model-assignment/activate`,
  );
  assert.deepEqual(requests[2].body, transfer);
});
