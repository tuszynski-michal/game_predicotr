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
