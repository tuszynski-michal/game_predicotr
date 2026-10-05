import assert from 'node:assert/strict';
import test from 'node:test';
import { createBoardSearchShareDataSource } from '../src/features/board-search-share/board-search-share-data-source.ts';
import {
  proxyBoardSearchShareRequest,
  boardSearchShareRoute,
} from '../src/security/board-search-share-proxy.ts';

function storage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
    values,
  };
}
const request = {
  action: 'reassign',
  targetSymbolCode: 'B',
  expectedCellVersion: 'a'.repeat(64),
  startSequenceNumber: 10,
  spinCount: 100000,
  stakeGrosze: 500,
};
const receipt = {
  saved: true,
  changed: true,
  sequenceNumber: 20,
  cellIndex: 3,
  cellVersion: 'b'.repeat(64),
};
const json = (body, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

test('a lost response survives a new adapter and retries the exact saved operation', async () => {
  const durable = storage();
  const writes = [];
  const source = createBoardSearchShareDataSource({
    sessionId: 'A',
    storage: durable,
    fetchImplementation: async (_url, init) => {
      writes.push(JSON.parse(init.body));
      throw new Error('Response lost after commit');
    },
  });
  await assert.rejects(source.correctBoardSearchCell('shared', 20, 3, request));
  assert.equal(source.hasPendingBoardSearchCell('shared', 20), true);
  assert.equal(durable.values.size, 1);
  const restored = createBoardSearchShareDataSource({
    sessionId: 'A',
    storage: durable,
    fetchImplementation: async (_url, init) => {
      writes.push(JSON.parse(init.body));
      return json(receipt);
    },
  });
  assert.deepEqual(
    (await restored.retryBoardSearchCell('shared', 20)).data,
    receipt,
  );
  assert.deepEqual(writes[0], writes[1]);
  assert.match(writes[0].operationId, /^[0-9a-f-]{36}$/);
  assert.equal(durable.values.size, 0);
  assert.equal(
    createBoardSearchShareDataSource({
      sessionId: 'B',
      storage: durable,
    }).hasPendingBoardSearchCell('shared', 20),
    false,
  );
});

test('cached searches retain their own context and correction invalidates both caches', async () => {
  const calls = [];
  const writes = [];
  const source = createBoardSearchShareDataSource({
    sessionId: 'A',
    storage: storage(),
    fetchImplementation: async (url, init) => {
      calls.push(url);
      if (init.method === 'POST') {
        writes.push(JSON.parse(init.body));
        return json(receipt);
      }
      if (url.includes('/search?'))
        return json({
          searchContextId: url.includes('0%3AA') ? 'context-A' : 'context-B',
          results: [],
          scope: 'all_searchable',
          queryCellCount: 1,
        });
      return json({ sequenceNumber: 20, matches: [] });
    },
  });
  const A = { cells: [{ cellIndex: 0, symbolCode: 'A' }] };
  await source.searchGameBoards('shared', A);
  await source.searchGameBoards('shared', {
    cells: [{ cellIndex: 0, symbolCode: 'B' }],
  });
  await source.searchGameBoards('shared', A);
  await source.getBoardSearchBoardDetail('shared', 20);
  await source.correctBoardSearchCell('shared', 20, 3, request);
  assert.equal(writes[0].searchContextId, 'context-A');
  const before = calls.length;
  await source.searchGameBoards('shared', A);
  await source.getBoardSearchBoardDetail('shared', 20);
  assert.equal(calls.length, before + 2);
});

test('an unresolved operation blocks other choices, duplicate submits and cross-session recovery', async () => {
  const durable = storage();
  let finish;
  let writes = 0;
  const source = createBoardSearchShareDataSource({
    sessionId: 'A',
    storage: durable,
    fetchImplementation: async () => {
      writes += 1;
      return new Promise((resolve) => {
        finish = resolve;
      });
    },
  });
  const first = source.correctBoardSearchCell('shared', 20, 3, request);
  assert.ok(
    (await source.correctBoardSearchCell('shared', 20, 3, request)).error,
  );
  assert.ok(
    (await source.correctBoardSearchCell('shared', 21, 4, request)).error,
  );
  assert.equal(writes, 1);
  assert.equal(
    createBoardSearchShareDataSource({
      sessionId: 'B',
      storage: durable,
    }).hasPendingBoardSearchCell('shared', 20),
    false,
  );
  finish(json({ code: 'BOARD_SEARCH_SHARE_CORRECTION_UNAVAILABLE' }, 503));
  await first;
  assert.equal(source.hasPendingBoardSearchCell('shared', 20), true);
});

test('invalid success receipts retain recovery; conflicts release it and refresh data', async () => {
  const durable = storage();
  let reply = json({ saved: true });
  const source = createBoardSearchShareDataSource({
    sessionId: 'A',
    storage: durable,
    fetchImplementation: async () => reply,
  });
  await assert.rejects(source.correctBoardSearchCell('shared', 20, 3, request));
  assert.equal(durable.values.size, 1);
  reply = json({ code: 'BOARD_SEARCH_SHARE_CORRECTION_CONFLICT' }, 409);
  assert.equal(
    (await source.retryBoardSearchCell('shared', 20)).error.code,
    'BOARD_SEARCH_SHARE_CORRECTION_CONFLICT',
  );
  assert.equal(durable.values.size, 0);
});

test('the mutation proxy enforces exact route, origin, cookie, JSON and size', async () => {
  const path = '/api/v1/board-search-shares/boards/20/cells/3/decision';
  assert.equal(boardSearchShareRoute('POST', path).kind, 'mutation');
  for (const invalid of [
    path.replace('/3/', '/15/'),
    path.replace('/20/', '/0/'),
    path + '/extra',
  ])
    assert.equal(boardSearchShareRoute('POST', invalid), null);
  const origin = 'https://share.example';
  const token = 'x'.repeat(40);
  const headers = {
    Host: 'share.example',
    Origin: origin,
    'Sec-Fetch-Site': 'same-origin',
    'Content-Type': 'application/json',
    Cookie: `gp_board_search_token=${token}`,
  };
  let calls = 0;
  const proxy = (overrides = {}, body = JSON.stringify(request), suffix = '') =>
    proxyBoardSearchShareRequest(
      new Request(`${origin}/board-search-api${path}${suffix}`, {
        method: 'POST',
        headers: { ...headers, ...overrides },
        body,
      }),
      {
        shareEnabled: true,
        fetchImplementation: async (_url, init) => {
          calls += 1;
          assert.equal(
            new Headers(init.headers).get('Cookie'),
            `gp_board_search_token=${token}`,
          );
          assert.equal(
            new Headers(init.headers).get('Content-Type'),
            'application/json',
          );
          assert.deepEqual(
            JSON.parse(Buffer.from(init.body).toString()),
            request,
          );
          return json(receipt);
        },
      },
    );
  assert.equal((await proxy()).status, 200);
  assert.equal(
    (await proxy({ Origin: 'https://attacker.example' })).status,
    403,
  );
  assert.equal((await proxy({ 'Sec-Fetch-Site': 'cross-site' })).status, 403);
  assert.equal((await proxy({ Cookie: '' })).status, 401);
  assert.equal((await proxy({ 'Content-Type': 'text/plain' })).status, 415);
  assert.equal((await proxy({}, 'x'.repeat(4097))).status, 413);
  assert.equal(
    (await proxy({}, JSON.stringify(request), '?gameId=other')).status,
    403,
  );
  assert.equal(calls, 1);
});
