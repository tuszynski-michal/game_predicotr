import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  boardLatticeCells,
  boardLatticeCorners,
  boardLatticeTransportCorners,
  boardLatticeUnavailable,
  boardLatticeWithoutPixels,
  boardLatticePointInSource,
  parseBoardLattice,
  translatedBoardLattice,
  transformedBoardLattice,
  regularBoardLattice,
} from '../src/features/operational-reviews/board-lattice-state.ts';
import {
  readBoardLatticeDraft,
  writeBoardLatticeDraft,
} from '../src/features/operational-reviews/board-lattice-draft-storage.ts';
import { completeManualGridFlags } from '@game-predictor/manual-image-selection-core/manual-grid-qualification';
import { gridReviewGeometryPreviewCommand } from '../src/features/operational-reviews/board-geometry-correction-state.ts';
import {
  deferredBoardCellGeometryPreviewCommand,
  deferredBoardCellGeometryResolutionCommand,
} from '../src/features/operational-reviews/deferred-board-cell-geometry-state.ts';
const nodes = Array.from({ length: 24 }, (_, i) => ({
  x: 10.125 + (i % 6) * 20.5,
  y: 20.375 + Math.floor(i / 6) * 30.25,
}));
function storage() {
  const data = new Map();
  return {
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => data.set(k, v),
    removeItem: (k) => data.delete(k),
  };
}
test('reported and deferred commands retain all float nodes and the immutable proposal pin', () => {
  const item = {
    geometryRevision: 2,
    resolutionRevision: 3,
    sourceChecksumSha256: 'a'.repeat(64),
    expectedProposalChecksumSha256: 'b'.repeat(64),
    gridRows: 3,
    gridColumns: 5,
  };
  const reported = gridReviewGeometryPreviewCommand(
    item,
    boardLatticeCorners(nodes),
    nodes,
  );
  const context = {
    sourceWidth: 200,
    sourceHeight: 200,
    expectedProposalChecksumSha256: item.expectedProposalChecksumSha256,
    item: {
      ...item,
      expectedGeometryRevision: 2,
      expectedReviewResolutionRevision: 3,
      processingManifestChecksumSha256: 'c'.repeat(64),
    },
  };
  const deferred = deferredBoardCellGeometryPreviewCommand(
    context,
    boardLatticeCorners(nodes),
    completeManualGridFlags,
    nodes,
  );
  const resolution = deferredBoardCellGeometryResolutionCommand(
    context,
    boardLatticeCorners(nodes),
    'request-key',
    completeManualGridFlags,
    nodes,
  );
  for (const command of [reported, deferred, resolution]) {
    assert.deepEqual(command.latticeNodes, nodes);
    assert.equal(
      command.expectedProposalChecksumSha256,
      item.expectedProposalChecksumSha256,
    );
    assert.equal(command.corners[0].x, 10);
  }
});
test('all 24 float coordinates survive geometry, cells and transport outline', () => {
  assert.deepEqual(parseBoardLattice(nodes), nodes);
  assert.deepEqual(boardLatticeCorners(nodes), [
    nodes[0],
    nodes[5],
    nodes[23],
    nodes[18],
  ]);
  assert.deepEqual(boardLatticeCells(nodes)[6], [
    nodes[7],
    nodes[8],
    nodes[14],
    nodes[13],
  ]);
  assert.equal(boardLatticeCells(nodes).length, 15);
  assert.equal(boardLatticeTransportCorners(nodes)[0].x, 10);
  assert.equal(nodes[0].x, 10.125);
  assert.equal(parseBoardLattice(nodes.slice(0, 23)), null);
  const inverted = structuredClone(nodes);
  inverted[7] = { ...nodes[19] };
  assert.equal(parseBoardLattice(inverted), null);
});
test('partial cells keep pixels while outside cells cannot receive crop symbols', () => {
  const shifted = nodes.map((p) => ({ x: p.x - 50, y: p.y }));
  assert.deepEqual(boardLatticeWithoutPixels(shifted, 200, 200), [0, 5, 10]);
  assert.deepEqual(
    boardLatticeUnavailable(shifted, 200, 200),
    [0, 1, 5, 6, 10, 11],
  );
});
test('pointer and translation retain fractions, with explicit outside mode', () => {
  assert.deepEqual(
    boardLatticePointInSource(
      { x: 1.125, y: 2.375 },
      { x: 4.5, y: 8.5 },
      200,
      200,
      false,
    ),
    { x: 5.625, y: 10.875 },
  );
  assert.equal(
    translatedBoardLattice(nodes, { x: 0.125, y: -0.125 }, 200, 200, false)[7]
      .x,
    nodes[7].x + 0.125,
  );
  assert.equal(
    translatedBoardLattice(nodes, { x: -100, y: 0 }, 200, 200, false)[0].x,
    0,
  );
  assert.equal(
    translatedBoardLattice(nodes, { x: -100, y: 0 }, 200, 200, true)[0].x,
    -89.875,
  );
});
test('restart restores float nodes, symbols and exact idempotency; source drift blocks', () => {
  const store = storage(),
    scope = {
      targetKey: 'neural:1:revision2',
      sourceUrl: 'source?sha=a',
      width: 200,
      height: 200,
    };
  const draft = {
    corners: boardLatticeCorners(nodes),
    latticeNodes: nodes,
    flags: completeManualGridFlags,
    symbols: { 0: 'cherry', 1: null },
    idempotency: {
      commandKey: 'exact-24-nodes',
      idempotencyKey: 'saved-before-request',
    },
  };
  writeBoardLatticeDraft(store, scope, draft);
  assert.deepEqual(readBoardLatticeDraft(store, scope), draft);
  assert.throws(
    () => readBoardLatticeDraft(store, { ...scope, sourceUrl: 'source?sha=b' }),
    /innego źródła/,
  );
});

test('corner homography preserves internal correction and maps every node by one projective transform', () => {
  const adjusted = structuredClone(nodes);
  adjusted[7].x += 3.125;
  adjusted[7].y -= 2.375;
  const project = ({ x, y }) => ({
    x: (1.2 * x + 0.15 * y + 4) / (1 + 0.001 * x + 0.0005 * y),
    y: (0.1 * x + 1.1 * y + 9) / (1 + 0.001 * x + 0.0005 * y),
  });
  const outline = boardLatticeCorners(adjusted).map(project);
  const transformed = transformedBoardLattice(adjusted, outline);
  transformed.forEach((p, i) => {
    assert.ok(Math.abs(p.x - project(adjusted[i]).x) < 1e-9);
    assert.ok(Math.abs(p.y - project(adjusted[i]).y) < 1e-9);
  });
  assert.notDeepEqual(transformed[7], regularBoardLattice(outline)[7]);
  const crossed = [outline[0], outline[2], outline[1], outline[3]];
  assert.throws(() => transformedBoardLattice(adjusted, crossed), /Narożniki/);
  assert.throws(() => regularBoardLattice(crossed), /Narożniki/);
  assert.deepEqual(regularBoardLattice(boardLatticeCorners(nodes)), nodes);
});
test('locally convex cells cannot overlap distant cells or cross distant edges', () => {
  const winding = Array.from({ length: 24 }, (_, i) => {
    const angle = (-(i % 6) * 80 * Math.PI) / 180,
      radius = 100 + Math.floor(i / 6) * 30;
    return {
      x: 300 + radius * Math.cos(angle),
      y: 300 + radius * Math.sin(angle),
    };
  });
  assert.equal(parseBoardLattice(winding), null);
});
test('draft revision drift blocks restoring older geometry into a newer server view', () => {
  const store = storage(),
    scope = {
      targetKey: 'stable-board',
      revisionKey: 'r1',
      sourceUrl: 'sha=a',
      width: 200,
      height: 200,
    };
  writeBoardLatticeDraft(store, scope, {
    corners: boardLatticeCorners(nodes),
    latticeNodes: nodes,
    flags: completeManualGridFlags,
    symbols: {},
    idempotency: null,
  });
  assert.throws(
    () => readBoardLatticeDraft(store, { ...scope, revisionKey: 'r2' }),
    /innego źródła/,
  );
});

test('all three real adapters advertise empty neural drafts by provenance pin and preserve exact nodes in requests', async () => {
  const {
    deferredBoardGeometryTarget,
    reportedBoardGeometryTarget,
    operationalBoardGeometryTarget,
  } =
    await import('../src/features/operational-reviews/board-geometry-correction-target.ts');
  const outline = boardLatticeCorners(nodes);
  for (const [pin, existingNodes] of [
    [null, null],
    ['d'.repeat(64), null],
    [null, nodes],
  ]) {
    const item = {
      id: 'board',
      reviewItemId: 'board',
      slotId: 'slot',
      gameId: 'game',
      importJobId: 'job',
      sourceChecksumSha256: 'a'.repeat(64),
      sourceWidth: 200,
      sourceHeight: 200,
      positionIndex: 0,
      sequenceNumber: 1,
      geometryRevision: 2,
      resolutionRevision: 3,
      geometryQualification: null,
      geometry: { latticeBoundsQuad: outline },
      gridRows: 3,
      gridColumns: 5,
      reportedCellIndices: [],
      expectedProposalChecksumSha256: pin,
      latticeNodes: existingNodes,
    };
    const context = {
      item: {
        ...item,
        expectedGeometryRevision: 2,
        expectedReviewResolutionRevision: 3,
        processingManifestChecksumSha256: 'b'.repeat(64),
      },
      sourceWidth: 200,
      sourceHeight: 200,
      suggestedCorners: outline,
      expectedProposalChecksumSha256: pin,
      latticeNodes: existingNodes,
    };
    const requests = [];
    const preview = async (...args) => {
      requests.push(args.at(-1));
      return { data: new Blob(['png']) };
    };
    const save = async (...args) => {
      requests.push(args.at(-1));
      return { data: { reviewItemId: 'board', item } };
    };
    const api = {
      getPendingBoardCellGeometryCorrectionContext: async () => ({
        data: context,
      }),
      previewPendingBoardCellGeometryCorrection: preview,
      resolvePendingBoardCellGeometryManually: save,
      imageGridReviewSourceAssetUrl: () => 'source',
      previewImageGridReviewGeometry: preview,
      createImageGridReviewGeometryRevision: save,
      previewOperationalImageReviewGeometry: preview,
      createOperationalImageReviewGeometryRevision: save,
    };
    const targets = [
      deferredBoardGeometryTarget({
        api,
        apiBaseUrl: 'http://localhost',
        pendingId: 'p',
        scope: { gameId: 'game', importJobId: 'job' },
      }),
      reportedBoardGeometryTarget({ api, item }),
      operationalBoardGeometryTarget({
        api,
        apiBaseUrl: 'http://localhost',
        importJobId: 'job',
        item,
      }),
    ];
    for (const target of targets) {
      const loaded = await target.load();
      assert.equal(loaded.ok, true);
      assert.equal(
        loaded.view.supportsLatticeEditing,
        pin !== null || existingNodes !== null,
      );
      assert.deepEqual(
        loaded.view.suggestedLatticeNodes,
        existingNodes ?? undefined,
      );
      if (pin !== null || existingNodes !== null) {
        const regular = regularBoardLattice(loaded.view.suggestedCorners);
        await target.preview(outline, completeManualGridFlags, regular);
        await target.save(
          outline,
          completeManualGridFlags,
          'key',
          undefined,
          regular,
        );
        for (const request of requests.slice(-2)) {
          assert.deepEqual(request.latticeNodes, regular);
          assert.equal(
            request.expectedProposalChecksumSha256,
            pin ?? undefined,
          );
        }
      }
    }
  }
});
test('pre-revision draft format is safely rejected when explicit revision is required', () => {
  const store = storage(),
    scope = { targetKey: 'same', sourceUrl: 'source', width: 200, height: 200 };
  writeBoardLatticeDraft(store, scope, {
    corners: boardLatticeCorners(nodes),
    latticeNodes: nodes,
    flags: completeManualGridFlags,
    symbols: {},
    idempotency: null,
  });
  assert.throws(
    () => readBoardLatticeDraft(store, { ...scope, revisionKey: 'r1' }),
    /innego źródła/,
  );
});
