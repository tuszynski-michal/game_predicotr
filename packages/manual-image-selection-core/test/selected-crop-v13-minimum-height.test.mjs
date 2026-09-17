import assert from 'node:assert/strict';
import test from 'node:test';

import {
  CROP_V13_FINGERPRINT,
  CROP_V13_MINIMUM_HEIGHT_CONFIG,
  CROP_V13_POLICY,
  cropMeetsV13MinimumHeight,
  cropV13MinimumHeightPx,
  enforceCropV13MinimumHeight,
  isCompatibleCropV13Fingerprint,
} from '../src/auto-crop-v13-minimum-height.ts';
import {
  createSelectedImageCropManifest,
  validateSelectedImageCropManifest,
} from '../src/crop.ts';
import {
  finishFourPointRegisteredCropForPolicy,
  prepareStructuralCrop,
} from '../src/crop-preparation.ts';

test('v13 versions the reference lower-tail measurement and scales its floor', () => {
  assert.equal(
    CROP_V13_POLICY,
    'selected-image-board-band-v13-v12-minimum-height',
  );
  assert.equal(CROP_V13_MINIMUM_HEIGHT_CONFIG.lowerTailMeanHeightPx, 422.96);
  assert.equal(CROP_V13_MINIMUM_HEIGHT_CONFIG.safetyBufferRatio, 0.05);
  assert.equal(cropV13MinimumHeightPx({ width: 1080, height: 1920 }), 401);
  assert.equal(cropV13MinimumHeightPx({ width: 2160, height: 3840 }), 802);
  assert.equal(isCompatibleCropV13Fingerprint(CROP_V13_FINGERPRINT), true);
  assert.equal(isCompatibleCropV13Fingerprint('stale-v13'), false);
});

test('v13 expands a short crop around its center without removing candidate pixels', () => {
  const crop = enforceCropV13MinimumHeight({
    width: 1080,
    height: 1920,
    topY: 600,
    bottomY: 950,
  });
  assert.deepEqual(crop, {
    width: 1080,
    height: 1920,
    topY: 575,
    bottomY: 976,
  });
  assert.equal(cropMeetsV13MinimumHeight(crop), true);
});

test('v13 uses the available side at an image edge and keeps a short source whole', () => {
  assert.deepEqual(
    enforceCropV13MinimumHeight({
      width: 1080,
      height: 1920,
      topY: 0,
      bottomY: 350,
    }),
    { width: 1080, height: 1920, topY: 0, bottomY: 401 },
  );
  assert.deepEqual(
    enforceCropV13MinimumHeight({
      width: 1080,
      height: 380,
      topY: 20,
      bottomY: 300,
    }),
    { width: 1080, height: 380, topY: 0, bottomY: 380 },
  );
});

test('manifest validation rejects a persisted v13 crop below its achievable floor', async () => {
  const source = {
    width: 1080,
    height: 1920,
    rgba: new Uint8ClampedArray(1080 * 1920 * 4),
  };
  const structural = await prepareStructuralCrop(source);
  const proposal = await finishFourPointRegisteredCropForPolicy(
    CROP_V13_POLICY,
    source,
    structural,
    null,
  );
  const shortCrop = {
    width: 1080,
    height: 1920,
    topY: 600,
    bottomY: 950,
  };
  const invalidProposal = {
    ...proposal,
    crop: shortCrop,
    structural: { ...proposal.structural, crop: shortCrop },
  };
  const manifest = createSelectedImageCropManifest({
    sourceDirectoryName: 'source',
    outputDirectoryName: 'source cut',
    sourceInventoryChecksumSha256: 'a'.repeat(64),
    entries: [
      {
        fileName: 'seq_1-9.jpg',
        sizeBytes: 1,
        lastModifiedMs: 0,
        rangeStart: 1,
        rangeEnd: 9,
      },
    ],
    now: '2026-09-17T00:00:00.000Z',
  });
  const persisted = {
    ...manifest,
    entries: [
      {
        ...manifest.entries[0],
        result: {
          status: 'accepted',
          crop: shortCrop,
          sourceChecksumSha256: 'b'.repeat(64),
          outputChecksumSha256: 'c'.repeat(64),
          acceptedAt: '2026-09-17T00:00:00.000Z',
          autoCropProposal: invalidProposal,
        },
      },
    ],
  };
  assert.throws(
    () => validateSelectedImageCropManifest(persisted),
    /SELECTED_IMAGE_CROP_PROPOSAL_INVALID/,
  );
});
