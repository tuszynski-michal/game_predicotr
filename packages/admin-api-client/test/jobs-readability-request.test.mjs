import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('Jobs wrapper reads readability jobs without dropping their counters or error', async () => {
  const game = '11111111-1111-4111-8111-111111111111';
  const id = '22222222-2222-4222-8222-222222222222';
  const job = {
    id,
    gameId: game,
    jobType: 'symbol_readability',
    status: 'failed',
    inputPayload: {
      schemaVersion: 1,
      workflow: 'symbol_readability',
      action: 'prepare',
      identifier: id,
    },
    progress: {
      current: 7,
      total: 15,
      stage: 'symbol_readability_prepare',
      succeeded: 7,
      failed: 0,
      review: 0,
    },
    error: { code: 'JOB_EXECUTION_FAILED', message: 'OperationalError' },
  };
  const calls = [];
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      const url = new URL(request.url);
      calls.push({
        method: request.method,
        path: url.pathname,
        query: url.search,
      });
      return Response.json(url.pathname.endsWith(id) ? job : [job]);
    },
  });
  const list = await client.listJobs({
    gameId: game,
    jobType: 'symbol_readability',
    limit: 10,
  });
  const detail = await client.getJob(id);
  assert.deepEqual(list.data, [job]);
  assert.deepEqual(detail.data, job);
  assert.deepEqual(calls, [
    {
      method: 'GET',
      path: '/api/v1/admin/jobs',
      query: `?job_type=symbol_readability&game_id=${game}&limit=10`,
    },
    { method: 'GET', path: `/api/v1/admin/jobs/${id}`, query: '' },
  ]);
});
