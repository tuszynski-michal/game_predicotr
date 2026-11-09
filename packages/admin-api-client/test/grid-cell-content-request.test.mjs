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

test('readiness wrapper keeps unresolved live boards separate from frozen evidence', async () => {
  const game = '11111111-1111-4111-8111-111111111111';
  const role = {
    state: 'evaluable',
    reasonCodes: [],
    boards: 2,
    slots: 30,
    unapprovedSlots: 0,
    unresolvedPhotos: 0,
    states: { visible: 30, unknown: 0, occluded: 0, out_of_frame: 0 },
    fullPhotos: 0,
    missingFullPhotos: 0,
  };
  const coverage = {
    version: 'source-cell-content-v1',
    state: 'evaluable',
    games: { [game]: { TRAIN: role } },
  };
  const report = {
    ...coverage,
    basis: 'frozen_content_pins',
    frozenPinCoverage: coverage,
    annotationProgress: {
      ...coverage,
      state: 'not_evaluable',
      games: {
        [game]: {
          TRAIN: {
            ...role,
            state: 'not_evaluable',
            reasonCodes: ['CONTENT_SEQUENCE_CONFLICT', 'CONTENT_UNKNOWN_LIMIT'],
            unapprovedSlots: 15,
            states: { ...role.states, visible: 15, unknown: 15 },
          },
        },
      },
    },
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async () =>
      new Response(JSON.stringify(report), {
        headers: { 'Content-Type': 'application/json' },
      }),
  });
  const response = await client.getGridContentReadiness(
    game,
    game,
    'a'.repeat(64),
  );
  assert.deepEqual(response.data, report);
  assert.equal(response.data.state, 'evaluable');
  assert.equal(response.data.annotationProgress.games[game].TRAIN.slots, 30);
  assert.equal(
    response.data.annotationProgress.games[game].TRAIN.unapprovedSlots,
    15,
  );
});

test('target metadata and plain asset wrappers pin exact cohort and manifest', async () => {
  const calls = [];
  const game = '11111111-1111-4111-8111-111111111111';
  const source = '22222222-2222-4222-8222-222222222222';
  const pins = { cohortId: game, manifestSha256: 'a'.repeat(64) };
  const page = {
    version: 'source-cell-content-targets-v1',
    gameId: game,
    ...pins,
    items: [
      {
        source: {
          sourceId: source,
          sourceSha256: 'b'.repeat(64),
          sourceRepresentativeSha256: 'c'.repeat(64),
          width: 320,
          height: 240,
          coordinateSpace: 'exif-normalized-rgb-pixels-v1',
          normalizationAdapterVersion:
            'image-normalization-v2-in-memory-source-v1',
        },
        displayName: null,
        positionIndex: 0,
        sequenceNumber: null,
        role: 'B',
        state: 'unresolved',
        reasonCodes: ['CONTENT_SEQUENCE_CONFLICT'],
      },
    ],
    nextOffset: 3,
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000/',
    fetch: async (request) => {
      calls.push(request);
      return new Response(JSON.stringify(page), {
        headers: { 'Content-Type': 'application/json' },
      });
    },
  });
  const prefix = `http://127.0.0.1:8000/api/v1/admin/games/${game}/grid-quality-measurements/content-targets`;
  const query = `cohortId=${game}&manifestSha256=${pins.manifestSha256}`;
  const result = await client.listGridContentTargets(game, {
    ...pins,
    limit: 2,
    offset: 1,
  });
  assert.deepEqual(result.data, page);
  assert.equal(calls[0].method, 'GET');
  assert.equal(calls[0].url, `${prefix}?${query}&limit=2&offset=1`);
  await client.getGridContentTargetSource(game, source, pins);
  assert.equal(calls[1].url, `${prefix}/sources/${source}/asset?${query}`);
  assert.equal(
    client.gridContentTargetSourceUrl(game, source, pins),
    calls[1].url,
  );
  assert.equal(
    new URL(client.gridContentTargetSourceUrl('a/b', 'x/y', pins)).pathname,
    '/api/v1/admin/games/a%2Fb/grid-quality-measurements/content-targets/sources/x%2Fy/asset',
  );
});
