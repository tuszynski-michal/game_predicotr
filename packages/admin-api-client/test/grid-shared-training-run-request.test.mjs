import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('a shared grid-training run sends the other games cohorts in the same route', async () => {
  const calls = [];
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      calls.push({ url: request.url, body: await request.text() });
      return new Response('{}', {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    },
  });
  const game = '11111111-1111-4111-8111-111111111111';
  const body = {
    idempotencyKey: '33333333-3333-4333-8333-333333333333',
    cohortId: '44444444-4444-4444-8444-444444444444',
    presetId: 'grid-only-v1',
    presetFingerprint: 'a'.repeat(64),
    sharedCohorts: [
      {
        gameId: '55555555-5555-4555-8555-555555555555',
        cohortId: '66666666-6666-4666-8666-666666666666',
      },
    ],
  };
  await client.createGridTrainingRun(game, body);
  assert.equal(
    calls[0].url,
    `http://127.0.0.1:8000/api/v1/admin/games/${game}/grid-training-runs`,
  );
  assert.deepEqual(JSON.parse(calls[0].body), body);
});
