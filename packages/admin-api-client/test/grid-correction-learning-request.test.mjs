import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('screen correction mode and explicit rescue recipe remain pinned through preview/start', async () => {
  const calls = [];
  const detectorReadiness = {
    photos: 134,
    fullPhotos: 0,
    partialPhotos: 134,
    partialExcludedFromDetector: 134,
    roles: [],
    reasonCodes: ['SCREEN_FULL_PHOTOS_REQUIRED'],
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      calls.push(JSON.parse(await request.text()));
      return new Response(
        JSON.stringify({
          trainingMode: 'screen+grid',
          detectorReadiness,
          canStart: false,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    },
  });
  const game = '11111111-1111-4111-8111-111111111111';
  const command = {
    trainingMode: 'screen+grid',
    historicalCohorts: [
      {
        gameId: '22222222-2222-4222-8222-222222222222',
        cohortId: game,
        manifestSha256: 'c'.repeat(64),
      },
    ],
    rescueVariant: {
      contractVersion: 'grid-rescue-variant-v1',
      preprocessingContract: 'neural-grid-rescue-preprocessing-v1',
      board: { margin: 0.2 },
    },
  };
  const preview = await client.previewGridCorrectionLearning(game, command);
  assert.deepEqual(preview.data.detectorReadiness, detectorReadiness);
  assert.equal(preview.data.canStart, false);
  const start = {
    ...command,
    idempotencyKey: game,
    previewSha256: 'a'.repeat(64),
  };
  await client.startGridCorrectionLearning(game, start);
  assert.deepEqual(calls, [command, start]);
});

test('ready and preview preserve deduplicated progress, overlapping photos and exclusions', async () => {
  const progressCounts = {
    approved: { photos: 2, boards: 4 },
    availableTrain: { photos: 1, boards: 3 },
    usedTrain: { photos: 1, boards: 2 },
    newTrain: { photos: 1, boards: 1 },
    validation: { photos: 0, boards: 0 },
    regression: { photos: 0, boards: 0 },
    validationReserve: { photos: 5, boards: 0 },
    regressionReserve: { photos: 0, boards: 0 },
    buffers: { photos: 10, boards: 1 },
    excluded: { photos: 1, boards: 1 },
    exclusionReasons: [
      { reason: 'GRID_CORRECTION_BUFFER', photos: 1, boards: 1 },
    ],
  };
  const calls = [];
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      calls.push(request.method);
      return new Response(JSON.stringify({ progressCounts }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    },
  });
  const game = '11111111-1111-4111-8111-111111111111';
  assert.deepEqual(
    (await client.getGridCorrectionLearningReady(game)).data.progressCounts,
    progressCounts,
  );
  assert.deepEqual(
    (
      await client.previewGridCorrectionLearning(game, {
        importJobIds: [],
        exclusions: [],
      })
    ).data.progressCounts,
    progressCounts,
  );
  assert.deepEqual(calls, ['GET', 'POST']);
});

test('readiness carries server availability and lower-bound deficits unchanged', async () => {
  for (const dataAvailability of [
    null,
    {
      photos: 7,
      boards: 21,
      minimumPhotos: 20,
      minimumBoards: 60,
      photoDeficit: 13,
      boardDeficit: 39,
      splitStatus: 'minima',
    },
    {
      photos: 40,
      boards: 120,
      minimumPhotos: 20,
      minimumBoards: 60,
      photoDeficit: 0,
      boardDeficit: 0,
      splitStatus: 'infeasible',
    },
    {
      photos: 40,
      boards: 120,
      minimumPhotos: 20,
      minimumBoards: 60,
      photoDeficit: 0,
      boardDeficit: 0,
      splitStatus: 'ready',
    },
  ]) {
    const client = createAdminApiClient({
      baseUrl: 'http://127.0.0.1:8000',
      fetch: async () =>
        new Response(JSON.stringify({ dataAvailability }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
    });
    const result = await client.getGridCorrectionLearningReady(
      '11111111-1111-4111-8111-111111111111',
    );
    assert.deepEqual(result.data.dataAvailability, dataAvailability);
  }
});

test('learning and assigned comparison use pinned commands and read-only status routes', async () => {
  const calls = [];
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      calls.push([request.method, request.url, await request.text()]);
      return new Response('{}', {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    },
  });
  const game = '11111111-1111-4111-8111-111111111111';
  const run = '22222222-2222-4222-8222-222222222222';
  const preview = { importJobIds: [game], exclusions: [] };
  const start = {
    ...preview,
    idempotencyKey: run,
    previewSha256: 'a'.repeat(64),
  };
  const comparison = {
    idempotencyKey: run,
    versionId: run,
    gameId: game,
    cohortId: game,
  };
  await client.getGridCorrectionLearningReady(game);
  await client.previewGridCorrectionLearning(game, preview);
  await client.startGridCorrectionLearning(game, start);
  await client.listGridCorrectionLearning(game);
  await client.getGridCorrectionLearning(game, run);
  await client.cancelGridCorrectionLearning(game, run);
  await client.resumeGridCorrectionLearning(game, run);
  await client.getGridCorrectionLearningEvaluation(game, run);
  await client.createGridAssignedComparison(comparison);
  const root = `http://127.0.0.1:8000/api/v1/admin/games/${game}/grid-correction-learning`;
  assert.deepEqual(
    calls.map(([method, url]) => [method, url]),
    [
      ['GET', `${root}/ready`],
      ['POST', `${root}/preview`],
      ['POST', root],
      ['GET', root],
      ['GET', `${root}/${run}`],
      ['POST', `${root}/${run}/cancel`],
      ['POST', `${root}/${run}/resume`],
      ['GET', `${root}/${run}/evaluation`],
      [
        'POST',
        'http://127.0.0.1:8000/api/v1/admin/grid-model-evaluations/assigned-comparison',
      ],
    ],
  );
  assert.deepEqual(JSON.parse(calls[1][2]), preview);
  assert.deepEqual(JSON.parse(calls[2][2]), start);
  assert.deepEqual(JSON.parse(calls[8][2]), comparison);
  assert.equal(calls[4][2], '');
});
