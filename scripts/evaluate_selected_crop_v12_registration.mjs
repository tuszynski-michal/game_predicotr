import { promises as fs } from 'node:fs';
import path from 'node:path';

import { createHash } from 'node:crypto';

import { CROP_V11_POLICY } from '../packages/manual-image-selection-core/src/auto-crop-v11.ts';
import {
  CROP_V12_FINGERPRINT,
  CROP_V12_POLICY,
  fourPointAnchorFromStructuralEvidence,
} from '../packages/manual-image-selection-core/src/auto-crop-v12-registration.ts';
import { fourthCropReferences } from '../packages/manual-image-selection-core/test/fixtures/selected-crop-v11-fourth.mjs';
import { fifthCropReferences } from '../packages/manual-image-selection-core/test/fixtures/selected-crop-v11-fifth.mjs';
import { sixthCropReferences } from '../packages/manual-image-selection-core/test/fixtures/selected-crop-v11-sixth.mjs';
import { cropQualityReferences } from '../packages/manual-image-selection-core/test/fixtures/selected-crop-quality.mjs';
import {
  renderCropSource,
  sha256,
} from './lib/selected-crop-durable-runner.mjs';

const root = path.resolve(process.argv[2] ?? 'C:/Users/user/Documents/777');
const requestedLimit = Number(
  process.argv
    .find((argument) => argument.startsWith('--limit='))
    ?.split('=')[1] ?? Infinity,
);
const disclosedReferences = [
  ...fourthCropReferences,
  ...fifthCropReferences,
  ...sixthCropReferences,
];
const qualityReferences = cropQualityReferences.map((reference) => ({
  ...reference,
  protectedTop:
    (Math.min(...reference.boards.map((box) => box[1])) / reference.height) *
    640,
  protectedBottom:
    (Math.max(...reference.labels.map((box) => box[3])) / reference.height) *
    640,
  topMin: (reference.topInterval[0] / reference.height) * 640,
  topMax: (reference.topInterval[1] / reference.height) * 640,
  bottomMin: (reference.bottomInterval[0] / reference.height) * 640,
  bottomMax: (reference.bottomInterval[1] / reference.height) * 640,
}));
const requestedSplit = process.argv
  .find((argument) => argument.startsWith('--split='))
  ?.split('=')[1];
const requestedFile = process.argv
  .find((argument) => argument.startsWith('--file='))
  ?.slice('--file='.length);
const references = (
  process.argv.includes('--quality')
    ? qualityReferences.filter(
        (reference) =>
          requestedSplit === undefined || reference.split === requestedSplit,
      )
    : disclosedReferences
)
  .filter(
    (reference) =>
      requestedFile === undefined || reference.fileName === requestedFile,
  )
  .slice(0, requestedLimit);

function sequenceStart(name) {
  return Number(/^seq_(\d+)-/.exec(name)?.[1] ?? NaN);
}

async function nearestAnchor(directory, targetName) {
  const entries = (await fs.readdir(directory))
    .filter((name) => /^seq_\d+-\d+\.jpe?g$/i.test(name))
    .sort((left, right) => sequenceStart(left) - sequenceStart(right));
  const targetIndex = entries.indexOf(targetName);
  if (targetIndex < 0) return null;
  for (let distance = 1; distance <= 2; distance += 1)
    for (const index of [targetIndex - distance, targetIndex + distance]) {
      const name = entries[index];
      if (!name) continue;
      const bytes = await fs.readFile(path.join(directory, name));
      const { proposal } = await renderCropSource(bytes, CROP_V11_POLICY);
      if (proposal.structural?.status !== 'detected') continue;
      return {
        bytes,
        descriptor: fourPointAnchorFromStructuralEvidence({
          sourceName: name,
          sourceChecksumSha256: sha256(bytes),
          evidence: proposal.structural,
        }),
      };
    }
  return null;
}

const observations = [];
for (const reference of references) {
  const directory = path.join(root, reference.directory);
  const sourcePath = path.join(directory, reference.fileName);
  try {
    const bytes = await fs.readFile(sourcePath);
    if (sha256(bytes) !== reference.sha256)
      throw new Error('SOURCE_CHECKSUM_MISMATCH');
    const anchor = await nearestAnchor(directory, reference.fileName);
    const { proposal } = await renderCropSource(bytes, CROP_V12_POLICY, anchor);
    const top = (proposal.crop.topY / proposal.crop.height) * 640;
    const bottom = (proposal.crop.bottomY / proposal.crop.height) * 640;
    const safe =
      top <= reference.protectedTop && bottom >= reference.protectedBottom;
    const precise =
      top >= reference.topMin &&
      top <= reference.topMax &&
      bottom >= reference.bottomMin &&
      bottom <= reference.bottomMax;
    observations.push({
      directory: reference.directory,
      fileName: reference.fileName,
      sourceSha256: reference.sha256,
      anchor: anchor?.descriptor.sourceName ?? null,
      status:
        proposal.registration?.status === 'registered'
          ? 'registered'
          : proposal.structural?.status === 'detected'
            ? 'structural'
            : 'manual',
      reason:
        proposal.registration?.reason ?? proposal.structural?.reason ?? null,
      registration:
        proposal.registration === undefined
          ? null
          : {
              matches: proposal.registration.matchCount,
              inliers: proposal.registration.inlierCount,
              inlierRatio: proposal.registration.inlierRatio,
              p90ResidualPx: proposal.registration.p90ResidualPx,
              coveredQuadrants: proposal.registration.coveredQuadrants,
            },
      top,
      bottom,
      safe,
      precise,
    });
  } catch (cause) {
    observations.push({
      directory: reference.directory,
      fileName: reference.fileName,
      status: 'failed',
      reason: cause instanceof Error ? cause.message : 'UNKNOWN_ERROR',
      safe: false,
      precise: false,
    });
  }
}

const automatic = observations.filter((item) =>
  ['structural', 'registered'].includes(item.status),
);
const report = {
  schemaVersion: 1,
  policy: CROP_V12_POLICY,
  fingerprint: CROP_V12_FINGERPRINT,
  corpus: process.argv.includes('--quality')
    ? 'disclosed-selected-crop-quality-development-only'
    : 'disclosed-v11-fourth-fifth-sixth-development-only',
  sourceRootHash: createHash('sha256').update(root.toLowerCase()).digest('hex'),
  total: observations.length,
  automatic: automatic.length,
  registered: observations.filter((item) => item.status === 'registered')
    .length,
  manual: observations.filter((item) => item.status === 'manual').length,
  safeAutomatic: automatic.filter((item) => item.safe).length,
  preciseAutomatic: automatic.filter((item) => item.precise).length,
  observations,
};
const outputReport = process.argv.includes('--summary')
  ? {
      ...report,
      observations: undefined,
      unsafe: observations.filter(
        (item) =>
          ['structural', 'registered'].includes(item.status) && !item.safe,
      ),
      imprecise: observations
        .filter(
          (item) =>
            ['structural', 'registered'].includes(item.status) && !item.precise,
        )
        .map(({ directory, fileName, status, reason, top, bottom }) => ({
          directory,
          fileName,
          status,
          reason,
          top,
          bottom,
        })),
    }
  : report;
process.stdout.write(`${JSON.stringify(outputReport, null, 2)}\n`);
