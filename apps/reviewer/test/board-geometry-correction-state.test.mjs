import assert from 'node:assert/strict';
import test from 'node:test';

import {
  gridCellsWithoutPixels,
  gridReviewCorners,
  gridReviewGeometryPreviewCommand,
  gridReviewQualification,
} from '../src/features/operational-reviews/board-geometry-correction-state.ts';

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
  state: 'needs_correction',
};

const quad = (x, y, width, height) => [
  { x, y },
  { x: x + width, y },
  { x: x + width, y: y + height },
  { x, y: y + height },
];

test('an unsaved board starts from its symbol lattice', () => {
  const symbolGridQuad = quad(20, 20, 180, 100);
  assert.deepEqual(
    gridReviewCorners({
      ...item,
      analysisQuad: quad(10, 10, 200, 120),
      geometryRevision: 0,
      symbolGridQuad,
    }),
    symbolGridQuad,
  );
});

test('a projected draft wins over the lattice, a saved human revision wins over both', () => {
  const draft = quad(15, 105, 80, 80);
  const candidate = {
    ...item,
    geometryRevision: 0,
    reviewDraftQuad: draft,
    symbolGridQuad: quad(20, 20, 180, 100),
  };
  assert.deepEqual(gridReviewCorners(candidate), draft);
  const manual = quad(30, 30, 160, 80);
  assert.deepEqual(
    gridReviewCorners({
      ...candidate,
      geometry: { corners: manual },
      geometryRevision: 1,
    }),
    manual,
  );
});

test('without any geometry the board starts from an inset frame', () => {
  assert.deepEqual(gridReviewCorners(item), [
    { x: 120, y: 80 },
    { x: 1079, y: 80 },
    { x: 1079, y: 719 },
    { x: 120, y: 719 },
  ]);
});

test('corners outside the photo are kept only for a partial board', () => {
  const outside = quad(-20, 80, 320, 420);
  const partial = {
    completenessStatus: 'pending_partial',
    excludeFromGeometryTraining: true,
    exclusionReason: 'missing_pixels',
    includeInPartialGridTraining: false,
    unavailableCellIndices: [0, 4],
    version: 'manual-geometry-qualification-v2',
  };
  assert.deepEqual(
    gridReviewCorners({ ...item, geometry: { quad: outside } }),
    gridReviewCorners(item),
  );
  assert.deepEqual(
    gridReviewCorners({
      ...item,
      geometry: { quad: outside },
      geometryQualification: partial,
    }),
    outside,
  );
});

test('a persisted qualification wins over automatic proposals', () => {
  const frame = { completenessStatus: 'complete', version: 'frame' };
  const partial = { completenessStatus: 'pending_partial', version: 'partial' };
  const persisted = { completenessStatus: 'complete', version: 'persisted' };
  assert.equal(gridReviewQualification(item), undefined);
  assert.equal(
    gridReviewQualification({
      ...item,
      automaticPartialProposal: { geometryQualification: partial },
    }),
    partial,
  );
  assert.equal(
    gridReviewQualification({
      ...item,
      automaticFrameProposal: { geometryQualification: frame },
      automaticPartialProposal: { geometryQualification: partial },
    }),
    frame,
  );
  assert.equal(
    gridReviewQualification({
      ...item,
      automaticFrameProposal: { geometryQualification: frame },
      geometryQualification: persisted,
    }),
    persisted,
  );
});

test('preview and save bind the exact topology and source identity', () => {
  const corners = quad(1, 2, 2, 2);
  assert.deepEqual(gridReviewGeometryPreviewCommand(item, corners), {
    corners,
    expectedGeometryRevision: 4,
    expectedGridColumns: 4,
    expectedGridRows: 2,
    expectedResolutionRevision: 7,
    expectedSourceChecksumSha256: 'a'.repeat(64),
    expectedSourceHeight: 800,
    expectedSourceWidth: 1200,
  });
});

test('only cells with no area inside the photo have no pixels to label', () => {
  // Five 100 px columns: the first lies entirely left of the photo, the
  // second is cut by its edge and keeps real pixels.
  const corners = [
    { x: -150, y: 100 },
    { x: 350, y: 100 },
    { x: 350, y: 400 },
    { x: -150, y: 400 },
  ];
  assert.deepEqual(gridCellsWithoutPixels(corners, 1000, 800), [0, 5, 10]);
  assert.deepEqual(
    gridCellsWithoutPixels(
      corners.map((point) => ({ ...point, x: point.x + 200 })),
      1000,
      800,
    ),
    [],
  );
});
