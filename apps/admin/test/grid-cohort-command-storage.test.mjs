import assert from 'node:assert/strict';
import test from 'node:test';
import {
  readGridCohortCommand,
  reserveGridCohortCommand,
  clearGridCohortCommand,
  discardGridCohortCommand,
  gridCohortCommandKey,
} from '../src/features/model-quality/grid-cohort-command-storage.ts';
const api = 'http://127.0.0.1:8000',
  game = '11111111-1111-4111-8111-111111111111',
  cohort = '22222222-2222-4222-8222-222222222222';
const command = {
  kind: 'prepare-page',
  cohortId: cohort,
  body: { idempotencyKey: cohort, expectedRevision: 3, cursor: 200 },
};
function storage() {
  const values = new Map();
  return {
    values,
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
}
test('pending body survives a new reader, remains game scoped and cannot be replaced after conflict', () => {
  const s = storage();
  reserveGridCohortCommand(s, api, game, command);
  assert.deepEqual(readGridCohortCommand({ ...s }, api, game), command);
  assert.equal(readGridCohortCommand(s, api, cohort), null);
  assert.throws(() =>
    reserveGridCohortCommand(s, api, game, {
      ...command,
      body: { ...command.body, expectedRevision: 4 },
    }),
  );
  clearGridCohortCommand(s, api, game, game);
  assert.deepEqual(readGridCohortCommand(s, api, game), command);
  clearGridCohortCommand(s, api, game, cohort);
  assert.equal(readGridCohortCommand(s, api, game), null);
});
test('corrupt pending body blocks writes and explicit discard archives before removal', () => {
  const s = storage(),
    key = gridCohortCommandKey(api, game);
  s.setItem(key, '{broken');
  assert.throws(() => readGridCohortCommand(s, api, game));
  assert.throws(() => reserveGridCohortCommand(s, api, game, command));
  discardGridCohortCommand(s, api, game);
  assert.equal(s.getItem(key), null);
  assert.equal([...s.values.values()][0], '{broken');
});
test('a prepare body names exactly one selection form: photos, one import or several imports', () => {
  const other = '33333333-3333-4333-8333-333333333333';
  const prepare = (selector) => ({
    kind: 'prepare',
    body: {
      idempotencyKey: cohort,
      familyId: game,
      baseVersionId: game,
      mode: 'grid-only',
      selector,
      recordings: [{ groupId: other, role: 'TRAIN' }],
    },
  });
  for (const selector of [
    { importJobIds: [game, other] },
    { importJobId: game },
    { sourceIds: [game] },
  ]) {
    const s = storage();
    reserveGridCohortCommand(s, api, game, prepare(selector));
    assert.deepEqual(
      readGridCohortCommand(s, api, game).body.selector,
      selector,
    );
  }
  for (const selector of [
    { importJobIds: [game] },
    { importJobIds: [game, game] },
    { importJobIds: [game, other], importJobId: game },
    { importJobIds: [game, 'not-a-uuid'] },
    {},
  ])
    assert.throws(() =>
      reserveGridCohortCommand(storage(), api, game, prepare(selector)),
    );
});
test('failed local persistence prevents submission and does not overwrite an unresolved command', () => {
  const s = storage();
  s.setItem = () => {
    throw new Error('quota');
  };
  assert.throws(() => reserveGridCohortCommand(s, api, game, command), /quota/);
  assert.equal(s.getItem(gridCohortCommandKey(api, game)), null);
});
