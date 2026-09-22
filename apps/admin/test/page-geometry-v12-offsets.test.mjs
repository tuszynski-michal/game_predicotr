import assert from 'node:assert/strict';
import test from 'node:test';

import {
  v12FrameFromGrid,
  v12OffsetsFromPair,
  v12PreviewFrameFromDraft,
  v12PreviewFrameFromGrid,
} from '../src/features/imports/page-geometry-v12-offsets.ts';

test('asymmetric margins follow the perspective of one symbol grid', () => {
  const grid = [
    { x: 20, y: 20 },
    { x: 120, y: 25 },
    { x: 115, y: 75 },
    { x: 15, y: 70 },
  ];
  const offsets = { top: 10, bottom: 0, left: 5, right: 20 };
  const frame = v12FrameFromGrid(grid, offsets);
  assert.ok(frame);
  const restored = v12OffsetsFromPair(grid, frame);
  assert.ok(restored);
  for (const side of ['top', 'bottom', 'left', 'right'])
    assert.ok(Math.abs(restored[side] - offsets[side]) < 1e-7);
});

test('negative margin is previewable but cannot become a saved frame', () => {
  const grid = [
    { x: 20, y: 20 },
    { x: 120, y: 20 },
    { x: 120, y: 70 },
    { x: 20, y: 70 },
  ];
  const offsets = { top: -5, bottom: 2, left: 2, right: 2 };
  assert.ok(v12PreviewFrameFromGrid(grid, offsets));
  assert.equal(v12FrameFromGrid(grid, offsets), null);
});

test('partial margin draft previews the entered side before save is ready', () => {
  const grid = [
    { x: 20, y: 20 },
    { x: 120, y: 20 },
    { x: 120, y: 70 },
    { x: 20, y: 70 },
  ];
  const frame = v12PreviewFrameFromDraft(grid, { top: 10 });
  assert.ok(frame);
  assert.ok(frame[0].y < grid[0].y);
  assert.equal(frame[3].x, grid[3].x);
  assert.equal(v12PreviewFrameFromDraft(grid, {}), null);
});
