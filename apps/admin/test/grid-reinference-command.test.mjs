import assert from 'node:assert/strict';
import test from 'node:test';
import {
  discardGridCommand,
  gridCommandKey,
  readGridCommand,
  saveGridCommand,
} from '../src/features/model-quality/grid-reinference-command.ts';

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
  kind: 'prepare',
  operationId: null,
  body: {
    idempotencyKey: '11111111-1111-4111-8111-111111111111',
    selector: { categories: ['grid_issue', 'deferred'] },
  },
};
test('command journal scopes API and game; existing exact body cannot be overwritten', () => {
  const s = storage();
  saveGridCommand(s, 'api-a', 'game-a', command);
  assert.deepEqual(readGridCommand(s, 'api-a', 'game-a'), command);
  assert.equal(readGridCommand(s, 'api-b', 'game-a'), null);
  assert.equal(readGridCommand(s, 'api-a', 'game-b'), null);
  assert.throws(() => saveGridCommand(s, 'api-a', 'game-a', command));
});
test('archive failure preserves malformed raw pending and confirmation is mandatory', () => {
  const s = storage();
  const key = gridCommandKey('api', 'game');
  s.setItem(key, '{broken');
  discardGridCommand(s, 'api', 'game', false);
  assert.equal(s.getItem(key), '{broken');
  s.setItem = () => {
    throw new Error('quota');
  };
  assert.throws(() => discardGridCommand(s, 'api', 'game', true), /quota/);
  assert.equal(s.getItem(key), '{broken');
});

test('archive preserves explicit command identity metadata and exact raw body', () => {
  const s = storage();
  const exact = {
    kind: 'freeze',
    operationId: '22222222-2222-4222-8222-222222222222',
    body: {
      idempotencyKey: command.body.idempotencyKey,
      expectedRevision: 7,
      manifestSha256: 'a'.repeat(64),
    },
  };
  saveGridCommand(s, 'api', 'game', exact);
  const raw = s.getItem(gridCommandKey('api', 'game'));
  discardGridCommand(s, 'api', 'game', true);
  const archive = JSON.parse([...s.items.values()][0]);
  assert.equal(archive.operationId, exact.operationId);
  assert.equal(archive.idempotencyKey, exact.body.idempotencyKey);
  assert.equal(archive.kind, 'freeze');
  assert.equal(archive.apiNamespace, 'api');
  assert.equal(archive.namespace, gridCommandKey('api', 'game'));
  assert.equal(archive.raw, raw);
  assert.equal(s.getItem(gridCommandKey('api', 'game')), null);
});

test('malformed archive has null identity metadata and retains raw bytes', () => {
  const s = storage();
  const key = gridCommandKey('api', 'game');
  s.setItem(key, '{broken');
  discardGridCommand(s, 'api', 'game', true);
  const archive = JSON.parse([...s.items.values()][0]);
  assert.equal(archive.raw, '{broken');
  assert.equal(archive.operationId, null);
  assert.equal(archive.idempotencyKey, null);
  assert.equal(archive.kind, null);
});
