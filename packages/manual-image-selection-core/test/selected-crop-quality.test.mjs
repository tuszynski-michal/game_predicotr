import assert from 'node:assert/strict';
import test from 'node:test';
import { cropQualityReferences } from './fixtures/selected-crop-quality.mjs';
import {
  evaluateCrop,
  validateReferences,
} from './crop-quality-evaluation.mjs';
import { v10Baseline } from './fixtures/selected-crop-v10-baseline.mjs';

test('measured v10 snapshots reproduce all three reported failure classes', () => {
  for (const [id, expected] of [
    ['79903', 'excess_bottom'],
    ['80074', 'content_removed'],
    ['80299', 'excess_top'],
  ]) {
    const ref = cropQualityReferences.find((item) => item.id === id);
    const [topY, bottomY] = v10Baseline[id];
    assert.ok(
      evaluateCrop(ref, {
        width: ref.width,
        height: ref.height,
        topY,
        bottomY,
      }).includes(expected),
    );
  }
});

test('real-source annotations are bounded, checksum-bound and directory-disjoint', () => {
  validateReferences(cropQualityReferences);
});
test('same source or directory cannot leak into the acceptance split', () => {
  const first = cropQualityReferences[0];
  assert.throws(
    () => validateReferences([...cropQualityReferences, first]),
    /CORPUS_HASH/,
  );
  assert.throws(
    () =>
      validateReferences([
        ...cropQualityReferences,
        { ...first, sha256: 'a'.repeat(64), split: 'holdout' },
      ]),
    /CORPUS_LEAKAGE/,
  );
});
test('oracle detects actual paytable-only crop, not a successful JPEG write', () => {
  const ref = cropQualityReferences.find((item) => item.id === '80074');
  const issues = evaluateCrop(ref, {
    width: 1080,
    height: 1920,
    topY: 0,
    bottomY: 538,
  });
  assert.ok(issues.includes('content_removed'));
  assert.ok(issues.includes('bottom_too_tight'));
});
test('oracle rejects retained cabinet and retained paytable independently', () => {
  const ref = cropQualityReferences[0];
  assert.deepEqual(
    evaluateCrop(ref, { width: 1080, height: 1920, topY: 515, bottomY: 1800 }),
    ['excess_bottom'],
  );
  assert.deepEqual(
    evaluateCrop(ref, { width: 1080, height: 1920, topY: 0, bottomY: 1000 }),
    ['excess_top'],
  );
});
test('full source is safe content-wise but is not counted as a good automatic crop', () => {
  const ref = cropQualityReferences[0];
  assert.deepEqual(
    evaluateCrop(ref, { width: 1080, height: 1920, topY: 0, bottomY: 1920 }),
    ['excess_top', 'excess_bottom'],
  );
});
test('both annotation interval endpoints retain all nine boards and numbers', () => {
  for (const ref of cropQualityReferences) {
    for (const topY of ref.topInterval)
      for (const bottomY of ref.bottomInterval) {
        assert.deepEqual(
          evaluateCrop(ref, {
            width: ref.width,
            height: ref.height,
            topY,
            bottomY,
          }),
          [],
        );
      }
  }
});
