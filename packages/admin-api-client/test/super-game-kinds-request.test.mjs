import assert from 'node:assert/strict';
import test from 'node:test';

import { createAdminApiClient } from '../src/index.ts';

function recordingClient(responseBody) {
  const requests = [];
  const client = createAdminApiClient({
    baseUrl: 'http://127.0.0.1:8000',
    fetch: async (request) => {
      requests.push(request);
      return new Response(JSON.stringify(responseBody), {
        headers: { 'Content-Type': 'application/json' },
        status: 200,
      });
    },
  });
  return { client, requests };
}

test('TASK-0931: lists the code-defined super game kinds', async () => {
  const kinds = [
    { code: 'none', label: 'Brak' },
    { code: 'wild_super_spins', label: 'Wild super spins' },
  ];
  const { client, requests } = recordingClient(kinds);

  const result = await client.listSuperGameKinds();

  assert.deepEqual(result.data, kinds);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].method, 'GET');
  assert.equal(
    requests[0].url,
    'http://127.0.0.1:8000/api/v1/admin/super-game-kinds',
  );
});

test('TASK-0931: sends the super game kind and the symbol trigger role', async () => {
  const { client, requests } = recordingClient({});

  await client.updateGame('game-1', { superGameKind: 'wild_super_spins' });
  await client.updateSymbol('game-1', 'symbol-1', {
    isWildcard: true,
    superGameTriggerCount: 3,
  });
  await client.updateSymbol('game-1', 'symbol-1', {
    superGameTriggerCount: null,
  });

  assert.deepEqual(
    requests.map((request) => [request.method, new URL(request.url).pathname]),
    [
      ['PATCH', '/api/v1/admin/games/game-1'],
      ['PATCH', '/api/v1/admin/games/game-1/symbols/symbol-1'],
      ['PATCH', '/api/v1/admin/games/game-1/symbols/symbol-1'],
    ],
  );
  assert.deepEqual(await requests[0].json(), {
    superGameKind: 'wild_super_spins',
  });
  assert.deepEqual(await requests[1].json(), {
    isWildcard: true,
    superGameTriggerCount: 3,
  });
  // An explicit null removes the trigger role and must reach the API.
  assert.deepEqual(await requests[2].json(), { superGameTriggerCount: null });
});
