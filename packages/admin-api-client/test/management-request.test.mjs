import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('management wrappers send generated routes, revisions, UUID and local-owner intent', async () => {
  const calls = [];
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      calls.push({
        url: request.url,
        method: request.method,
        intent: request.headers.get('X-Admin-Intent'),
        body: request.method === 'GET' ? null : await request.json(),
      });
      return new Response(JSON.stringify({}), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    },
  });
  const body = {
    operationId: 'operation-1',
    expectedRevision: 2,
    name: 'P',
    city: 'M',
    street: 'U',
    archived: false,
  };
  await client.getManagementSnapshot();
  await client.createManagementPoint(body);
  await client.updateManagementPoint('point', body);
  await client.createManagementMachine('point', {
    operationId: 'operation-2',
    expectedRevision: 0,
    name: 'M',
  });
  await client.updateManagementMachine('point', 'machine', {
    operationId: 'operation-3',
    expectedRevision: 1,
    name: 'M',
    archived: true,
  });
  await client.updateManagementAssignments('machine', {
    operationId: 'operation-4',
    expectedRevision: 3,
    gameIds: ['game'],
  });
  assert.deepEqual(
    calls.map((call) => [call.method, new URL(call.url).pathname]),
    [
      ['GET', '/api/v1/admin/management'],
      ['POST', '/api/v1/admin/management/points'],
      ['PUT', '/api/v1/admin/management/points/point'],
      ['POST', '/api/v1/admin/management/points/point/machines'],
      ['PUT', '/api/v1/admin/management/points/point/machines/machine'],
      ['PUT', '/api/v1/admin/management/machines/machine/assignments'],
    ],
  );
  assert.ok(calls.every((call) => call.intent === 'local-owner'));
  assert.deepEqual(calls[2].body, body);
});
