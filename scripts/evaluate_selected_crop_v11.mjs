// Read-only bounded experiment; development by default, holdout only explicitly.
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import assert from 'node:assert/strict';
import sharp from 'sharp';
import {
  detectStructuralLayout,
  detectStructuralCandidates,
} from '../packages/manual-image-selection-core/src/auto-crop-v11.ts';
import { cropQualityReferences } from '../packages/manual-image-selection-core/test/fixtures/selected-crop-quality.mjs';
const [root, split = 'development'] = process.argv.slice(2);
if (!root || !['development', 'holdout'].includes(split))
  throw new Error('Usage: <root> [development|holdout]');
const deadline = setTimeout(() => process.exit(2), 120000);
try {
  for (const ref of cropQualityReferences.filter((r) => r.split === split)) {
    const bytes = await readFile(path.join(root, ref.directory, ref.fileName));
    assert.equal(createHash('sha256').update(bytes).digest('hex'), ref.sha256);
    const decoded = await sharp(bytes)
      .rotate()
      .raw()
      .toBuffer({ resolveWithObject: true });
    for (const level of [960, 1600]) {
      const sample = await sharp(decoded.data, { raw: decoded.info })
        .resize({
          width: level,
          height: level,
          fit: 'inside',
          withoutEnlargement: true,
        })
        .ensureAlpha()
        .raw()
        .toBuffer({ resolveWithObject: true });
      const s = {
        width: sample.info.width,
        height: sample.info.height,
        rgba: new Uint8ClampedArray(sample.data),
      };
      const start = performance.now();
      const result = detectStructuralLayout(s);
      console.log(
        JSON.stringify({
          id: ref.id,
          level,
          ms: performance.now() - start,
          ...result,
          ...(process.env.CROP_DEBUG === '1'
            ? { candidates: detectStructuralCandidates(s).boards }
            : {}),
        }),
      );
      if (result.status === 'detected') break;
    }
  }
} finally {
  clearTimeout(deadline);
}
