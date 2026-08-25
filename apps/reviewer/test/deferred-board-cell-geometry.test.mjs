import assert from 'node:assert/strict';
import test from 'node:test';

import {
  loadDeferredBoardCellGeometryContext,
  loadDeferredBoardCellGeometryPage,
  previewDeferredBoardCellGeometry,
  resolveDeferredBoardCellGeometry,
} from '../src/features/operational-reviews/deferred-board-cell-geometry-actions.ts';
import {
  deferredBoardCellGeometryCommandKey,
  deferredBoardCellGeometryCorners,
  deferredBoardCellGeometryIdempotency,
  deferredBoardCellGeometryPreviewCommand,
  deferredBoardCellGeometryReasonLabel,
  deferredBoardCellGeometryResolutionCommand,
  deferredBoardCellGeometrySourceUrl,
} from '../src/features/operational-reviews/deferred-board-cell-geometry-state.ts';

const scope = {
  gameId: '11111111-1111-4111-8111-111111111111',
  importJobId: '22222222-2222-4222-8222-222222222222',
};
const item = {
  createdAt: '2026-08-23T10:00:00Z',
  expectedGeometryRevision: 2,
  expectedReviewResolutionRevision: 3,
  gameId: scope.gameId,
  id: '33333333-3333-4333-8333-333333333333',
  importJobId: scope.importJobId,
  pipelineFingerprintSha256: 'b'.repeat(64),
  positionIndex: 4,
  processingManifestChecksumSha256: 'a'.repeat(64),
  processingManifestRelativePath: 'manifests/processing.json',
  reasonCode: 'incomplete_lattice',
  recognizedBoardId: null,
  resolvedAt: null,
  reviewItemId: null,
  sequenceNumber: 253,
  sourceChecksumSha256: 'c'.repeat(64),
  sourceImageId: '44444444-4444-4444-8444-444444444444',
  sourceRelativePath: 'seq_253-261.jpg',
  status: 'pending',
  supersededAt: null,
  updatedAt: '2026-08-23T10:00:00Z',
};
const context = {
  boardQuad: [
    { x: 90, y: 80 },
    { x: 590, y: 70 },
    { x: 610, y: 390 },
    { x: 80, y: 400 },
  ],
  item,
  sourceHeight: 900,
  sourceOrderIndex: 28,
  sourceWidth: 1200,
  suggestedCorners: [
    { x: 110, y: 100 },
    { x: 570, y: 92 },
    { x: 585, y: 370 },
    { x: 102, y: 380 },
  ],
};

test('binds deferred preview and resolution to manifest and both revisions', () => {
  const corners = deferredBoardCellGeometryCorners(context);
  assert.notEqual(corners, context.suggestedCorners);
  assert.deepEqual(deferredBoardCellGeometryPreviewCommand(context, corners), {
    corners,
    expectedGeometryRevision: 2,
    expectedManifestChecksumSha256: 'a'.repeat(64),
    expectedResolutionRevision: 3,
  });
  const command = deferredBoardCellGeometryResolutionCommand(
    context,
    corners,
    '55555555-5555-4555-8555-555555555555',
  );
  assert.equal(command.correctedBy, 'reviewer-operator');
  assert.equal(command.idempotencyKey, '55555555-5555-4555-8555-555555555555');
  assert.equal(
    deferredBoardCellGeometryCommandKey(context, corners),
    JSON.stringify(deferredBoardCellGeometryPreviewCommand(context, corners)),
  );
  assert.equal(
    deferredBoardCellGeometryReasonLabel('incomplete_lattice'),
    'Niepełna siatka symboli',
  );
});

test('reuses one idempotency key only for an unchanged save command', () => {
  const first = deferredBoardCellGeometryIdempotency(
    null,
    'command-a',
    () => 'key-a',
  );
  const retry = deferredBoardCellGeometryIdempotency(
    first,
    'command-a',
    () => 'must-not-be-used',
  );
  const changed = deferredBoardCellGeometryIdempotency(
    first,
    'command-b',
    () => 'key-b',
  );

  assert.equal(retry, first);
  assert.deepEqual(changed, {
    commandKey: 'command-b',
    idempotencyKey: 'key-b',
  });
});

test('builds scoped checksum-versioned source URLs for local Reviewer proxy', () => {
  const url = deferredBoardCellGeometrySourceUrl('/review-api/', item);
  assert.equal(
    url,
    `/review-api/api/v1/admin/games/${scope.gameId}/image-imports/${scope.importJobId}/board-cell-geometry-pending/${item.id}/source?v=${item.sourceChecksumSha256}`,
  );
});

test('loads one pending item and executes preview and resolution through scoped client', async () => {
  const calls = [];
  const page = {
    counts: { pending: 1, resolved: 0, superseded: 0, total: 1 },
    items: [item],
    nextCursor: null,
  };
  const resolution = {
    created: true,
    geometryRevision: 4,
    item: { ...item, status: 'resolved' },
    reviewItemId: '66666666-6666-4666-8666-666666666666',
  };
  const client = {
    getPendingBoardCellGeometryCorrectionContext: async (...args) => {
      calls.push(['context', ...args]);
      return { data: context };
    },
    listPendingBoardCellGeometry: async (options) => {
      calls.push(['list', options]);
      return { data: page };
    },
    previewPendingBoardCellGeometryCorrection: async (...args) => {
      calls.push(['preview', ...args]);
      return { data: new Blob(['png']) };
    },
    resolvePendingBoardCellGeometryManually: async (...args) => {
      calls.push(['resolve', ...args]);
      return { data: resolution };
    },
  };
  const corners = deferredBoardCellGeometryCorners(context);
  const previewCommand = deferredBoardCellGeometryPreviewCommand(
    context,
    corners,
  );
  const resolutionCommand = deferredBoardCellGeometryResolutionCommand(
    context,
    corners,
    '55555555-5555-4555-8555-555555555555',
  );

  assert.deepEqual(
    await loadDeferredBoardCellGeometryPage(client, scope, 'cursor-1'),
    { ok: true, page },
  );
  assert.deepEqual(
    await loadDeferredBoardCellGeometryContext(client, scope, item.id),
    { context, ok: true },
  );
  assert.equal(
    (
      await previewDeferredBoardCellGeometry(
        client,
        scope,
        item.id,
        previewCommand,
      )
    ).ok,
    true,
  );
  assert.deepEqual(
    await resolveDeferredBoardCellGeometry(
      client,
      scope,
      item.id,
      resolutionCommand,
    ),
    { ok: true, resolution },
  );
  assert.deepEqual(calls[0], [
    'list',
    { ...scope, cursor: 'cursor-1', limit: 1, status: 'pending' },
  ]);
  assert.deepEqual(calls[1], ['context', item.id, scope]);
  assert.deepEqual(calls[2], ['preview', item.id, scope, previewCommand]);
  assert.deepEqual(calls[3], ['resolve', item.id, scope, resolutionCommand]);
});

test('marks stale deferred state as conflict without hiding the server error', async () => {
  const result = await resolveDeferredBoardCellGeometry(
    {
      resolvePendingBoardCellGeometryManually: async () => ({
        error: {
          code: 'IMAGE_BOARD_CELL_PENDING_REVISION_CONFLICT',
          message: 'The deferred item changed.',
        },
      }),
    },
    scope,
    item.id,
    deferredBoardCellGeometryResolutionCommand(
      context,
      deferredBoardCellGeometryCorners(context),
      '55555555-5555-4555-8555-555555555555',
    ),
  );
  assert.equal(result.ok, false);
  assert.equal(result.isConflict, true);
  assert.match(result.error, /deferred item changed/i);
});
