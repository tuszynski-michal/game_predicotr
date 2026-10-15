import assert from 'node:assert/strict';
import test from 'node:test';
import {
  discardRecordingRegistration,
  nextRecordingMembershipCommand,
  readRecordingRegistration,
  recordingRegistrationKey,
  saveRecordingRegistration,
} from '../src/features/model-quality/recording-registration.ts';

const groupId = '11111111-1111-4111-8111-111111111111';
const prepare = {
  kind: 'prepare',
  idempotencyKey: groupId,
  expectedRevision: 0,
  selection: { importJobId: groupId },
};
const group = {
  id: groupId,
  manifestId: groupId,
  revision: 8,
  registeredSources: 200,
  expectedSources: 2000,
  pageCount: 10,
  membershipComplete: false,
  nextPageIndex: 5,
  registeredPages: 1,
  createdAt: '2026-10-15T10:00:00Z',
  importJobId: groupId,
};
function storage() {
  const items = new Map();
  return {
    items,
    getItem: (key) => items.get(key) ?? null,
    setItem: (key, value) => items.set(key, value),
    removeItem: (key) => items.delete(key),
  };
}

test('membership continuation uses the authoritative next page even with non-contiguous progress', () => {
  const command = nextRecordingMembershipCommand(group);
  assert.equal(command.kind, 'attach');
  assert.equal(command.pageIndex, 5);
  assert.equal(command.expectedRevision, 8);
  assert.equal(
    nextRecordingMembershipCommand({ ...group, nextPageIndex: null }).kind,
    'complete',
  );
  assert.equal(
    nextRecordingMembershipCommand({
      ...group,
      membershipComplete: true,
      nextPageIndex: null,
    }),
    null,
  );
});

test('missing or invalid DTO progress cannot be guessed from source totals', () => {
  for (const field of [
    'nextPageIndex',
    'registeredPages',
    'createdAt',
    'importJobId',
  ]) {
    const stale = { ...group };
    delete stale[field];
    assert.throws(
      () => nextRecordingMembershipCommand(stale),
      /potwierdzonego postępu/,
    );
  }
  assert.throws(
    () => nextRecordingMembershipCommand({ ...group, nextPageIndex: 10 }),
    /następnej partii/,
  );
});

test('registration intent preserves original prepare identity and namespace across restart', () => {
  const store = storage();
  const intent = { prepare, groupId: null };
  saveRecordingRegistration(store, 'api', 'game', intent);
  assert.deepEqual(readRecordingRegistration(store, 'api', 'game'), intent);
  assert.equal(readRecordingRegistration(store, 'api', 'other-game'), null);
  assert.equal(readRecordingRegistration(store, 'other-api', 'game'), null);
  const raw = store.getItem(recordingRegistrationKey('api', 'game'));
  const restarted = storage();
  restarted.setItem(recordingRegistrationKey('api', 'game'), raw);
  assert.deepEqual(readRecordingRegistration(restarted, 'api', 'game'), intent);
});

test('discard archives even malformed registration bytes and archive failure preserves progress', () => {
  const store = storage();
  const key = recordingRegistrationKey('api', 'game');
  store.setItem(key, '{broken');
  assert.throws(() => readRecordingRegistration(store, 'api', 'game'));
  const original = store.setItem;
  store.setItem = () => {
    throw new Error('quota');
  };
  assert.throws(
    () => discardRecordingRegistration(store, 'api', 'game'),
    /quota/,
  );
  assert.equal(store.getItem(key), '{broken');
  store.setItem = original;
  discardRecordingRegistration(store, 'api', 'game');
  assert.equal(store.getItem(key), null);
  assert.equal(JSON.parse([...store.items.values()][0]).raw, '{broken');
});
