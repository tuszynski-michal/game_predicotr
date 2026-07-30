import assert from 'node:assert/strict';
import test from 'node:test';

import {
  freezeVerifiedCohort,
  loadVerifiedCohortHistory,
  loadOperationalReviewGames,
  loadOperationalReviewJobs,
  loadOperationalReviewPage,
  loadOperationalReviewSymbols,
  previewOperationalReviewGeometry,
  resolveOperationalReview,
  saveOperationalReviewGeometry,
} from '../src/features/operational-reviews/operational-review-actions.ts';

const activeGame = {
  code: 'blazing-hot',
  createdAt: '2026-07-29T10:00:00Z',
  id: 'game-1',
  name: 'Blazing Hot',
  status: 'active',
  updatedAt: '2026-07-29T10:00:00Z',
};

const archivedGame = {
  ...activeGame,
  code: 'archived',
  id: 'game-2',
  name: 'Archiwalna',
  status: 'archived',
};

function job(id, importKind, createdAt) {
  return {
    attemptCount: 0,
    cancelRequestedAt: null,
    createdAt,
    error: null,
    finishedAt: null,
    gameId: activeGame.id,
    heartbeatAt: null,
    id,
    inputPayload:
      importKind === 'image_directory'
        ? {
            importKind,
            pipelineFingerprint: 'a'.repeat(64),
            schemaVersion: 1,
          }
        : {
            contractVersion: 1,
            fileFormat: 'csv',
            importKind,
            schemaVersion: 1,
            sourceChecksum: 'b'.repeat(64),
            sourcePath: 'layouts.csv',
            sourceSizeBytes: 20,
          },
    jobType: 'import',
    leaseExpiresAt: null,
    progress: {
      current: 0,
      failed: 0,
      review: 0,
      stage: null,
      succeeded: 0,
      total: null,
    },
    startedAt: null,
    status: 'created',
    updatedAt: createdAt,
    workerVersion: null,
  };
}

test('loads only active games and image-directory jobs in stable order', async () => {
  const games = await loadOperationalReviewGames({
    listGames: async () => ({
      data: [
        archivedGame,
        { ...activeGame, id: 'game-3', name: 'Alpha' },
        activeGame,
      ],
    }),
  });
  assert.equal(games.ok, true);
  assert.deepEqual(
    games.games.map((game) => game.name),
    ['Alpha', 'Blazing Hot'],
  );

  let receivedFilters;
  const jobs = await loadOperationalReviewJobs(
    {
      listJobs: async (filters) => {
        receivedFilters = filters;
        return {
          data: [
            job('image-old', 'image_directory', '2026-07-29T09:00:00Z'),
            job('layout', 'layout_file', '2026-07-29T11:00:00Z'),
            job('image-new', 'image_directory', '2026-07-29T10:00:00Z'),
          ],
        };
      },
    },
    activeGame.id,
  );
  assert.deepEqual(receivedFilters, {
    gameId: activeGame.id,
    jobType: 'import',
    limit: 50,
  });
  assert.equal(jobs.ok, true);
  assert.deepEqual(
    jobs.jobs.map((value) => value.id),
    ['image-new', 'image-old'],
  );
});

test('loads exactly one scope-bound board with the requested cursor', async () => {
  let receivedOptions;
  const page = {
    counts: {
      accepted: 1,
      completed: 1,
      corrected: 0,
      pending: 2999,
      rejected: 0,
      total: 3000,
    },
    gameId: activeGame.id,
    importJobId: 'job-1',
    items: [{ id: 'review-1500' }],
    nextCursor: null,
    previousCursor: null,
    view: 'pending',
  };
  const result = await loadOperationalReviewPage(
    {
      listOperationalImageReviewItems: async (options) => {
        receivedOptions = options;
        return { data: page };
      },
    },
    {
      afterCursor: 'opaque-next',
      gameId: activeGame.id,
      importJobId: 'job-1',
      view: 'pending',
    },
  );
  assert.deepEqual(receivedOptions, {
    afterCursor: 'opaque-next',
    gameId: activeGame.id,
    importJobId: 'job-1',
    limit: 1,
    view: 'pending',
  });
  assert.deepEqual(result, { ok: true, page });
  assert.equal(result.page.items.length, 1);
  assert.equal(result.page.counts.total, 3000);
});

test('marks stale cursor as a recoverable queue conflict', async () => {
  const result = await loadOperationalReviewPage(
    {
      listOperationalImageReviewItems: async () => ({
        error: {
          code: 'IMAGE_REVIEW_CURSOR_STALE',
          details: {},
          message: 'Cursor is stale.',
        },
      }),
    },
    {
      gameId: activeGame.id,
      importJobId: 'job-1',
      view: 'completed',
    },
  );
  assert.deepEqual(result, {
    error: 'Cursor is stale. (IMAGE_REVIEW_CURSOR_STALE)',
    isCursorConflict: true,
    ok: false,
  });
});

test('loads only active symbols in stable display order', async () => {
  const result = await loadOperationalReviewSymbols(
    {
      listSymbols: async (gameId) => ({
        data: [
          {
            code: 'archived',
            displayOrder: 0,
            gameId,
            id: 'symbol-3',
            imagePath: null,
            isWildcard: false,
            mobileCode: 3,
            name: 'Archived',
            status: 'archived',
          },
          {
            code: 'seven',
            displayOrder: 2,
            gameId,
            id: 'symbol-2',
            imagePath: null,
            isWildcard: false,
            mobileCode: 2,
            name: 'Seven',
            status: 'active',
          },
          {
            code: 'lemon',
            displayOrder: 1,
            gameId,
            id: 'symbol-1',
            imagePath: null,
            isWildcard: false,
            mobileCode: 1,
            name: 'Lemon',
            status: 'active',
          },
        ],
      }),
    },
    activeGame.id,
  );
  assert.equal(result.ok, true);
  assert.deepEqual(
    result.symbols.map((symbol) => symbol.code),
    ['lemon', 'seven'],
  );
});

test('submits a scope-bound whole-board command and classifies revision conflict', async () => {
  const command = {
    action: 'accepted',
    cells: [],
    expectedRevision: 0,
    geometryRevision: 0,
    idempotencyKey: '11111111-1111-4111-8111-111111111111',
    resolvedBy: 'local-admin',
    sequenceNumber: 29,
  };
  let received;
  const resolution = { created: true, event: {}, item: {} };
  const success = await resolveOperationalReview(
    {
      resolveOperationalImageReviewItem: async (...args) => {
        received = args;
        return { data: resolution };
      },
    },
    {
      command,
      gameId: activeGame.id,
      importJobId: 'job-1',
      reviewItemId: 'review-1',
    },
  );
  assert.deepEqual(received, [
    'review-1',
    { gameId: activeGame.id, importJobId: 'job-1' },
    command,
  ]);
  assert.deepEqual(success, { ok: true, resolution });

  const conflict = await resolveOperationalReview(
    {
      resolveOperationalImageReviewItem: async () => ({
        error: {
          code: 'IMAGE_REVIEW_REVISION_CONFLICT',
          details: {},
          message: 'Revision changed.',
        },
      }),
    },
    {
      command,
      gameId: activeGame.id,
      importJobId: 'job-1',
      reviewItemId: 'review-1',
    },
  );
  assert.deepEqual(conflict, {
    error: 'Revision changed. (IMAGE_REVIEW_REVISION_CONFLICT)',
    isRevisionConflict: true,
    ok: false,
  });
});

test('previews and saves geometry through the generated scope-bound client', async () => {
  const previewCommand = {
    corners: [
      { x: 10, y: 10 },
      { x: 510, y: 10 },
      { x: 510, y: 310 },
      { x: 10, y: 310 },
    ],
    expectedGeometryRevision: 0,
    expectedResolutionRevision: 1,
  };
  const blob = new Blob(['png'], { type: 'image/png' });
  let previewArgs;
  const preview = await previewOperationalReviewGeometry(
    {
      previewOperationalImageReviewGeometry: async (...args) => {
        previewArgs = args;
        return { data: blob };
      },
    },
    {
      command: previewCommand,
      gameId: activeGame.id,
      importJobId: 'job-1',
      reviewItemId: 'review-1',
    },
  );
  assert.deepEqual(previewArgs, [
    'review-1',
    { gameId: activeGame.id, importJobId: 'job-1' },
    previewCommand,
  ]);
  assert.deepEqual(preview, { blob, ok: true });

  const command = {
    ...previewCommand,
    correctedBy: 'local-admin',
    idempotencyKey: '11111111-1111-4111-8111-111111111111',
  };
  const geometry = { created: true, geometryRevision: {}, item: {} };
  const saved = await saveOperationalReviewGeometry(
    {
      createOperationalImageReviewGeometryRevision: async () => ({
        data: geometry,
      }),
    },
    {
      command,
      gameId: activeGame.id,
      importJobId: 'job-1',
      reviewItemId: 'review-1',
    },
  );
  assert.deepEqual(saved, { geometry, ok: true });
});

test('loads and explicitly freezes immutable verified cohort history', async () => {
  const context = { gameId: activeGame.id, importJobId: 'job-1' };
  const versions = [{ boardCount: 12, version: 2 }];
  let listOptions;
  let freezeArgs;
  const history = await loadVerifiedCohortHistory(
    {
      listVerifiedImageReviewCohorts: async (options) => {
        listOptions = options;
        return { data: versions };
      },
    },
    context.gameId,
    context.importJobId,
  );
  const freezeResponse = {
    created: true,
    export: { boardCount: 12, sampleCount: 180, version: 2 },
  };
  const frozen = await freezeVerifiedCohort(
    {
      freezeVerifiedImageReviewCohort: async (...args) => {
        freezeArgs = args;
        return { data: freezeResponse };
      },
    },
    context.gameId,
    context.importJobId,
  );

  assert.deepEqual(listOptions, { ...context, limit: 20 });
  assert.deepEqual(history, { exports: versions, ok: true });
  assert.deepEqual(freezeArgs, [context, { createdBy: 'local-admin' }]);
  assert.deepEqual(frozen, { freeze: freezeResponse, ok: true });
});
