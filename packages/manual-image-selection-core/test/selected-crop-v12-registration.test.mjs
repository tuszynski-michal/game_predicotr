import assert from 'node:assert/strict';
import test from 'node:test';

import {
  CROP_V12_FINGERPRINT,
  CROP_V12_LEGACY_FINGERPRINT,
  CROP_V12_POLICY,
  cropFromRegisteredBoardBand,
  isCompatibleCropV12Fingerprint,
  prepareFourPointRegistrationAnchor,
  registerFourPointBoardBand,
  validateFourPointRegistrationEvidence,
} from '../src/auto-crop-v12-registration.ts';

const SHA = 'a'.repeat(64);

function textured(width, height, dx = 0, dy = 0) {
  const rgba = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y += 1)
    for (let x = 0; x < width; x += 1) {
      const sourceX = x - dx;
      const sourceY = y - dy;
      const inBand =
        sourceX >= 50 && sourceX <= 270 && sourceY >= 42 && sourceY <= 194;
      const value = inBand
        ? ((Math.imul(sourceX + 17, 73856093) ^
            Math.imul(sourceY + 29, 19349663) ^
            Math.imul((sourceX >> 3) + (sourceY >> 3), 83492791)) >>>
            0) %
          256
        : 18;
      const offset = (y * width + x) * 4;
      rgba[offset] = value;
      rgba[offset + 1] = value;
      rgba[offset + 2] = value;
      rgba[offset + 3] = 255;
    }
  return { width, height, rgba };
}

const anchor = {
  sourceName: 'seq_1-9.jpg',
  sourceChecksumSha256: SHA,
  sourceWidth: 320,
  sourceHeight: 240,
  boardBand: [
    { x: 50, y: 42 },
    { x: 270, y: 42 },
    { x: 50, y: 194 },
    { x: 270, y: 194 },
  ],
  medianBoardHeight: 42,
};

test('registers a four-point board band without requiring 36 board corners', () => {
  const evidence = registerFourPointBoardBand({
    anchor,
    anchorImage: textured(320, 240),
    targetImage: textured(320, 240, 8, 6),
  });
  assert.equal(evidence.status, 'registered', JSON.stringify(evidence));
  assert.equal(evidence.reason, 'registered_from_four_point_anchor');
  assert.ok(evidence.inlierCount >= 9);
  assert.ok(evidence.p90ResidualPx <= 3.5);
  assert.ok(Math.abs(evidence.registeredBoardBand[0].x - 58) <= 2);
  assert.ok(Math.abs(evidence.registeredBoardBand[0].y - 48) <= 2);
  validateFourPointRegistrationEvidence(evidence);
  const crop = cropFromRegisteredBoardBand({
    evidence,
    sourceWidth: 320,
    sourceHeight: 240,
    anchorMedianBoardHeight: 42,
  });
  assert.ok(crop.topY < 48);
  assert.ok(crop.bottomY > 200);
});

test('prepared anchor features preserve the exact registration result', () => {
  const anchorImage = textured(320, 240);
  const targetImage = textured(320, 240, 8, 6);
  const direct = registerFourPointBoardBand({
    anchor,
    anchorImage,
    targetImage,
  });
  const prepared = registerFourPointBoardBand({
    anchor,
    preparedAnchor: prepareFourPointRegistrationAnchor({
      anchor,
      anchorImage,
    }),
    targetImage,
  });
  assert.deepEqual(prepared, direct);
});

test('rejects an unrelated image instead of transferring a crop', () => {
  const target = textured(320, 240);
  target.rgba.fill(32);
  for (let index = 3; index < target.rgba.length; index += 4)
    target.rgba[index] = 255;
  const evidence = registerFourPointBoardBand({
    anchor,
    anchorImage: textured(320, 240),
    targetImage: target,
  });
  assert.equal(evidence.status, 'needs_manual_crop');
  assert.equal(evidence.registeredBoardBand, null);
  assert.equal(
    cropFromRegisteredBoardBand({
      evidence,
      sourceWidth: 320,
      sourceHeight: 240,
      anchorMedianBoardHeight: 42,
    }),
    null,
  );
  validateFourPointRegistrationEvidence(evidence);
});

test('versions the deterministic registration contract separately from v11', () => {
  assert.equal(
    CROP_V12_POLICY,
    'selected-image-board-band-v12-four-point-anchor-registration',
  );
  assert.match(CROP_V12_FINGERPRINT, /oriented-brief-affine-ransac-v1/);
  assert.match(
    CROP_V12_FINGERPRINT,
    /selected-image-board-band-v11-full-layout-structural/,
  );
  assert.match(CROP_V12_FINGERPRINT, /boardOnlyBottomPaddingRatio/);
  assert.match(CROP_V12_FINGERPRINT, /registered-band-bounded-intersection-v2/);
  assert.doesNotMatch(
    CROP_V12_LEGACY_FINGERPRINT,
    /registered-band-bounded-intersection-v2/,
  );
  assert.equal(isCompatibleCropV12Fingerprint(CROP_V12_FINGERPRINT), true);
  assert.equal(
    isCompatibleCropV12Fingerprint(CROP_V12_LEGACY_FINGERPRINT),
    true,
  );
  assert.equal(isCompatibleCropV12Fingerprint('stale-v12'), false);
});

test('rejects non-finite persisted registration metrics', () => {
  const evidence = registerFourPointBoardBand({
    anchor,
    anchorImage: textured(320, 240),
    targetImage: textured(320, 240, 8, 6),
  });
  assert.equal(evidence.status, 'registered');
  assert.throws(
    () =>
      validateFourPointRegistrationEvidence({
        ...evidence,
        p90ResidualPx: Number.NaN,
      }),
    /CROP_V12_EVIDENCE_INVALID/,
  );
});
