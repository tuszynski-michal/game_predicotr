import assert from 'node:assert/strict';
import test from 'node:test';
import {
  prepareStructuralCrop,
  sampleCanonicalCropImage,
  assertCropPreparationPolicy,
  CROP_V11_RELEASE_ENABLED,
  projectDetectedLayout,
} from '../src/crop-preparation.ts';
test('shared sampler preserves full aspect ratio and is deterministic', () => {
  const source = {
    width: 1080,
    height: 1920,
    rgba: new Uint8ClampedArray(1080 * 1920 * 4),
  };
  const a = sampleCanonicalCropImage(source, 960),
    b = sampleCanonicalCropImage(source, 960);
  assert.equal(a.width, 540);
  assert.equal(a.height, 960);
  assert.deepEqual(a.rgba, b.rgba);
});
test('detected layout can refine label evidence at the next analysis level', () => {
  const layout = {
    status: 'detected',
    reason: 'complete_layout',
    boards: Array.from({ length: 9 }, (_, index) => ({
      left: 20 + (index % 3) * 100,
      top: 30 + Math.floor(index / 3) * 70,
      right: 100 + (index % 3) * 100,
      bottom: 80 + Math.floor(index / 3) * 70,
      support: 1,
      textureTiles: 9,
    })),
    candidateCount: 9,
    analysisWidth: 400,
    analysisHeight: 600,
  };
  const projected = projectDetectedLayout(layout, { width: 800, height: 1200 });
  assert.equal(projected.analysisWidth, 800);
  assert.deepEqual(projected.boards[0], {
    left: 40,
    top: 60,
    right: 200,
    bottom: 160,
    support: 1,
    textureTiles: 9,
  });
});
test('full source on uncertainty; bounded progressive levels and no arbitrary confidence', async () => {
  const source = {
    width: 800,
    height: 1000,
    rgba: new Uint8ClampedArray(800 * 1000 * 4),
  };
  const result = await prepareStructuralCrop(source);
  assert.deepEqual(result.analysisLevels, [960, 1600]);
  assert.equal(result.confidence, null);
  assert.equal(result.crop.topY, 0);
  assert.equal(result.crop.bottomY, 1000);
  assert.ok(result.preparationFingerprint.includes('bilinear-rgba-v1'));
});
test('unknown policy fails closed and experimental release is not activated', () => {
  assert.throws(
    () => assertCropPreparationPolicy('future-v99'),
    /POLICY_UNSUPPORTED/,
  );
  assert.equal(CROP_V11_RELEASE_ENABLED, false);
});
