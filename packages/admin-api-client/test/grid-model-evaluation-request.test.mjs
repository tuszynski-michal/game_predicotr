import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('grid model evaluation wrappers use admin routes and exact bodies', async () => {
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
  const version = '11111111-1111-4111-8111-111111111111',
    evaluation = '22222222-2222-4222-8222-222222222222',
    report = '55555555-5555-4555-8555-555555555555';
  const body = {
    idempotencyKey: '33333333-3333-4333-8333-333333333333',
    versionId: version,
    cohorts: [
      {
        gameId: '44444444-4444-4444-8444-444444444444',
        cohortId: '66666666-6666-4666-8666-666666666666',
      },
    ],
  };
  await client.createGridModelEvaluation(body);
  await client.listGridModelEvaluations(version);
  await client.getGridModelEvaluation(evaluation);
  await client.verifyGridModelEvaluationCurrentness(report);
  const root = 'http://127.0.0.1:8000/api/v1/admin/grid-model-evaluations';
  assert.deepEqual(
    calls.map(({ url, method }) => [method, url]),
    [
      ['POST', root],
      ['GET', `${root}?versionId=${version}`],
      ['GET', `${root}/${evaluation}`],
      ['POST', `${root}/reports/${report}/currentness`],
    ],
  );
  assert.deepEqual(JSON.parse(calls[0].body), body);
  assert.equal(calls[3].body, '');
});
