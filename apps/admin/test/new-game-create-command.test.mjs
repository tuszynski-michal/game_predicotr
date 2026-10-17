import assert from 'node:assert/strict';
import test from 'node:test';

import {
  EMPTY_GAME_DRAFT,
  usesNeuralGridConfiguration,
  isGridEngineProfileConfiguration,
} from '../src/features/games/game-catalog-state.ts';
import {
  archivePendingCommand,
  gameCreateCommand,
  gameCreateStorageKey,
  pendingGameDraft,
  readPendingGameCreate,
  reserveGameCreate,
} from '../src/features/games/new-game-create-command.ts';
import { saveGameIdentity } from '../src/features/games/game-catalog-actions.ts';

function storage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
}
const draft = { ...EMPTY_GAME_DRAFT, code: 'new-game', name: 'New game' };
const key = '10040000-0000-4000-8000-000000000001';

test('create persists exact command before POST, then reload retries the same key without adopting code', async () => {
  const store = storage();
  const namespace = gameCreateStorageKey('http://127.0.0.1:8000/');
  const command = reserveGameCreate(
    store,
    namespace,
    gameCreateCommand(draft, key),
  );
  let requests = 0;
  const api = {
    createGame: async (body) => {
      requests++;
      assert.deepEqual(readPendingGameCreate(store, namespace), body);
      assert.equal('shapeGeometryConfiguration' in body, false);
      throw new Error('lost response');
    },
    listGames: () => {
      throw new Error('Never adopt a game by code');
    },
    getGame: () => {
      throw new Error('No known game ID before receipt replay');
    },
  };
  assert.equal(
    (await saveGameIdentity(api, { mode: 'create', command }, draft)).ok,
    false,
  );
  const restored = readPendingGameCreate(store, namespace);
  const retried = reserveGameCreate(
    store,
    namespace,
    gameCreateCommand(pendingGameDraft(restored), crypto.randomUUID()),
  );
  assert.deepEqual(retried, command);
  await saveGameIdentity(
    api,
    { mode: 'create', command: retried },
    pendingGameDraft(restored),
  );
  assert.equal(requests, 2);
  assert.equal(readPendingGameCreate(store, namespace).idempotencyKey, key);
  assert.throws(
    () =>
      reserveGameCreate(
        store,
        namespace,
        gameCreateCommand({ ...draft, name: 'Changed' }, key),
      ),
    /Dokończ poprzednie/,
  );
});

test('storage failure blocks creation before transport and advanced fork survives reload', () => {
  const store = storage();
  const advanced = {
    ...draft,
    gridModel: {
      mode: 'fork',
      baseVersionId: key,
      familyCode: 'new_family',
      familyLabel: 'New family',
    },
  };
  const command = gameCreateCommand(advanced, key);
  reserveGameCreate(store, 'namespace', command);
  assert.deepEqual(
    pendingGameDraft(readPendingGameCreate(store, 'namespace')).gridModel,
    advanced.gridModel,
  );
  assert.throws(
    () =>
      reserveGameCreate(
        {
          ...store,
          setItem() {
            throw new Error('quota');
          },
        },
        'empty',
        command,
      ),
    /quota/,
  );
});

test('all V3 formats use the neural engine while static profiles and historical7 remain distinct', () => {
  for (const configuration of [
    'neural_grid_v3',
    'grid_profile_mumie_v1',
    'grid_profile_777_v2',
  ]) {
    assert.equal(usesNeuralGridConfiguration(configuration, 'new-game'), true);
    assert.equal(usesNeuralGridConfiguration(configuration, '7'), false);
  }
  for (const configuration of [
    'framed_full_page_v2',
    'requires_clarification',
    null,
  ]) {
    assert.equal(usesNeuralGridConfiguration(configuration, 'legacy'), false);
  }
  assert.equal(isGridEngineProfileConfiguration('neural_grid_v3'), false);
});

test('confirmed abandonment archives raw corrupt content first; archive failure preserves pending', () => {
  const store = storage();
  const namespace = gameCreateStorageKey('http://api');
  const raw = '{broken json';
  store.setItem(namespace, raw);
  const archive = archivePendingCommand(store, namespace);
  const record = JSON.parse(store.getItem(archive));
  assert.equal(record.raw, raw);
  assert.equal(record.namespace, namespace);
  assert.equal(record.schemaVersion, 'game-command-recovery-v1');
  assert.ok(record.createdAt);
  assert.equal(store.getItem(namespace), null);
  store.setItem(namespace, raw);
  const blocked = {
    ...store,
    setItem: () => {
      throw new Error('disk full');
    },
  };
  assert.throws(() => archivePendingCommand(blocked, namespace), /disk full/);
  assert.equal(store.getItem(namespace), raw);
  assert.ok(store.getItem(archive));
});

test('only matching server proof on 4xx allows replacing pending; 422, 5xx and wrong key stay ambiguous', async () => {
  const command = gameCreateCommand(draft, key);
  for (const [status, proof, allowed] of [
    [
      409,
      {
        schemaVersion: 'game-create-recovery-v1',
        idempotencyKey: key,
        reservation: 'not_created',
      },
      true,
    ],
    [
      409,
      {
        schemaVersion: 'game-create-recovery-v1',
        idempotencyKey: crypto.randomUUID(),
        reservation: 'not_created',
      },
      false,
    ],
    [422, undefined, false],
    [409, undefined, false],
    [
      503,
      {
        schemaVersion: 'game-create-recovery-v1',
        idempotencyKey: key,
        reservation: 'not_created',
      },
      false,
    ],
  ]) {
    const api = {
      createGame: async () => ({
        error: {
          code: 'GRID_MODEL_FAMILY_CONFLICT',
          message: 'Rejected',
          details: { createRecovery: proof },
        },
        response: { status },
      }),
    };
    const result = await saveGameIdentity(
      api,
      { mode: 'create', command },
      draft,
    );
    assert.equal(result.rejectedBeforeReservation, allowed);
  }
});
