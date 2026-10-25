import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('sequence wrapper sends the generated POST body and preserves its response', async () => {
  let sent;
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      sent = request;
      return Response.json({
        patternCount: 2,
        queryCellCount: 2,
        scope: 'all_searchable',
        gameId: '11111111-1111-4111-8111-111111111111',
        superGameState: null,
        results: [],
      });
    },
  });
  const body = {
    patterns: [
      { cells: [{ cellIndex: 0, symbolCode: 'A' }] },
      { cells: [{ cellIndex: 2, symbolCode: 'B' }] },
    ],
    limit: 15,
  };
  const response = await client.searchGameBoardSequence(
    '11111111-1111-4111-8111-111111111111',
    body,
  );
  assert.equal(sent.method, 'POST');
  assert.match(
    sent.url,
    /\/games\/11111111-1111-4111-8111-111111111111\/board-search$/,
  );
  assert.deepEqual(await sent.json(), body);
  assert.equal(response.data.patternCount, 2);
});
