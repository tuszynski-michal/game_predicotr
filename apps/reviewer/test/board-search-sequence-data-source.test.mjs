import assert from 'node:assert/strict';
import test from 'node:test';
import {
  createBoardSearchShareDataSource,
  SEARCH_CACHE_TTL_MS,
} from '../src/features/board-search-share/board-search-share-data-source.ts';
const pattern = (code) => ({ cells: [{ cellIndex: 0, symbolCode: code }] });
const request = {
  patterns: [pattern('A'), pattern('B')],
  scope: 'all_searchable',
  limit: 15,
};
const payload = (context = 'context', extra = {}) => ({
  patternCount: 2,
  queryCellCount: 2,
  scope: 'all_searchable',
  superGameState: { fresh: true },
  searchContextId: context,
  results: [
    {
      startSequenceNumber: 6,
      endSequenceNumber: 1,
      score: { score: 90 },
      boards: [6, 1].map((sequenceNumber) => ({
        sequenceNumber,
        status: 'pending',
        boardChecksumSha256: 'a'.repeat(64),
        score: { score: 100 },
      })),
    },
  ],
  ...extra,
});
const json = (body, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
const storage = () => {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
};
test('sequence POST uses each host base, includes ordered patterns and caches only the exact key and receipt', async () => {
  for (const apiBase of [
    '/board-search-api/api/v1/board-search-shares',
    '/board-search-panels/p/s/g/api/v1/board-search-shares',
  ]) {
    const calls = [];
    let now = 1000;
    const api = createBoardSearchShareDataSource({
      apiBase,
      now: () => now,
      fetchImplementation: async (url, options) => {
        calls.push([url, options]);
        return json(payload(`context-${calls.length}`));
      },
    });
    const first = await api.searchGameBoardSequence('shared', request);
    assert.equal(first.data.results[0].boards[0].reviewItemId, null);
    assert.equal(first.searchContextId, 'context-1');
    assert.equal(calls[0][0], `${apiBase}/search`);
    assert.equal(calls[0][1].method, 'POST');
    assert.deepEqual(JSON.parse(calls[0][1].body), request);
    const cached = await api.searchGameBoardSequence('shared', request);
    assert.equal(cached.searchContextId, 'context-1');
    assert.equal(calls.length, 1);
    await api.searchGameBoardSequence('shared', {
      ...request,
      patterns: [pattern('B'), pattern('A')],
    });
    await api.searchGameBoardSequence('shared', {
      ...request,
      patterns: [pattern('A'), pattern('C')],
    });
    await api.searchGameBoardSequence('shared', {
      ...request,
      scope: 'approved_only',
    });
    await api.searchGameBoardSequence('shared', { ...request, limit: 7 });
    assert.equal(calls.length, 5);
    now += SEARCH_CACHE_TTL_MS + 1;
    await api.searchGameBoardSequence('shared', request);
    assert.equal(calls.length, 6);
  }
});
test('markers, stale generation and unauthorized access are never cached', async () => {
  for (const body of [
    payload('x', { superGameState: { fresh: false } }),
    payload('x', {
      results: [
        {
          ...payload().results[0],
          boards: [
            {
              ...payload().results[0].boards[0],
              superGame: { kind: 'trigger' },
            },
          ],
        },
      ],
    }),
  ]) {
    let count = 0;
    const api = createBoardSearchShareDataSource({
      fetchImplementation: async () => {
        count++;
        return json(body);
      },
    });
    await api.searchGameBoardSequence('shared', request);
    await api.searchGameBoardSequence('shared', request);
    assert.equal(count, 2);
  }
  let count = 0,
    unauthorized = 0;
  const api = createBoardSearchShareDataSource({
    onUnauthorized: () => unauthorized++,
    fetchImplementation: async () => {
      count++;
      return count === 2
        ? json({ code: 'UNAUTHORIZED' }, 401)
        : json(payload());
    },
  });
  await api.searchGameBoardSequence('shared', request);
  await api.searchGameBoardSequence('shared', { ...request, limit: 7 });
  assert.equal(unauthorized, 1);
  await api.searchGameBoardSequence('shared', request);
  assert.equal(count, 3);
});
test('late response cannot change an explicitly bound correction context or refill a cleared cache', async () => {
  const pending = [];
  const bodies = [];
  let readCount = 0;
  const api = createBoardSearchShareDataSource({
    sessionId: 's',
    storage: storage(),
    fetchImplementation: async (url, options) => {
      if (String(url).endsWith('/search')) {
        readCount++;
        return new Promise((resolve) => pending.push(resolve));
      }
      bodies.push(JSON.parse(options.body));
      return json({
        saved: true,
        changed: true,
        sequenceNumber: 6,
        cellIndex: 0,
        cellVersion: 'b'.repeat(64),
      });
    },
  });
  const old = api.searchGameBoardSequence('shared', request);
  const recent = api.searchGameBoardSequence('shared', {
    ...request,
    limit: 7,
  });
  pending[1](json(payload('recent')));
  const active = await recent;
  await api.correctBoardSearchCell('shared', 6, 0, {
    searchContextId: active.searchContextId,
    startSequenceNumber: 6,
    expectedCellVersion: 'a'.repeat(64),
    action: 'unreadable',
  });
  pending[0](json(payload('old')));
  await old;
  await api.correctBoardSearchCell('shared', 6, 0, {
    searchContextId: active.searchContextId,
    startSequenceNumber: 6,
    expectedCellVersion: 'b'.repeat(64),
    action: 'unreadable',
  });
  assert.equal(bodies[0].searchContextId, 'recent');
  assert.equal(bodies[1].searchContextId, 'recent');
  assert.equal(bodies[0].spinCount, undefined);
  const read = api.searchGameBoardSequence('shared', request);
  assert.equal(readCount, 3);
  pending[2](json(payload('fresh')));
  await read;
});
