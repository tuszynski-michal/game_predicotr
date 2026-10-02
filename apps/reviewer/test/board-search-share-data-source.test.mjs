import assert from 'node:assert/strict';
import test from 'node:test';

import {
  BOARD_SEARCH_SHARE_API_BASE,
  SEARCH_CACHE_MAX_ENTRIES,
  SEARCH_CACHE_TTL_MS,
  createBoardSearchShareDataSource,
} from '../src/features/board-search-share/board-search-share-data-source.ts';
import {
  formatShareTimeLeft,
  shareErrorMessage,
} from '../src/features/board-search-share/board-search-share-state.ts';

const symbolId = '11111111-1111-4111-8111-111111111111';

function source(routes, options = {}) {
  const calls = [];
  let unauthorized = 0;
  const clock = { now: 1_000_000 };
  const dataSource = createBoardSearchShareDataSource({
    fetchImplementation: async (url) => {
      const path = String(url).slice(BOARD_SEARCH_SHARE_API_BASE.length);
      calls.push(path);
      const route = routes(path);
      return new Response(JSON.stringify(route.body), {
        headers: { 'Content-Type': 'application/json' },
        status: route.status ?? 200,
      });
    },
    now: () => clock.now,
    onUnauthorized: () => {
      unauthorized += 1;
    },
    ...options,
  });
  return { calls, clock, dataSource, unauthorized: () => unauthorized };
}

const searchBody = {
  queryCellCount: 1,
  results: [
    {
      boardChecksumSha256: 'a'.repeat(64),
      score: { score: 100 },
      sequenceNumber: 7,
      status: 'pending',
    },
  ],
  scope: 'all_searchable',
};

test('search results are mapped to the Admin shape and cached for five minutes', async () => {
  const { calls, clock, dataSource } = source(() => ({ body: searchBody }));
  const options = { cells: [{ cellIndex: 0, symbolCode: 'A' }], limit: 5 };
  const first = await dataSource.searchGameBoards('shared', options);
  assert.deepEqual(first.data.results[0], {
    assetMode: 'operational_review',
    boardChecksumSha256: 'a'.repeat(64),
    importJobId: null,
    recognizedBoardId: null,
    reviewItemId: null,
    score: { score: 100 },
    sequenceNumber: 7,
    status: 'pending',
  });
  await dataSource.searchGameBoards('shared', options);
  assert.equal(calls.length, 1, 'a repeated pattern is served from the cache');
  clock.now += SEARCH_CACHE_TTL_MS + 1;
  await dataSource.searchGameBoards('shared', options);
  assert.equal(calls.length, 2, 'an expired entry is fetched again');
  assert.equal(calls[0], '/search?cell=0%3AA&limit=5');
});

test('the search cache keeps at most 50 patterns', async () => {
  const { calls, dataSource } = source(() => ({ body: searchBody }));
  for (let index = 0; index <= SEARCH_CACHE_MAX_ENTRIES; index += 1) {
    await dataSource.searchGameBoards('shared', {
      cells: [{ cellIndex: 0, symbolCode: `S${index}` }],
    });
  }
  const before = calls.length;
  await dataSource.searchGameBoards('shared', {
    cells: [{ cellIndex: 0, symbolCode: 'S0' }],
  });
  assert.equal(calls.length, before + 1, 'the oldest pattern was evicted');
  await dataSource.searchGameBoards('shared', {
    cells: [{ cellIndex: 0, symbolCode: `S${SEARCH_CACHE_MAX_ENTRIES}` }],
  });
  assert.equal(calls.length, before + 1, 'a recent pattern is still cached');
});

test('board details are cached until the range data changes', async () => {
  let fingerprint = 'f1';
  const { calls, dataSource } = source((path) =>
    path.startsWith('/approximate-win')
      ? { body: { dataFingerprintSha256: fingerprint, rows: [] } }
      : { body: { matches: [], sequenceNumber: 9 } },
  );
  await dataSource.getBoardSearchApproximateWin('shared', {
    spinCount: 10,
    startSequenceNumber: 1,
  });
  await dataSource.getBoardSearchBoardDetail('shared', 9);
  await dataSource.getBoardSearchBoardDetail('shared', 9);
  assert.equal(calls.filter((path) => path === '/boards/9').length, 1);
  await dataSource.getBoardSearchApproximateWin('shared', {
    spinCount: 10,
    startSequenceNumber: 1,
  });
  await dataSource.getBoardSearchBoardDetail('shared', 9);
  assert.equal(
    calls.filter((path) => path === '/boards/9').length,
    1,
    'same data',
  );
  fingerprint = 'f2';
  await dataSource.getBoardSearchApproximateWin('shared', {
    spinCount: 10,
    startSequenceNumber: 1,
  });
  await dataSource.getBoardSearchBoardDetail('shared', 9);
  assert.equal(
    calls.filter((path) => path === '/boards/9').length,
    2,
    'new data',
  );
  assert.equal(
    calls.filter((path) => path.startsWith('/approximate-win')).length,
    3,
    'every range calculation is a request',
  );
});

test('symbols are read once, map without paths and give revision-bound image URLs', async () => {
  const { calls, dataSource } = source(() => ({
    body: [
      {
        code: 'A',
        displayOrder: 0,
        id: symbolId,
        imageRevision: 'b'.repeat(64),
        isWildcard: false,
        mobileCode: 1,
        name: 'Wiśnia',
        nameEn: null,
        namePl: null,
        status: 'active',
      },
    ],
  }));
  const [first, second] = await Promise.all([
    dataSource.listSymbols('shared'),
    dataSource.listSymbols('shared'),
  ]);
  assert.equal(calls.length, 1);
  assert.deepEqual(first, second);
  assert.equal(first.data[0].imagePath, 'shared');
  assert.equal(
    dataSource.symbolImageAssetUrl('shared', symbolId),
    `${BOARD_SEARCH_SHARE_API_BASE}/symbols/${symbolId}/image?revision=${'b'.repeat(64)}`,
  );
  assert.equal(
    dataSource.boardSearchBoardViewUrl(
      'shared',
      4,
      'c'.repeat(64),
      'd'.repeat(64),
    ),
    `${BOARD_SEARCH_SHARE_API_BASE}/boards/4/view?expectedBoardChecksumSha256=${'c'.repeat(64)}&viewRevision=${'d'.repeat(64)}`,
  );
});

test('the adapter is read-only and reports an ended access', async () => {
  const { dataSource, unauthorized } = source(() => ({
    body: { code: 'BOARD_SEARCH_SHARE_TOKEN_INVALID', message: 'x' },
    status: 401,
  }));
  assert.equal(dataSource.applySymbolCellReviewDecision, undefined);
  assert.equal(dataSource.refreshBoardSearchBoardDocument, undefined);
  assert.equal(dataSource.operationalImageReviewBoardAssetUrl, undefined);
  const result = await dataSource.getBoardSearchBoardDetail('shared', 3);
  assert.equal(result.data, undefined);
  assert.equal(result.error.code, 'BOARD_SEARCH_SHARE_TOKEN_INVALID');
  assert.equal(unauthorized(), 1);
});

test('gate helpers format the remaining time and map error codes', () => {
  const now = Date.parse('2026-09-30T10:00:00Z');
  assert.equal(formatShareTimeLeft('2026-09-30T18:00:00Z', now), '8 h');
  assert.equal(formatShareTimeLeft('2026-09-30T10:45:10Z', now), '46 min');
  assert.equal(formatShareTimeLeft('2026-09-30T11:30:00Z', now), '1 h 30 min');
  assert.equal(formatShareTimeLeft('2026-09-30T09:00:00Z', now), '0 min');
  assert.equal(
    shareErrorMessage({ code: 'BOARD_SEARCH_SHARE_CODE_INVALID' }),
    'Nieprawidłowy kod dostępu.',
  );
  assert.match(shareErrorMessage(undefined), /Nie udało się/);
});

test('a stake choice is reported for its range; the base stake has no parameter', async () => {
  const { calls, dataSource } = source((path) =>
    path.includes('startSequenceNumber=9')
      ? { body: { code: 'BOARD_SEARCH_SHARE_RATE_LIMITED' }, status: 429 }
      : { body: { recorded: true } },
  );
  const chosen = await dataSource.recordBoardSearchApproximateWinStake(
    'shared',
    { spinCount: 100, stakeGrosze: 200, startSequenceNumber: 7 },
  );
  const base = await dataSource.recordBoardSearchApproximateWinStake('shared', {
    spinCount: 100,
    stakeGrosze: null,
    startSequenceNumber: 7,
  });
  const refused = await dataSource.recordBoardSearchApproximateWinStake(
    'shared',
    { spinCount: 100, stakeGrosze: 200, startSequenceNumber: 9 },
  );
  assert.deepEqual(calls, [
    '/approximate-win/stake?spinCount=100&startSequenceNumber=7&stakeGrosze=200',
    '/approximate-win/stake?spinCount=100&startSequenceNumber=7',
    '/approximate-win/stake?spinCount=100&startSequenceNumber=9&stakeGrosze=200',
  ]);
  assert.equal(chosen.error, undefined);
  assert.equal(base.error, undefined);
  assert.notEqual(refused.error, undefined);
});
