import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('managed preflight sends source identity without another upload', async () => {
  const requests = [];
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requests.push(request);
      return Response.json({ job: {} }, { status: 201 });
    },
  });
  const body = {
    gameId: '11111111-1111-4111-8111-111111111111',
    geometryEngineVariant: 'structured_lattice_v4_partial_sides',
    managedSourceJobId: '33333333-3333-4333-8333-333333333333',
  };
  await client.startBrowserPageGeometryPreflight(
    '22222222-2222-4222-8222-222222222222',
    body,
  );
  assert.equal(requests.length, 1);
  assert.match(requests[0].url, /\/geometry-preflight$/);
  assert.deepEqual(JSON.parse(await requests[0].text()), body);
});

test('managed rerun sends explicit variant and pinned replacement preflight', async () => {
  const requests = [];
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requests.push(request);
      return Response.json({ job: {} }, { status: 201 });
    },
  });
  const source = '22222222-2222-4222-8222-222222222222';
  const preflight = '33333333-3333-4333-8333-333333333333';
  await client.reprocessManagedImageImport(source, false, {
    geometryEngineVariant: 'structured_lattice_v4_partial_sides',
    geometryPreflightJobId: preflight,
    geometryManifestChecksumSha256: 'a'.repeat(64),
  });
  assert.equal(requests.length, 1);
  const query = new URL(requests[0].url).searchParams;
  assert.equal(
    query.get('geometryEngineVariant'),
    'structured_lattice_v4_partial_sides',
  );
  assert.equal(query.get('geometryPreflightJobId'), preflight);
  assert.equal(query.get('geometryManifestChecksumSha256'), 'a'.repeat(64));
  assert.equal(query.has('continueWithManualGeometry'), false);
  assert.equal(
    requests[0].headers.get('X-Admin-Target'),
    `image-import:${source}:reprocess`,
  );
});

test('import wrapper sends per-run variant without changing game policy', async () => {
  const requests = [];
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requests.push(request);
      return Response.json(
        { code: 'IMAGE_GEOMETRY_ENGINE_VARIANT_NOT_ENABLED' },
        { status: 409 },
      );
    },
  });
  const body = {
    gameId: '11111111-1111-4111-8111-111111111111',
    manifestChecksumSha256: 'a'.repeat(64),
    preflightChecksumSha256: 'b'.repeat(64),
    imageEnginePolicy: 'structured_lattice_v3',
    geometryEngineVariant: 'structured_lattice_v4_partial_sides',
  };
  await client.startReadyBrowserImageImport(
    '22222222-2222-4222-8222-222222222222',
    body,
  );
  assert.equal(requests.length, 1);
  assert.equal(requests[0].method, 'POST');
  assert.match(
    requests[0].url,
    /browser-selections\/22222222-2222-4222-8222-222222222222\/start$/,
  );
  assert.deepEqual(JSON.parse(await requests[0].text()), body);
});

test('engine policy wrapper sends a virtual target and surfaces the legacy refusal', async () => {
  const requests = [];
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requests.push(request);
      return Response.json(
        {
          code: 'IMAGE_ENGINE_POLICY_LEGACY_UNSUPPORTED',
          message: 'Request data is invalid.',
          details: {},
        },
        { status: 422 },
      );
    },
  });
  const gameId = '11111111-1111-4111-8111-111111111111';
  const preview = await client.previewImageImportEnginePolicy(gameId, {
    targetPolicy: 'structured_lattice_v3',
  });
  const update = await client.updateImageImportEnginePolicy(gameId, {
    targetPolicy: 'structured_default',
    expectedRevision: 1,
    previewToken: 'c'.repeat(64),
  });
  assert.equal(requests.length, 2);
  assert.equal(requests[0].method, 'POST');
  assert.match(requests[0].url, /\/image-import-engine-policy\/preview$/);
  assert.deepEqual(JSON.parse(await requests[0].text()), {
    targetPolicy: 'structured_lattice_v3',
  });
  assert.equal(requests[1].method, 'PUT');
  assert.equal(
    JSON.parse(await requests[1].text()).targetPolicy,
    'structured_default',
  );
  assert.equal(preview.error?.code, 'IMAGE_ENGINE_POLICY_LEGACY_UNSUPPORTED');
  assert.equal(update.response.status, 422);
});
