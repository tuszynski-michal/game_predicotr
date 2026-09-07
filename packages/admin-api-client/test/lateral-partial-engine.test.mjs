import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

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
