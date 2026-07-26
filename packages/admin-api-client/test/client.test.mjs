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
