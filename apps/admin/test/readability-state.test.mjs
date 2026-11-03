import assert from 'node:assert/strict';
import test from 'node:test';
import {
  canAcceptReadabilityModel,
  readabilityTargets,
  readabilityCommandKey,
  completeReadabilityCommand,
  pendingReadabilityCommand,
} from '../src/features/readability/readability-state.ts';
import {
  parseAdminNavigation,
  serializeAdminNavigation,
} from '../src/features/catalog/admin-navigation-state.ts';

test('labels bind every selected cell to its exact identity and revision; stale and over-limit batches fail closed', () => {
  const item = {
    cellId: 'cell',
    identity: 'a'.repeat(64),
    revision: 7,
    state: 'pending',
  };
  assert.deepEqual(readabilityTargets([item]), [
    { cellId: 'cell', expectedIdentity: item.identity, expectedRevision: 7 },
  ]);
  assert.equal(
    readabilityTargets(
      Array.from({ length: 250 }, (_, index) => ({
        ...item,
        cellId: String(index),
      })),
    ).length,
    250,
  );
  for (const items of [
    [],
    Array(251).fill(item),
    [{ ...item, state: 'stale' }],
    [{ ...item, state: 'error' }],
  ])
    assert.throws(() => readabilityTargets(items));
});

test('acceptance requires completed PASS independently of previous acceptance', () => {
  const model = {
    status: 'completed',
    report: { status: 'PASS' },
    accepted: false,
  };
  assert.equal(canAcceptReadabilityModel(model), true);
  assert.equal(
    canAcceptReadabilityModel({ ...model, status: 'running' }),
    false,
  );
  assert.equal(
    canAcceptReadabilityModel({ ...model, report: { status: 'STOP' } }),
    false,
  );
  assert.equal(canAcceptReadabilityModel({ ...model, accepted: true }), false);
});

test('cold recovery retains the complete command and key; changed commands cannot replace an uncertain result', () => {
  const saved = new Map();
  globalThis.window = {
    localStorage: {
      getItem: (key) => saved.get(key) ?? null,
      setItem: (key, value) => saved.set(key, value),
      removeItem: (key) => saved.delete(key),
    },
  };
  const payload = {
    targets: [
      { cellId: 'c', expectedIdentity: 'a'.repeat(64), expectedRevision: 2 },
    ],
    state: 'readable',
    overlap: null,
  };
  const first = readabilityCommandKey('game', 'labels:run', payload);
  const coldIntent = JSON.parse(saved.get('readability-command:game'));
  assert.deepEqual(coldIntent.payload, payload);
  assert.equal(
    readabilityCommandKey('game', coldIntent.command, coldIntent.payload),
    first,
  );
  assert.throws(
    () => readabilityCommandKey('game', 'fit:run', {}),
    /Najpierw ponów/,
  );
  completeReadabilityCommand('other-game', 'labels:run', payload);
  assert.equal(pendingReadabilityCommand('game').idempotencyKey, first);
  completeReadabilityCommand('game', 'labels:run', payload);
  assert.equal(pendingReadabilityCommand('game'), null);
  assert.notEqual(readabilityCommandKey('game', 'labels:run', payload), first);
  delete globalThis.window;
});

test('suspicious symbols is a game section preserved by URL navigation', () => {
  const state = parseAdminNavigation('?game=game&section=suspicious-symbols');
  assert.equal(state.section, 'suspicious-symbols');
  assert.equal(
    parseAdminNavigation(serializeAdminNavigation('', state)).section,
    'suspicious-symbols',
  );
  assert.equal(
    parseAdminNavigation('?section=suspicious-symbols').section,
    null,
  );
});
