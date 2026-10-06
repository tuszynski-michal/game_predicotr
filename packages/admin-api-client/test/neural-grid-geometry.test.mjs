import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

const gameId = '11111111-1111-4111-8111-111111111111';
const itemId = '22222222-2222-4222-8222-222222222222';
const latticeNodes = Array.from({ length: 24 }, (_, i) => ({
  x: (i % 6) * 20.25 + 1.125,
  y: Math.floor(i / 6) * 20.375 + 1.625,
}));
latticeNodes[8].x += 0.3125;
const body = {
  corners: [{ x: 1, y: 2 }, { x: 102, y: 2 }, { x: 102, y: 63 }, { x: 1, y: 63 }],
  actor: 'local-owner',
  expectedGeometryRevision: 2,
  expectedSourceChecksumSha256: 'a'.repeat(64),
  latticeNodes,
  expectedProposalChecksumSha256: 'b'.repeat(64),
};

test('existing geometry wrappers transmit exact floating24 nodes and proposal CAS pin', async () => {
  const requests = [];
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requests.push({ url: new URL(request.url), body: await request.clone().json() });
      return Response.json({});
    },
  });
  const context = { gameId, importJobId: itemId };
  await api.previewOperationalImageReviewGeometry(itemId, context, body);
  await api.createOperationalImageReviewGeometryRevision(itemId, context, { ...body, commandKey: 'same-op' });
  await api.previewImageGridReviewGeometry(itemId, context, body);
  await api.createImageGridReviewGeometryRevision(itemId, context, { ...body, commandKey: 'same-op' });
  await api.previewPendingBoardCellGeometryCorrection(itemId, context, body);
  await api.previewPendingBoardCellGeometrySymbols(itemId, context, body);
  await api.resolvePendingBoardCellGeometryManually(itemId, context, { ...body, commandKey: 'same-op' });
  assert.equal(requests.length, 7);
  for (const request of requests) {
    assert.deepEqual(request.body.latticeNodes, latticeNodes);
    assert.equal(request.body.expectedProposalChecksumSha256, body.expectedProposalChecksumSha256);
    assert.ok(request.url.searchParams.get('gameId') === gameId ||
      request.url.pathname.includes(`/games/${gameId}/`));
  }
});

test('neural source binding uses existing override route without invented quads', async () => {
  const requests = [];
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requests.push({ url: new URL(request.url), body: await request.clone().json() });
      return Response.json({});
    },
  });
  const selected = {
    gameId, sourceChecksumSha256: 'a'.repeat(64), imageWidth: 500, imageHeight: 300,
    finalQuads: [], actor: 'local-owner', expectedOverrideRevision: 0,
    geometryPreflightJobId: itemId, geometryManifestChecksumSha256: 'c'.repeat(64),
    neuralProposalBinding: {
      contractVersion: 'neural-source-binding-v1', gameId, sourceSelectionId: itemId,
      sourceChecksumSha256: 'a'.repeat(64), sourceWidth: 500, sourceHeight: 300,
      proposalChecksumSha256: 'b'.repeat(64),
      originalRange: { sequenceRangeStart: 101, sequenceRangeEnd: 105 },
      confirmedRange: { sequenceRangeStart: 101, sequenceRangeEnd: 105 },
      assignments: [{ detectionId: 'd', positionIndex: 3 }],
      missingPositionIndexes: [0, 1, 2, 4], ignoredDetectionIds: ['a', 'b', 'c'],
    },
  };
  await api.createBrowserPageGeometryOverride(itemId, selected);
  assert.deepEqual(requests[0].body, selected);
  assert.equal(requests[0].url.pathname,
    `/api/v1/admin/image-imports/browser-selections/${itemId}/page-geometry-overrides`);
});

test('legacy geometry wrapper keeps its previous body without lattice fields', async () => {
  let received;
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      received = await request.clone().json();
      return Response.json({});
    },
  });
  const { latticeNodes: _nodes, expectedProposalChecksumSha256: _pin, ...legacy } = body;
  await api.previewImageGridReviewGeometry(itemId, { gameId }, legacy);
  assert.deepEqual(received, legacy);
  assert.equal('latticeNodes' in received, false);
  assert.equal('expectedProposalChecksumSha256' in received, false);
});
