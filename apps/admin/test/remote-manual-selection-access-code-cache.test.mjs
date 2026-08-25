import assert from 'node:assert/strict';
import test from 'node:test';

import {
  REMOTE_MANUAL_SELECTION_ACCESS_CODE_STORAGE_KEY,
  loadRemoteManualSelectionAccessCodes,
  rememberRemoteManualSelectionAccessCode,
  removeRemoteManualSelectionAccessCode,
  retainActiveRemoteManualSelectionAccessCodes,
} from '../src/features/manual-image-selection/remote-manual-selection-access-code-cache.ts';

const now = new Date('2026-08-25T10:00:00.000Z');
const future = '2026-08-25T18:00:00.000Z';

test('persists a newly created remote access code locally through a reload', () => {
  const storage = new MemoryStorage();
  const remembered = rememberRemoteManualSelectionAccessCode(
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
  assert.deepEqual(
    loadRemoteManualSelectionAccessCodes(storage, now),
    remembered,
  );
  assert.match(
    storage.getItem(REMOTE_MANUAL_SELECTION_ACCESS_CODE_STORAGE_KEY),
    /ABCD-EFGH/,
  );
});

test('drops malformed and expired cached access codes without touching a valid session', () => {
  const storage = new MemoryStorage({
    [REMOTE_MANUAL_SELECTION_ACCESS_CODE_STORAGE_KEY]: JSON.stringify({
      expired: {
        accessCode: 'OLD-CODE',
        expiresAt: '2026-08-25T09:59:59.000Z',
      },
      malformed: { accessCode: '', expiresAt: future },
      valid: { accessCode: 'WXYZ-1234', expiresAt: future },
    }),
  });

  assert.deepEqual(loadRemoteManualSelectionAccessCodes(storage, now), {
    valid: { accessCode: 'WXYZ-1234', expiresAt: future },
  });
});

test('clears an unreadable cache instead of retaining an unverifiable access code', () => {
  const storage = new MemoryStorage({
    [REMOTE_MANUAL_SELECTION_ACCESS_CODE_STORAGE_KEY]: '{not-json',
  });

  assert.deepEqual(loadRemoteManualSelectionAccessCodes(storage, now), {});
  assert.equal(
    storage.getItem(REMOTE_MANUAL_SELECTION_ACCESS_CODE_STORAGE_KEY),
    null,
  );
});

test('removes codes when a session is no longer active or is explicitly stopped', () => {
  const storage = new MemoryStorage();
  const current = {
    active: { accessCode: 'ABCD-EFGH', expiresAt: future },
    stale: { accessCode: 'WXYZ-1234', expiresAt: future },
  };
  const retained = retainActiveRemoteManualSelectionAccessCodes(
    current,
    ['active'],
    storage,
    now,
  );

  assert.deepEqual(retained, {
    active: { accessCode: 'ABCD-EFGH', expiresAt: future },
  });
  assert.deepEqual(
    removeRemoteManualSelectionAccessCode(retained, 'active', storage),
    {},
  );
  assert.equal(
    storage.getItem(REMOTE_MANUAL_SELECTION_ACCESS_CODE_STORAGE_KEY),
    null,
  );
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
