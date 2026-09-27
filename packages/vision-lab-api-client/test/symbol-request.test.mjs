import test from 'node:test';
import assert from 'node:assert/strict';
import {
  writeSymbol,
  symbolCrop,
  symbolLabels,
  symbolDictionary,
  backupSymbols,
  symbolBoard,
} from '../src/index.ts';

test('symbol wrappers preserve discriminator, CAS, retry identity and read tokens', async () => {
  const originalFetch = globalThis.fetch;
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
    calls.push({
      url: request.url,
      method: request.method,
      body: request.method === 'POST' ? await request.json() : null,
    });
    return new Response(JSON.stringify({ revision: 7, kind: 'lab_board' }), {
      headers: { 'Content-Type': 'application/json' },
    });
  };
  try {
    const body = {
      op: 'dictionary_draft',
      request_id: 'exact',
      expected_revision: 6,
      actor: 'operator',
      game_id: 'local-a',
      base_version: null,
      entries: [],
    };
    await writeSymbol(body);
    await writeSymbol(body);
    assert.deepEqual(calls[0].body, body);
    assert.deepEqual(calls[1].body, body);
    await symbolCrop({ kind: 'db_approved', sample_id: 'a'.repeat(64) });
    assert.equal(calls[2].body.kind, 'db_approved');
    assert.equal(Object.hasOwn(calls[2].body, 'binding'), false);
    await symbolLabels('local-a', undefined, 50, 'stable-view');
    const url = new URL(calls[3].url);
    assert.equal(url.searchParams.get('read_token'), 'stable-view');
    assert.equal(url.searchParams.get('offset'), '50');
    await symbolDictionary('local-a', 2);
    assert.equal(
      new URL(calls[4].url).pathname,
      '/api/lab/symbol-dictionaries/local-a/2',
    );
    await backupSymbols();
    assert.deepEqual(calls[5].body, {});
    const board = {
      kind: 'lab_board',
      source_id: 'source',
      board_index: 2,
      expected_geometry_revision: 9,
    };
    await symbolBoard(board);
    assert.deepEqual(calls[6].body, board);
    const batch = {
      op: 'label_board_decide',
      request_id: 'batch',
      expected_revision: 7,
      actor: 'operator',
      dictionary_version: 1,
      dictionary_digest: 'a'.repeat(64),
      cells: Array.from({ length: 15 }, (_, cell_index) => ({
        binding: { cell_index },
        action: 'unknown',
        symbol_id: null,
      })),
    };
    await writeSymbol(batch);
    await writeSymbol(batch);
    assert.deepEqual(calls[7].body, batch);
    assert.deepEqual(calls[8].body, batch);
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.Request = OriginalRequest;
  }
});
