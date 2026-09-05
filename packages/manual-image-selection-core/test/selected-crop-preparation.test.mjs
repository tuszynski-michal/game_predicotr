import assert from 'node:assert/strict';
import test from 'node:test';
import {
  prepareStructuralCrop,
  sampleCanonicalCropImage,
  assertCropPreparationPolicy,
  CROP_V11_RELEASE_ENABLED,
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
