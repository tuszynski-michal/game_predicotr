import assert from 'node:assert/strict';
import test from 'node:test';

import {
  detectSelectedImageCropBand,
  SELECTED_IMAGE_AUTO_CROP_POLICY,
  SELECTED_IMAGE_AUTO_CROP_SAMPLE_WIDTH,
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

function boardPixel(x, y, variant = 'blue') {
  const bright = (x + y) % 8 < 4;
  if (variant === 'green') return bright ? [35, 185, 70] : [12, 65, 35];
  return bright ? [35, 95, 205] : [18, 45, 105];
}

test('uses a 512 px analysis budget and versions the multicolumn policy', () => {
  assert.equal(SELECTED_IMAGE_AUTO_CROP_SAMPLE_WIDTH, 512);
  assert.equal(
    SELECTED_IMAGE_AUTO_CROP_POLICY,
    'selected-image-board-band-v4-conservative-multicolumn',
  );
});

test('finds a tilted panel with independent support across the full width', () => {
  const input = sample(180, 240, (x, y) => {
    const top = 72 + Math.round((x / 180) * 8);
    const bottom = 178 + Math.round((x / 180) * 8);
    return y >= top && y <= bottom ? boardPixel(x, y) : [22, 18, 20];
  });
  const result = detectSelectedImageCropBand(input, {
    width: 1440,
    height: 1920,
  });
  assert.equal(result.strategy, 'multicolumn_panel');
  assert.equal(result.classification, 'high_confidence');
  assert.ok(result.crop.topY <= 420);
  assert.ok(result.crop.bottomY >= 1450);
  assert.ok(result.confidence >= 0.8);
});

test('does not let a local paytable or side light move the full crop', () => {
  const input = sample(180, 240, (x, y) => {
    if (x < 45 && y >= 18 && y <= 62) return boardPixel(x, y, 'green');
    if ((x < 12 || x > 168) && y >= 5 && y <= 230) return [15, 45, 190];
    return y >= 85 && y <= 184 ? boardPixel(x, y) : [20, 18, 20];
  });
  const result = detectSelectedImageCropBand(input, {
    width: 1440,
    height: 1920,
  });
  assert.equal(result.strategy, 'multicolumn_panel');
  assert.ok(result.crop.topY >= 350);
  assert.ok(result.crop.bottomY >= 1450);
});

test('requires evidence in left, center and right groups', () => {
  const input = sample(180, 240, (x, y) =>
    x >= 80 && x <= 170 && y >= 75 && y <= 180
      ? boardPixel(x, y)
      : [24, 22, 23],
  );
  const result = detectSelectedImageCropBand(input, {
    width: 1440,
    height: 1920,
  });
  assert.equal(result.strategy, 'safe_wide');
  assert.equal(result.classification, 'safe_wide');
  assert.deepEqual(result.crop, {
    width: 1440,
    height: 1920,
    topY: 96,
    bottomY: 1824,
  });
});

test('uses a conservative union when chromatic and structural bands disagree', () => {
  const input = sample(180, 240, (x, y) => {
    if (y >= 48 && y <= 112) return [20, 105, 175];
    if (y >= 102 && y <= 184) {
      const value = (x + y) % 2 === 0 ? 225 : 35;
      return [value, value, value];
    }
    return [20, 20, 20];
  });
  const result = detectSelectedImageCropBand(input, {
    width: 1440,
    height: 1920,
  });
  assert.equal(result.strategy, 'multicolumn_panel');
  assert.equal(result.classification, 'conservative');
  assert.ok(result.crop.topY <= 250);
  assert.ok(result.crop.bottomY >= 1480);
});

test('keeps detecting a panel obscured by a hand-sized vertical region', () => {
  const input = sample(180, 240, (x, y) => {
    if (x >= 72 && x <= 100 && y >= 60 && y <= 205) return [32, 25, 22];
    if (y >= 70 && y <= 185) return boardPixel(x, y, 'green');
    return [20, 18, 20];
  });
  const result = detectSelectedImageCropBand(input, {
    width: 1440,
    height: 1920,
  });
  assert.equal(result.strategy, 'multicolumn_panel');
  assert.ok(result.crop.topY <= 400);
  assert.ok(result.crop.bottomY >= 1480);
});

test('keeps black bars and a local glare outside the crop decision', () => {
  const input = sample(180, 240, (x, y) => {
    if (y < 22 || y > 220) return [0, 0, 0];
    if (x >= 78 && x <= 98 && y >= 48 && y <= 205) return [235, 235, 225];
    if (y >= 78 && y <= 184) return boardPixel(x, y);
    return [22, 19, 21];
  });
  const result = detectSelectedImageCropBand(input, {
    width: 1440,
    height: 1920,
  });
  assert.equal(result.strategy, 'multicolumn_panel');
  assert.ok(result.crop.topY >= 250);
  assert.ok(result.crop.bottomY <= 1700);
});

test('expands a boundary outward when broad content remains in its safety strip', () => {
  const input = sample(180, 240, (x, y) => {
    if (y >= 47 && y <= 58) return boardPixel(x, y, 'green');
    if (y >= 82 && y <= 184) return boardPixel(x, y);
    return [20, 18, 20];
  });
  const result = detectSelectedImageCropBand(input, {
    width: 1440,
    height: 1920,
  });
  assert.equal(result.strategy, 'multicolumn_panel');
  assert.ok(result.crop.topY <= 400);
});

test('returns safe wide for a flat, blurred or otherwise unsupported image', () => {
  const input = sample(160, 240, () => [35, 35, 35]);
  const result = detectSelectedImageCropBand(input, {
    width: 1440,
    height: 1920,
  });
  assert.equal(result.strategy, 'safe_wide');
  assert.equal(result.classification, 'safe_wide');
  assert.equal(result.confidence, 0);
  assert.deepEqual(result.crop, {
    width: 1440,
    height: 1920,
    topY: 96,
    bottomY: 1824,
  });
});

test('does not auto-save a very shallow candidate', () => {
  const input = sample(180, 240, (x, y) =>
    y >= 115 && y <= 138 ? boardPixel(x, y) : [20, 20, 20],
  );
  const result = detectSelectedImageCropBand(input, {
    width: 1440,
    height: 1920,
  });
  assert.equal(result.classification, 'safe_wide');
});
