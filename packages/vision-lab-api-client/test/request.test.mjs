import test from 'node:test';
import assert from 'node:assert/strict';
import {
  detectGeometry,
  saveAnnotation,
  saveFamily,
  createBackup,
} from '../src/generated/sdk.gen.ts';
import { boundary } from '../../../apps/vision-lab/src/lib/boundary.ts';
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
test('annotation and family requests preserve revision, explicit intent and idempotency', async () => {
  for (const [call, route, body] of [
    [
      saveAnnotation,
      'annotations',
      {
        request_id: 'reject-photo',
        expected_revision: 8,
        actor: 'operator',
        action: 'reject',
        source_id: 'source',
        source_sha256: 'a'.repeat(64),
        expected_board_revisions: { 0: 2, 4: 1 },
        board_indices: [],
        note: '',
      },
    ],
    [
      saveAnnotation,
      'annotations',
      {
        request_id: 'request-01',
        expected_revision: 7,
        actor: 'human',
        action: 'approve_location',
        annotation: {
          source_id: 'source',
          board_index: 0,
          topology: { columns: 3, rows: 3 },
          corners: [],
        },
      },
    ],
    [
      saveFamily,
      'families',
      {
        request_id: 'request-02',
        expected_revision: 8,
        actor: 'human',
        decision: {
          source_ids: ['a', 'b'],
          family_id: 'recording',
          evidence: 'verified recording',
          provenance: 'verified',
          related_source_ids: ['c'],
        },
      },
    ],
    [
      saveAnnotation,
      'annotations',
      {
        request_id: 'review-request-03',
        expected_revision: 9,
        actor: 'operator',
        action: 'mark',
        source_id: 'source',
        source_sha256: 'a'.repeat(64),
        expected_board_revisions: { 0: 2, 4: 1 },
        board_indices: [4],
        note: 'Left corner',
      },
    ],
  ]) {
    let captured;
    await call({
      baseUrl: 'http://127.0.0.1:3102/api/lab',
      body,
      throwOnError: true,
      fetch: async (request) => {
        captured = request;
        return new Response('{}', {
          headers: { 'content-type': 'application/json' },
        });
      },
    });
    assert.equal(captured.url, `http://127.0.0.1:3102/api/lab/${route}`);
    assert.equal(captured.headers.get('content-type'), 'application/json');
    assert.deepEqual(await captured.json(), body);
  }
});

test('backup sends explicit JSON through the same mutation boundary', async () => {
  let captured;
  await createBackup({
    baseUrl: 'http://127.0.0.1:3102/api/lab',
    body: {},
    throwOnError: true,
    headers: { host: '127.0.0.1:3102', origin: 'http://127.0.0.1:3102' },
    fetch: async (request) => {
      captured = request;
      assert.equal(boundary(request), null);
      return new Response('{"backup_id":"test","revision":1}', {
        headers: { 'content-type': 'application/json' },
      });
    },
  });
  assert.equal(captured.headers.get('content-type'), 'application/json');
  assert.deepEqual(await captured.json(), {});
});

test('manual preview extends the geometry route without annotation writes', async () => {
  const body = {
    source_id: 'source',
    topology: { columns: 3, rows: 3 },
    preview_board: {
      position_index: 2,
      status: 'complete',
      nodes: [{ x: 12, y: 34, provenance: 'human' }],
    },
  };
  await detectGeometry({
    baseUrl: 'http://127.0.0.1:3102/api/lab',
    body,
    throwOnError: true,
    fetch: async (request) => {
      assert.equal(request.url, 'http://127.0.0.1:3102/api/lab/geometry');
      assert.deepEqual(await request.json(), body);
      return new Response('{}', {
        headers: { 'content-type': 'application/json' },
      });
    },
  });
});
