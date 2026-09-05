import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';
import sharp from 'sharp';
import { renderCropSource } from './lib/selected-crop-durable-runner.mjs';
import { CROP_V11_POLICY } from '../packages/manual-image-selection-core/src/auto-crop-v11.ts';
import { SELECTED_IMAGE_AUTO_CROP_POLICY } from '../packages/manual-image-selection-core/src/auto-crop.ts';
import { cropQualityReferences } from '../packages/manual-image-selection-core/test/fixtures/selected-crop-quality.mjs';
import {
  evaluateCrop,
  validateReferences,
} from '../packages/manual-image-selection-core/test/crop-quality-evaluation.mjs';
const [root, split = 'holdout'] = process.argv.slice(2);
if (!root || !['holdout', 'development'].includes(split))
  throw new Error('Usage: <source-root> [holdout|development]');
const timeout = setTimeout(() => {
  console.error('ACCEPTANCE_TIMEOUT');
  process.exit(2);
}, 120000);
try {
  validateReferences(cropQualityReferences);
  const rows = [];
  for (const ref of cropQualityReferences.filter((r) => r.split === split)) {
    const bytes = await readFile(path.join(root, ref.directory, ref.fileName));
    assert.equal(createHash('sha256').update(bytes).digest('hex'), ref.sha256);
    let start = performance.now();
    const baseline = await renderCropSource(
      bytes,
      SELECTED_IMAGE_AUTO_CROP_POLICY,
    );
    const baselineMs = performance.now() - start;
    start = performance.now();
    const result = await renderCropSource(bytes, CROP_V11_POLICY);
    const ms = performance.now() - start;
    const metadata = await sharp(result.output).metadata();
    assert.equal(metadata.width, ref.width);
    assert.equal(
      metadata.height,
      result.proposal.crop.bottomY - result.proposal.crop.topY,
    );
    const automatic = result.proposal.structural.status === 'detected',
      issues = automatic ? evaluateCrop(ref, result.proposal.crop) : [];
    rows.push({
      id: ref.id,
      sha256: ref.sha256,
      family: ref.family,
      automatic,
      issues,
      reason: result.proposal.structural.reason,
      levels: result.proposal.analysisLevels,
      crop: result.proposal.crop,
      ms,
      baselineMs,
      baselineIssues: evaluateCrop(ref, baseline.proposal.crop),
      fingerprint: result.proposal.preparationFingerprint,
    });
  }
  const times = rows.map((r) => r.ms).sort((a, b) => a - b),
    pct = (p) =>
      times[Math.min(times.length - 1, Math.ceil(times.length * p) - 1)];
  const good = rows.filter((r) => r.automatic && !r.issues.length).length,
    bad = rows.filter((r) => r.automatic && r.issues.length).length;
  const gate = bad === 0 && good / rows.length >= 0.9;
  console.log(
    JSON.stringify(
      {
        split,
        gatePassed: gate,
        sources: rows.length,
        correctAutomatic: good,
        incorrectAutomatic: bad,
        manual: rows.filter((r) => !r.automatic).length,
        medianMs: pct(0.5),
        p95Ms: pct(0.95),
        totalMs: rows.reduce((n, r) => n + r.ms, 0),
        processMaxRssKiB: process.resourceUsage().maxRSS,
        otherGameAcceptance: 'unverified-original-missing',
        rows,
      },
      null,
      2,
    ),
  );
  if (!gate) process.exitCode = 3;
} finally {
  clearTimeout(timeout);
}
