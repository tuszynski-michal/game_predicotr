import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';
test('single wrapper sends GET and has no sequence method', async () => {
  let sent;
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      sent = request;
      return Response.json({ results: [] });
    },
  });
  assert.equal(client.searchGameBoardSequence, undefined);
  await client.searchGameBoards('11111111-1111-4111-8111-111111111111', {
    cells: [{ cellIndex: 0, symbolCode: 'A' }],
    limit: 40,
  });
  assert.equal(sent.method, 'GET');
  const url = new URL(sent.url);
  assert.equal(url.searchParams.get('cell'), '0:A');
  assert.equal(url.searchParams.get('limit'), '40');
});
