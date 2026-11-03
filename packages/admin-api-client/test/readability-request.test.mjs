import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('readability transport keeps pilot independent and exact retry/label identities', async () => {
  const sent = [];
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      sent.push({
        url: new URL(request.url),
        method: request.method,
        body: request.method === 'GET' ? null : await request.json(),
      });
      return Response.json({});
    },
  });
  const start = { idempotencyKey: 'key', kind: 'pilot', seed: 'draw' };
  const command = { idempotencyKey: 'fit-key', expectedRevision: 4 };
  const label = {
    idempotencyKey: 'label-key',
    targets: [
      { cellId: 'cell', expectedIdentity: 'a'.repeat(64), expectedRevision: 3 },
    ],
    state: 'readable',
    overlap: true,
  };
  await api.getReadabilityWorkspace('game');
  await api.startReadabilityRun('game', start);
  await api.startReadabilityRun('game', start);
  await api.listReadabilityItems('game', 'run', {
    offset: 250,
    historical: false,
    problem: 'overlap',
  });
  await api.labelReadabilityItems('game', 'run', label);
  await api.fitReadabilityPilot('game', 'run', command);
  await api.acceptReadabilityModel('game', 'model', command);
  assert.equal(
    sent[0].url.pathname,
    '/api/v1/admin/games/game/symbol-cell-reviews/readability/runs',
  );
  assert.deepEqual(sent[1].body, start);
  assert.deepEqual(sent[2].body, start);
  assert.equal(sent[3].url.searchParams.get('historical'), 'false');
  assert.equal(sent[3].url.searchParams.get('offset'), '250');
  assert.deepEqual(sent[4].body, label);
  assert.equal(sent[5].url.pathname, `${sent[0].url.pathname}/run/fit`);
  assert.deepEqual(sent[6].body, command);
  assert.equal(
    sent[6].url.pathname,
    '/api/v1/admin/games/game/symbol-cell-reviews/readability/models/model/accept',
  );
  assert.equal(
    api.exportReadabilityCsvUrl('game', 'run'),
    `${sent[0].url.origin}${sent[0].url.pathname}/run/export`,
  );
});
