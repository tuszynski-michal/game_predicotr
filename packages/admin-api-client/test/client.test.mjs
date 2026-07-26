import assert from 'node:assert/strict';
import test from 'node:test';

import { createAdminApiClient } from '../src/index.ts';

test('generated client calls the typed health operation', async () => {
  const requests = [];
  const mockFetch = async (request) => {
    requests.push(request);
    return new Response(
      JSON.stringify({
        status: 'ok',
        version: '0.1.0',
      }),
      {
        headers: { 'Content-Type': 'application/json' },
        status: 200,
      },
    );
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: mockFetch,
  });

  const result = await client.getHealth();

  assert.deepEqual(result.data, { status: 'ok', version: '0.1.0' });
  assert.equal(result.error, undefined);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, 'http://127.0.0.1:8000/api/v1/health');
});

test('generated client sends typed game and symbol requests', async () => {
  const requests = [];
  const gameId = '11111111-1111-4111-8111-111111111111';
  const symbolId = '22222222-2222-4222-8222-222222222222';
  const mockFetch = async (request) => {
    requests.push(request);
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname.endsWith('/games')) {
      return Response.json(
        {
          id: gameId,
          code: 'game-1',
          name: 'Game 1',
          status: 'draft',
          createdAt: '2026-07-26T10:00:00Z',
          updatedAt: '2026-07-26T10:00:00Z',
        },
        { status: 201 },
      );
    }
    if (request.method === 'POST' && url.pathname.endsWith('/symbols')) {
      return Response.json(
        {
          id: symbolId,
          gameId,
          mobileCode: 1,
          code: 'S1',
          name: 'Symbol 1',
          imagePath: null,
          isWildcard: false,
          displayOrder: 0,
          status: 'active',
        },
        { status: 201 },
      );
    }
    throw new Error(`Unexpected request: ${request.method} ${url.pathname}`);
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: mockFetch,
  });

  const game = await client.createGame({ code: 'game-1', name: 'Game 1' });
  const symbol = await client.createSymbol(gameId, {
    mobileCode: 1,
    code: 'S1',
    name: 'Symbol 1',
    displayOrder: 0,
  });

  assert.equal(game.data?.id, gameId);
  assert.equal(symbol.data?.id, symbolId);
  assert.equal(requests.length, 2);
  assert.deepEqual(await requests[0].clone().json(), {
    code: 'game-1',
    name: 'Game 1',
  });
  assert.equal(
    new URL(requests[1].url).pathname,
    `/api/v1/admin/games/${gameId}/symbols`,
  );
});
