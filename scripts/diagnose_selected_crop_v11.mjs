// Read-only diagnostics on the previously exposed regression corpus, not holdout.
import { mkdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import sharp from 'sharp';
import { cropQualityReferences } from '../packages/manual-image-selection-core/test/fixtures/selected-crop-quality.mjs';
import { independentCropReferences } from '../packages/manual-image-selection-core/test/fixtures/selected-crop-v11-independent.mjs';
import { thirdCropReferences } from '../packages/manual-image-selection-core/test/fixtures/selected-crop-v11-third.mjs';
import { fourthCropReferences } from '../packages/manual-image-selection-core/test/fixtures/selected-crop-v11-fourth.mjs';
import { fifthCropReferences } from '../packages/manual-image-selection-core/test/fixtures/selected-crop-v11-fifth.mjs';
import { sixthCropReferences } from '../packages/manual-image-selection-core/test/fixtures/selected-crop-v11-sixth.mjs';
import { sampleCanonicalCropImage } from '../packages/manual-image-selection-core/src/crop-preparation.ts';
import {
  detectStructuralLayout,
  detectStructuralCandidates,
} from '../packages/manual-image-selection-core/src/auto-crop-v11.ts';
import { findNumberRegions } from '../packages/manual-image-selection-core/src/auto-crop-v11-boundaries.ts';
const deadline = setTimeout(() => process.exit(2), 120000);
try {
  for (const ref of [
    ...cropQualityReferences,
    ...independentCropReferences.map((r) => ({
      ...r,
      id: r.fileName.match(/\d+/)[0],
    })),
    ...thirdCropReferences.map((r) => ({
      ...r,
      id: r.fileName.match(/\d+/)[0],
    })),
    ...fourthCropReferences.map((r) => ({
      ...r,
      id: r.fileName.match(/\d+/)[0],
    })),
    ...fifthCropReferences.map((r) => ({
      ...r,
      id: r.fileName.match(/\d+/)[0],
    })),
    ...sixthCropReferences.map((r) => ({
      ...r,
      id: r.fileName.match(/\d+/)[0],
    })),
  ]) {
    if (process.argv[3] && ref.id !== process.argv[3]) continue;
    const decoded = await sharp(
      await readFile(path.join(process.argv[2], ref.directory, ref.fileName)),
    )
      .rotate()
      .ensureAlpha()
      .raw()
      .toBuffer({ resolveWithObject: true });
    for (const level of [960, 1600]) {
      const sample = sampleCanonicalCropImage(
        {
          width: decoded.info.width,
          height: decoded.info.height,
          rgba: new Uint8ClampedArray(decoded.data),
        },
        level,
      );
      const detectedCandidates = detectStructuralCandidates(sample);
      const layout = detectStructuralLayout(sample);
      if (process.argv[3]) {
        const diagnosticsRoot = path.resolve(
          '.tmp/crop-v11-layout-diagnostics',
        );
        await mkdir(diagnosticsRoot, { recursive: true });
        const overlay = `<svg width="${sample.width}" height="${sample.height}" xmlns="http://www.w3.org/2000/svg">${detectedCandidates.boards
          .map(
            (box, index) =>
              `<rect x="${box.left}" y="${box.top}" width="${box.right - box.left}" height="${box.bottom - box.top}" fill="none" stroke="${index < 9 ? '#00ff88' : '#ffcc00'}" stroke-width="2"/><text x="${box.left + 2}" y="${box.top + 14}" fill="white" stroke="black" stroke-width="2" paint-order="stroke">${index}:${box.support}</text>`,
          )
          .join('')}</svg>`;
        await sharp(Buffer.from(sample.rgba), {
          raw: { width: sample.width, height: sample.height, channels: 4 },
        })
          .composite([{ input: Buffer.from(overlay) }])
          .png()
          .toFile(path.join(diagnosticsRoot, `${ref.id}-${level}.png`));
      }
      console.log(
        JSON.stringify({
          id: ref.id,
          level,
          reason: layout.reason,
          candidateCount: detectedCandidates.boards.length,
          candidates: process.argv[3] ? detectedCandidates.boards : undefined,
          boards: layout.boards,
          labels: findNumberRegions(sample, layout.boards),
          individualLabels: layout.boards.map((board) =>
            findNumberRegions(sample, [board]),
          ),
        }),
      );
    }
  }
} finally {
  clearTimeout(deadline);
}
