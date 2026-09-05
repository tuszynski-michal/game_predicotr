import assert from 'node:assert/strict';
import test from 'node:test';

import {
  loadSymbolReviewCounts,
  loadSymbolReviewProjection,
  loadSymbolReviewPage,
  loadSymbolReviewSymbols,
  startSymbolReviewProjection,
} from '../src/features/symbol-reviews/symbol-review-actions.ts';

const gameId = '11111111-1111-4111-8111-111111111111';
const page = {
  catalogRevision: 7,
  items: [],
  nextCursor: 'next-page',
  previousCursor: null,
};

function client(overrides = {}) {
  return {
    listGames: async () => ({ data: [] }),
    getSymbolCellReviewCounts: async () => ({
      data: {
        catalogRevision: 7,
        counts: { allCount: 3, approvedCount: 2, pendingCount: 1 },
      },
    }),
    listSymbolCellReviews: async () => ({ data: page }),
    listSymbols: async () => ({ data: [] }),
    getSymbolCellReviewProjectionStatus: async () => ({
      data: { gameId, status: 'not_started' },
    }),
    startSymbolCellReviewProjectionBackfill: async () => ({
      data: {
        created: true,
        jobId: 'job-1',
        projection: { gameId, status: 'rebuilding' },
      },
    }),
    symbolCellReviewAssetUrl: () => '',
    ...overrides,
  };
}

test('loads projection readiness and starts the durable preparation job', async () => {
  const status = {
    activeJobId: null,
    databaseFreeBytesCurrent: 1_000,
    expectedBoardCount: 2,
    expectedCellCount: 30,
    failureMessage: null,
    gameId,
    indexBytesBefore: 0,
    indexBytesCurrent: 0,
    invalidCropCount: 0,
    invalidGeometryCount: 0,
    missingSequenceCount: 0,
    persistedCellCount: 0,
    processedBoardCount: 0,
    sampleProblemReviewItemIds: [],
    status: 'not_started',
    tableBytesBefore: 0,
    tableBytesCurrent: 0,
  };
  let starts = 0;
  const api = client({
    getSymbolCellReviewProjectionStatus: async () => ({ data: status }),
    startSymbolCellReviewProjectionBackfill: async () => {
      starts += 1;
      return {
        data: {
          created: true,
          jobId: '22222222-2222-4222-8222-222222222222',
          projection: { ...status, status: 'rebuilding' },
        },
      };
    },
  });

  assert.deepEqual(await loadSymbolReviewProjection(api, gameId), {
    ok: true,
    status,
  });
  const started = await startSymbolReviewProjection(api, gameId);
  assert.equal(started.ok, true);
  assert.equal(starts, 1);
});

test('starts a missing-cell reconciliation from an already ready projection', async () => {
  const status = {
    activeJobId: null,
    gameId,
    status: 'ready',
  };
  let starts = 0;
  const api = client({
    startSymbolCellReviewProjectionBackfill: async () => {
      starts += 1;
      return {
        data: {
          created: true,
          jobId: '33333333-3333-4333-8333-333333333333',
          projection: { ...status, status: 'rebuilding' },
        },
      };
    },
  });

  const started = await startSymbolReviewProjection(api, gameId);

  assert.equal(started.ok, true);
  assert.equal(starts, 1);
  if (started.ok) {
    assert.equal(started.value.projection.status, 'rebuilding');
  }
});

test('loads a bounded, checksum-independent metadata page with its keyset cursor', async () => {
  let request;
  const result = await loadSymbolReviewPage(
    client({
      listSymbolCellReviews: async (options) => {
        request = options;
        return { data: page };
      },
    }),
    {
      afterCursor: 'after-page',
      gameId,
      limit: 42,
      state: 'pending',
      symbolId: 'unknown',
    },
  );

  assert.deepEqual(request, {
    afterCursor: 'after-page',
    gameId,
    limit: 42,
    state: 'pending',
    symbolId: 'unknown',
  });
  assert.deepEqual(result, { ok: true, page });
});

test('loads counts independently and binds them to the page catalog revision', async () => {
  let request;
  const result = await loadSymbolReviewCounts(
    client({
      getSymbolCellReviewCounts: async (options) => {
        request = options;
        return {
          data: {
            catalogRevision: 7,
            counts: { allCount: 3, approvedCount: 2, pendingCount: 1 },
          },
        };
      },
    }),
    {
      catalogRevision: 7,
      gameId,
      state: 'pending',
      symbolId: 'unknown',
    },
  );

  assert.deepEqual(request, {
    catalogRevision: 7,
    gameId,
    state: 'pending',
    symbolId: 'unknown',
  });
  assert.equal(result.ok, true);
  if (result.ok) assert.equal(result.snapshot.counts.pendingCount, 1);
});

test('a counts failure remains separate from a successful metadata page', async () => {
  const api = client({
    getSymbolCellReviewCounts: async () => ({
      error: { code: 'COUNTS_TIMEOUT', message: 'slow aggregate' },
    }),
  });

  const loadedPage = await loadSymbolReviewPage(api, {
    gameId,
    limit: 500,
    state: 'pending',
    symbolId: 'unknown',
  });
  const loadedCounts = await loadSymbolReviewCounts(api, {
    catalogRevision: 7,
    gameId,
    state: 'pending',
    symbolId: 'unknown',
  });

  assert.equal(loadedPage.ok, true);
  assert.equal(loadedCounts.ok, false);
});

test('exposes a controlled rebuilding state instead of treating it as an empty page', async () => {
  const result = await loadSymbolReviewPage(
    client({
      listSymbolCellReviews: async () => ({
        error: {
          code: 'SYMBOL_CELL_REVIEW_PROJECTION_INCOMPLETE',
          message: 'Backfill is still running.',
        },
      }),
    }),
    { gameId, limit: 12, state: 'all', symbolId: 'symbol-1' },
  );

  assert.equal(result.ok, false);
  if (!result.ok) {
    assert.equal(result.isProjectionRebuilding, true);
  }
});

test('lists only active symbols in deterministic catalog order', async () => {
  const result = await loadSymbolReviewSymbols(
    client({
      listSymbols: async () => ({
        data: [
          { code: 'Z', displayOrder: 2, id: 'z', status: 'active' },
          { code: 'A', displayOrder: 1, id: 'a', status: 'active' },
          { code: 'OLD', displayOrder: 0, id: 'old', status: 'archived' },
        ],
      }),
    }),
    gameId,
  );

  assert.equal(result.ok, true);
  if (result.ok) {
    assert.deepEqual(
      result.symbols.map((symbol) => symbol.id),
      ['a', 'z'],
    );
  }
});
