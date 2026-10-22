import assert from 'node:assert/strict';
import test from 'node:test';
import { createAdminApiClient } from '../src/index.ts';

test('board search wrapper keeps the server wildcard policy and sends the existing query', async () => {
  const id = '11111111-1111-4111-8111-111111111111';
  const score = {
    score: 100,
    exactMatchCount: 1,
    alternativeMatchCount: 0,
    weightedAlternativeScore: 0,
    mismatchCount: 0,
    unknownCount: 1,
    unknownMatchesAll: true,
  };
  let sent;
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      sent = new URL(request.url);
      return Response.json({
        gameId: id,
        scope: 'all_searchable',
        queryCellCount: 2,
        results: [{ sequenceNumber: 7, score }],
      });
    },
  });
  const response = await client.searchGameBoards(id, {
    cells: [
      { cellIndex: 0, symbolCode: 'seven' },
      { cellIndex: 1, symbolCode: 'bell' },
    ],
    scope: 'all_searchable',
    limit: 15,
  });
  assert.equal(sent.pathname, `/api/v1/admin/games/${id}/board-search`);
  assert.deepEqual(sent.searchParams.getAll('cell'), ['0:seven', '1:bell']);
  assert.equal(sent.searchParams.get('limit'), '15');
  assert.deepEqual(response.data.results[0].score, score);
});
