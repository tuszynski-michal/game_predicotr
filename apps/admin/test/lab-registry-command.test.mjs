import assert from 'node:assert/strict';
import test from 'node:test';
import {
  clearLabRegistryCommand,
  readPendingLabRegistryCommand,
  reconcileLabRegistryFailure,
  saveLabRegistryCommand,
} from '../src/features/model-quality/lab-registry-command.ts';

function storage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
}
const gameId = '11111111-1111-4111-8111-111111111111';
const iterationA = '22222222-2222-4222-8222-222222222222';
const iterationB = '33333333-3333-4333-8333-333333333333';
const operation = '44444444-4444-4444-8444-444444444444';

test('lost response and new UI process preserve complete import command', () => {
  const disk = storage();
  const command = {
    kind: 'import',
    gameId,
    body: {
      candidateFingerprint: 'a'.repeat(64),
      idempotencyKey: operation,
    },
  };
  saveLabRegistryCommand(disk, command);
  assert.deepEqual(readPendingLabRegistryCommand(disk, gameId), command);
  assert.equal(reconcileLabRegistryFailure(disk, gameId, 503), false);
  assert.deepEqual(
    saveLabRegistryCommand(disk, {
      ...command,
      body: { ...command.body, idempotencyKey: iterationB },
    }),
    command,
  );
  clearLabRegistryCommand(disk, gameId);
  assert.equal(readPendingLabRegistryCommand(disk, gameId), null);
});

test('stale A deactivation receives 409 and allows fresh preview for B', () => {
  const disk = storage();
  const commandA = {
    kind: 'deactivate',
    gameId,
    body: {
      expectedCurrentModelIterationId: iterationA,
      actor: 'local-owner',
      idempotencyKey: operation,
      reason: 'Owner-confirmed deactivation.',
    },
  };
  saveLabRegistryCommand(disk, commandA);
  assert.equal(reconcileLabRegistryFailure(disk, gameId, 409), true);
  assert.equal(readPendingLabRegistryCommand(disk, gameId), null);
  const commandB = {
    ...commandA,
    body: {
      ...commandA.body,
      expectedCurrentModelIterationId: iterationB,
      idempotencyKey: '55555555-5555-4555-8555-555555555555',
    },
  };
  assert.deepEqual(saveLabRegistryCommand(disk, commandB), commandB);
  assert.deepEqual(readPendingLabRegistryCommand(disk, gameId), commandB);
});

test('timeouts and throttling retain frozen deactivation expectation', () => {
  const disk = storage();
  const command = {
    kind: 'deactivate',
    gameId,
    body: {
      expectedCurrentModelIterationId: iterationA,
      actor: 'local-owner',
      idempotencyKey: operation,
    },
  };
  saveLabRegistryCommand(disk, command);
  for (const status of [0, 401, 403, 408, 429, 500, 503]) {
    assert.equal(reconcileLabRegistryFailure(disk, gameId, status), false);
    assert.deepEqual(readPendingLabRegistryCommand(disk, gameId), command);
  }
  assert.equal(readPendingLabRegistryCommand(disk, iterationB), null);
});

test('lost reply followed by 403 and reauthorization retries identical receipt', () => {
  const disk = storage();
  const original = {
    kind: 'import',
    gameId,
    body: {
      candidateFingerprint: 'a'.repeat(64),
      idempotencyKey: operation,
    },
  };
  saveLabRegistryCommand(disk, original);
  assert.equal(reconcileLabRegistryFailure(disk, gameId, 403), false);
  const restored = readPendingLabRegistryCommand(disk, gameId);
  const retry = saveLabRegistryCommand(disk, {
    ...original,
    body: {
      ...original.body,
      idempotencyKey: iterationB,
    },
  });
  assert.deepEqual(retry, restored);
  assert.equal(retry.body.idempotencyKey, operation);
});
