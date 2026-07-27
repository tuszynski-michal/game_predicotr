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

test('generated client sends server-versioned rules draft requests', async () => {
  const requests = [];
  const gameId = '11111111-1111-4111-8111-111111111111';
  const rulesVersionId = '33333333-3333-4333-8333-333333333333';
  const responseBody = {
    columns: 5,
    createdAt: '2026-07-27T10:00:00Z',
    gameId,
    id: rulesVersionId,
    publishedAt: null,
    rows: 3,
    spinCost: 10,
    status: 'draft',
    version: 1,
  };
  const mockFetch = async (request) => {
    requests.push(request);
    return Response.json(responseBody, {
      status: request.method === 'POST' ? 201 : 200,
    });
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: mockFetch,
  });

  const created = await client.createRulesVersion(gameId, {
    columns: 5,
    rows: 3,
    spinCost: 10,
  });
  const updated = await client.updateRulesVersion(rulesVersionId, {
    spinCost: 20,
  });

  assert.equal(created.data?.version, 1);
  assert.equal(updated.data?.id, rulesVersionId);
  assert.equal(
    new URL(requests[0].url).pathname,
    `/api/v1/admin/games/${gameId}/rules-versions`,
  );
  assert.equal(
    new URL(requests[1].url).pathname,
    `/api/v1/admin/rules-versions/${rulesVersionId}`,
  );
  assert.deepEqual(await requests[0].clone().json(), {
    columns: 5,
    rows: 3,
    spinCost: 10,
  });
});

test('generated client sends zero-based payline CRUD requests', async () => {
  const requests = [];
  const rulesVersionId = '33333333-3333-4333-8333-333333333333';
  const paylineId = '44444444-4444-4444-8444-444444444444';
  const responseBody = {
    code: 'line-v',
    displayOrder: 10,
    id: paylineId,
    isActive: true,
    name: 'V',
    rowPath: [0, 1, 2, 1, 0],
    rulesVersionId,
  };
  const mockFetch = async (request) => {
    requests.push(request);
    if (request.method === 'DELETE') {
      return new Response(null, { status: 204 });
    }
    return Response.json(responseBody, {
      status: request.method === 'POST' ? 201 : 200,
    });
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: mockFetch,
  });

  const created = await client.createPayline(rulesVersionId, {
    code: 'line-v',
    displayOrder: 10,
    name: 'V',
    rowPath: [0, 1, 2, 1, 0],
  });
  await client.updatePayline(rulesVersionId, paylineId, {
    displayOrder: 5,
  });
  await client.archivePayline(rulesVersionId, paylineId);

  assert.equal(created.data?.id, paylineId);
  assert.equal(
    new URL(requests[0].url).pathname,
    `/api/v1/admin/rules-versions/${rulesVersionId}/paylines`,
  );
  assert.equal(
    new URL(requests[1].url).pathname,
    `/api/v1/admin/rules-versions/${rulesVersionId}/paylines/${paylineId}`,
  );
  assert.equal(requests[2].method, 'DELETE');
  assert.deepEqual(await requests[0].clone().json(), {
    code: 'line-v',
    displayOrder: 10,
    name: 'V',
    rowPath: [0, 1, 2, 1, 0],
  });
});

test('generated client sends symbol minimum and payout rule requests', async () => {
  const requests = [];
  const rulesVersionId = '33333333-3333-4333-8333-333333333333';
  const symbolId = '22222222-2222-4222-8222-222222222222';
  const payoutRuleId = '55555555-5555-4555-8555-555555555555';
  const mockFetch = async (request) => {
    requests.push(request);
    const url = new URL(request.url);
    if (request.method === 'DELETE') return new Response(null, { status: 204 });
    if (url.pathname.endsWith(`/symbols/${symbolId}`)) {
      return Response.json({
        isActive: true,
        minimumMatchLength: 2,
        rulesVersionId,
        symbolId,
      });
    }
    return Response.json(
      {
        id: payoutRuleId,
        isActive: true,
        matchLength: 2,
        payoutCredits: 10,
        rulesVersionId,
        symbolId,
      },
      { status: request.method === 'POST' ? 201 : 200 },
    );
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: mockFetch,
  });

  await client.updateRulesVersionSymbol(rulesVersionId, symbolId, {
    minimumMatchLength: 2,
  });
  const created = await client.createPayoutRule(rulesVersionId, {
    matchLength: 2,
    payoutCredits: 10,
    symbolId,
  });
  await client.updatePayoutRule(rulesVersionId, payoutRuleId, {
    payoutCredits: 20,
  });
  await client.archivePayoutRule(rulesVersionId, payoutRuleId);

  assert.equal(created.data?.id, payoutRuleId);
  assert.equal(
    new URL(requests[0].url).pathname,
    `/api/v1/admin/rules-versions/${rulesVersionId}/symbols/${symbolId}`,
  );
  assert.equal(
    new URL(requests[1].url).pathname,
    `/api/v1/admin/rules-versions/${rulesVersionId}/payout-rules`,
  );
  assert.deepEqual(await requests[0].clone().json(), {
    minimumMatchLength: 2,
  });
  assert.equal(requests[3].method, 'DELETE');
});

test('generated client sends rules publication workflow requests', async () => {
  const requests = [];
  const rulesVersionId = '33333333-3333-4333-8333-333333333333';
  const rulesVersion = {
    columns: 5,
    createdAt: '2026-07-27T10:00:00Z',
    gameId: '11111111-1111-4111-8111-111111111111',
    id: rulesVersionId,
    publishedAt: '2026-07-27T11:00:00Z',
    rows: 3,
    spinCost: 10,
    status: 'published',
    version: 1,
  };
  const mockFetch = async (request) => {
    requests.push(request);
    const url = new URL(request.url);
    if (request.method === 'DELETE') {
      return new Response(null, { status: 204 });
    }
    if (url.pathname.endsWith('/publication-readiness')) {
      return Response.json({
        issues: [],
        ready: true,
        rulesVersionId,
      });
    }
    return Response.json(rulesVersion);
  };
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: mockFetch,
  });

  const readiness = await client.getRulesPublicationReadiness(rulesVersionId);
  const published = await client.publishRulesVersion(rulesVersionId);
  await client.archiveRulesVersion(rulesVersionId);

  assert.equal(readiness.data?.ready, true);
  assert.equal(published.data?.status, 'published');
  assert.deepEqual(
    requests.map((request) => [request.method, new URL(request.url).pathname]),
    [
      [
        'GET',
        `/api/v1/admin/rules-versions/${rulesVersionId}/publication-readiness`,
      ],
      ['POST', `/api/v1/admin/rules-versions/${rulesVersionId}/publish`],
      ['DELETE', `/api/v1/admin/rules-versions/${rulesVersionId}`],
    ],
  );
});
