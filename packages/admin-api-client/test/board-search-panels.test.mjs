import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';
const id = '11111111-1111-4111-8111-111111111111';

test('panel wrappers use the generated contract and explicit create/revoke targets', async () => {
  const calls = [];
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      calls.push({
        path: new URL(request.url).pathname,
        method: request.method,
        body:
          request.method === 'POST'
            ? await request
                .clone()
                .json()
                .catch(() => null)
            : null,
        target: request.headers.get('x-admin-target'),
      });
      return Response.json({});
    },
  });
  const body = { gameIds: [id], lifetimeMinutes: 4320, label: 'Odbiorca' };
  await client.createBoardSearchPanel(body);
  await client.listBoardSearchPanels();
  await client.revokeBoardSearchPanel(id);
  assert.deepEqual(
    calls.map((call) => [call.method, call.path, call.target]),
    [
      ['POST', '/api/v1/admin/board-search-panels', 'board-search-panel:new'],
      ['GET', '/api/v1/admin/board-search-panels', null],
      [
        'POST',
        `/api/v1/admin/board-search-panels/${id}/revoke`,
        `board-search-panel:${id}`,
      ],
    ],
  );
  assert.deepEqual(calls[0].body, body);
});
