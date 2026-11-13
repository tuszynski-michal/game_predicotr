import assert from 'node:assert/strict';
import test from 'node:test';
import {
  outlineApprovalCommand,
  outlineSelectable,
  outlineViewBox,
  selectPage,
  symbolOutlinesWindowUrl,
  toggleSelection,
} from '../src/features/model-quality/symbol-outline-state.ts';

const quad = (x, y) => [
  [x, y],
  [x + 10, y],
  [x + 10, y + 8],
  [x, y + 8],
];
function proposal(overrides = {}) {
  return {
    boardId: 'board-1',
    source: {
      sourceId: 'source-1',
      sourceSha256: 'a'.repeat(64),
      sourceRepresentativeSha256: 'b'.repeat(64),
      width: 200,
      height: 100,
    },
    positionIndex: 2,
    sequenceNumber: 41,
    contentRevision: 3,
    contentApproved: false,
    cells: Array.from({ length: 15 }, (_, i) => ({
      state: 'visible',
      quad: quad(20 + (i % 5) * 10, 10 + Math.floor(i / 5) * 8),
    })),
    ...overrides,
  };
}

test('view box frames all outlines with a margin and stays inside the photo', () => {
  assert.deepEqual(outlineViewBox(proposal(), 0), [20, 10, 50, 24]);
  outlineViewBox(proposal(), 0.1).forEach((value, index) =>
    assert.ok(Math.abs(value - [15, 7.6, 60, 28.8][index]) < 1e-9),
  );
  assert.deepEqual(outlineViewBox(proposal(), 5), [0, 0, 200, 100]);
  assert.deepEqual(
    outlineViewBox(proposal({ cells: null }), 0.1),
    [0, 0, 200, 100],
  );
});

test('approval sends the ordinary approved content write with the shown cells', () => {
  const item = proposal();
  const command = outlineApprovalCommand(item, 'key-1');
  assert.deepEqual(command, {
    idempotencyKey: 'key-1',
    sourceId: 'source-1',
    expectedSourceSha256: 'a'.repeat(64),
    expectedPixelSha256: 'b'.repeat(64),
    positionIndex: 2,
    sequenceNumber: 41,
    expectedRevision: 3,
    cells: item.cells,
    origin: 'manual',
    humanApproval: true,
  });
});

test('approved boards and unusable grids cannot be selected or approved', () => {
  for (const item of [
    proposal({ contentApproved: true }),
    proposal({ cells: null }),
  ]) {
    assert.equal(outlineSelectable(item), false);
    assert.throws(() => outlineApprovalCommand(item, 'key'));
    assert.equal(toggleSelection(new Map(), item).size, 0);
  }
});

test('tile clicks toggle and page selection keeps boards from other pages', () => {
  const first = proposal();
  const other = proposal({ boardId: 'board-2' });
  const approved = proposal({ boardId: 'board-3', contentApproved: true });
  let selected = toggleSelection(new Map(), first);
  assert.deepEqual([...selected.keys()], ['board-1']);
  selected = toggleSelection(selected, first);
  assert.equal(selected.size, 0);
  selected = selectPage(
    new Map([['board-9', proposal({ boardId: 'board-9' })]]),
    [first, other, approved],
  );
  assert.deepEqual([...selected.keys()].sort(), [
    'board-1',
    'board-2',
    'board-9',
  ]);
});

test('window URL keeps the admin origin and carries only the game', () => {
  assert.equal(
    symbolOutlinesWindowUrl('http://127.0.0.1:3000/?tab=quality#x', 'game-1'),
    'http://127.0.0.1:3000/symbol-outlines?gameId=game-1',
  );
});
