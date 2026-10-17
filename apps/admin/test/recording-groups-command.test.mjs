import assert from 'node:assert/strict';
import test from 'node:test';
import {
  completeRecordingCommand,
  discardRecordingCommand,
  readRecordingCommand,
  recordingCommandKey,
  reserveRecordingCommand,
} from '../src/features/model-quality/recording-groups-command.ts';

function storage() {
  const items = new Map();
  return {
    items,
    getItem: (key) => items.get(key) ?? null,
    setItem: (key, value) => items.set(key, value),
    removeItem: (key) => items.delete(key),
  };
}
const command = {
  kind: 'assign_role',
  idempotencyKey: '11111111-1111-4111-8111-111111111111',
  expectedRevision: 4,
  role: 'TRAIN',
};

test('restart recovers immutable exact command with original key and revision in own namespace', () => {
  const s = storage();
  const frozen = reserveRecordingCommand(s, 'api-a', 'game-a', command);
  assert.deepEqual(frozen, command);
  assert.notEqual(frozen, command);
  const freshProcess = storage();
  for (const [key, value] of s.items) freshProcess.setItem(key, value);
  assert.deepEqual(
    readRecordingCommand(freshProcess, 'api-a', 'game-a'),
    command,
  );
  assert.equal(readRecordingCommand(freshProcess, 'api-b', 'game-a'), null);
  assert.equal(readRecordingCommand(freshProcess, 'api-a', 'game-b'), null);
  assert.throws(
    () => reserveRecordingCommand(s, 'api-a', 'game-a', command),
    /Najpierw/,
  );
});

test('malformed or wrong namespace commands block replacement and stay archived exactly', () => {
  for (const raw of [
    '{broken',
    JSON.stringify({ version: 1, api: 'other', gameId: 'game', command }),
  ]) {
    const s = storage();
    const key = recordingCommandKey('api', 'game');
    s.setItem(key, raw);
    assert.throws(() => readRecordingCommand(s, 'api', 'game'));
    assert.throws(() => reserveRecordingCommand(s, 'api', 'game', command));
    discardRecordingCommand(s, 'api', 'game', false);
    assert.equal(s.getItem(key), raw);
    discardRecordingCommand(s, 'api', 'game', true);
    const archive = JSON.parse([...s.items.values()][0]);
    assert.equal(archive.raw, raw);
    assert.equal(archive.gameId, 'game');
    assert.equal(s.getItem(key), null);
  }
});

test('failed persistence or archive does not permit mutation or discard', () => {
  const s = storage();
  s.setItem = () => {
    throw new Error('quota');
  };
  assert.throws(
    () => reserveRecordingCommand(s, 'api', 'game', command),
    /quota/,
  );
  const key = recordingCommandKey('api', 'game');
  s.items.set(key, '{broken');
  assert.throws(() => discardRecordingCommand(s, 'api', 'game', true), /quota/);
  assert.equal(s.getItem(key), '{broken');
  s.setItem = () => {};
  assert.throws(
    () => discardRecordingCommand(s, 'api', 'game', true),
    /archiwum/,
  );
  assert.equal(s.getItem(key), '{broken');
});

test('late confirmation cannot clear a changed command even when keys match', () => {
  const s = storage();
  reserveRecordingCommand(s, 'api', 'game', command);
  completeRecordingCommand(s, 'api', 'game', {
    ...command,
    expectedRevision: 5,
  });
  assert.deepEqual(readRecordingCommand(s, 'api', 'game'), command);
  completeRecordingCommand(s, 'api', 'game', command);
  assert.equal(readRecordingCommand(s, 'api', 'game'), null);
});
