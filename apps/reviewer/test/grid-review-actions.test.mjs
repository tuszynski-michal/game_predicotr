import assert from 'node:assert/strict';
import test from 'node:test';

import { approveGridReviewSource } from '../src/features/grid-reviews/grid-review-actions.ts';

const qualification = {
  completenessStatus: 'pending_partial',
  excludeFromGeometryTraining: true,
  exclusionReason: 'missing_pixels',
  unavailableCellIndices: [0, 5, 10],
  version: 'manual-geometry-qualification-v1',
};

function partialItem() {
  return {
    approvedGeometryRevision: null,
    assetMode: 'virtual_source',
    automaticPartialProposal: { geometryQualification: qualification },
    boardConfidence: 0,
    gameId: '11111111-1111-4111-8111-111111111111',
    geometry: { manualGeometryRequired: false },
    geometryEngineName: 'structured',
    geometryEngineVersion: 'v0.10',
    geometryQualification: null,
    geometryRevision: 0,
    gridColumns: 5,
    gridRows: 3,
    importJobId: '22222222-2222-4222-8222-222222222222',
    pendingGeometryId: '33333333-3333-4333-8333-333333333333',
    positionIndex: 0,
    reasonCodes: ['partial_lattice_requires_confirmation'],
    recognizedBoardId: null,
    resolutionRevision: 0,
    reviewItemId: null,
    sequenceNumber: 1,
    slotId: '33333333-3333-4333-8333-333333333333',
    slotKind: 'deferred_geometry',
    sourceChecksumSha256: 'a'.repeat(64),
    sourceHeight: 800,
    sourceImageId: '44444444-4444-4444-8444-444444444444',
    sourceWidth: 1200,
    state: 'needs_validation',
    symbolGridQuad: [
      { x: -20, y: 80 },
      { x: 300, y: 80 },
      { x: 300, y: 500 },
      { x: -20, y: 500 },
    ],
  };
}

test('confirmation persists an automatic partial grid with its qualification', async () => {
  let command;
  const api = {
    async createImageGridReviewSourceGeometryRevision(
      _gameId,
      _query,
      payload,
    ) {
      command = payload;
      return { data: { created: true, geometryRevisions: [{}] } };
    },
    async approveImageGridReviewSourceGeometry() {
      assert.fail('a pending proposal must be materialized before approval');
    },
  };
  const item = partialItem();

  const result = await approveGridReviewSource(api, [item]);

  assert.equal(result.ok, true);
  assert.equal(result.approval.changedCount, 1);
  assert.deepEqual(command.targets[0].corners, item.symbolGridQuad);
  assert.deepEqual(command.targets[0].geometryQualification, qualification);
  assert.equal(command.targets[0].pendingGeometryId, item.pendingGeometryId);
});

test('confirmation persists a complete grid recovered from a weak frame', async () => {
  let command;
  const api = {
    async createImageGridReviewSourceGeometryRevision(
      _gameId,
      _query,
      payload,
    ) {
      command = payload;
      return { data: { created: true, geometryRevisions: [{}] } };
    },
    async approveImageGridReviewSourceGeometry() {
      assert.fail('a pending proposal must be materialized before approval');
    },
  };
  const item = partialItem();
  const frameQualification = {
    completenessStatus: 'complete',
    excludeFromGeometryTraining: true,
    exclusionReason: 'manual_exclusion',
    includeInPartialGridTraining: false,
    unavailableCellIndices: [],
    version: 'manual-geometry-qualification-v2',
  };
  item.automaticPartialProposal = null;
  item.automaticFrameProposal = { geometryQualification: frameQualification };
  item.symbolGridQuad = [
    { x: 20, y: 80 },
    { x: 300, y: 80 },
    { x: 300, y: 500 },
    { x: 20, y: 500 },
  ];

  const result = await approveGridReviewSource(api, [item]);

  assert.equal(result.ok, true);
  assert.deepEqual(command.targets[0].corners, item.symbolGridQuad);
  assert.deepEqual(
    command.targets[0].geometryQualification,
    frameQualification,
  );
});

test('a pending slot without an automatic grid still requires manual geometry', async () => {
  const item = partialItem();
  item.automaticPartialProposal = null;
  item.symbolGridQuad = null;
  let called = false;
  const api = {
    async createImageGridReviewSourceGeometryRevision() {
      called = true;
    },
  };

  const result = await approveGridReviewSource(api, [item]);

  assert.equal(result.ok, false);
  assert.match(result.error, /wymagają zapisania kompletnej geometrii/);
  assert.equal(called, false);
});
