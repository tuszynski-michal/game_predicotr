import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('page override wrapper preserves complete slot decisions and the 15/15 mask', async () => {
  const requests = [];
  const qualification = {
    version: 'manual-geometry-qualification-v1',
    completenessStatus: 'pending_partial',
    unavailableCellIndices: Array.from({ length: 15 }, (_, index) => index),
    excludeFromGeometryTraining: true,
    exclusionReason: 'missing_pixels',
  };
  const body = {
    gameId: '11111111-1111-4111-8111-111111111111',
    sourceChecksumSha256: 'a'.repeat(64),
    imageWidth: 320,
    imageHeight: 320,
    finalQuads: [
      [
        { x: 0, y: 0 },
        { x: 20, y: 0 },
        { x: 20, y: 20 },
        { x: 0, y: 20 },
      ],
    ],
    actor: 'local-owner',
    slotQualifications: [qualification],
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requests.push(request);
      return Response.json({
        created: true,
        slotQualifications: [qualification],
      });
    },
  });
  await client.createBrowserPageGeometryOverride(
    '22222222-2222-4222-8222-222222222222',
    body,
  );
  assert.equal(requests.length, 1);
  assert.equal(requests[0].method, 'POST');
  assert.deepEqual(JSON.parse(await requests[0].text()), body);
});
