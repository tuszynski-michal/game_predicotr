import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('corrected-grid preview and start use the existing routes and explicit scope', async () => {
  const requests = [];
  const game = '11111111-1111-4111-8111-111111111111';
  const importId = '22222222-2222-4222-8222-222222222222';
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requests.push(request);
      return Response.json({});
    },
  });
  const scope = { correctedGeometry: true, importJobId: importId };
  await api.previewPendingSymbolReinference(game, scope);
  await api.startPendingSymbolReinference(game, scope);
  for (const request of requests) {
    const url = new URL(request.url);
    assert.equal(url.searchParams.get('corrected_geometry'), 'true');
    assert.equal(url.searchParams.get('import_job_id'), importId);
  }
  assert.equal(requests[1].method, 'POST');
  assert.equal(
    requests[1].headers.get('x-admin-target'),
    `pending-symbol-reinference:${game}`,
  );
  await api.startPendingSymbolReinference(game);
  assert.equal(new URL(requests[2].url).search, '');
});
