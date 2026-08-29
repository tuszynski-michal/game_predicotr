import assert from 'node:assert/strict';
import test from 'node:test';

import {
  addGridGeometryPoint,
  GRID_CORNER_LABELS,
  GRID_REVIEW_VIEWS,
  gridGeometryDragTarget,
  gridReviewApprovalCommand,
  gridReviewGeometryCommand,
  gridReviewGeometryPreviewCommand,
  moveGridGeometry,
  moveGridGeometryCorner,
  undoGridGeometryPoint,
} from '../src/features/grid-reviews/grid-review-state.ts';

const item = {
  approvedGeometryRevision: null,
  gameId: '11111111-1111-4111-8111-111111111111',
  geometry: {},
  geometryRevision: 4,
  gridColumns: 4,
  gridRows: 2,
  importJobId: '22222222-2222-4222-8222-222222222222',
  recognizedBoardId: '33333333-3333-4333-8333-333333333333',
  resolutionRevision: 7,
  reviewItemId: '44444444-4444-4444-8444-444444444444',
  sequenceNumber: 91,
  sourceChecksumSha256: 'a'.repeat(64),
  sourceHeight: 800,
  sourceWidth: 1200,
  state: 'needs_validation',
};

test('grid workflow exposes the three accepted filters in operator order', () => {
  assert.deepEqual(
    GRID_REVIEW_VIEWS.map(({ label, value }) => [value, label]),
    [
      ['needs_validation', 'Do walidacji'],
      ['needs_correction', 'Do poprawy'],
      ['all', 'Wszystkie'],
    ],
  );
});

test('four clicks create corners in LT PT PD LD order and undo removes the last point', () => {
  let draft = [];
  for (const point of [
    { x: 10, y: 20 },
    { x: 110, y: 20 },
    { x: 110, y: 80 },
    { x: 10, y: 80 },
  ]) {
    draft = addGridGeometryPoint(draft, point, 120, 100);
  }
  assert.deepEqual(GRID_CORNER_LABELS, ['LT', 'PT', 'PD', 'LD']);
  assert.equal(draft.length, 4);
  assert.deepEqual(undoGridGeometryPoint(draft), draft.slice(0, 3));
  assert.strictEqual(
    addGridGeometryPoint(draft, { x: 50, y: 50 }, 120, 100),
    draft,
  );
});

test('corner drag changes one point and whole-grid drag preserves shape within source bounds', () => {
  const corners = [
    { x: 10, y: 10 },
    { x: 90, y: 10 },
    { x: 90, y: 70 },
    { x: 10, y: 70 },
  ];
  assert.deepEqual(gridGeometryDragTarget(corners, { x: 12, y: 12 }, 5), {
    index: 0,
    kind: 'corner',
  });
  assert.deepEqual(gridGeometryDragTarget(corners, { x: 50, y: 40 }, 5), {
    kind: 'grid',
  });
  assert.equal(gridGeometryDragTarget(corners, { x: 110, y: 90 }, 5), null);
  assert.deepEqual(
    moveGridGeometryCorner(corners, 1, { x: 95, y: 12 }, 120, 100)[1],
    { x: 95, y: 12 },
  );
  assert.deepEqual(moveGridGeometry(corners, { x: 40, y: 50 }, 120, 100), [
    { x: 39, y: 39 },
    { x: 119, y: 39 },
    { x: 119, y: 99 },
    { x: 39, y: 99 },
  ]);
});

test('approval, preview and save bind exact topology and source identity', () => {
  const approval = gridReviewApprovalCommand(item);
  assert.deepEqual(approval, {
    expectedGeometryRevision: 4,
    expectedGridColumns: 4,
    expectedGridRows: 2,
    expectedResolutionRevision: 7,
    expectedSourceChecksumSha256: 'a'.repeat(64),
    expectedSourceHeight: 800,
    expectedSourceWidth: 1200,
  });
  const corners = [
    { x: 1, y: 2 },
    { x: 3, y: 2 },
    { x: 3, y: 4 },
    { x: 1, y: 4 },
  ];
  assert.deepEqual(gridReviewGeometryPreviewCommand(item, corners), {
    corners,
    ...approval,
  });
  assert.deepEqual(gridReviewGeometryCommand(item, corners, 'idem'), {
    corners,
    ...approval,
    idempotencyKey: 'idem',
  });
});
