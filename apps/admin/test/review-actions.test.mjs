import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createReviewFeedbackExport,
  loadReviewBatches,
  loadReviewFeedbackExports,
  loadReviewItem,
  loadReviewItems,
  loadReviewResolutions,
  submitReviewResolution,
} from '../src/features/reviews/review-actions.ts';

const batch = {
  activeLearningVersion: 'whole-layout-active-learning-v1',
  calibrationReportSha256: '1'.repeat(64),
  createdAt: '2026-07-29T10:00:00Z',
  datasetSha256: '2'.repeat(64),
  gameId: 'game-1',
  id: 'batch-1',
  inventorySha256: '3'.repeat(64),
  itemCount: 2,
  modelArtifactSha256: '4'.repeat(64),
  modelVersion: 'model-v1',
  sourceReportSha256: '5'.repeat(64),
  splitSha256: '6'.repeat(64),
  temperature: 1.03,
};

function item(id, rank) {
  return {
    createdAt: '2026-07-29T10:00:00Z',
    id,
    resolvedAt: null,
    resolvedBy: null,
    resolvedValue: null,
    resolutionRevision: 0,
    reviewBatchId: batch.id,
    snapshot: {
      cells: [],
      selectionRank: rank,
      sequenceNumber: rank,
    },
    status: 'pending',
  };
}

test('loads immutable batches through the typed client', async () => {
  const result = await loadReviewBatches({
    listReviewBatches: async () => ({ data: [batch] }),
  });

  assert.deepEqual(result, { batches: [batch], ok: true });
});

test('submits a typed resolution and loads immutable history', async () => {
  const selected = item('item-1', 1);
  const command = {
    action: 'accepted',
    expectedRevision: 0,
    geometryAccepted: true,
    idempotencyKey: 'request-1',
    labels: [],
    resolvedBy: 'local-admin',
  };
  const resolution = {
    action: 'accepted',
    commandSha256: 'a'.repeat(64),
    createdAt: '2026-07-29T10:01:00Z',
    id: 'resolution-1',
    idempotencyKey: 'request-1',
    resolvedBy: 'local-admin',
    resolvedValue: {},
    reviewItemId: selected.id,
    revision: 1,
  };
  const resolvedItem = {
    ...selected,
    resolutionRevision: 1,
    status: 'accepted',
  };
  const api = {
    listReviewResolutions: async (itemId) => {
      assert.equal(itemId, selected.id);
      return { data: [resolution] };
    },
    resolveReviewItem: async (itemId, body) => {
      assert.equal(itemId, selected.id);
      assert.deepEqual(body, command);
      return {
        data: { created: true, item: resolvedItem, resolution },
      };
    },
  };

  const saved = await submitReviewResolution(api, selected.id, command);
  const history = await loadReviewResolutions(api, selected.id);

  assert.equal(saved.ok, true);
  assert.equal(saved.item.resolutionRevision, 1);
  assert.deepEqual(history, { ok: true, resolutions: [resolution] });
});

test('creates and lists versioned feedback exports', async () => {
  const feedbackExport = {
    createdAt: '2026-07-29T10:02:00Z',
    createdBy: 'local-admin',
    gameId: batch.gameId,
    id: 'export-1',
    payload: {},
    payloadSha256: 'a'.repeat(64),
    rejectedItemCount: 1,
    reviewBatchId: batch.id,
    sampleCount: 15,
    sourceStateSha256: 'b'.repeat(64),
    version: 1,
  };
  const api = {
    createReviewFeedbackExport: async (batchId, body) => {
      assert.equal(batchId, batch.id);
      assert.deepEqual(body, { createdBy: 'local-admin' });
      return { data: { created: true, feedbackExport } };
    },
    listReviewFeedbackExports: async (batchId) => {
      assert.equal(batchId, batch.id);
      return { data: [feedbackExport] };
    },
  };

  const created = await createReviewFeedbackExport(
    api,
    batch.id,
    'local-admin',
  );
  const listed = await loadReviewFeedbackExports(api, batch.id);

  assert.equal(created.ok, true);
  assert.equal(created.feedbackExport.version, 1);
  assert.deepEqual(listed, {
    feedbackExports: [feedbackExport],
    ok: true,
  });
});

test('loads one bounded filtered queue and restores selection-rank order', async () => {
  let receivedBatch;
  let receivedOptions;
  const second = item('item-2', 2);
  const first = item('item-1', 1);

  const result = await loadReviewItems(
    {
      listReviewItems: async (reviewBatchId, options) => {
        receivedBatch = reviewBatchId;
        receivedOptions = options;
        return {
          data: {
            items: [second, first],
            nextAfterSelectionRank: null,
            reviewBatchId,
          },
        };
      },
    },
    batch.id,
    'pending',
  );

  assert.equal(receivedBatch, batch.id);
  assert.deepEqual(receivedOptions, {
    afterSelectionRank: 0,
    limit: 100,
    status: 'pending',
  });
  assert.deepEqual(
    result.items.map((value) => value.id),
    ['item-1', 'item-2'],
  );
});

test('loads detail and preserves stable API and transport errors', async () => {
  const selected = item('item-1', 1);
  const detail = await loadReviewItem(
    {
      getReviewItem: async (reviewItemId) => {
        assert.equal(reviewItemId, selected.id);
        return { data: selected };
      },
    },
    selected.id,
  );
  assert.deepEqual(detail, { item: selected, ok: true });

  const stableError = await loadReviewBatches({
    listReviewBatches: async () => ({
      error: {
        code: 'REVIEW_BATCH_NOT_FOUND',
        details: {},
        message: 'Review batch does not exist.',
      },
    }),
  });
  assert.deepEqual(stableError, {
    error: 'Review batch does not exist. (REVIEW_BATCH_NOT_FOUND)',
    ok: false,
  });

  const transportError = await loadReviewItem(
    {
      getReviewItem: async () => {
        throw new Error('sensitive details');
      },
    },
    selected.id,
  );
  assert.deepEqual(transportError, {
    error: 'Połączenie z lokalnym Admin API zostało przerwane.',
    ok: false,
  });
});
