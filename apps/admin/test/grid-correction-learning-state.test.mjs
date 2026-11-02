import assert from 'node:assert/strict';
import test from 'node:test';
import {
  archiveLearningCommand,
  clearLearningCommand,
  learningCommandKey,
  readLearningCommand,
} from '../src/features/model-quality/grid-correction-learning-state.ts';

const storage = () => {
  const data = new Map();
  return {
    data,
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, value),
    removeItem: (key) => data.delete(key),
  };
};
test('saved command retains exact key and body; a late response cannot clear a newer command', () => {
  const target = storage(),
    key = learningCommandKey('api', 'game');
  const command = {
    kind: 'start',
    key: 'a',
    target: 'game',
    body: {
      idempotencyKey: 'a',
      previewSha256: 'hash',
      importJobIds: ['import'],
      exclusions: [],
    },
  };
  target.setItem(key, JSON.stringify(command));
  assert.deepEqual(readLearningCommand(target, key), command);
  clearLearningCommand(target, key, 'older');
  assert.ok(target.getItem(key));
  clearLearningCommand(target, key, 'a');
  assert.equal(target.getItem(key), null);
});
test('corrupt JSON is archived before a pending command is abandoned', () => {
  const target = storage(),
    key = 'command';
  target.setItem(key, '{broken');
  assert.throws(() => readLearningCommand(target, key));
  archiveLearningCommand(target, key);
  assert.equal(target.getItem(key), null);
  assert.deepEqual([...target.data.values()], ['{broken']);
});
test('mismatched idempotency identity cannot be replayed', () => {
  const target = storage();
  target.setItem(
    'key',
    JSON.stringify({
      kind: 'start',
      target: 'game',
      key: 'a',
      body: { idempotencyKey: 'b' },
    }),
  );
  assert.throws(() => readLearningCommand(target, 'key'), /niezgodny klucz/);
});
