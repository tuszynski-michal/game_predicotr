import assert from 'node:assert/strict';
import test from 'node:test';
import {
  contentCommandKey,
  emptyContentCells,
  manualContentLattice,
  readContentCommand,
  saveContentCommand,
  clearContentCommand,
  validContentCells,
  validContentNodes,
} from '../src/features/model-quality/grid-content-state.ts';

const game = '11111111-1111-4111-8111-111111111111';
const session = '22222222-2222-4222-8222-222222222222';
const source = '33333333-3333-4333-8333-333333333333';
const id = '44444444-4444-4444-8444-444444444444';
function storage() {
  const data = new Map();
  return {
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => data.set(k, v),
    removeItem: (k) => data.delete(k),
  };
}
const nodes = manualContentLattice([
  [0, 0],
  [100, 0],
  [100, 60],
  [0, 60],
]);
const command = {
  kind: 'observe',
  sessionId: session,
  body: {
    idempotencyKey: id,
    expectedSessionRevision: 1,
    sourceId: source,
    positionIndex: 0,
    passNumber: 1,
    cells: emptyContentCells(),
    measuredNodes: nodes,
    humanApproval: true,
  },
};

test('manual lattice is seeded only from four new corners, keeps float precision and independent content', () => {
  assert.equal(nodes.length, 24);
  assert.deepEqual(nodes[23], [100, 60]);
  const cells = emptyContentCells();
  cells[0] = {
    state: 'visible',
    quad: [
      [1.125, 1],
      [9, 1],
      [9, 8],
      [1, 8],
    ],
  };
  assert.equal(validContentCells(cells), true);
  const moved = structuredClone(nodes);
  moved[0] = [3.25, 3];
  assert.equal(validContentNodes(moved), true);
  assert.equal(cells[0].quad[0][0], 1.125);
  assert.throws(() =>
    manualContentLattice([
      [0, 0],
      [1, 1],
      [0, 1],
      [1, 0],
    ]),
  );
  cells[0] = { state: 'visible' };
  assert.equal(validContentCells(cells), false);
  cells[0] = { state: 'unknown' };
  assert.equal(validContentCells(cells), true);
});

test('exact pending command survives a fresh storage reader, cannot change modes or game, and clears only its own receipt', () => {
  const saved = storage(),
    key = contentCommandKey('api', game, 'blind');
  saveContentCommand(saved, key, game, 'blind', command);
  assert.deepEqual(readContentCommand(saved, key, game, 'blind'), command);
  assert.throws(() => readContentCommand(saved, key, source, 'blind'));
  assert.throws(() => readContentCommand(saved, key, game, 'ordinary'));
  assert.throws(() =>
    saveContentCommand(saved, key, game, 'blind', {
      ...command,
      body: { ...command.body, passNumber: 2 },
    }),
  );
  clearContentCommand(saved, key, source);
  assert.deepEqual(readContentCommand(saved, key, game, 'blind'), command);
  clearContentCommand(saved, key, id);
  assert.equal(readContentCommand(saved, key, game, 'blind'), null);
  assert.notEqual(key, contentCommandKey('api', game, 'ordinary'));
  assert.notEqual(key, contentCommandKey('other-api', game, 'blind'));
});

test('corrupt or cross-protocol payload cannot be replayed as a blind measurement', () => {
  const saved = storage(),
    key = contentCommandKey('api', game, 'blind');
  for (const body of [
    { ...command.body, humanApproval: 'true' },
    { ...command.body, measuredNodes: [[0, 0]] },
    { ...command.body, cells: [] },
  ]) {
    saved.setItem(
      key,
      JSON.stringify({
        version: 1,
        gameId: game,
        mode: 'blind',
        command: { ...command, body },
      }),
    );
    assert.throws(() => readContentCommand(saved, key, game, 'blind'));
  }
});
