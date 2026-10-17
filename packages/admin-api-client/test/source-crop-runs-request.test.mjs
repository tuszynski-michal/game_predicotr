import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('source crop run wrappers use storage routes, exact bodies and the start target', async () => {
  const calls = [];
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      calls.push({
        url: request.url,
        method: request.method,
        body: request.method === 'POST' ? await request.text() : '',
        confirmation: request.headers.get('X-Admin-Confirmation'),
        target: request.headers.get('X-Admin-Target'),
      });
      return new Response(JSON.stringify({ runs: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    },
  });
  const preview = '11111111-1111-4111-8111-111111111111';
  const previewBody = {
    kind: 'crop',
    scope: { gameId: null, onlyChecksums: ['a'.repeat(64)], limit: 40 },
  };
  const startBody = {
    manifestChecksumSha256: 'b'.repeat(64),
    previewToken: 'c'.repeat(64),
    confirmed: true,
    acknowledgeIrreversible: false,
  };
  await client.createSourceCropPreview(previewBody);
  await client.startSourceCropRun(preview, startBody);
  await client.getSourceCropRun(preview);
  await client.listSourceCropRuns(5);
  const root = 'http://127.0.0.1:8000/api/v1/admin/image-storage';
  assert.deepEqual(
    calls.map(({ url, method }) => [method, url]),
    [
      ['POST', `${root}/source-crop-previews`],
      ['POST', `${root}/source-crop-previews/${preview}/start`],
      ['GET', `${root}/source-crop-runs/${preview}`],
      ['GET', `${root}/source-crop-runs?limit=5`],
    ],
  );
  assert.deepEqual(JSON.parse(calls[0].body), previewBody);
  assert.deepEqual(JSON.parse(calls[1].body), startBody);
  assert.equal(calls[0].target, null);
  assert.equal(calls[1].confirmation, 'confirmed');
  assert.equal(calls[1].target, `source-crop-preview:${preview}`);
});
