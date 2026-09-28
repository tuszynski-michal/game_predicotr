import test from 'node:test';
import assert from 'node:assert/strict';
import {
  writeSymbol,
  symbolCrop,
  symbolLabels,
  symbolDictionary,
  backupSymbols,
  symbolBoard,
  symbolQueue,
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
    return new Response(JSON.stringify({ revision: 7, kind: calls.at(-1).body?.kind === 'lab_queue' ? 'lab_queue' : 'lab_board' }), {
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
    const queue = await symbolQueue('local-a', 30, 'view');
    assert.equal(queue.kind, 'lab_queue');
    assert.deepEqual(calls[9].body, {
      kind: 'lab_queue', game_id: 'local-a', offset: 30, limit: 30,
      read_token: 'view',
    });
    const selective = { op: 'label_cells_decide', request_id: 'selective',
      expected_revision: 7, actor: 'operator', dictionary_version: 1,
      dictionary_digest: 'a'.repeat(64), symbol_id: 'lemon', bindings: [{ crop_id: 'id' }] };
    await writeSymbol(selective);
    assert.deepEqual(calls[10].body, selective);
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.Request = OriginalRequest;
  }
});

test('symbol crop previews are FIFO and a failed board releases the queue', async () => {
  const originalFetch = globalThis.fetch;
  const OriginalRequest = globalThis.Request;
  globalThis.Request = class extends OriginalRequest {
    constructor(input, init) {
      super(typeof input === 'string'
        ? new URL(input, 'http://127.0.0.1:3102') : input, init);
    }
  };
  const calls = [];
  let rejectBoard;
  globalThis.fetch = async (request) => {
    const body = await request.json();
    calls.push(body.kind);
    if (body.kind === 'lab_board')
      return await new Promise((resolve) => { rejectBoard = resolve; });
    return new Response(JSON.stringify({ kind: 'lab_queue', items: [],
      total: 0, revision: 0, read_token: 'token' }),
    { headers: { 'Content-Type': 'application/json' } });
  };
  try {
    const board = symbolBoard({ kind: 'lab_board', source_id: 's', board_index: 0,
      expected_geometry_revision: 1 });
    const queue = symbolQueue('g');
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.deepEqual(calls, ['lab_board']);
    rejectBoard(new Response(JSON.stringify({ detail: 'ANNOTATION_STORE_BUSY' }),
      { status: 409, headers: { 'Content-Type': 'application/json' } }));
    await assert.rejects(board);
    const result = await queue;
    assert.equal(result.kind, 'lab_queue');
    assert.deepEqual(calls, ['lab_board', 'lab_queue']);
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.Request = OriginalRequest;
  }
});

test('a hung preview is aborted on its bound and releases the next preview', async () => {
  const originalFetch = globalThis.fetch;
  const OriginalRequest = globalThis.Request;
  globalThis.Request = class extends OriginalRequest {
    constructor(input, init) {
      super(typeof input === 'string'
        ? new URL(input, 'http://127.0.0.1:3102') : input, init);
    }
  };
  const calls = [];
  let abandonedSignal;
  globalThis.fetch = async (request) => {
    const body = await request.json();
    calls.push(body.kind);
    if (body.kind === 'lab_board') {
      abandonedSignal = request.signal;
      return await new Promise(() => {});
    }
    return new Response(JSON.stringify({ kind: 'lab_queue', items: [],
      total: 0, revision: 0, read_token: 'token' }),
    { headers: { 'Content-Type': 'application/json' } });
  };
  try {
    const hung = symbolCrop({ kind: 'lab_board', source_id: 's', board_index: 0,
      expected_geometry_revision: 1 }, 20);
    const next = symbolQueue('g');
    await assert.rejects(hung, /SYMBOL_PREVIEW_TIMEOUT/);
    assert.equal(abandonedSignal.aborted, true);
    assert.equal((await next).kind, 'lab_queue');
    assert.deepEqual(calls, ['lab_board', 'lab_queue']);
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.Request = OriginalRequest;
  }
});
