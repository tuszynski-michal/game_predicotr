import assert from 'node:assert/strict';
import test from 'node:test';

import { createAdminApiClient } from '../src/index.ts';

test('coverage diagnostics use existing GET with explicit game scope and opt-in', async () => {
  const requests = [];
  const api = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requests.push({ method: request.method, url: new URL(request.url) });
      return Response.json({ diagnostics: { scope: 'whole_game' } });
    },
  });
  const gameId = '11111111-1111-4111-8111-111111111111';
  const result = await api.getBoardImportCoverage({
    gameId,
    includeDiagnostics: true,
    from: 5,
    to: 10,
  });
  assert.equal(result.data.diagnostics.scope, 'whole_game');
  assert.equal(requests[0].method, 'GET');
  assert.equal(
    requests[0].url.pathname,
    `/api/v1/admin/image-review-items/board-import-coverage/${gameId}`,
  );
  assert.equal(requests[0].url.searchParams.get('includeDiagnostics'), 'true');
  assert.equal(requests[0].url.searchParams.get('from'), '5');
  await api.getBoardImportCoverage({ gameId });
  assert.equal(requests[1].url.searchParams.has('includeDiagnostics'), false);
});
