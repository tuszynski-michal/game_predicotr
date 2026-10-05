import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('owner correction wrappers use the generated routes, aliases and review body', async () => {
  const requests = [];
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requests.push(request);
      return Response.json({});
    },
  });
  await client.listBoardSearchShareCorrections('session', {
    status: 'pending',
    before: 'cursor',
    limit: 25,
    pattern: ['0:A', '4:B'],
  });
  await client.getBoardSearchShareCorrection('session', 100000, { limit: 50 });
  const body = { expectedRevision: 3, expectedBoardVersion: 'a'.repeat(64) };
  await client.reviewBoardSearchShareCorrection('session', 100000, body);
  const list = new URL(requests[0].url);
  assert.equal(
    list.pathname,
    '/api/v1/admin/board-search-shares/sessions/session/corrections',
  );
  assert.deepEqual(list.searchParams.getAll('pattern'), ['0:A', '4:B']);
  assert.equal(list.searchParams.get('status'), 'pending');
  assert.equal(
    new URL(requests[1].url).pathname,
    '/api/v1/admin/board-search-shares/sessions/session/corrections/100000',
  );
  assert.equal(requests[2].method, 'POST');
  assert.deepEqual(await requests[2].json(), body);
  assert.equal(
    new URL(requests[2].url).pathname,
    '/api/v1/admin/board-search-shares/sessions/session/corrections/100000/review',
  );
});
