import assert from 'node:assert/strict';
import test from 'node:test';

import {
  addGridGeometryPoint,
  completeGridGeometrySourceDrafts,
  emptyGridGeometrySourceDrafts,
  firstIncompleteGridGeometrySourceItem,
  GRID_CORNER_LABELS,
  gridGeometrySourceDraft,
  GRID_REVIEW_VIEWS,
  gridGeometryDragTarget,
  gridReviewApprovalCommand,
  gridReviewGeometryCommand,
  gridReviewGeometryPreviewCommand,
  gridReviewSourceStats,
  orderGridReviewSourceItems,
  moveGridGeometry,
  moveGridGeometryCorner,
  nextIncompleteGridGeometrySourceItem,
  replaceGridGeometrySourceDraft,
  undoGridGeometryPoint,
} from '../src/features/grid-reviews/grid-review-state.ts';

const item = {
  approvedGeometryRevision: null,
  assetMode: 'virtual_source',
  boardConfidence: 0.9,
  gameId: '11111111-1111-4111-8111-111111111111',
  geometry: {},
  geometryEngineName: 'board-cell-processing-v20',
  geometryEngineVersion: 'v20',
  geometryRevision: 4,
  gridColumns: 4,
  gridRows: 2,
  importJobId: '22222222-2222-4222-8222-222222222222',
  positionIndex: 0,
  reasonCodes: ['verified_registration'],
  recognizedBoardId: '33333333-3333-4333-8333-333333333333',
  resolutionRevision: 7,
  reviewItemId: '44444444-4444-4444-8444-444444444444',
  sequenceNumber: 91,
  sourceChecksumSha256: 'a'.repeat(64),
  sourceHeight: 800,
  sourceImageId: '55555555-5555-4555-8555-555555555555',
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

test('source statistics and slot ordering stay deterministic for one image', () => {
  const correction = {
    ...item,
    geometryRevision: 0,
    positionIndex: 2,
    reviewItemId: '66666666-6666-4666-8666-666666666666',
    sequenceNumber: 93,
    state: 'needs_correction',
  };
  const approved = {
    ...item,
    approvedGeometryRevision: 4,
    geometryRevision: 4,
    positionIndex: 1,
    reviewItemId: '77777777-7777-4777-8777-777777777777',
    sequenceNumber: 92,
    state: 'approved',
  };
  const ordered = orderGridReviewSourceItems([correction, approved, item]);

  assert.deepEqual(
    ordered.map((candidate) => candidate.positionIndex),
    [0, 1, 2],
  );
  assert.deepEqual(gridReviewSourceStats(ordered), {
    approvedBoards: 1,
    imageState: 'needs_correction',
    manualBoards: 2,
    needsCorrectionBoards: 1,
    needsValidationBoards: 1,
    totalBoards: 3,
  });
});

test('source manual geometry completes exactly nine slots in row-major order', () => {
  const sourceItems = Array.from({ length: 9 }, (_, positionIndex) => ({
    ...item,
    positionIndex,
    reviewItemId: `00000000-0000-4000-8000-00000000000${positionIndex}`,
    sequenceNumber: 100 + positionIndex,
  }));
  let drafts = emptyGridGeometrySourceDrafts(sourceItems);

  for (const sourceItem of sourceItems) {
    const draft = [
      { x: 10, y: 10 },
      { x: 50, y: 10 },
      { x: 50, y: 40 },
      { x: 10, y: 40 },
    ];
    drafts = replaceGridGeometrySourceDraft(
      drafts,
      sourceItem.reviewItemId,
      draft,
    );
  }

  const completed = completeGridGeometrySourceDrafts(sourceItems, drafts);
  assert.deepEqual(
    completed?.map(({ item: sourceItem }) => sourceItem.positionIndex),
    [0, 1, 2, 3, 4, 5, 6, 7, 8],
  );
  assert.equal(
    nextIncompleteGridGeometrySourceItem(
      sourceItems,
      drafts,
      sourceItems[8].reviewItemId,
    ),
    null,
  );
});

test('pausing source geometry preserves completed drafts and resumes at the next row-major slot', () => {
  const sourceItems = [
    {
      ...item,
      positionIndex: 0,
      reviewItemId: '10000000-0000-4000-8000-000000000001',
      sequenceNumber: 100,
    },
    {
      ...item,
      positionIndex: 1,
      reviewItemId: '10000000-0000-4000-8000-000000000002',
      sequenceNumber: 101,
    },
  ];
  const firstCorners = [
    { x: 10, y: 10 },
    { x: 50, y: 10 },
    { x: 50, y: 40 },
    { x: 10, y: 40 },
  ];
  const drafts = replaceGridGeometrySourceDraft(
    emptyGridGeometrySourceDrafts(sourceItems),
    sourceItems[0].reviewItemId,
    firstCorners,
  );

  assert.deepEqual(
    gridGeometrySourceDraft(drafts, sourceItems[0].reviewItemId),
    firstCorners,
  );
  assert.equal(
    firstIncompleteGridGeometrySourceItem(sourceItems, drafts)?.reviewItemId,
    sourceItems[1].reviewItemId,
  );
  assert.deepEqual(
    gridGeometrySourceDraft(drafts, sourceItems[1].reviewItemId),
    [],
  );
});
