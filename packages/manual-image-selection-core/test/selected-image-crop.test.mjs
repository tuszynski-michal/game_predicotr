import assert from 'node:assert/strict';
import test from 'node:test';

import {
  approvePreparedSelectedImageCrop,
  beginSelectedImageCropWrite,
  createDefaultSelectedImageCropBand,
  createSelectedImageCropManifest,
  finalizeSelectedImageCropWrite,
  inheritSelectedImageCropBand,
  selectedImageCropReviewedFileNames,
  selectedImageCropRecoveryAction,
  validateSelectedImageCropBand,
  validateSelectedImageCropSources,
} from '../src/crop.ts';

const HASH_A = 'a'.repeat(64);
const HASH_B = 'b'.repeat(64);

test('creates and inherits a bounded full-width crop band', () => {
  const first = createDefaultSelectedImageCropBand({
    width: 1440,
    height: 1920,
  });
  assert.deepEqual(first, {
    width: 1440,
    height: 1920,
    topY: 346,
    bottomY: 1651,
  });
  const inherited = inheritSelectedImageCropBand(first, {
    width: 1920,
    height: 1080,
  });
  assert.deepEqual(inherited, {
    width: 1920,
    height: 1080,
    topY: 195,
    bottomY: 929,
  });
  assert.throws(
    () =>
      validateSelectedImageCropBand({
        width: 100,
        height: 100,
        topY: 50,
        bottomY: 55,
      }),
    /TOO_SHORT/,
  );
});

test('keeps automatic output separate from human review', () => {
  const manifest = createSelectedImageCropManifest({
    sourceDirectoryName: 'picked',
    outputDirectoryName: 'picked cut',
    sourceInventoryChecksumSha256: HASH_A,
    entries: [
      {
        fileName: 'seq_1-9.jpg',
        sizeBytes: 10,
        lastModifiedMs: 1,
        rangeStart: 1,
        rangeEnd: 9,
      },
    ],
    now: '2026-09-04T11:00:00.000Z',
  });
  const pending = beginSelectedImageCropWrite(
    manifest,
    {
      kind: 'write_crop',
      fileName: 'seq_1-9.jpg',
      expectedSourceChecksumSha256: HASH_A,
      expectedOutputChecksumSha256: HASH_B,
      crop: { width: 1080, height: 1920, topY: 400, bottomY: 1100 },
      startedAt: '2026-09-04T11:01:00.000Z',
      replacesOutputChecksumSha256: null,
      markReviewed: false,
    },
    '2026-09-04T11:01:00.000Z',
  );
  const prepared = finalizeSelectedImageCropWrite(
    pending,
    '2026-09-04T11:02:00.000Z',
  );
  assert.ok(prepared.entries[0].result);
  assert.deepEqual(selectedImageCropReviewedFileNames(prepared), []);
  assert.deepEqual(
    selectedImageCropReviewedFileNames({
      ...prepared,
      reviewedFileNames: undefined,
    }),
    ['seq_1-9.jpg'],
  );
  const reviewed = approvePreparedSelectedImageCrop(
    prepared,
    'seq_1-9.jpg',
    '2026-09-04T11:03:00.000Z',
  );
  assert.deepEqual(selectedImageCropReviewedFileNames(reviewed), [
    'seq_1-9.jpg',
  ]);
  assert.equal(reviewed.entries[0].result, prepared.entries[0].result);
});

test('validates and orders only non-overlapping seq inputs', () => {
  const sources = validateSelectedImageCropSources([
    { fileName: 'seq_10-18.jpeg', sizeBytes: 20, lastModifiedMs: 2 },
    { fileName: 'seq_1-9.jpg', sizeBytes: 10, lastModifiedMs: 1 },
  ]);
  assert.deepEqual(
    sources.map((entry) => entry.fileName),
    ['seq_1-9.jpg', 'seq_10-18.jpeg'],
  );
  assert.throws(
    () =>
      validateSelectedImageCropSources([
        { fileName: 'seq_1-9.jpg', sizeBytes: 10, lastModifiedMs: 1 },
        { fileName: 'seq_9-17.jpg', sizeBytes: 10, lastModifiedMs: 1 },
      ]),
    /OVERLAPPING/,
  );
});

test('journals and deterministically recovers a crop write', () => {
  const entries = validateSelectedImageCropSources([
    { fileName: 'seq_1-9.jpg', sizeBytes: 10, lastModifiedMs: 1 },
  ]);
  const manifest = createSelectedImageCropManifest({
    sourceDirectoryName: 'picked',
    outputDirectoryName: 'picked cut',
    sourceInventoryChecksumSha256: HASH_A,
    entries,
    now: '2026-09-04T10:00:00.000Z',
  });
  const pending = beginSelectedImageCropWrite(
    manifest,
    {
      kind: 'write_crop',
      fileName: 'seq_1-9.jpg',
      expectedSourceChecksumSha256: HASH_A,
      expectedOutputChecksumSha256: HASH_B,
      crop: { width: 1440, height: 1920, topY: 300, bottomY: 1700 },
      startedAt: '2026-09-04T10:01:00.000Z',
      replacesOutputChecksumSha256: null,
    },
    '2026-09-04T10:01:00.000Z',
  );
  assert.equal(
    selectedImageCropRecoveryAction(pending, null),
    'rollback_missing_output',
  );
  assert.equal(
    selectedImageCropRecoveryAction(pending, HASH_B),
    'finalize_matching_output',
  );
  assert.equal(
    selectedImageCropRecoveryAction(pending, HASH_A),
    'block_conflicting_output',
  );
  const completed = finalizeSelectedImageCropWrite(
    pending,
    '2026-09-04T10:02:00.000Z',
  );
  assert.equal(completed.entries[0].result?.outputChecksumSha256, HASH_B);
  assert.equal(completed.pendingOperation, null);
});

test('persists automatic proposal provenance and preserves it on manual correction', () => {
  const manifest = createSelectedImageCropManifest({
    sourceDirectoryName: 'picked',
    outputDirectoryName: 'picked cut',
    sourceInventoryChecksumSha256: HASH_A,
    entries: [
      {
        fileName: 'seq_1-9.jpg',
        sizeBytes: 10,
        lastModifiedMs: 1,
        rangeStart: 1,
        rangeEnd: 9,
      },
    ],
    now: '2026-09-05T10:00:00.000Z',
  });
  const proposal = {
    crop: { width: 1440, height: 1920, topY: 200, bottomY: 1700 },
    strategy: 'multicolumn_panel',
    classification: 'conservative',
    confidence: 0.71,
    policyVersion: 'selected-image-board-band-v4-conservative-multicolumn',
    evidence: {
      sampleWidth: 360,
      sampleHeight: 480,
      localBounds: [
        {
          signal: 'chromatic',
          stripIndex: 0,
          topRatio: 0.2,
          bottomRatio: 0.8,
        },
      ],
      chromaticCandidateCount: 1,
      structuralCandidateCount: 1,
      chromaticSupportedStrips: [0, 1, 2, 3, 4],
      structuralSupportedStrips: [0, 1, 2, 3, 4],
      evidenceIoU: 0.7,
      boundaryExpanded: false,
      fallbackReason: null,
    },
  };
  const automatic = finalizeSelectedImageCropWrite(
    beginSelectedImageCropWrite(
      manifest,
      {
        kind: 'write_crop',
        fileName: 'seq_1-9.jpg',
        expectedSourceChecksumSha256: HASH_A,
        expectedOutputChecksumSha256: HASH_B,
        crop: proposal.crop,
        startedAt: '2026-09-05T10:01:00.000Z',
        replacesOutputChecksumSha256: null,
        markReviewed: false,
        autoCropProposal: proposal,
      },
      '2026-09-05T10:01:00.000Z',
    ),
    '2026-09-05T10:02:00.000Z',
  );
  assert.deepEqual(automatic.entries[0].result?.autoCropProposal, proposal);
  const corrected = finalizeSelectedImageCropWrite(
    beginSelectedImageCropWrite(
      automatic,
      {
        kind: 'write_crop',
        fileName: 'seq_1-9.jpg',
        expectedSourceChecksumSha256: HASH_A,
        expectedOutputChecksumSha256: HASH_A,
        crop: { ...proposal.crop, topY: 180 },
        startedAt: '2026-09-05T10:03:00.000Z',
        replacesOutputChecksumSha256: HASH_B,
      },
      '2026-09-05T10:03:00.000Z',
    ),
    '2026-09-05T10:04:00.000Z',
  );
  assert.deepEqual(corrected.entries[0].result?.autoCropProposal, proposal);
});

test('uses a separate compatible output for the filled-gaps handoff', () => {
  const manifest = createSelectedImageCropManifest({
    sourceDirectoryName: 'picked',
    outputDirectoryName: 'picked filled-gaps cut',
    sourceInventoryChecksumSha256: HASH_A,
    entries: [
      {
        fileName: 'seq_10-18.jpg',
        sizeBytes: 10,
        lastModifiedMs: 1,
        rangeStart: 10,
        rangeEnd: 18,
      },
    ],
    now: '2026-09-04T12:00:00.000Z',
  });
  assert.equal(manifest.outputDirectoryName, 'picked filled-gaps cut');
  assert.throws(
    () =>
      createSelectedImageCropManifest({
        sourceDirectoryName: 'picked',
        outputDirectoryName: 'picked arbitrary',
        sourceInventoryChecksumSha256: HASH_A,
        entries: manifest.entries,
        now: '2026-09-04T12:00:00.000Z',
      }),
    /OUTPUT_NAME_INVALID/,
  );
});
