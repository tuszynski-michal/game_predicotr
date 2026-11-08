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
  corners: [
    { x: 1, y: 2 },
    { x: 102, y: 2 },
    { x: 102, y: 63 },
    { x: 1, y: 63 },
  ],
  actor: 'local-owner',
  expectedGeometryRevision: 2,
  expectedSourceChecksumSha256: 'a'.repeat(64),
  latticeNodes,
  expectedProposalChecksumSha256: 'b'.repeat(64),
};

test('source review request preserves a separate input variant stamp', async () => {
  const inputVariant = {
    version: 'full-board-input-variant-v1',
    variantKey: '1'.repeat(64),
    sourceSha256: '2'.repeat(64),
    modelManifestSha256: '3'.repeat(64),
    operationPinSha256: '4'.repeat(64),
    detectionId: 'det-1',
    nodesSha256: '5'.repeat(64),
    screenQuad: [
      [1, 1],
      [101, 1],
      [101, 61],
      [1, 61],
    ],
    boardInputSupport: [
      [0, 0],
      [120, 0],
      [120, 80],
      [0, 80],
    ],
    availableSourceBox: [0, 0, 500, 300],
    sha256: '6'.repeat(64),
  };
  const document = {
    sources: [
      {
        neuralProposal: {
          detections: [{ detectionId: 'det-1', inputVariant }],
        },
      },
    ],
  };
  const requests = [];
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requests.push([request.method, new URL(request.url)]);
      return Response.json(document);
    },
  });
  assert.deepEqual(
    (await api.listBrowserPageGeometryReviewSources(itemId, itemId, gameId))
      .data,
    document,
  );
  assert.equal(requests[0][0], 'GET');
  assert.equal(requests[0][1].searchParams.get('game_id'), gameId);
  assert.ok(requests[0][1].pathname.includes(itemId));
});

test('existing geometry wrappers transmit exact floating24 nodes and proposal CAS pin', async () => {
  const requests = [];
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requests.push({
        url: new URL(request.url),
        body: await request.clone().json(),
      });
      return Response.json({});
    },
  });
  const context = { gameId, importJobId: itemId };
  await api.previewOperationalImageReviewGeometry(itemId, context, body);
  await api.createOperationalImageReviewGeometryRevision(itemId, context, {
    ...body,
    commandKey: 'same-op',
  });
  await api.previewImageGridReviewGeometry(itemId, context, body);
  await api.createImageGridReviewGeometryRevision(itemId, context, {
    ...body,
    commandKey: 'same-op',
  });
  await api.previewPendingBoardCellGeometryCorrection(itemId, context, body);
  await api.previewPendingBoardCellGeometrySymbols(itemId, context, body);
  await api.resolvePendingBoardCellGeometryManually(itemId, context, {
    ...body,
    commandKey: 'same-op',
  });
  assert.equal(requests.length, 7);
  for (const request of requests) {
    assert.deepEqual(request.body.latticeNodes, latticeNodes);
    assert.equal(
      request.body.expectedProposalChecksumSha256,
      body.expectedProposalChecksumSha256,
    );
    assert.ok(
      request.url.searchParams.get('gameId') === gameId ||
        request.url.pathname.includes(`/games/${gameId}/`),
    );
  }
});

test('neural source binding uses existing override route without invented quads', async () => {
  const requests = [];
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requests.push({
        url: new URL(request.url),
        body: await request.clone().json(),
      });
      return Response.json({});
    },
  });
  const selected = {
    gameId,
    sourceChecksumSha256: 'a'.repeat(64),
    imageWidth: 500,
    imageHeight: 300,
    finalQuads: [],
    actor: 'local-owner',
    expectedOverrideRevision: 0,
    geometryPreflightJobId: itemId,
    geometryManifestChecksumSha256: 'c'.repeat(64),
    neuralProposalBinding: {
      contractVersion: 'neural-source-binding-v1',
      gameId,
      sourceSelectionId: itemId,
      sourceChecksumSha256: 'a'.repeat(64),
      sourceWidth: 500,
      sourceHeight: 300,
      proposalChecksumSha256: 'b'.repeat(64),
      originalRange: { sequenceRangeStart: 101, sequenceRangeEnd: 105 },
      confirmedRange: { sequenceRangeStart: 101, sequenceRangeEnd: 105 },
      assignments: [{ detectionId: 'd', positionIndex: 3 }],
      missingPositionIndexes: [0, 1, 2, 4],
      ignoredDetectionIds: ['a', 'b', 'c'],
    },
  };
  await api.createBrowserPageGeometryOverride(itemId, selected);
  assert.deepEqual(requests[0].body, selected);
  assert.equal(
    requests[0].url.pathname,
    `/api/v1/admin/image-imports/browser-selections/${itemId}/page-geometry-overrides`,
  );
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
  const {
    latticeNodes: _nodes,
    expectedProposalChecksumSha256: _pin,
    ...legacy
  } = body;
  await api.previewImageGridReviewGeometry(itemId, { gameId }, legacy);
  assert.deepEqual(received, legacy);
  assert.equal('latticeNodes' in received, false);
  assert.equal('expectedProposalChecksumSha256' in received, false);
});

test('getJob wrapper preserves the catalogue snapshot and its version pin', async () => {
  const snapshot = {
    contractVersion: 'neural-grid-proposal-snapshot-v2',
    gameId,
    gameConfiguration: 'neural_grid_v3',
    expectedLayoutCount: 500000,
    catalogueManifestSha256: 'a'.repeat(64),
    catalogueManifest: {
      versionId: itemId,
      familyCode: 'third_geometry',
      preprocessingVersion: 'neural-grid-preprocessing-v1',
      decodingPolicyVersion: 'neural-grid-decoding-v1',
    },
  };
  let requested;
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requested = new URL(request.url);
      return Response.json({
        id: itemId,
        inputPayload: { neuralGridProposal: snapshot },
      });
    },
  });
  const response = await api.getJob(itemId);
  assert.equal(requested.pathname, `/api/v1/admin/jobs/${itemId}`);
  assert.deepEqual(response.data.inputPayload.neuralGridProposal, snapshot);
});
