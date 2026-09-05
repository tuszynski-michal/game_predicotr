// Read-only diagnostics on the previously exposed regression corpus, not holdout.
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import sharp from 'sharp';
import { cropQualityReferences } from '../packages/manual-image-selection-core/test/fixtures/selected-crop-quality.mjs';
import { sampleCanonicalCropImage } from '../packages/manual-image-selection-core/src/crop-preparation.ts';
import {
  detectStructuralLayout,
  detectStructuralCandidates,
} from '../packages/manual-image-selection-core/src/auto-crop-v11.ts';
import { findNumberRegions } from '../packages/manual-image-selection-core/src/auto-crop-v11-boundaries.ts';
const deadline = setTimeout(() => process.exit(2), 120000);
try {
  for (const ref of cropQualityReferences) {
    if (process.argv[3] && ref.id !== process.argv[3]) continue;
    const decoded = await sharp(
      await readFile(path.join(process.argv[2], ref.directory, ref.fileName)),
    )
      .rotate()
      .ensureAlpha()
      .raw()
      .toBuffer({ resolveWithObject: true });
    const sample = sampleCanonicalCropImage(
      {
        width: decoded.info.width,
        height: decoded.info.height,
        rgba: new Uint8ClampedArray(decoded.data),
      },
      960,
    );
    const layout = detectStructuralLayout(sample);
    console.log(
      JSON.stringify({
        id: ref.id,
        reason: layout.reason,
        candidates: detectStructuralCandidates(sample).boards,
        boards: layout.boards.map((b) => ({
          ...b,
          labels: findNumberRegions(sample, [b]),
        })),
      }),
    );
  }
} finally {
  clearTimeout(deadline);
}
