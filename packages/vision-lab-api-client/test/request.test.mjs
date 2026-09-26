import test from 'node:test';
import assert from 'node:assert/strict';
import { detectGeometry } from '../src/generated/sdk.gen.ts';
test('generated request uses JSON and declared source/topology, never a path', async () => {
  let captured;
  const fetch = async (request) => {
    captured = request;
    return new Response(
      JSON.stringify({
        source_id: 'source',
        topology: { columns: 3, rows: 3 },
        model_version: 'test',
        status: 'unsupported',
        boards: [],
        reasons: [],
        width: 0,
        height: 0,
      }),
      { headers: { 'content-type': 'application/json' } },
    );
  };
  const response = await detectGeometry({
    baseUrl: 'http://127.0.0.1:3102/api/lab',
    body: { source_id: 'source', topology: { columns: 3, rows: 3 } },
    fetch,
    throwOnError: true,
  });
  assert.equal(captured.url, 'http://127.0.0.1:3102/api/lab/geometry');
  assert.equal(captured.headers.get('content-type'), 'application/json');
  assert.deepEqual(await captured.json(), {
    source_id: 'source',
    topology: { columns: 3, rows: 3 },
  });
  assert.equal(response.data.status, 'unsupported');
});
