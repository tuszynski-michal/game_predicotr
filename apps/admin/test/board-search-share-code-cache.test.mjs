import assert from 'node:assert/strict';
import test from 'node:test';

import {
  BOARD_SEARCH_SHARE_CODE_STORAGE_KEY,
  loadBoardSearchShareCodes,
  rememberBoardSearchShareCode,
  removeBoardSearchShareCode,
  removeEndedBoardSearchShareCodes,
  retainActiveBoardSearchShareCodes,
} from '../src/features/board-search/board-search-share-code-cache.ts';

const now = new Date('2026-08-25T10:00:00.000Z');
const future = '2026-08-25T18:00:00.000Z';

test('persists a newly created share access code locally through a reload', () => {
  const storage = new MemoryStorage();
  const remembered = rememberBoardSearchShareCode(
    {},
    {
      accessCode: 'ABCD-EFGH',
      expiresAt: future,
      sessionId: 'session-1',
    },
    storage,
    now,
  );

  assert.deepEqual(remembered, {
    'session-1': { accessCode: 'ABCD-EFGH', expiresAt: future },
  });
  assert.deepEqual(loadBoardSearchShareCodes(storage, now), remembered);
  assert.match(
    storage.getItem(BOARD_SEARCH_SHARE_CODE_STORAGE_KEY),
    /ABCD-EFGH/,
  );
});

test('drops malformed and expired cached access codes without touching a valid session', () => {
  const storage = new MemoryStorage({
    [BOARD_SEARCH_SHARE_CODE_STORAGE_KEY]: JSON.stringify({
      expired: {
        accessCode: 'OLD-CODE',
        expiresAt: '2026-08-25T09:59:59.000Z',
      },
      malformed: { accessCode: '', expiresAt: future },
      valid: { accessCode: 'WXYZ-1234', expiresAt: future },
    }),
  });

  assert.deepEqual(loadBoardSearchShareCodes(storage, now), {
    valid: { accessCode: 'WXYZ-1234', expiresAt: future },
  });
});

test('clears an unreadable cache instead of retaining an unverifiable access code', () => {
  const storage = new MemoryStorage({
    [BOARD_SEARCH_SHARE_CODE_STORAGE_KEY]: '{not-json',
  });

  assert.deepEqual(loadBoardSearchShareCodes(storage, now), {});
  assert.equal(storage.getItem(BOARD_SEARCH_SHARE_CODE_STORAGE_KEY), null);
});

test('removes codes when a session is no longer active or is explicitly stopped', () => {
  const storage = new MemoryStorage();
  const current = {
    active: { accessCode: 'ABCD-EFGH', expiresAt: future },
    stale: { accessCode: 'WXYZ-1234', expiresAt: future },
  };
  const retained = retainActiveBoardSearchShareCodes(
    current,
    ['active'],
    storage,
    now,
  );

  assert.deepEqual(retained, {
    active: { accessCode: 'ABCD-EFGH', expiresAt: future },
  });
  assert.deepEqual(removeBoardSearchShareCode(retained, 'active', storage), {});
  assert.equal(storage.getItem(BOARD_SEARCH_SHARE_CODE_STORAGE_KEY), null);
});

class MemoryStorage {
  #values;

  constructor(values = {}) {
    this.#values = new Map(Object.entries(values));
  }

  getItem(key) {
    return this.#values.get(key) ?? null;
  }

  removeItem(key) {
    this.#values.delete(key);
  }

  setItem(key, value) {
    this.#values.set(key, value);
  }
}

test('share codes live under their own key, apart from remote selection codes', () => {
  const storage = new MemoryStorage();
  rememberBoardSearchShareCode(
    {},
    { accessCode: 'ABCD-EFGH', expiresAt: future, sessionId: 'share-1' },
    storage,
    now,
  );
  assert.equal(
    BOARD_SEARCH_SHARE_CODE_STORAGE_KEY,
    'game-predictor-board-search-share-codes-v1',
  );
  assert.equal(
    storage.getItem('game-predictor-remote-manual-selection-access-codes-v1'),
    null,
  );
});

test('only codes of links known to have ended are forgotten', () => {
  const storage = new MemoryStorage();
  let codes = rememberBoardSearchShareCode(
    {},
    { accessCode: 'GAME-A001', expiresAt: future, sessionId: 'game-a' },
    storage,
    now,
  );
  codes = rememberBoardSearchShareCode(
    codes,
    { accessCode: 'GAME-B001', expiresAt: future, sessionId: 'game-b' },
    storage,
    now,
  );
  // Game B's panel lists only its own links; game A's code must survive.
  const next = removeEndedBoardSearchShareCodes(codes, ['game-b'], storage);
  assert.deepEqual(Object.keys(next), ['game-a']);
  assert.deepEqual(Object.keys(loadBoardSearchShareCodes(storage, now)), [
    'game-a',
  ]);
  assert.equal(
    removeEndedBoardSearchShareCodes(next, ['unknown'], storage),
    next,
  );
});
