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
