import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('run preview wrapper sends one scoped GET without a body', async () => {
  const calls = [];
  const preview = {
    policy: 'grid-training-admission-v1',
    selectedPresetId: 'grid-only-v1',
    apiBlockers: [],
    pendingWorkerChecks: ['GPU_AVAILABLE'],
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      calls.push({
        url: request.url,
        method: request.method,
        body: await request.text(),
      });
      return new Response(JSON.stringify(preview), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    },
  });
  const game = '11111111-1111-4111-8111-111111111111',
    cohort = '22222222-2222-4222-8222-222222222222';
  const result = await client.previewGridTrainingRun(game, cohort);
  assert.deepEqual(result.data, preview);
  assert.deepEqual(calls, [
    {
      url: `http://127.0.0.1:8000/api/v1/admin/games/${game}/grid-training-cohorts/${cohort}/run-preview`,
      method: 'GET',
      body: '',
    },
  ]);
});
