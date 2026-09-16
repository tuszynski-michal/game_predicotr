// Read-only, bounded real-source evaluation. No output JPEGs or manifests written.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import sharp from 'sharp';
import {
  detectSelectedImageCropBand,
  SELECTED_IMAGE_AUTO_CROP_POLICY,
} from '../packages/manual-image-selection-core/src/auto-crop.ts';
import { cropQualityReferences } from '../packages/manual-image-selection-core/test/fixtures/selected-crop-quality.mjs';
import { v10Baseline } from '../packages/manual-image-selection-core/test/fixtures/selected-crop-v10-baseline.mjs';
import {
  evaluateCrop,
  validateReferences,
} from '../packages/manual-image-selection-core/test/crop-quality-evaluation.mjs';

const parent = process.argv[2];
if (!parent)
  throw new Error(
    'Usage: node --experimental-strip-types scripts/evaluate_selected_crop_quality.mjs <source-root>',
  );
// Hard runtime deadline; no orphan child process is started by this runner.
const deadline = setTimeout(() => {
  console.error('CROP_EVALUATION_TIMEOUT');
  process.exit(2);
}, 120_000);
try {
  validateReferences(cropQualityReferences);
  assert.equal(
    SELECTED_IMAGE_AUTO_CROP_POLICY,
    'selected-image-board-band-v10-top-board-row-guided',
    'Select an explicit historical adapter before replaying a changed default',
  );
  for (const ref of cropQualityReferences) {
    const bytes = await readFile(
      path.join(parent, ref.directory, ref.fileName),
    );
    assert.equal(
      createHash('sha256').update(bytes).digest('hex'),
      ref.sha256,
      `SOURCE_CHANGED:${ref.id}`,
    );
    const decoded = await sharp(bytes)
      .rotate()
      .raw()
      .toBuffer({ resolveWithObject: true });
    assert.equal(decoded.info.width, ref.width);
    assert.equal(decoded.info.height, ref.height);
    // Exact sampling path used by the v10 directory runner, not a screenshot.
    const sample = await sharp(decoded.data, { raw: decoded.info })
      .resize({ width: 512 })
      .ensureAlpha()
      .raw()
      .toBuffer({ resolveWithObject: true });
    const result = detectSelectedImageCropBand(
      {
        width: sample.info.width,
        height: sample.info.height,
        rgba: new Uint8ClampedArray(sample.data),
      },
      { width: ref.width, height: ref.height },
    );
    assert.deepEqual(
      [result.crop.topY, result.crop.bottomY, result.classification],
      v10Baseline[ref.id],
      `BASELINE_CHANGED:${ref.id}`,
    );
    console.log(
      JSON.stringify({
        id: ref.id,
        split: ref.split,
        sha256: ref.sha256,
        policy: result.policyVersion,
        topY: result.crop.topY,
        bottomY: result.crop.bottomY,
        classification: result.classification,
        issues: evaluateCrop(ref, result.crop),
      }),
    );
  }
} finally {
  clearTimeout(deadline);
}
