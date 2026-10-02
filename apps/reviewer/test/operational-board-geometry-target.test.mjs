import assert from 'node:assert/strict';
import test from 'node:test';

import { operationalBoardGeometryTarget } from '../src/features/operational-reviews/board-geometry-correction-target.ts';
import {
  resolveOperationalReview,
  SEQUENCE_PINNED_BY_SOURCE_MESSAGE,
} from '../src/features/operational-reviews/operational-review-actions.ts';

const LATTICE = [
  { x: 100, y: 80 },
  { x: 500, y: 80 },
  { x: 500, y: 320 },
  { x: 100, y: 320 },
];
const PARTIAL = [
  { x: -200, y: 80 },
  { x: 300, y: 80 },
  { x: 300, y: 320 },
  { x: -200, y: 320 },
];
const COMPLETE_FLAGS = {
  exclude: false,
  includeInPartialGridTraining: false,
  manualUnavailable: [],
  partial: false,
};
const PARTIAL_FLAGS = { ...COMPLETE_FLAGS, exclude: true, partial: true };

function operationalItem(overrides = {}) {
  return {
    boardChecksumSha256: 'b'.repeat(64),
    cells: [],
    createdAt: '2026-10-01T00:00:00Z',
    gameId: 'game-1',
    geometry: { latticeBoundsQuad: LATTICE },
    geometryQualification: null,
    geometryRevision: 1,
    id: 'review-1',
    importJobId: 'job-1',
    pipelineFingerprint: 'c'.repeat(64),
    positionIndex: 2,
    recognizedBoardId: 'board-1',
    resolutionRevision: 0,
    resolvedAt: null,
    resolvedBy: null,
    resolvedValue: null,
    sequenceNumber: null,
    sourceChecksumSha256: 'a'.repeat(64),
    sourceHeight: 420,
    sourceOrderIndex: 0,
    sourceWidth: 620,
    status: 'pending',
    suggestedSequenceNumber: 102,
    ...overrides,
  };
}

function fakeApi() {
  const calls = { preview: [], save: [] };
  return {
    api: {
      createOperationalImageReviewGeometryRevision: async (id, scope, body) => {
        calls.save.push({ body, id, scope });
        return { data: { created: true, geometryRevision: { revision: 2 } } };
      },
      previewOperationalImageReviewGeometry: async (id, scope, body) => {
        calls.preview.push({ body, id, scope });
        return { data: new Blob(['png'], { type: 'image/png' }) };
      },
    },
    calls,
  };
}

function target(item, api) {
  return operationalBoardGeometryTarget({
    api,
    apiBaseUrl: 'http://localhost:3001/api/review',
    importJobId: 'job-1',
    item,
  });
}

test('a plain board previews and saves without a qualification (TASK-0798)', async () => {
  const { api, calls } = fakeApi();
  const board = target(operationalItem(), api);
  const loaded = await board.load();
  assert.equal(loaded.ok, true);
  assert.equal(loaded.view.kind, 'operational');
  assert.equal(loaded.view.supportsPartial, true);
  assert.deepEqual(loaded.view.initialFlags, COMPLETE_FLAGS);
  assert.deepEqual(loaded.view.suggestedCorners, LATTICE);
  assert.match(
    loaded.view.sourceUrl,
    /usage=board-cell-geometry-editor-v19-v1/,
  );
  assert.match(
    loaded.view.metadata.map((fact) => `${fact.label}:${fact.value}`).join('|'),
    /Numer planszy:102/,
  );

  assert.equal((await board.preview(LATTICE, COMPLETE_FLAGS)).ok, true);
  assert.deepEqual(calls.preview[0], {
    body: {
      corners: LATTICE,
      expectedGeometryRevision: 1,
      expectedResolutionRevision: 0,
      geometryQualification: null,
    },
    id: 'review-1',
    scope: { gameId: 'game-1', importJobId: 'job-1' },
  });
  assert.equal(board.takeSavedGeometry(), null);
});

test('a board marked partial sends the qualification on preview and save', async () => {
  const { api, calls } = fakeApi();
  const board = target(operationalItem(), api);
  await board.load();
  await board.preview(PARTIAL, PARTIAL_FLAGS);
  const saved = await board.save(PARTIAL, PARTIAL_FLAGS, 'key-1');

  const previewQualification = calls.preview[0].body.geometryQualification;
  assert.equal(previewQualification.completenessStatus, 'pending_partial');
  assert.deepEqual(
    previewQualification.unavailableCellIndices,
    [0, 1, 5, 6, 10, 11],
  );
  assert.deepEqual(saved, { ok: true, reviewItemId: 'review-1' });
  assert.deepEqual(calls.save[0].body, {
    corners: PARTIAL,
    correctedBy: 'local-admin',
    expectedGeometryRevision: 1,
    expectedResolutionRevision: 0,
    geometryQualification: previewQualification,
    idempotencyKey: 'key-1',
  });
  // The dialog reads the saved response exactly once.
  assert.deepEqual(board.takeSavedGeometry(), {
    created: true,
    geometryRevision: { revision: 2 },
  });
  assert.equal(board.takeSavedGeometry(), null);
});

test('a persisted partial board opens partial and keeps sending a qualification', async () => {
  const { api, calls } = fakeApi();
  const board = target(
    operationalItem({
      geometry: { latticeBoundsQuad: PARTIAL },
      geometryQualification: {
        completenessStatus: 'pending_partial',
        excludeFromGeometryTraining: true,
        exclusionReason: 'missing_pixels',
        unavailableCellIndices: [0, 1, 5, 6, 10, 11],
        version: 'manual-geometry-qualification-v1',
      },
      geometryRevision: 2,
    }),
    api,
  );
  const loaded = await board.load();
  assert.equal(loaded.view.initialFlags.partial, true);
  // Signed corners of the partial board are kept, never clamped to the photo.
  assert.deepEqual(loaded.view.suggestedCorners, PARTIAL);
  await board.preview(PARTIAL, loaded.view.initialFlags);
  assert.equal(
    calls.preview[0].body.geometryQualification.completenessStatus,
    'pending_partial',
  );
  // A partial flag without any missing field is refused before any request.
  assert.throws(
    () => board.commandKey(LATTICE, PARTIAL_FLAGS),
    /Niepełna plansza/,
  );
});

test('a board without the source size cannot open the editor', async () => {
  const { api } = fakeApi();
  const loaded = await target(
    operationalItem({ sourceHeight: null, sourceWidth: null }),
    api,
  ).load();
  assert.equal(loaded.ok, false);
  assert.equal(loaded.isConflict, false);
  assert.match(loaded.error, /wymiarów zdjęcia źródłowego/);
});

test('a decision that moves a board to another number explains the source rule', async () => {
  const result = await resolveOperationalReview(
    {
      resolveOperationalImageReviewItem: async () => ({
        error: {
          code: 'IMAGE_REVIEW_SEQUENCE_PINNED_BY_SOURCE',
          details: { boardSequenceNumber: 102, requestedSequenceNumber: 109 },
          message: 'The board number comes from its source geometry.',
        },
      }),
    },
    {
      command: { action: 'corrected', sequenceNumber: 109 },
      gameId: 'game-1',
      importJobId: 'job-1',
      reviewItemId: 'review-1',
    },
  );
  assert.equal(result.ok, false);
  // Not a revision conflict: the form keeps its draft instead of reloading.
  assert.equal(result.isRevisionConflict, false);
  assert.equal(result.error, SEQUENCE_PINNED_BY_SOURCE_MESSAGE);
  assert.match(result.error, /nazwy zdjęcia seq_\*/);
});
