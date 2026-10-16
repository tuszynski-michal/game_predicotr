import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('quality measurement transport keeps exact game, scope and command identity', async () => {
  const sent = [];
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      sent.push({
        url: new URL(request.url),
        method: request.method,
        body: request.method === 'GET' ? null : await request.json(),
      });
      return Response.json({ items: [], nextCursor: null });
    },
  });
  const capture = {
    idempotencyKey: 'key',
    seed: 'replay-seed',
    sampleSize: 4,
    hardSourceIds: ['source'],
  };
  await api.listGridQualityMeasurements('game', { limit: 10 });
  await api.getGridQualityMeasurement('game', 'measurement');
  await api.captureGridQualityMeasurement('game', capture);
  await api.captureGridQualityMeasurement('game', capture);
  const approve = {
    idempotencyKey: 'approve-key',
    measurementId: 'measurement',
    sourceId: 'source',
    sampleKind: 'random',
    positionIndex: 0,
    manifestSha256: 'a'.repeat(64),
    targetSha256: 'b'.repeat(64),
  };
  await api.approveOperationalGeometry(
    'review',
    { gameId: 'game', importJobId: 'import' },
    approve,
  );
  await api.listSourceRecordingGroups('game', { sourceId: 'source', limit: 1 });
  assert.equal(
    sent[0].url.pathname,
    '/api/v1/admin/games/game/grid-quality-measurements',
  );
  assert.equal(sent[1].method, 'GET');
  assert.equal(sent[2].url.pathname, `${sent[0].url.pathname}/capture`);
  assert.deepEqual(sent[2].body, capture);
  assert.deepEqual(sent[3].body, capture);
  assert.equal(
    sent[4].url.pathname,
    '/api/v1/admin/image-reviews/review/geometry-approvals',
  );
  assert.equal(sent[4].url.searchParams.get('gameId'), 'game');
  assert.equal(sent[4].url.searchParams.get('importJobId'), 'import');
  assert.deepEqual(sent[4].body, approve);
  assert.equal(sent[5].url.searchParams.get('sourceId'), 'source');
});
