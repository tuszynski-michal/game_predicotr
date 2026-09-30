import assert from 'node:assert/strict';
import test from 'node:test';

import {
  BOARD_LINE_COLORS,
  boardLineKey,
  boardLineOffset,
  boardLineStyle,
  boardLineStyles,
  boardLinesConsistency,
  boardLinesPolygonCentroid,
  boardSchemaCellPolygon,
  initialBoardLineVisibility,
  setAllBoardLinesVisibility,
  toggleBoardLineVisibility,
} from '../src/features/board-search/board-search-board-lines-state.ts';

const match = (paylineId, displayOrder, cells, payout, symbolCode = 'A') => ({
  jokerCells: [],
  matchedCells: cells,
  matchedLength: cells.length,
  paylineCode: paylineId,
  paylineDisplayOrder: displayOrder,
  paylineId,
  paylineName: paylineId,
  payoutCredits: payout,
  rowPath: [0, 0, 0, 0, 0],
  symbolCode,
});

const detail = (matches, overrides = {}) => ({
  boardChecksumSha256: 'c'.repeat(64),
  boardStatus: 'accepted',
  dataSource: 'operational_review',
  gameId: 'g',
  matches,
  payoutCredits: matches.reduce((sum, item) => sum + item.payoutCredits, 0),
  payoutKind: 'exact',
  rules: {
    algorithmVersion: 'payout-v3-unknown-prefix-stop',
    rulesVersion: 1,
    rulesVersionId: 'rules-1',
    spinCost: 100,
  },
  sequenceNumber: 7,
  symbolCodes: Array.from({ length: 15 }, () => 'A'),
  view: null,
  ...overrides,
});

test('centroid of a rectangle and of a trapezoid', () => {
  assert.deepEqual(
    boardLinesPolygonCentroid([
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 20 },
      { x: 0, y: 20 },
    ]),
    { x: 5, y: 10 },
  );
  assert.deepEqual(
    boardLinesPolygonCentroid([
      { x: 2, y: 0 },
      { x: 8, y: 0 },
      { x: 10, y: 4 },
      { x: 0, y: 4 },
    ]),
    { x: 5, y: 2 },
  );
  assert.deepEqual(boardLinesPolygonCentroid([]), { x: 0, y: 0 });
});

test('a payline keeps its colour on every board, whatever else won', () => {
  const top = match('top', 3, [0, 1, 2], 10);
  const middle = match('middle', 1, [5, 6, 7], 10);
  const both = boardLineStyles([top, middle]);
  const alone = boardLineStyles([top]);
  assert.equal(both.get(boardLineKey(top)).color, BOARD_LINE_COLORS[3]);
  assert.equal(alone.get(boardLineKey(top)).color, BOARD_LINE_COLORS[3]);
  assert.equal(both.get(boardLineKey(middle)).color, BOARD_LINE_COLORS[1]);
  assert.equal(boardLineStyle(0).dashArray, undefined);
  assert.equal(
    boardLineStyle(BOARD_LINE_COLORS.length).color,
    BOARD_LINE_COLORS[0],
  );
  assert.notEqual(
    boardLineStyle(BOARD_LINE_COLORS.length).dashArray,
    undefined,
  );
});

test('toggling one line leaves the others untouched; show/hide all', () => {
  const lines = [
    match('top', 0, [0, 1, 2], 10),
    match('middle', 1, [5, 6, 7], 10),
  ];
  const all = initialBoardLineVisibility(lines);
  assert.equal(all.size, 2);
  const oneHidden = toggleBoardLineVisibility(all, boardLineKey(lines[0]));
  assert.equal(oneHidden.has(boardLineKey(lines[0])), false);
  assert.equal(oneHidden.has(boardLineKey(lines[1])), true);
  assert.equal(all.size, 2, 'the previous state is not mutated');
  assert.equal(setAllBoardLinesVisibility(lines, false).size, 0);
  assert.equal(setAllBoardLinesVisibility(lines, true).size, 2);
});

test('lines are drawn only when they explain the table row exactly', () => {
  const lines = [
    match('top', 0, [0, 1, 2], 10),
    match('middle', 1, [5, 6, 7], 25),
  ];
  assert.deepEqual(boardLinesConsistency(detail(lines), 35, 'rules-1'), {
    kind: 'consistent',
  });
  assert.deepEqual(boardLinesConsistency(detail(lines), 40, 'rules-1'), {
    kind: 'inconsistent',
    reason: 'payout',
  });
  assert.deepEqual(boardLinesConsistency(detail(lines), 35, 'rules-2'), {
    kind: 'inconsistent',
    reason: 'rules',
  });
  assert.deepEqual(
    boardLinesConsistency(detail(lines, { payoutCredits: 36 }), 36, 'rules-1'),
    { kind: 'inconsistent', reason: 'lines' },
  );
});

test('line offsets are centred and bounded', () => {
  assert.equal(boardLineOffset(0, 1), 0);
  assert.equal(boardLineOffset(0, 3) + boardLineOffset(2, 3), 0);
  assert.ok(Math.abs(boardLineOffset(0, 20)) <= 0.12);
});

test('schema cells are row-major 100-unit squares', () => {
  assert.deepEqual(boardSchemaCellPolygon(7)[0], { x: 200, y: 100 });
  assert.deepEqual(boardSchemaCellPolygon(14)[2], { x: 500, y: 300 });
});
