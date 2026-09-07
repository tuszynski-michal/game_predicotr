import assert from 'node:assert/strict';
import test from 'node:test';

import {
  guardGridLines,
  guardQuadFromUnknown,
  initialGuardQuad,
  toggleUnavailableCell,
  toggleUnavailableGroup,
} from '../src/features/imports/geometry-guard-resolution-state.ts';

const quad = [
  { x: 10, y: 20 },
  { x: 110, y: 20 },
  { x: 110, y: 80 },
  { x: 10, y: 80 },
];

test('starts from the proposed symbol grid before broader board geometry', () => {
  const target = {
    analysisQuad: quad.map((point) => ({ x: point.x + 50, y: point.y })),
    pageGeometry: {
      quad: quad.map((point) => ({ x: point.x + 100, y: point.y })),
    },
    proposedSymbolGridQuad: quad,
  };

  assert.deepEqual(initialGuardQuad(target), quad);
  assert.deepEqual(guardQuadFromUnknown({ quad }), quad);
});

test('starts an editable ready board from its final symbol grid', () => {
  const board = {
    analysisQuad: quad.map((point) => ({ x: point.x + 50, y: point.y })),
    pageGeometry: {
      quad: quad.map((point) => ({ x: point.x + 100, y: point.y })),
    },
    symbolGridQuad: quad,
  };

  assert.deepEqual(initialGuardQuad(board), quad);
});

test('builds four columns and three rows in the editable perspective quad', () => {
  const lines = guardGridLines(quad);

  assert.equal(lines.length, 6);
  assert.deepEqual(lines[0], [
    { x: 30, y: 20 },
    { x: 30, y: 80 },
  ]);
  assert.deepEqual(lines[5], [
    { x: 10, y: 60 },
    { x: 110, y: 60 },
  ]);
});

test('toggles individual, row and column source-unavailable masks deterministically', () => {
  assert.deepEqual(toggleUnavailableCell([], 7), [7]);
  assert.deepEqual(toggleUnavailableCell([7], 7), []);
  assert.deepEqual(
    toggleUnavailableGroup([], [5, 6, 7, 8, 9]),
    [5, 6, 7, 8, 9],
  );
  assert.deepEqual(toggleUnavailableGroup([0, 5, 10], [0, 5, 10]), []);
});

test('qualified grids follow projective cell boundaries without changing legacy interpolation', () => {
  const perspective = [
    { x: 0, y: 0 },
    { x: 300, y: 0 },
    { x: 200, y: 200 },
    { x: 100, y: 200 },
  ];
  const legacy = guardGridLines(perspective);
  const projective = guardGridLines(perspective, true);
  assert.equal(projective.length, 6);
  assert.ok(Math.abs(legacy[4][0].y - 200 / 3) < 1e-8);
  assert.ok(Math.abs(projective[4][0].y - 120) < 1e-8);
});
