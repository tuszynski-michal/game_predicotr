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

test('uses a 512 px analysis budget and versions the tight top boundary', () => {
  assert.equal(SELECTED_IMAGE_AUTO_CROP_SAMPLE_WIDTH, 512);
  assert.equal(
    SELECTED_IMAGE_AUTO_CROP_POLICY,
    'selected-image-board-band-v8-tight-top-boundary',
  );
});

test('prefers the blue board panel over a full-width paytable above it', () => {
  const input = sample(180, 240, (x, y) => {
    if (y >= 20 && y <= 72) {
      const bright = (x + y) % 8 < 4;
      return bright ? [205, 70, 25] : [90, 18, 18];
    }
    if (y >= 92 && y <= 176) return boardPixel(x, y);
    return [18, 16, 19];
  });
  const result = detectSelectedImageCropBand(input, {
    width: 1440,
    height: 1920,
  });
  assert.equal(result.strategy, 'blue_panel');
  assert.equal(result.classification, 'high_confidence');
  assert.equal(result.evidence.selectionBasis, 'blue_panel');
  assert.ok(result.crop.topY >= 650);
  assert.ok(result.crop.topY <= 710);
  assert.ok(result.crop.bottomY >= 1400);
  assert.ok(result.crop.bottomY <= 1560);
});

test('uses strong three-zone blue evidence when generic evidence is weak', () => {
  const input = sample(180, 240, (x, y) => {
    if (y < 88 || y > 184) return [24, 20, 22];
    const boardColumn = Math.floor(x / 60);
    const boardGap = x % 60 >= 48;
    const rowGap = (y - 88) % 32 >= 25;
    if (boardGap || rowGap) return [14, 35, 92];
    return boardColumn % 2 === 0 ? [20, 58, 145] : [30, 72, 175];
  });
  const result = detectSelectedImageCropBand(input, {
    width: 1440,
    height: 1920,
  });
  assert.equal(result.strategy, 'blue_panel');
  assert.equal(result.evidence.selectionBasis, 'blue_panel');
  assert.ok(result.evidence.chromaticSupportedStrips.length >= 5);
  assert.ok(result.crop.topY >= 500);
  assert.ok(result.crop.bottomY <= 1700);
});

test('tracks a tilted blue panel independently in left center and right strips', () => {
  const input = sample(180, 240, (x, y) => {
    const top = 78 + Math.round((x / 180) * 14);
    const bottom = 180 + Math.round((x / 180) * 14);
    if (y >= 18 && y <= 68) return [180, 42, 24];
    return y >= top && y <= bottom ? boardPixel(x, y) : [20, 18, 20];
  });
  const result = detectSelectedImageCropBand(input, {
    width: 1440,
    height: 1920,
  });
  assert.equal(result.strategy, 'blue_panel');
  assert.ok(result.crop.topY >= 450);
  assert.ok(result.crop.topY <= 600);
  assert.ok(result.crop.bottomY >= 1500);
  assert.ok(result.crop.bottomY <= 1800);
});

test('does not mistake narrow blue cabinet lights for a board panel', () => {
  const input = sample(180, 240, (x, y) =>
    (x < 12 || x > 168) && y >= 15 && y <= 220 ? [15, 45, 190] : [24, 22, 23],
  );
  const result = detectSelectedImageCropBand(input, {
    width: 1440,
    height: 1920,
  });
  assert.equal(result.strategy, 'safe_wide');
});

test('prefers the dedicated detector for a tilted blue panel', () => {
  const input = sample(180, 240, (x, y) => {
    const top = 72 + Math.round((x / 180) * 8);
    const bottom = 178 + Math.round((x / 180) * 8);
    return y >= top && y <= bottom ? boardPixel(x, y) : [22, 18, 20];
  });
  const result = detectSelectedImageCropBand(input, {
    width: 1440,
    height: 1920,
  });
  assert.equal(result.strategy, 'blue_panel');
  assert.equal(result.classification, 'high_confidence');
  assert.ok(result.crop.topY >= 500);
  assert.ok(result.crop.topY <= 560);
  assert.ok(result.crop.bottomY >= 1450);
  assert.ok(result.confidence >= 0.8);
  assert.equal(result.evidence.fallbackReason, null);
  assert.equal(result.evidence.sampleWidth, 180);
  assert.ok(result.evidence.localBounds.length >= 5);
  assert.ok(result.evidence.chromaticSupportedStrips.length >= 5);
  assert.deepEqual(result.evidence.structuralSupportedStrips, []);
});

test('does not let a local paytable or side light move a blue panel crop', () => {
  const input = sample(180, 240, (x, y) => {
    if (x < 45 && y >= 18 && y <= 62) return boardPixel(x, y, 'green');
    if ((x < 12 || x > 168) && y >= 5 && y <= 230) return [15, 45, 190];
    return y >= 85 && y <= 184 ? boardPixel(x, y) : [20, 18, 20];
  });
  const result = detectSelectedImageCropBand(input, {
    width: 1440,
    height: 1920,
  });
  assert.equal(result.strategy, 'blue_panel');
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
    if (y >= 48 && y <= 112) return [20, 175, 80];
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
  assert.ok(result.crop.topY >= 250);
  assert.ok(result.crop.topY <= 400);
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
  assert.ok(result.crop.topY >= 500);
  assert.ok(result.crop.topY <= 560);
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
  assert.equal(result.strategy, 'blue_panel');
  assert.ok(result.crop.topY >= 250);
  assert.ok(result.crop.bottomY <= 1700);
});

test('keeps the top tight while expanding a supported bottom boundary', () => {
  const input = sample(180, 240, (x, y) => {
    if (y >= 60 && y <= 70) return boardPixel(x, y, 'green');
    if (y >= 82 && y <= 184) return boardPixel(x, y, 'green');
    return [20, 18, 20];
  });
  const result = detectSelectedImageCropBand(input, {
    width: 1440,
    height: 1920,
  });
  assert.equal(result.strategy, 'multicolumn_panel');
  assert.ok(result.crop.topY >= 500);
  assert.equal(result.evidence.boundaryExpanded, true);
});

test('does not recursively expand from the board panel through a paytable', () => {
  const input = sample(180, 240, (x, y) => {
    if (y >= 8 && y <= 75) return boardPixel(x, y, 'green');
    if (y >= 88 && y <= 180) return boardPixel(x, y, 'green');
    return [20, 18, 20];
  });
  const result = detectSelectedImageCropBand(input, {
    width: 1440,
    height: 1920,
  });
  assert.equal(result.strategy, 'multicolumn_panel');
  assert.equal(result.evidence.boundaryExpanded, true);
  assert.ok(result.crop.topY >= 450);
  assert.ok(result.crop.bottomY <= 1650);
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
  assert.equal(result.evidence.fallbackReason, 'no_wide_evidence');
  assert.deepEqual(result.evidence.localBounds, []);
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
