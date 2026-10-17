import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('grid-training run wrappers use scoped routes and exact bodies', async () => {
  const calls = [];
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      calls.push({
        url: request.url,
        method: request.method,
        body: request.method === 'POST' ? await request.text() : '',
      });
      return new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    },
  });
  const game = '11111111-1111-4111-8111-111111111111',
    run = '22222222-2222-4222-8222-222222222222';
  const body = {
    idempotencyKey: '33333333-3333-4333-8333-333333333333',
    cohortId: '44444444-4444-4444-8444-444444444444',
    presetId: 'grid-only-v1',
    presetFingerprint: 'a'.repeat(64),
  };
  await client.createGridTrainingRun(game, body);
  await client.listGridTrainingRuns(game);
  await client.getGridTrainingRun(game, run);
  await client.cancelGridTrainingRun(game, run);
  await client.resumeGridTrainingRun(game, run);
  const root = `http://127.0.0.1:8000/api/v1/admin/games/${game}/grid-training-runs`;
  assert.deepEqual(
    calls.map(({ url, method }) => [method, url]),
    [
      ['POST', root],
      ['GET', root],
      ['GET', `${root}/${run}`],
      ['POST', `${root}/${run}/cancel`],
      ['POST', `${root}/${run}/resume`],
    ],
  );
  assert.deepEqual(JSON.parse(calls[0].body), body);
  assert.equal(calls[3].body, '');
});
