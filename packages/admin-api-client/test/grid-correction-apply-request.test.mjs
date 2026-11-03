import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('apply wrappers preserve explicit scope, confirmation and durable operation identity', async () => {
  const calls = [];
  const api = createAdminApiClient({
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
    learning = '22222222-2222-4222-8222-222222222222',
    apply = '33333333-3333-4333-8333-333333333333';
  const others = [
    '44444444-4444-4444-8444-444444444444',
    '55555555-5555-4555-8555-555555555555',
  ];
  const body = {
    idempotencyKey: '66666666-6666-4666-8666-666666666666',
    previewSha256: 'a'.repeat(64),
    additionalGameIds: others,
    confirmLimitedEvidence: true,
  };
  await api.previewGridCorrectionApply(game, learning, others);
  await api.startGridCorrectionApply(game, learning, body);
  await api.listGridCorrectionApply(game, learning);
  await api.getGridCorrectionApply(game, learning, apply);
  await api.resumeGridCorrectionApply(game, learning, apply);
  const root = `http://127.0.0.1:8000/api/v1/admin/games/${game}/grid-correction-learning/${learning}/apply`;
  assert.equal(calls[0].method, 'GET');
  assert.deepEqual(
    new URL(calls[0].url).searchParams.getAll('additionalGameIds'),
    others,
  );
  assert.deepEqual(
    calls.slice(1).map(({ method, url }) => [method, url]),
    [
      ['POST', root],
      ['GET', root],
      ['GET', `${root}/${apply}`],
      ['POST', `${root}/${apply}/resume`],
    ],
  );
  assert.deepEqual(JSON.parse(calls[1].body), body);
  assert.equal(calls[4].body, '');
});
