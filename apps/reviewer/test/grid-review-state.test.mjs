import assert from 'node:assert/strict';
import test from 'node:test';

import {
  addGridGeometryPoint,
  completeGridGeometrySourceDrafts,
  currentGridGeometrySourceDrafts,
  emptyGridGeometrySourceDrafts,
  firstIncompleteGridGeometrySourceItem,
  GRID_CORNER_LABELS,
  gridGeometryDraftAnchor,
  gridGeometryDraftsEqual,
  gridGeometrySourceDraft,
  gridGeometrySourceItemAtPoint,
  GRID_REVIEW_VIEWS,
  gridGeometryDragTarget,
  gridReviewAnalysisCorners,
  gridReviewApprovalCommand,
  gridReviewCorners,
  gridReviewLatticeReason,
  gridReviewQualification,
  gridReviewGeometryCommand,
  gridReviewGeometryPreviewCommand,
  gridReviewSourceStats,
  orderGridReviewSourceItems,
  moveGridGeometry,
  moveGridGeometryCorner,
  nextIncompleteGridGeometrySourceItem,
  replaceGridGeometrySourceDraft,
  requiredGridGeometrySourceDrafts,
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
  pendingGeometryId: null,
  slotId: '44444444-4444-4444-8444-444444444444',
  slotKind: 'current_review',
  sequenceNumber: 91,
  sourceChecksumSha256: 'a'.repeat(64),
  sourceHeight: 800,
  sourceImageId: '55555555-5555-4555-8555-555555555555',
  sourceWidth: 1200,
  state: 'needs_validation',
};

test('partial editing allows a bounded surrounding area without changing normal editing', () => {
  const corners = [
    { x: 10, y: 10 },
    { x: 90, y: 10 },
    { x: 90, y: 90 },
    { x: 10, y: 90 },
  ];
  assert.deepEqual(
    moveGridGeometryCorner(corners, 0, { x: -20, y: -30 }, 100, 100)[0],
    { x: 0, y: 0 },
  );
  assert.deepEqual(
    moveGridGeometryCorner(corners, 0, { x: -20, y: -30 }, 100, 100, true)[0],
    { x: -20, y: -30 },
  );
  assert.deepEqual(
    moveGridGeometryCorner(corners, 0, { x: -500, y: 700 }, 100, 100, true)[0],
    { x: -100, y: 200 },
  );
  assert.deepEqual(
    addGridGeometryPoint([], { x: -20, y: -30 }, 100, 100, true),
    [{ x: -20, y: -30 }],
  );
  const moved = moveGridGeometry(corners, { x: -100, y: -50 }, 100, 100, true);
  assert.deepEqual(moved[0], { x: -90, y: -40 });
  assert.equal(moved[1].x - moved[0].x, 80);
});

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

test('an individual draft stays pending until it exactly matches the automatic geometry', () => {
  const automatic = [
    { x: 10, y: 20 },
    { x: 110, y: 20 },
    { x: 110, y: 80 },
    { x: 10, y: 80 },
  ];
  const edited = automatic.map((point, index) =>
    index === 0 ? { ...point, x: point.x + 1 } : point,
  );

  assert.equal(gridGeometryDraftsEqual(automatic, [...automatic]), true);
  assert.equal(gridGeometryDraftsEqual(edited, automatic), false);
  assert.equal(
    gridGeometryDraftsEqual(automatic.slice(0, 3), automatic),
    false,
  );
});

test('direct source editing starts from every current grid without synthetic gaps', () => {
  const second = {
    ...item,
    positionIndex: 1,
    reviewItemId: '66666666-6666-4666-8666-666666666666',
    slotId: '66666666-6666-4666-8666-666666666666',
    sequenceNumber: 92,
  };
  const drafts = currentGridGeometrySourceDrafts([second, item]);

  assert.deepEqual(gridGeometrySourceDraft(drafts, item.slotId), [
    { x: 120, y: 80 },
    { x: 1079, y: 80 },
    { x: 1079, y: 719 },
    { x: 120, y: 719 },
  ]);
  assert.equal(
    completeGridGeometrySourceDrafts([second, item], drafts)?.length,
    2,
  );
});

test('automatic v3 review starts from the symbol lattice and keeps the analysis frame separate', () => {
  const analysisQuad = [
    { x: 10, y: 10 },
    { x: 210, y: 10 },
    { x: 210, y: 130 },
    { x: 10, y: 130 },
  ];
  const symbolGridQuad = [
    { x: 20, y: 20 },
    { x: 200, y: 20 },
    { x: 200, y: 120 },
    { x: 20, y: 120 },
  ];
  const candidate = {
    ...item,
    analysisQuad,
    geometry: { latticeReasonCode: 'content_boundary_conflict' },
    geometryRevision: 0,
    localLatticeStatus: 'estimated',
    localLatticeVersion: 'structured-v3-test',
    symbolGridQuad,
  };

  assert.deepEqual(gridReviewCorners(candidate), symbolGridQuad);
  assert.deepEqual(gridReviewAnalysisCorners(candidate), analysisQuad);
  assert.equal(gridReviewLatticeReason(candidate), 'content_boundary_conflict');
});

test('a persisted manual geometry remains truth over a shadow proposal', () => {
  const manual = [
    { x: 30, y: 30 },
    { x: 190, y: 30 },
    { x: 190, y: 110 },
    { x: 30, y: 110 },
  ];
  const candidate = {
    ...item,
    analysisQuad: [
      { x: 10, y: 10 },
      { x: 210, y: 10 },
      { x: 210, y: 130 },
      { x: 10, y: 130 },
    ],
    geometry: { quad: manual },
    geometryRevision: 1,
    symbolGridQuad: [
      { x: 20, y: 20 },
      { x: 200, y: 20 },
      { x: 200, y: 120 },
      { x: 20, y: 120 },
    ],
  };

  assert.deepEqual(gridReviewCorners(candidate), manual);
  assert.equal(gridReviewAnalysisCorners(candidate), null);
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

test('a newly selected source slot has no overlay anchor until its first click', () => {
  assert.equal(gridGeometryDraftAnchor([]), null);
  assert.deepEqual(gridGeometryDraftAnchor([{ x: 10, y: 20 }]), {
    x: 10,
    y: 20,
  });
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
    slotId: '66666666-6666-4666-8666-666666666666',
    sequenceNumber: 93,
    state: 'needs_correction',
  };
  const approved = {
    ...item,
    approvedGeometryRevision: 4,
    geometryRevision: 4,
    positionIndex: 1,
    reviewItemId: '77777777-7777-4777-8777-777777777777',
    slotId: '77777777-7777-4777-8777-777777777777',
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
    slotId: `00000000-0000-4000-8000-00000000000${positionIndex}`,
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
    drafts = replaceGridGeometrySourceDraft(drafts, sourceItem.slotId, draft);
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
      sourceItems[8].slotId,
    ),
    null,
  );
});

test('a deferred filename slot remains the ninth mandatory manual draft', () => {
  const sourceItems = Array.from({ length: 9 }, (_, positionIndex) => {
    const slotId = `30000000-0000-4000-8000-00000000000${positionIndex}`;
    return {
      ...item,
      positionIndex,
      sequenceNumber: 1234 + positionIndex,
      slotId,
      ...(positionIndex === 5
        ? {
            pendingGeometryId: slotId,
            reviewItemId: null,
            slotKind: 'deferred_geometry',
            state: 'needs_correction',
          }
        : { reviewItemId: slotId }),
    };
  });
  const drafts = currentGridGeometrySourceDrafts(sourceItems);
  const completed = completeGridGeometrySourceDrafts(sourceItems, drafts);

  assert.equal(sourceItems[5].sequenceNumber, 1239);
  assert.equal(sourceItems[5].reviewItemId, null);
  assert.equal(completed?.length, 9);
  assert.deepEqual(
    completed?.map(({ item: sourceItem }) => sourceItem.positionIndex),
    [0, 1, 2, 3, 4, 5, 6, 7, 8],
  );
  assert.equal(gridReviewSourceStats(sourceItems).needsCorrectionBoards, 1);
});

test('manual completion clears only slots for which the algorithm has no grid', () => {
  const automaticQuad = [
    { x: -20, y: 80 },
    { x: 300, y: 80 },
    { x: 300, y: 500 },
    { x: -20, y: 500 },
  ];
  const proposed = {
    ...item,
    automaticPartialProposal: {
      geometryQualification: {
        completenessStatus: 'pending_partial',
        excludeFromGeometryTraining: true,
        exclusionReason: 'missing_pixels',
        unavailableCellIndices: [0, 5, 10],
        version: 'manual-geometry-qualification-v1',
      },
    },
    geometry: { manualGeometryRequired: false },
    geometryRevision: 0,
    pendingGeometryId: '80000000-0000-4000-8000-000000000001',
    reviewItemId: null,
    slotId: '80000000-0000-4000-8000-000000000001',
    slotKind: 'deferred_geometry',
    state: 'needs_validation',
    symbolGridQuad: automaticQuad,
  };
  const missing = {
    ...item,
    geometry: { manualGeometryRequired: true },
    pendingGeometryId: '80000000-0000-4000-8000-000000000002',
    positionIndex: 1,
    reviewItemId: null,
    slotId: '80000000-0000-4000-8000-000000000002',
    slotKind: 'deferred_geometry',
    state: 'needs_correction',
    symbolGridQuad: null,
  };

  const drafts = requiredGridGeometrySourceDrafts([proposed, missing]);

  assert.deepEqual(
    gridGeometrySourceDraft(drafts, proposed.slotId),
    automaticQuad,
  );
  assert.deepEqual(gridGeometrySourceDraft(drafts, missing.slotId), []);
  assert.equal(
    firstIncompleteGridGeometrySourceItem([proposed, missing], drafts),
    missing,
  );
  assert.deepEqual(
    gridReviewQualification(proposed),
    proposed.automaticPartialProposal.geometryQualification,
  );
});

test('a complete grid recovered from a weak frame is ready for validation', () => {
  const automaticQuad = [
    { x: 20, y: 80 },
    { x: 300, y: 80 },
    { x: 300, y: 500 },
    { x: 20, y: 500 },
  ];
  const qualification = {
    completenessStatus: 'complete',
    excludeFromGeometryTraining: true,
    exclusionReason: 'manual_exclusion',
    includeInPartialGridTraining: false,
    unavailableCellIndices: [],
    version: 'manual-geometry-qualification-v2',
  };
  const proposed = {
    ...item,
    automaticFrameProposal: { geometryQualification: qualification },
    geometry: { manualGeometryRequired: false },
    geometryRevision: 0,
    pendingGeometryId: '80000000-0000-4000-8000-000000000003',
    reviewItemId: null,
    slotId: '80000000-0000-4000-8000-000000000003',
    slotKind: 'deferred_geometry',
    state: 'needs_validation',
    symbolGridQuad: automaticQuad,
  };

  const drafts = requiredGridGeometrySourceDrafts([proposed]);

  assert.deepEqual(
    gridGeometrySourceDraft(drafts, proposed.slotId),
    automaticQuad,
  );
  assert.deepEqual(gridReviewQualification(proposed), qualification);
  assert.equal(firstIncompleteGridGeometrySourceItem([proposed], drafts), null);
});

test('v1.1 projected draft opens with four corners while a saved human revision wins', () => {
  const draft = [
    { x: 15, y: 105 },
    { x: 95, y: 105 },
    { x: 95, y: 185 },
    { x: 15, y: 185 },
  ];
  const candidate = {
    ...item,
    geometry: { manualGeometryRequired: true },
    geometryRevision: 0,
    pendingGeometryId: '80000000-0000-4000-8000-000000000004',
    reviewDraftQuad: draft,
    reviewDraftOrigin: 'page_projection_confident_neighbors_v1',
    reviewItemId: null,
    slotId: '80000000-0000-4000-8000-000000000004',
    slotKind: 'deferred_geometry',
    state: 'needs_correction',
    symbolGridQuad: null,
  };
  const drafts = requiredGridGeometrySourceDrafts([candidate]);
  assert.deepEqual(gridGeometrySourceDraft(drafts, candidate.slotId), draft);
  assert.equal(firstIncompleteGridGeometrySourceItem([candidate], drafts), null);
  assert.deepEqual(completeGridGeometrySourceDrafts([candidate], drafts)?.[0].corners, draft);
  assert.deepEqual(
    gridReviewGeometryCommand(candidate, draft, 'v1.1-reviewed').corners,
    draft,
  );
  const human = {
    ...candidate,
    geometry: {
      corners: [
        { x: 20, y: 110 },
        { x: 100, y: 110 },
        { x: 100, y: 190 },
        { x: 20, y: 190 },
      ],
    },
    geometryRevision: 1,
  };
  assert.deepEqual(gridReviewCorners(human), human.geometry.corners);
});

test('pausing source geometry preserves completed drafts and resumes at the next row-major slot', () => {
  const sourceItems = [
    {
      ...item,
      positionIndex: 0,
      reviewItemId: '10000000-0000-4000-8000-000000000001',
      slotId: '10000000-0000-4000-8000-000000000001',
      sequenceNumber: 100,
    },
    {
      ...item,
      positionIndex: 1,
      reviewItemId: '10000000-0000-4000-8000-000000000002',
      slotId: '10000000-0000-4000-8000-000000000002',
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
    sourceItems[0].slotId,
    firstCorners,
  );

  assert.deepEqual(
    gridGeometrySourceDraft(drafts, sourceItems[0].slotId),
    firstCorners,
  );
  assert.equal(
    firstIncompleteGridGeometrySourceItem(sourceItems, drafts)?.slotId,
    sourceItems[1].slotId,
  );
  assert.deepEqual(gridGeometrySourceDraft(drafts, sourceItems[1].slotId), []);
});

test('canvas hit testing selects the visible moved source draft', () => {
  const firstItem = {
    ...item,
    geometry: {
      corners: [
        { x: 10, y: 10 },
        { x: 110, y: 10 },
        { x: 110, y: 110 },
        { x: 10, y: 110 },
      ],
    },
  };
  const secondItem = {
    ...item,
    positionIndex: 1,
    reviewItemId: '20000000-0000-4000-8000-000000000002',
    slotId: '20000000-0000-4000-8000-000000000002',
    geometry: {
      corners: [
        { x: 200, y: 200 },
        { x: 300, y: 200 },
        { x: 300, y: 300 },
        { x: 200, y: 300 },
      ],
    },
  };
  const movedCorners = [
    { x: 400, y: 400 },
    { x: 500, y: 400 },
    { x: 500, y: 500 },
    { x: 400, y: 500 },
  ];
  const drafts = replaceGridGeometrySourceDraft(
    emptyGridGeometrySourceDrafts([firstItem, secondItem]),
    secondItem.slotId,
    movedCorners,
  );

  assert.equal(
    gridGeometrySourceItemAtPoint(
      [firstItem, secondItem],
      drafts,
      firstItem.slotId,
      gridReviewCorners(firstItem),
      { x: 450, y: 450 },
    )?.slotId,
    secondItem.slotId,
  );
  assert.equal(
    gridGeometrySourceItemAtPoint(
      [firstItem, secondItem],
      drafts,
      firstItem.slotId,
      gridReviewCorners(firstItem),
      { x: 250, y: 250 },
    ),
    null,
  );
});

test('canvas hit testing includes a corner handle slightly outside the quad', () => {
  const corners = [
    { x: 100, y: 100 },
    { x: 200, y: 100 },
    { x: 200, y: 200 },
    { x: 100, y: 200 },
  ];
  const sourceItem = { ...item, geometry: { corners } };
  const drafts = currentGridGeometrySourceDrafts([sourceItem]);

  assert.equal(
    gridGeometrySourceItemAtPoint(
      [sourceItem],
      drafts,
      sourceItem.slotId,
      corners,
      { x: 92, y: 92 },
      12,
    )?.slotId,
    sourceItem.slotId,
  );
  assert.equal(
    gridGeometrySourceItemAtPoint(
      [sourceItem],
      drafts,
      sourceItem.slotId,
      corners,
      { x: 80, y: 80 },
      12,
    ),
    null,
  );
});
