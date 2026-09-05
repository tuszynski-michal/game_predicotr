import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import assert from 'node:assert/strict';
import { independentCropReferences } from '../packages/manual-image-selection-core/test/fixtures/selected-crop-v11-independent.mjs';
import { renderCropSource } from './lib/selected-crop-durable-runner.mjs';
import {
  CROP_V11_POLICY,
  CROP_V11_FINGERPRINT,
} from '../packages/manual-image-selection-core/src/auto-crop-v11.ts';
const deadline = setTimeout(() => process.exit(2), 120000);
try {
  const rows = [];
  for (const ref of independentCropReferences) {
    const bytes = await readFile(
      path.join(process.argv[2], ref.directory, ref.fileName),
    );
    assert.equal(createHash('sha256').update(bytes).digest('hex'), ref.sha256);
    const start = performance.now(),
      rendered = await renderCropSource(bytes, CROP_V11_POLICY);
    const proposal = rendered.proposal;
    const c = proposal.crop,
      top = (c.topY / c.height) * 640,
      bottom = (c.bottomY / c.height) * 640;
    const automatic = proposal.structural.status === 'detected';
    const safe = top <= ref.protectedTop && bottom >= ref.protectedBottom;
    const precise =
      top >= ref.topMin - 2 &&
      top <= ref.topMax + 2 &&
      bottom >= ref.bottomMin - 2 &&
      bottom <= ref.bottomMax + 2;
    rows.push({
      fileName: ref.fileName,
      automatic,
      safe,
      precise,
      top,
      bottom,
      reason: proposal.structural.reason,
      ms: performance.now() - start,
    });
  }
  const correct = rows.filter((r) => r.automatic && r.safe && r.precise).length;
  const incorrect = rows.filter(
    (r) => r.automatic && (!r.safe || !r.precise),
  ).length;
  const gatePassed = correct / rows.length >= 0.9 && incorrect === 0;
  console.log(
    JSON.stringify(
      {
        fingerprint: CROP_V11_FINGERPRINT,
        gatePassed,
        correct,
        incorrect,
        manual: rows.filter((r) => !r.automatic).length,
        rows,
      },
      null,
      2,
    ),
  );
  if (!gatePassed) process.exitCode = 3;
} finally {
  clearTimeout(deadline);
}
