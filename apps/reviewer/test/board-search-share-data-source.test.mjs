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

const seriesId = '33333333-3333-4333-8333-333333333333';
const publicMarker = {
  completeness: 'complete',
  kind: 'in_series',
  runVerification: 'verified',
  seriesLength: 10,
  spinIndex: 3,
  superSymbolCode: 'K',
};

const publicSeries = {
  completeness: 'complete',
  definedAt: null,
  endSequenceNumber: 110,
  id: seriesId,
  length: 10,
  retriggerSequenceNumbers: [105],
  revision: 2,
  runVerification: 'verified',
  startSequenceNumber: 101,
  superSymbolId: null,
  triggerSequenceNumber: 100,
  updatedAt: '2026-10-18T10:00:00Z',
};

test('super game markers and the state pass through with their series identity', async () => {
  // D-564: the share carries `seriesId`, so the marker can open the series.
  const withSeries = { ...publicMarker, seriesId };
  const body = {
    ...searchBody,
    results: [{ ...searchBody.results[0], superGame: withSeries }],
    superGameState: { fresh: true, generationInputVersion: 4, inputVersion: 4 },
  };
  const { dataSource } = source(() => ({ body }));
  const found = await dataSource.searchGameBoards('shared', {
    cells: [{ cellIndex: 0, symbolCode: 'A' }],
  });
  assert.deepEqual(found.data.results[0].superGame, withSeries);
  assert.equal(found.data.results[0].superGame.seriesId, seriesId);
  assert.deepEqual(found.data.superGameState, body.superGameState);
  // Boards outside every series keep the historical shape.
  const plain = await source(() => ({
    body: searchBody,
  })).dataSource.searchGameBoards('shared', {
    cells: [{ cellIndex: 0, symbolCode: 'A' }],
  });
  assert.equal('superGame' in plain.data.results[0], false);
  assert.equal('superGameState' in plain.data, false);
});

test('a re-search after the super symbol changed returns the new marker', async () => {
  let symbol = null;
  const { calls, dataSource } = source(() => ({
    body: {
      ...searchBody,
      results: [
        {
          ...searchBody.results[0],
          superGame: { ...publicMarker, superSymbolCode: symbol },
        },
      ],
      superGameState: {
        fresh: true,
        generationInputVersion: 4,
        inputVersion: 4,
      },
    },
  }));
  const options = { cells: [{ cellIndex: 0, symbolCode: 'A' }] };
  const first = await dataSource.searchGameBoards('shared', options);
  assert.equal(first.data.results[0].superGame.superSymbolCode, null);
  symbol = 'K';
  const second = await dataSource.searchGameBoards('shared', options);
  assert.equal(calls.length, 2, 'an answer with a marker is never cached');
  assert.equal(second.data.results[0].superGame.superSymbolCode, 'K');
});

test('an answer while the series are recalculated is not cached', async () => {
  let fresh = false;
  const { calls, dataSource } = source(() => ({
    body: {
      ...searchBody,
      superGameState: {
        fresh,
        generationInputVersion: 4,
        inputVersion: fresh ? 4 : 5,
      },
    },
  }));
  const options = { cells: [{ cellIndex: 0, symbolCode: 'A' }] };
  await dataSource.searchGameBoards('shared', options);
  await dataSource.searchGameBoards('shared', options);
  assert.equal(calls.length, 2, 'a stale generation is asked for again');
  fresh = true;
  await dataSource.searchGameBoards('shared', options);
  await dataSource.searchGameBoards('shared', options);
  assert.equal(calls.length, 3, 'a fresh answer is cached again');
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

// --- Super game series of the shared game (D-564) ---------------------------

test('the series boards are mapped to the Admin shape without identities', async () => {
  const { calls, dataSource } = source((path) => ({
    body: path.endsWith('/boards')
      ? {
          boards: [
            {
              boardChecksumSha256: 'b'.repeat(64),
              missing: false,
              role: 'trigger',
              sequenceNumber: 100,
              spinIndex: null,
              status: 'accepted',
            },
            {
              boardChecksumSha256: null,
              missing: true,
              role: 'spin',
              sequenceNumber: 101,
              spinIndex: 1,
              status: null,
            },
          ],
          series: publicSeries,
          superGameState: {
            fresh: true,
            generationInputVersion: 4,
            inputVersion: 4,
          },
        }
      : { fresh: false, generationInputVersion: 3, inputVersion: 4 },
  }));
  const boards = await dataSource.listSuperGameSeriesBoards('shared', seriesId);
  assert.equal(calls[0], `/super-game-series/${seriesId}/boards`);
  assert.deepEqual(boards.data.series, {
    ...publicSeries,
    definedBy: null,
    gameId: 'shared',
  });
  assert.deepEqual(boards.data.boards, [
    {
      assetMode: 'operational_review',
      boardChecksumSha256: 'b'.repeat(64),
      importJobId: null,
      missing: false,
      recognizedBoardId: null,
      reviewItemId: null,
      role: 'trigger',
      sequenceNumber: 100,
      spinIndex: null,
      status: 'accepted',
    },
    {
      assetMode: null,
      boardChecksumSha256: null,
      importJobId: null,
      missing: true,
      recognizedBoardId: null,
      reviewItemId: null,
      role: 'spin',
      sequenceNumber: 101,
      spinIndex: 1,
      status: null,
    },
  ]);
  assert.equal(boards.data.superGameState.fresh, true);
  const state = await dataSource.getSuperGameSeriesState('shared');
  assert.equal(calls[1], '/super-game-series/state');
  assert.equal(state.data.fresh, false);
});

test('the super symbol is sent as a same-origin JSON PUT and drops the caches', async () => {
  const requests = [];
  const { calls, dataSource, unauthorized } = source(
    (path) =>
      path.includes('/super-symbol')
        ? { body: { ...publicSeries, revision: 3, superSymbolId: symbolId } }
        : { body: searchBody },
    {
      fetchImplementation: async (url, init) => {
        requests.push({ init, url: String(url) });
        const path = String(url).slice(BOARD_SEARCH_SHARE_API_BASE.length);
        calls.push(path);
        if (path.includes('/super-symbol')) {
          return new Response(
            JSON.stringify({
              ...publicSeries,
              revision: 3,
              superSymbolId: symbolId,
            }),
            { headers: { 'Content-Type': 'application/json' } },
          );
        }
        return new Response(JSON.stringify(searchBody), {
          headers: { 'Content-Type': 'application/json' },
        });
      },
    },
  );
  const options = { cells: [{ cellIndex: 0, symbolCode: 'A' }], limit: 5 };
  await dataSource.searchGameBoards('shared', options);
  await dataSource.searchGameBoards('shared', options);
  assert.equal(calls.length, 1, 'the second search is served from the cache');

  const saved = await dataSource.setSuperGameSeriesSuperSymbol(
    'shared',
    seriesId,
    { expectedRevision: 2, symbolId },
  );
  const put = requests.at(-1);
  assert.equal(
    put.url,
    `${BOARD_SEARCH_SHARE_API_BASE}/super-game-series/${seriesId}/super-symbol`,
  );
  assert.equal(put.init.method, 'PUT');
  assert.equal(put.init.credentials, 'same-origin');
  assert.equal(put.init.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(put.init.body), {
    expectedRevision: 2,
    symbolId,
  });
  assert.equal(saved.data.revision, 3);
  assert.equal(saved.data.superSymbolId, symbolId);
  assert.equal(saved.data.gameId, 'shared');
  assert.equal(saved.data.definedBy, null);
  await dataSource.searchGameBoards('shared', options);
  assert.equal(calls.length, 3, 'the search cache was dropped by the save');
  assert.equal(unauthorized(), 0);
});

test('a refused or expired super symbol update is reported, and 401 ends the access', async () => {
  const conflict = source(() => ({
    body: { code: 'SUPER_GAME_SERIES_REVISION_CONFLICT', message: 'x' },
    status: 409,
  }));
  const refused = await conflict.dataSource.setSuperGameSeriesSuperSymbol(
    'shared',
    seriesId,
    { expectedRevision: 1, symbolId: null },
  );
  assert.equal(refused.data, undefined);
  assert.equal(refused.error.code, 'SUPER_GAME_SERIES_REVISION_CONFLICT');
  assert.equal(conflict.unauthorized(), 0);

  const expired = source(() => ({
    body: { code: 'BOARD_SEARCH_SHARE_TOKEN_INVALID', message: 'x' },
    status: 401,
  }));
  await expired.dataSource.setSuperGameSeriesSuperSymbol('shared', seriesId, {
    expectedRevision: 1,
    symbolId: null,
  });
  assert.equal(expired.unauthorized(), 1);
});

test('the next series without a symbol follows the trigger cursor only', async () => {
  const { calls, dataSource } = source(() => ({
    body: {
      items: [publicSeries],
      superGameState: {
        fresh: true,
        generationInputVersion: 4,
        inputVersion: 4,
      },
    },
  }));
  const fromStart = await dataSource.listNextUndefinedSuperGameSeries(
    'shared',
    { afterTrigger: null, filters: { completeness: 'complete' } },
  );
  const after = await dataSource.listNextUndefinedSuperGameSeries('shared', {
    afterTrigger: 100,
    filters: { completeness: 'all' },
  });
  assert.deepEqual(calls, [
    '/super-game-series/next-undefined',
    '/super-game-series/next-undefined?afterTrigger=100',
  ]);
  assert.equal(fromStart.data.items[0].id, seriesId);
  assert.equal(fromStart.data.items[0].gameId, 'shared');
  assert.equal(after.data.items.length, 1);
});

test('symbols carry their super game trigger count for the series view', async () => {
  const { dataSource } = source(() => ({
    body: [
      {
        code: 'A',
        displayOrder: 0,
        id: symbolId,
        imageRevision: null,
        isWildcard: false,
        mobileCode: 1,
        name: 'A',
        nameEn: null,
        namePl: null,
        status: 'active',
        superGameTriggerCount: 3,
      },
      {
        code: 'B',
        displayOrder: 1,
        id: '22222222-2222-4222-8222-222222222222',
        imageRevision: null,
        isWildcard: false,
        mobileCode: 2,
        name: 'B',
        nameEn: null,
        namePl: null,
        status: 'active',
      },
    ],
  }));
  const symbols = await dataSource.listSymbols('shared');
  assert.deepEqual(
    symbols.data.map((symbol) => symbol.superGameTriggerCount),
    [3, null],
  );
});
