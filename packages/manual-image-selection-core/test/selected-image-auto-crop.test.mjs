import assert from 'node:assert/strict';
import test from 'node:test';

import {
  detectSelectedImageCropBand,
  SELECTED_IMAGE_AUTO_CROP_POLICY,
} from '../src/auto-crop.ts';

function sample(width, height, paint) {
  const rgba = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const [r, g, b] = paint(x, y);
      const offset = (y * width + x) * 4;
      rgba[offset] = r;
      rgba[offset + 1] = g;
      rgba[offset + 2] = b;
      rgba[offset + 3] = 255;
    }
  }
  return { width, height, rgba };
}

test('finds a wide chromatic board panel and adds bounded padding', () => {
  const input = sample(100, 200, (x, y) =>
    y >= 55 && y <= 135 && x >= 5 && x <= 95
      ? [25 + (x % 20), 65 + (y % 20), 150]
      : [25, 20, 22],
  );
  const result = detectSelectedImageCropBand(input, {
    width: 1000,
    height: 2000,
  });
  assert.equal(result.strategy, 'chromatic_panel');
  assert.equal(result.policyVersion, SELECTED_IMAGE_AUTO_CROP_POLICY);
  assert.ok(result.crop.topY >= 250 && result.crop.topY <= 340);
  assert.ok(result.crop.bottomY >= 1400 && result.crop.bottomY <= 1500);
  assert.ok(result.confidence > 0.6);
});

test('rejects a cluster whose upper padding would start at the image edge', () => {
  const input = sample(100, 200, (x, y) =>
    y <= 90 && x >= 5 && x <= 95 ? [30, 70, 160] : [25, 20, 22],
  );
  const result = detectSelectedImageCropBand(input, {
    width: 1000,
    height: 2000,
  });
  assert.equal(result.strategy, 'safe_default');
  assert.equal(result.confidence, 0);
  assert.deepEqual(result.crop, {
    width: 1000,
    height: 2000,
    topY: 360,
    bottomY: 1720,
  });
});

test('uses a deterministic texture band when there is no blue panel', () => {
  const input = sample(120, 200, (x, y) => {
    if (y < 60 || y > 150) return [20, 20, 20];
    const value = (x + y) % 2 === 0 ? 230 : 35;
    return [value, value, value];
  });
  const result = detectSelectedImageCropBand(input, {
    width: 1200,
    height: 2000,
  });
  assert.equal(result.strategy, 'texture_band');
  assert.ok(result.crop.topY < 600);
  assert.ok(result.crop.bottomY > 1500);
});

test('returns an editable safe default for an unreadable flat image', () => {
  const input = sample(80, 160, () => [35, 35, 35]);
  const result = detectSelectedImageCropBand(input, {
    width: 800,
    height: 1600,
  });
  assert.equal(result.strategy, 'safe_default');
  assert.equal(result.confidence, 0);
  assert.deepEqual(result.crop, {
    width: 800,
    height: 1600,
    topY: 288,
    bottomY: 1376,
  });
});
