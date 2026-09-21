import assert from 'node:assert/strict';
import test from 'node:test';

import {
  acknowledgeV7LabelGeometryOperation,
  enqueueV7LabelGeometryOperation,
  isV7LabelGeometryPointInsideServerBounds,
  normaliseV7LabelGeometryPoint,
  projectV7LabelGeometryPendingSlots,
  restoreV7LabelGeometryQueue,
  resumeV7LabelGeometryQueue,
  stopV7LabelGeometryQueue,
  toV7LabelGeometrySessionMutation,
  v7LabelGeometryAssetKey,
} from '../src/features/v7-label-geometry/v7-label-geometry-calibration-queue.ts';

const sessionId = '11111111-1111-4111-8111-111111111111';
const sourceId = 'source-a';

function baseQueue(revision = 4) {
  return { confirmedRevision: revision, pending: [], stoppedReason: null };
}

test('fast annotation actions retain durable order, UUIDs, and original revisions', () => {
  const first = enqueueV7LabelGeometryOperation(baseQueue(), {
    centerX: 0.25,
    centerY: 0.75,
    cropAssessment: 'contained',
    kind: 'annotated',
    operationId: '00000000-0000-4000-8000-000000000001',
    positionIndex: 0,
    sessionId,
    sourceId,
  });
  const second = enqueueV7LabelGeometryOperation(first, {
    kind: 'unavailable',
    operationId: '00000000-0000-4000-8000-000000000002',
    positionIndex: 1,
    sessionId,
    sourceId,
  });

  assert.deepEqual(
    second.pending.map((operation) => [
      operation.operationId,
      operation.expectedRevision,
      operation.sequence,
    ]),
    [
      ['00000000-0000-4000-8000-000000000001', 4, 0],
      ['00000000-0000-4000-8000-000000000002', 5, 1],
    ],
  );
  assert.equal(second.pending[1]?.centerX, undefined);
  assert.equal(second.pending[1]?.cropAssessment, undefined);

  const afterLostResponseReplay = acknowledgeV7LabelGeometryOperation(
    second,
    '00000000-0000-4000-8000-000000000001',
    5,
  );
  assert.equal(afterLostResponseReplay.confirmedRevision, 5);
  assert.equal(
    afterLostResponseReplay.pending[0]?.operationId,
    '00000000-0000-4000-8000-000000000002',
  );
  assert.equal(afterLostResponseReplay.pending[0]?.expectedRevision, 5);
});

test('conflict can stop a queue but cannot silently rebase pending actions', () => {
  const queued = enqueueV7LabelGeometryOperation(baseQueue(2), {
    kind: 'set_capture_group',
    operationId: '00000000-0000-4000-8000-000000000003',
    captureGroupId: 'capture-b',
    sessionId,
    sourceId,
  });
  const stopped = stopV7LabelGeometryQueue(queued, 'revision conflict');

  assert.throws(
    () =>
      enqueueV7LabelGeometryOperation(stopped, {
        kind: 'set_capture_group',
        operationId: '00000000-0000-4000-8000-000000000004',
        captureGroupId: 'capture-c',
        sessionId,
        sourceId,
      }),
    /QUEUE_STOPPED/,
  );
  assert.throws(() => resumeV7LabelGeometryQueue(stopped, 3), /REBASE_FORBIDDEN/);
});

test('a lost receipt keeps the immutable first expected revision through refresh', () => {
  const first = enqueueV7LabelGeometryOperation(baseQueue(4), {
    kind: 'unavailable',
    operationId: '00000000-0000-4000-8000-000000000005',
    positionIndex: 0,
    sessionId,
    sourceId,
  });
  const second = enqueueV7LabelGeometryOperation(first, {
    kind: 'unavailable',
    operationId: '00000000-0000-4000-8000-000000000006',
    positionIndex: 1,
    sessionId,
    sourceId,
  });

  const restored = restoreV7LabelGeometryQueue(second.pending, 5, null);
  assert.equal(restored.confirmedRevision, 4);
  assert.equal(restored.pending.length, 2);
  const afterRefreshClick = enqueueV7LabelGeometryOperation(restored, {
    kind: 'unavailable',
    operationId: '00000000-0000-4000-8000-000000000007',
    positionIndex: 2,
    sessionId,
    sourceId,
  });
  assert.equal(afterRefreshClick.pending.at(-1)?.expectedRevision, 6);

  const invalid = restoreV7LabelGeometryQueue(second.pending, 7, null);
  assert.match(invalid.stoppedReason ?? '', /nie odpowiada rewizji/i);
});

test('HTTP mutation body excludes browser-only queue metadata', () => {
  const queued = enqueueV7LabelGeometryOperation(baseQueue(), {
    centerX: 0.25,
    centerY: 0.75,
    cropAssessment: 'clipped',
    kind: 'annotated',
    operationId: '00000000-0000-4000-8000-000000000008',
    positionIndex: 3,
    sessionId,
    sourceId,
  });
  const request = toV7LabelGeometrySessionMutation(queued.pending[0]);

  assert.deepEqual(request, {
    centerX: 0.25,
    centerY: 0.75,
    cropAssessment: 'clipped',
    expectedRevision: 4,
    kind: 'annotated',
    operationId: '00000000-0000-4000-8000-000000000008',
    positionIndex: 3,
    sourceId,
  });
  assert.equal('sequence' in request, false);
  assert.equal('sessionId' in request, false);
});

test('canonical asset key changes for a new source or checksum', () => {
  const original = v7LabelGeometryAssetKey(sessionId, sourceId, 'a'.repeat(64));
  assert.notEqual(
    original,
    v7LabelGeometryAssetKey(sessionId, 'source-b', 'a'.repeat(64)),
  );
  assert.notEqual(
    original,
    v7LabelGeometryAssetKey(sessionId, sourceId, 'b'.repeat(64)),
  );
});

test('display projection shows durable pending markers without treating them as server confirmations', () => {
  const queued = enqueueV7LabelGeometryOperation(baseQueue(), {
    centerX: 0.25,
    centerY: 0.75,
    cropAssessment: 'contained',
    kind: 'annotated',
    operationId: '00000000-0000-4000-8000-000000000009',
    positionIndex: 0,
    sessionId,
    sourceId,
  });
  const unavailable = enqueueV7LabelGeometryOperation(queued, {
    kind: 'unavailable',
    operationId: '00000000-0000-4000-8000-000000000010',
    positionIndex: 1,
    sessionId,
    sourceId,
  });

  assert.deepEqual(
    projectV7LabelGeometryPendingSlots([], unavailable.pending, sourceId),
    [
      {
        centerX: 0.25,
        centerY: 0.75,
        cropAssessment: 'contained',
        positionIndex: 0,
        sourceId,
        state: 'annotated',
      },
      {
        centerX: null,
        centerY: null,
        cropAssessment: null,
        positionIndex: 1,
        sourceId,
        state: 'unavailable',
      },
    ],
  );
  assert.deepEqual(
    projectV7LabelGeometryPendingSlots([], unavailable.pending, 'other-source'),
    [],
  );
});

test('normalises a canonical image click and clamps outside clicks at image edges', () => {
  const rect = { height: 200, left: 100, top: 50, width: 400 };
  assert.deepEqual(normaliseV7LabelGeometryPoint(200, 150, rect), {
    centerX: 0.25,
    centerY: 0.5,
  });
  assert.deepEqual(normaliseV7LabelGeometryPoint(-10, 500, rect), {
    centerX: 0,
    centerY: 1,
  });
  assert.equal(
    isV7LabelGeometryPointInsideServerBounds(
      normaliseV7LabelGeometryPoint(-10, 500, rect),
    ),
    false,
  );
  assert.equal(
    isV7LabelGeometryPointInsideServerBounds({ centerX: 0.5, centerY: 0.5 }),
    true,
  );
  assert.throws(
    () => normaliseV7LabelGeometryPoint(100, 50, { ...rect, width: 0 }),
    /IMAGE_RECT_INVALID/,
  );
});
