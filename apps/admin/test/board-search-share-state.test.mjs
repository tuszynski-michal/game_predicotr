import assert from 'node:assert/strict';
import test from 'node:test';

import {
  BOARD_SEARCH_SHARE_DEFAULT_LIFETIME_MINUTES,
  BOARD_SEARCH_SHARE_LIFETIMES,
  boardSearchShareErrorMessage,
  boardSearchShareStatusLabel,
  groupBoardSearchShareSessions,
} from '../src/features/board-search/board-search-share-state.ts';

function session(sessionId, status, createdAt) {
  return { createdAt, sessionId, status };
}

test('lifetimes are 1, 4, 8, 24, 48 and 72 hours with 8 hours by default', () => {
  assert.deepEqual(
    BOARD_SEARCH_SHARE_LIFETIMES.map((option) => option.minutes),
    [60, 240, 480, 1440, 2880, 4320],
  );
  assert.equal(BOARD_SEARCH_SHARE_DEFAULT_LIFETIME_MINUTES, 480);
});

test('the list separates active links from ended ones, newest first', () => {
  const groups = groupBoardSearchShareSessions([
    session('a', 'revoked', '2026-09-30T08:00:00Z'),
    session('b', 'active', '2026-09-30T09:00:00Z'),
    session('c', 'expired', '2026-09-30T10:00:00Z'),
    session('d', 'active', '2026-09-30T11:00:00Z'),
    session('e', 'locked', '2026-09-30T07:00:00Z'),
  ]);
  assert.deepEqual(
    groups.active.map((item) => item.sessionId),
    ['d', 'b'],
  );
  assert.deepEqual(
    groups.ended.map((item) => item.sessionId),
    ['c', 'a', 'e'],
  );
  assert.equal(
    boardSearchShareStatusLabel('locked'),
    'Zablokowany (błędne kody)',
  );
});

test('errors are explained, including a missing public ingress', () => {
  assert.match(
    boardSearchShareErrorMessage(
      { code: 'REVIEWER_INGRESS_NOT_READY', message: 'x' },
      'f',
    ),
    /publicznego adresu Reviewera/,
  );
  assert.match(
    boardSearchShareErrorMessage(
      { code: 'BOARD_SEARCH_SHARE_ACTIVE_LIMIT', message: 'x' },
      'f',
    ),
    /najwyżej 5/,
  );
  assert.equal(
    boardSearchShareErrorMessage({ code: 'OTHER', message: 'Coś' }, 'f'),
    'Coś (OTHER)',
  );
  assert.equal(boardSearchShareErrorMessage(undefined, 'fallback'), 'fallback');
});
