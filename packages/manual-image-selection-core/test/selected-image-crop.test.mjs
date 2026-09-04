import assert from 'node:assert/strict';
import test from 'node:test';

import {
  beginSelectedImageCropWrite,
  createDefaultSelectedImageCropBand,
  createSelectedImageCropManifest,
  finalizeSelectedImageCropWrite,
  inheritSelectedImageCropBand,
  selectedImageCropRecoveryAction,
  validateSelectedImageCropBand,
  validateSelectedImageCropSources,
} from '../src/crop.ts';

const HASH_A = 'a'.repeat(64);
const HASH_B = 'b'.repeat(64);

test('creates and inherits a bounded full-width crop band', () => {
  const first = createDefaultSelectedImageCropBand({ width: 1440, height: 1920 });
  assert.deepEqual(first, { width: 1440, height: 1920, topY: 346, bottomY: 1651 });
  const inherited = inheritSelectedImageCropBand(first, { width: 1920, height: 1080 });
  assert.deepEqual(inherited, { width: 1920, height: 1080, topY: 195, bottomY: 929 });
  assert.throws(
    () => validateSelectedImageCropBand({ width: 100, height: 100, topY: 50, bottomY: 55 }),
    /TOO_SHORT/,
  );
});

test('validates and orders only non-overlapping seq inputs', () => {
  const sources = validateSelectedImageCropSources([
    { fileName: 'seq_10-18.jpeg', sizeBytes: 20, lastModifiedMs: 2 },
    { fileName: 'seq_1-9.jpg', sizeBytes: 10, lastModifiedMs: 1 },
  ]);
  assert.deepEqual(sources.map((entry) => entry.fileName), [
    'seq_1-9.jpg',
    'seq_10-18.jpeg',
  ]);
  assert.throws(
    () => validateSelectedImageCropSources([
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
  const pending = beginSelectedImageCropWrite(manifest, {
    kind: 'write_crop',
    fileName: 'seq_1-9.jpg',
    expectedSourceChecksumSha256: HASH_A,
    expectedOutputChecksumSha256: HASH_B,
    crop: { width: 1440, height: 1920, topY: 300, bottomY: 1700 },
    startedAt: '2026-09-04T10:01:00.000Z',
    replacesOutputChecksumSha256: null,
  }, '2026-09-04T10:01:00.000Z');
  assert.equal(selectedImageCropRecoveryAction(pending, null), 'rollback_missing_output');
  assert.equal(selectedImageCropRecoveryAction(pending, HASH_B), 'finalize_matching_output');
  assert.equal(selectedImageCropRecoveryAction(pending, HASH_A), 'block_conflicting_output');
  const completed = finalizeSelectedImageCropWrite(pending, '2026-09-04T10:02:00.000Z');
  assert.equal(completed.entries[0].result?.outputChecksumSha256, HASH_B);
  assert.equal(completed.pendingOperation, null);
});
