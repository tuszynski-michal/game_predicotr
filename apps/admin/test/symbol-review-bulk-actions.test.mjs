import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createSymbolReviewBulkCommand,
  isSymbolReviewBulkOperationTerminal,
  previewSymbolReviewBulkOperation,
  startSymbolReviewBulkOperation,
} from '../src/features/symbol-reviews/symbol-review-bulk-actions.ts';
import {
  createEmptySymbolReviewSelection,
  toggleSymbolReviewItem,
} from '../src/features/symbol-reviews/symbol-review-selection-state.ts';

const item = {
  cropChecksumSha256: 'a'.repeat(64),
  cropSampleId: 'b'.repeat(64),
  geometryRevision: 3,
  id: 'cell-1',
  revision: 4,
};

test('builds only explicit page-local crop-bound commands', () => {
  const explicit = toggleSymbolReviewItem(
    createEmptySymbolReviewSelection(),
    item,
  ).selection;
  const explicitCommand = createSymbolReviewBulkCommand(
    'approve',
    explicit,
    null,
  );
  assert.deepEqual(explicitCommand?.request.selection, {
    kind: 'explicit',
    targets: [
      {
        cellReviewId: 'cell-1',
        expectedCropChecksumSha256: 'a'.repeat(64),
        expectedCropSampleId: 'b'.repeat(64),
        expectedGeometryRevision: 3,
        expectedRevision: 4,
      },
    ],
  });
  assert.deepEqual(
    createSymbolReviewBulkCommand('reassign', explicit, 'symbol-2')?.request,
    {
      action: 'reassign',
      selection: explicitCommand?.request.selection,
      targetSymbolId: 'symbol-2',
    },
  );
  assert.equal(
    createSymbolReviewBulkCommand('mark_unreadable', explicit, null)?.request
      .action,
    'mark_unreadable',
  );
});

test('delegates preview and start to the local client with one idempotency key', async () => {
  const requests = [];
  const operation = {
    action: 'approve',
    appliedCount: 0,
    catalogRevision: 7,
    commandSha256: 'c'.repeat(64),
    conflictCount: 0,
    errorCode: null,
    errorMessage: null,
    failedCount: 0,
    gameId: 'game-1',
    id: 'operation-1',
    jobId: 'job-1',
    pendingCount: 1,
    selectionKind: 'explicit',
    status: 'created',
    targetCount: 1,
    targetSymbolId: null,
  };
  const api = {
    getSymbolCellReviewBulkOperation: async () => ({ data: operation }),
    previewSymbolCellReviewBulkOperation: async (_gameId, body) => {
      requests.push(['preview', body]);
      return {
        data: {
          action: 'approve',
          boardCount: 1,
          catalogRevision: 7,
          selectionKind: 'explicit',
          targetCount: 1,
          targetSymbolId: null,
        },
      };
    },
    startSymbolCellReviewBulkOperation: async (_gameId, body) => {
      requests.push(['start', body]);
      return { data: { created: true, operation } };
    },
  };
  const command = createSymbolReviewBulkCommand(
    'approve',
    toggleSymbolReviewItem(createEmptySymbolReviewSelection(), item).selection,
    null,
  );

  const preview = await previewSymbolReviewBulkOperation(
    api,
    'game-1',
    command,
  );
  const start = await startSymbolReviewBulkOperation(
    api,
    'game-1',
    command,
    'key-1',
  );

  assert.equal(preview.ok, true);
  assert.equal(start.ok, true);
  assert.equal(requests[0][0], 'preview');
  assert.equal(requests[1][1].idempotencyKey, 'key-1');
  assert.equal(isSymbolReviewBulkOperationTerminal(operation), false);
  assert.equal(
    isSymbolReviewBulkOperationTerminal({ ...operation, status: 'completed' }),
    true,
  );
});
