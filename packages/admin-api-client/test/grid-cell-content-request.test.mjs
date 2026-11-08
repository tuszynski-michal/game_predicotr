import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('content wrappers preserve independent CAS and blind session bodies', async () => {
  const calls = [];
  const missing = {
    version: 'source-cell-content-v1',
    state: 'not_evaluable',
    games: {},
  };
  const readiness = {
    ...missing,
    basis: 'frozen_content_pins',
    annotationProgress: { ...missing, state: 'evaluable' },
    frozenPinCoverage: missing,
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      calls.push({
        url: request.url,
        method: request.method,
        body:
          request.method === 'POST' ? JSON.parse(await request.text()) : null,
      });
      return new Response(
        JSON.stringify(
          request.url.includes('/content-readiness?')
            ? readiness
            : { items: [] },
        ),
        {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        },
      );
    },
  });
  const game = '11111111-1111-4111-8111-111111111111';
  const session = '22222222-2222-4222-8222-222222222222';
  const source = '33333333-3333-4333-8333-333333333333';
  const key = '44444444-4444-4444-8444-444444444444';
  const prefix = `http://127.0.0.1:8000/api/v1/admin/games/${game}/grid-quality-measurements`;
  const create = {
    idempotencyKey: key,
    cohortId: session,
    expectedManifestSha256: 'a'.repeat(64),
    sourceIds: [source],
    targetSelection: [{ sourceId: source, positionIndices: [0, 1, 2] }],
  };
  const observe = {
    idempotencyKey: key,
    expectedSessionRevision: 3,
    passNumber: 2,
    sourceId: source,
    positionIndex: 1,
    humanApproval: true,
    cells: Array.from({ length: 15 }, () => ({ state: 'unknown' })),
    measuredNodes: Array.from({ length: 24 }, (_, i) => [
      i % 6,
      Math.floor(i / 6),
    ]),
  };
  const reference = {
    idempotencyKey: key,
    sourceId: source,
    positionIndex: 0,
    sequenceNumber: 123,
    expectedRevision: 7,
    expectedSourceSha256: 'b'.repeat(64),
    expectedPixelSha256: 'c'.repeat(64),
    humanApproval: true,
    cells: observe.cells,
  };
  await client.createGridContentSession(game, create);
  await client.writeGridBlindContentObservation(game, session, observe);
  await client.writeGridCellContentReference(game, reference);
  await client.advanceGridContentSession(game, session, {
    idempotencyKey: key,
    expectedSessionRevision: 4,
  });
  await client.getGridContentSession(game, session);
  await client.listGridContentSessions(game, 5);
  await client.getGridCellContentReference(game, source, 0);
  const coverage = await client.getGridContentReadiness(
    game,
    session,
    'a'.repeat(64),
  );
  assert.deepEqual(coverage.data, readiness);
  const sampling = {
    baseVersionId: session,
    familyId: game,
    importJobIds: [source],
    trainingMode: 'grid-only',
  };
  await client.previewGridContentSampling(game, sampling);
  assert.deepEqual(
    calls.slice(0, 3).map((c) => c.body),
    [create, observe, reference],
  );
  assert.equal(calls[0].url, `${prefix}/content-sessions`);
  assert.equal(
    calls[1].url,
    `${prefix}/content-sessions/${session}/observations`,
  );
  assert.equal(calls[2].url, `${prefix}/content-references`);
  assert.equal(calls[3].url, `${prefix}/content-sessions/${session}/advance`);
  assert.equal(calls[4].method, 'GET');
  assert.equal(calls[5].url, `${prefix}/content-sessions?limit=5`);
  assert.equal(calls[6].url, `${prefix}/content-references/${source}/0`);
  assert.equal(
    calls[7].url,
    `${prefix}/content-readiness?cohortId=${session}&manifestSha256=${'a'.repeat(64)}`,
  );
  assert.deepEqual(calls[8].body, sampling);
  assert.equal(calls[8].method, 'POST');
  assert.equal(calls[8].url, `${prefix}/content-sampling-preview`);
  assert.equal(
    client.gridContentSessionSourceUrl(game, session, source),
    `${prefix}/content-sessions/${session}/sources/${source}/asset`,
  );
});
