import assert from 'node:assert/strict';
import test from 'node:test';

import { gridAuditBoardGeometryTarget } from '../src/features/operational-reviews/board-geometry-correction-target.ts';
import {
  gridAuditClassLabel,
  gridAuditProgressText,
  gridAuditSuggestedCorners,
} from '../src/features/operational-reviews/grid-audit-correction-state.ts';

const CURRENT = [
  { x: 300, y: 250 },
  { x: 700, y: 250 },
  { x: 700, y: 500 },
  { x: 300, y: 500 },
];
const NETWORK = [
  { x: 380, y: 250 },
  { x: 780, y: 251 },
  { x: 781, y: 500 },
  { x: 380, y: 499 },
];
const COMPLETE_FLAGS = {
  exclude: false,
  includeInPartialGridTraining: false,
  manualUnavailable: [],
  partial: false,
};

function reviewItem(overrides = {}) {
  return {
    approvedGeometryRevision: null,
    assetMode: 'virtual_source',
    boardConfidence: 1,
    gameId: 'g',
    geometry: { quad: CURRENT },
    geometryEngineName: 'manual_v1',
    geometryEngineVersion: 'v1',
    geometryRevision: 1,
    gridColumns: 5,
    gridRows: 3,
    importJobId: 'j',
    pendingGeometryId: null,
    positionIndex: 2,
    reasonCodes: [],
    recognizedBoardId: 'b1',
    reportedCellIndices: [],
    resolutionRevision: 0,
    reviewItemId: 'r1',
    sequenceNumber: 437061,
    slotId: 'r1',
    slotKind: 'current_review',
    sourceChecksumSha256: 'a'.repeat(64),
    sourceHeight: 900,
    sourceImageId: 'src',
    sourceWidth: 1200,
    state: 'needs_validation',
    ...overrides,
  };
}

function proposal(overrides = {}) {
  return {
    auditId: 'silent-grid-777-20261004',
    gameId: 'g',
    item: {
      auditClass: 'column_shift',
      auditGeometryRevision: 1,
      currentGeometryRevision: 1,
      humanDecidedCells: 3,
      importJobId: 'j',
      importStatus: 'proposal',
      itemId: 'p00001',
      level: 'S',
      ordinal: 0,
      positionIndex: 2,
      recognizedBoardId: 'b1',
      sequenceNumber: 437061,
      sourceImageId: 'src',
      status: 'open',
      verdictSource: 'operator',
    },
    proposal: {
      coordinateSpace: 'exif-normalized-rgb-pixels-v1',
      corners: NETWORK,
      nodes: [],
      provenance: 'audit-network-proposal',
    },
    reviewItem: reviewItem(),
    ...overrides,
  };
}

function fakeApi() {
  const calls = { preview: [], save: [] };
  return {
    api: {
      createImageGridReviewGeometryRevision: async (id, scope, command) => {
        calls.save.push({ command, id, scope });
        return { data: { created: true } };
      },
      imageGridReviewSourceAssetUrl: (id) =>
        `http://127.0.0.1:8000/source/${id}`,
      previewImageGridReviewGeometry: async (id, scope, command) => {
        calls.preview.push({ command, id, scope });
        return { data: new Blob(['png']) };
      },
    },
    calls,
  };
}

test('proposal corners stay as they are inside the photo', () => {
  const result = gridAuditSuggestedCorners(NETWORK, 1200, 900, false);
  assert.equal(result.clamped, false);
  assert.deepEqual(result.corners, NETWORK);
});

test('corners outside the photo are moved to its edge unless the board is partial', () => {
  const outside = [
    { x: -6.3, y: 365.8 },
    { x: 140.8, y: 382.8 },
    { x: 133.2, y: 472.6 },
    { x: -10.5, y: 452 },
  ];
  const fitted = gridAuditSuggestedCorners(outside, 1080, 676, false);
  assert.equal(fitted.clamped, true);
  assert.deepEqual(fitted.corners, [
    { x: 0, y: 366 },
    { x: 141, y: 383 },
    { x: 133, y: 473 },
    { x: 0, y: 452 },
  ]);
  const partial = gridAuditSuggestedCorners(outside, 1080, 676, true);
  assert.equal(partial.clamped, false);
  assert.equal(partial.corners[0].x, -6);
});

test('progress names open, corrected and skipped (stale) boards', () => {
  assert.equal(
    gridAuditProgressText({
      corrected: 10,
      noProposal: 0,
      open: 960,
      openWithSymbolDecisions: 230,
      removed: 1,
      stale: 4,
      total: 975,
    }),
    'Do poprawy: 960 · poprawione: 10 z 975 · z decyzjami symboli: 230 · nieaktualne (bez propozycji): 5',
  );
  assert.equal(gridAuditClassLabel('row_shift'), 'przesunięcie o rząd');
  assert.equal(gridAuditClassLabel('other'), 'other');
});

test('the audit target suggests the network grid, outlines the current one and saves through the existing route', async () => {
  const { api, calls } = fakeApi();
  const target = gridAuditBoardGeometryTarget({ api, proposal: proposal() });
  const loaded = await target.load();
  assert.equal(loaded.ok, true);
  const view = loaded.view;
  assert.equal(view.kind, 'audit');
  assert.deepEqual(view.suggestedCorners, NETWORK);
  assert.deepEqual(view.referenceCorners, CURRENT);
  assert.match(view.suggestionNotice, /propozycja sieci/);
  assert.ok(view.metadata.some((fact) => fact.label === 'Audyt siatek'));
  assert.equal(view.sourceUrl, 'http://127.0.0.1:8000/source/r1');

  await target.preview(NETWORK, COMPLETE_FLAGS);
  const saved = await target.save(NETWORK, COMPLETE_FLAGS, 'k1', [
    { cellIndex: 0, symbolId: 'sym' },
  ]);
  assert.deepEqual(saved, { ok: true, reviewItemId: 'r1' });
  assert.equal(calls.save.length, 1);
  assert.equal(calls.save[0].id, 'r1');
  assert.deepEqual(calls.save[0].scope, { gameId: 'g', importJobId: 'j' });
  const command = calls.save[0].command;
  assert.deepEqual(command.corners, NETWORK);
  // Bound to exactly the audited board version.
  assert.equal(command.expectedGeometryRevision, 1);
  assert.equal(command.expectedResolutionRevision, 0);
  assert.equal(command.idempotencyKey, 'k1');
  assert.deepEqual(command.cellSymbols, [{ cellIndex: 0, symbolId: 'sym' }]);
  assert.equal(command.geometryQualification, null);
  assert.deepEqual(calls.preview[0].command.corners, NETWORK);
});

test('a board without a proposal (changed after the audit) never gets the stale grid', async () => {
  const { api, calls } = fakeApi();
  const target = gridAuditBoardGeometryTarget({
    api,
    proposal: proposal({ proposal: null, reviewItem: null }),
  });
  const loaded = await target.load();
  assert.equal(loaded.ok, false);
  assert.match(loaded.error, /zmieniła się po audycie/);
  const saved = await target.save(NETWORK, COMPLETE_FLAGS, 'k');
  assert.equal(saved.ok, false);
  assert.equal(calls.save.length, 0);
});

test('audit hints use only new symbols of the exact preview and never read old approvals', async () => {
  const { api, calls } = fakeApi();
  const unprepared = gridAuditBoardGeometryTarget({
    api,
    proposal: proposal(),
  });
  await unprepared.preview(NETWORK, COMPLETE_FLAGS);
  const cells = [
    { cellIndex: 0, symbolId: 'new-plum', origin: 'predicted' },
    { cellIndex: 1, symbolId: null, origin: 'predicted' },
  ];
  const target = gridAuditBoardGeometryTarget({
    api,
    symbolsApi: {
      getImageGridReviewCorrectionSymbols: () => {
        throw new Error('Old approvals must not be read');
      },
    },
    proposal: proposal({
      symbolSuggestions: {
        artifactSha256: 'd'.repeat(64),
        previewCommand: calls.preview[0].command,
        cells,
      },
    }),
  });
  assert.deepEqual(await target.symbols(NETWORK, COMPLETE_FLAGS), {
    ok: true,
    cells,
  });
  const moved = NETWORK.map((point) => ({ ...point, x: point.x + 1 }));
  assert.equal((await target.symbols(moved, COMPLETE_FLAGS)).ok, false);
  assert.equal(
    (await target.symbols(NETWORK, { ...COMPLETE_FLAGS, exclude: true })).ok,
    false,
  );
  assert.equal((await unprepared.symbols(NETWORK, COMPLETE_FLAGS)).ok, false);
  await target.save(NETWORK, COMPLETE_FLAGS, 'k-new');
  assert.equal(calls.save[0].command.cellSymbols, undefined);
});
