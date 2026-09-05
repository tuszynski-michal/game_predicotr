import assert from 'node:assert/strict';
import test from 'node:test';
import {
  selectStructuralLayout,
  detectStructuralLayout,
  luminance,
} from '../src/auto-crop-v11.ts';

test('small cabinet buttons cannot substitute the missing third row', () => {
  const input = boards();
  for (const box of input.slice(6)) {
    box.right = box.left + 50;
    box.bottom = box.top + 30;
  }
  assert.equal(
    selectStructuralLayout(input, 600, 960).status,
    'needs_manual_crop',
  );
});
function boards(dx = 0, dy = 0) {
  return Array.from({ length: 9 }, (_, i) => ({
    left: 40 + (i % 3) * 120 + dx,
    top: 80 + Math.floor(i / 3) * 90 + (i % 3) * 8 + dy,
    right: 140 + (i % 3) * 120 + dx,
    bottom: 140 + Math.floor(i / 3) * 90 + (i % 3) * 8 + dy,
    textureTiles: 9,
    support: 2,
  }));
}
test('independent sloping boards form a full layout; no missing row is invented', () => {
  assert.equal(selectStructuralLayout(boards(), 600, 960).status, 'detected');
  assert.equal(
    selectStructuralLayout(boards().slice(0, 8), 600, 960).status,
    'needs_manual_crop',
  );
  assert.equal(
    selectStructuralLayout(boards().slice(0, 3), 600, 960).status,
    'needs_manual_crop',
  );
});
test('two complete layouts are ambiguous, not the first or brightest winner', () => {
  assert.equal(
    selectStructuralLayout([...boards(), ...boards(0, 430)], 600, 960).reason,
    'ambiguous_layout',
  );
});
test('blank grayscale image produces manual review', () => {
  assert.equal(
    detectStructuralLayout({
      width: 100,
      height: 100,
      rgba: new Uint8ClampedArray(40000),
    }).status,
    'needs_manual_crop',
  );
});
test('luminance, not red/blue membership, drives detection input', () => {
  const rgba = new Uint8ClampedArray(8 * 8 * 4).fill(0);
  rgba.set([100, 100, 100, 255]);
  assert.equal(luminance({ width: 8, height: 8, rgba })[0], 100);
  assert.throws(
    () => detectStructuralLayout({ width: 2000, height: 8, rgba }),
    /SAMPLE_INVALID/,
  );
});
