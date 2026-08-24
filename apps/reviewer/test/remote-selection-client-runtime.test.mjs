import assert from 'node:assert/strict';
import test from 'node:test';
import {
  fetchRemoteSelectionWithTimeout,
  readOrCreateRemoteSelectionClientInstance,
} from '../src/features/manual-selection/remote-selection-client-runtime.ts';

const fixedUuid = '11111111-1111-4111-8111-111111111111';

test('uses an in-memory client id when mobile session storage rejects access', () => {
  const storage = {
    getItem() {
      throw new DOMException('Storage disabled', 'SecurityError');
    },
    setItem() {
      throw new DOMException('Storage disabled', 'SecurityError');
    },
  };
  const cryptoSource = {
    getRandomValues(value) {
      return value;
    },
    randomUUID() {
      return fixedUuid;
    },
  };

  assert.equal(
    readOrCreateRemoteSelectionClientInstance(
      'remote-selection-client',
      storage,
      cryptoSource,
    ),
    fixedUuid,
  );
});

test('creates a valid UUID v4 when randomUUID is unavailable', () => {
  const storage = new Map();
  const result = readOrCreateRemoteSelectionClientInstance(
    'remote-selection-client',
    {
      getItem(key) {
        return storage.get(key) ?? null;
      },
      setItem(key, value) {
        storage.set(key, value);
      },
    },
    {
      getRandomValues(value) {
        value.fill(0x11);
        return value;
      },
    },
  );

  assert.match(
    result,
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
  );
  assert.equal(storage.get('remote-selection-client'), result);
});

test('aborts a remote selection request after the bounded timeout', async () => {
  let observedSignal;
  const fetchImplementation = (_input, init) => {
    observedSignal = init.signal;
    return new Promise((_resolve, reject) => {
      init.signal.addEventListener('abort', () => {
        reject(new DOMException('Request aborted', 'AbortError'));
      });
    });
  };

  await assert.rejects(
    fetchRemoteSelectionWithTimeout(
      '/selection-api/context',
      {},
      5,
      fetchImplementation,
    ),
    { name: 'AbortError' },
  );
  assert.equal(observedSignal.aborted, true);
});
