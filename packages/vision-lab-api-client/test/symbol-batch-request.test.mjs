import test from 'node:test';
import assert from 'node:assert/strict';
import { symbolBatchQueue, writeSymbol } from '../src/index.ts';

test('batch corrections use existing symbol routes and preserve exact retry payload', async () => {
  const oldFetch = globalThis.fetch;
  const OriginalRequest = globalThis.Request;
  globalThis.Request = class extends OriginalRequest {
    constructor(input, init) {
      super(
        typeof input === 'string'
          ? new URL(input, 'http://127.0.0.1:3102')
          : input,
        init,
      );
    }
  };
  const calls = [];
  globalThis.fetch = async (request) => {
    const body = await request.json();
    calls.push({ path: new URL(request.url).pathname, body });
    return new Response(
      JSON.stringify(
        body.kind
          ? { kind: 'batch_queue', items: [], revision: 0 }
          : { request_id: body.request_id, revision: 1 },
      ),
      {
        headers: { 'Content-Type': 'application/json' },
      },
    );
  };
  try {
    await symbolBatchQueue();
    const body = {
      op: 'batch_label_decide',
      request_id: 'exact',
      expected_revision: 0,
      reference_id: 'a'.repeat(64),
      case_id: 'b'.repeat(64),
      action: 'approve',
      symbol_id: 'mumia',
      actor: 'operator',
    };
    await writeSymbol(body);
    await writeSymbol(body);
    assert.deepEqual(calls[0], {
      path: '/api/lab/symbol-crops',
      body: { kind: 'batch_queue' },
    });
    assert.equal(calls[1].path, '/api/lab/symbols');
    assert.deepEqual(calls[1].body, body);
    assert.deepEqual(calls[2].body, body);
  } finally {
    globalThis.fetch = oldFetch;
    globalThis.Request = OriginalRequest;
  }
});
