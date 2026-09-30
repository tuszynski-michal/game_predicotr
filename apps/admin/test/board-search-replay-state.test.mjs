import assert from 'node:assert/strict';
import test from 'node:test';

import {
  consumeBoardSearchReplay,
  boardSearchReplayHref,
  boardSearchReplayPlan,
  readBoardSearchReplayParameter,
} from '../src/features/board-search/board-search-replay-state.ts';
import {
  boardSearchQueryPatternCells,
  describeBoardSearchQueryEntry,
} from '../src/features/board-search/board-search-share-query-log-state.ts';

const eventId = '33333333-3333-4333-8333-333333333333';
const search = {
  id: 'search-1',
  kind: 'search',
  request: {
    cells: ['6:lemon', '0:cherry', '3:?'],
    limit: 7,
    scope: 'approved_only',
  },
};

test('a search entry replays its exact pattern, scope and limit', () => {
  const result = boardSearchReplayPlan(
    { approximateWin: null, event: search, search },
    'n1',
  );
  assert.equal(result.kind, 'plan');
  assert.deepEqual(result.plan, {
    approximateWin: null,
    boardSequenceNumber: null,
    cells: [
      { cellIndex: 6, symbolCode: 'lemon' },
      { cellIndex: 0, symbolCode: 'cherry' },
      { cellIndex: 3, symbolCode: null },
    ],
    id: 'search-1:n1',
    limit: 7,
    scope: 'approved_only',
  });
});

test('a range or board entry adds the range and the board to open', () => {
  const range = {
    id: 'range-1',
    kind: 'approximate_win',
    request: { spinCount: 250, startSequenceNumber: 12 },
  };
  const detail = {
    id: 'detail-1',
    kind: 'board_detail',
    request: { sequenceNumber: 13 },
  };
  const fromRange = boardSearchReplayPlan(
    { approximateWin: range, event: range, search },
    'n',
  );
  assert.deepEqual(fromRange.plan.approximateWin, {
    spinCount: 250,
    startSequenceNumber: 12,
  });
  assert.equal(fromRange.plan.boardSequenceNumber, null);
  const fromDetail = boardSearchReplayPlan(
    { approximateWin: range, event: detail, search },
    'n',
  );
  assert.equal(fromDetail.plan.boardSequenceNumber, 13);
});

test('without an earlier search the parameters are explained instead', () => {
  const range = {
    id: 'range-2',
    kind: 'approximate_win',
    request: { spinCount: 100, startSequenceNumber: 5 },
  };
  const result = boardSearchReplayPlan(
    { approximateWin: range, event: range, search: null },
    'n',
  );
  assert.equal(result.kind, 'no_search');
  assert.match(result.message, /plansza startowa #5, zakres 100 spinów/);
  const broken = boardSearchReplayPlan(
    {
      approximateWin: null,
      event: search,
      search: { ...search, request: { cells: 'x' } },
    },
    'n',
  );
  assert.equal(broken.kind, 'no_search');
});

test('the replay parameter accepts only an event id', () => {
  assert.equal(
    readBoardSearchReplayParameter(`?boardSearchReplay=${eventId}`),
    eventId,
  );
  assert.equal(readBoardSearchReplayParameter('?boardSearchReplay=../x'), null);
  assert.equal(readBoardSearchReplayParameter('?game=1'), null);
  assert.equal(
    boardSearchReplayHref(
      'http://127.0.0.1:3000/?game=g&section=board-search',
      eventId,
    ),
    `/?game=g&section=board-search&boardSearchReplay=${eventId}`,
  );
});

test('log entries show the pattern as a board and readable details', () => {
  const board = boardSearchQueryPatternCells({
    ...search,
    outcomeCode: 'ok',
    resultSummary: {},
  });
  assert.equal(board.length, 15);
  assert.equal(board[0], 'cherry');
  assert.equal(board[3], '?');
  assert.equal(board[6], 'lemon');
  assert.equal(board[1], null);
  assert.match(
    describeBoardSearchQueryEntry({
      ...search,
      outcomeCode: 'ok',
      resultSummary: { firstSequenceNumbers: [4, 9], resultCount: 2 },
    }).details,
    /tylko zatwierdzone · limit 7 · wyniki: 2 \(#4, #9\)/,
  );
  assert.equal(
    describeBoardSearchQueryEntry({
      kind: 'board_detail',
      outcomeCode: 'BOARD_SEARCH_BOARD_NOT_FOUND',
      request: { sequenceNumber: 8 },
      resultSummary: {},
    }).details,
    'Plansza #8',
  );
});

test('a taken-over replay is dropped so a remount does not replay again', () => {
  const plan = { id: 'e:1' };
  assert.equal(
    consumeBoardSearchReplay({ gameId: 'g', message: null, plan }, 'e:1'),
    null,
  );
  assert.deepEqual(
    consumeBoardSearchReplay({ gameId: 'g', message: 'Uwaga', plan }, 'e:1'),
    { gameId: 'g', message: 'Uwaga', plan: null },
  );
  const other = { gameId: 'g', message: null, plan: { id: 'e:2' } };
  assert.equal(consumeBoardSearchReplay(other, 'e:1'), other);
  assert.equal(consumeBoardSearchReplay(null, 'e:1'), null);
});
