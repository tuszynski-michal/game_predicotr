import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createRepairManifest,
  deriveFilledGapsManifest,
  deriveCollectionBounds,
  finalizePendingRepairOperation,
  findSequenceGaps,
  migrateLegacyRepairManifest,
  parseSequenceFileName,
  sortAndValidateSequenceFiles,
  validateRepairManifest,
  validateFilledGapsManifest,
} from '../src/repair.ts';

test('parses and numerically sorts bounded seq files', () => {
  const files = sortAndValidateSequenceFiles([
    'seq_100-108.jpg',
    'seq_10-18.jpeg',
    'seq_2-9.JPG',
  ]);
  assert.deepEqual(
    files.map((file) => file.start),
    [2, 10, 100],
  );
  assert.deepEqual(parseSequenceFileName('seq_19-22.jpg'), {
    end: 22,
    fileName: 'seq_19-22.jpg',
    start: 19,
  });
});

test('rejects malformed, oversized, duplicate and overlapping JPEG ranges', () => {
  assert.throws(() => parseSequenceFileName('photo.jpg'), /INVALID_SEQUENCE/);
  assert.throws(
    () => parseSequenceFileName('seq_1-10.jpg'),
    /INVALID_SEQUENCE_RANGE/,
  );
  assert.throws(
    () => sortAndValidateSequenceFiles(['seq_1-9.jpg', 'SEQ_1-9.JPG']),
    /DUPLICATE_SEQUENCE_FILE/,
  );
  assert.throws(
    () => sortAndValidateSequenceFiles(['seq_1-9.jpg', 'seq_9-17.jpg']),
    /OVERLAPPING_SEQUENCE_RANGES/,
  );
});

test('preserves manifest bounds after deleting edge files', () => {
  const initial = sortAndValidateSequenceFiles([
    'seq_1-9.jpg',
    'seq_10-18.jpg',
    'seq_19-27.jpg',
  ]);
  const manifest = createRepairManifest({
    bounds: { end: 27, start: 1 },
    files: initial,
    now: '2026-08-30T00:00:00.000Z',
    repairKey: 'repair-1',
    selectedDirectoryName: 'selected',
  });
  const remaining = sortAndValidateSequenceFiles(['seq_10-18.jpg']);
  assert.deepEqual(
    deriveCollectionBounds({
      files: remaining,
      outputBounds: null,
      repairManifest: manifest,
    }),
    { end: 27, start: 1 },
  );
  assert.deepEqual(findSequenceGaps({ end: 27, start: 1 }, remaining), [
    { end: 9, start: 1 },
    { end: 27, start: 19 },
  ]);
});

test('widens corrupted repair bounds from active and deleted range evidence', () => {
  const files = sortAndValidateSequenceFiles(['seq_1-9.jpg', 'seq_28-36.jpg']);
  const corrupted = createRepairManifest({
    bounds: { end: 36, start: 28 },
    files,
    now: '2026-09-06T00:00:00.000Z',
    repairKey: 'repair-descending',
    selectedDirectoryName: 'descending',
  });
  assert.deepEqual(
    deriveCollectionBounds({
      files,
      outputBounds: null,
      repairManifest: {
        ...corrupted,
        deletedRanges: [{ end: 27, start: 19 }],
      },
    }),
    { end: 36, start: 1 },
  );
});

test('keeps exact known deletions and splits unknown long gaps from the left', () => {
  const files = sortAndValidateSequenceFiles(['seq_1-9.jpg', 'seq_40-48.jpg']);
  assert.deepEqual(
    findSequenceGaps({ end: 48, start: 1 }, files, [{ end: 27, start: 20 }]),
    [
      { end: 18, start: 10 },
      { end: 19, start: 19 },
      { end: 27, start: 20 },
      { end: 36, start: 28 },
      { end: 39, start: 37 },
    ],
  );
});

test('validates the repair manifest and rejects mismatched file ranges', () => {
  const files = sortAndValidateSequenceFiles(['seq_1-9.jpg']);
  const manifest = createRepairManifest({
    bounds: { end: 9, start: 1 },
    files,
    now: '2026-08-30T00:00:00.000Z',
    repairKey: 'repair-1',
    selectedDirectoryName: 'selected',
  });
  assert.equal(validateRepairManifest(manifest).repairKey, 'repair-1');
  assert.throws(
    () =>
      validateRepairManifest({
        ...manifest,
        activeFiles: [{ ...manifest.activeFiles[0], end: 8 }],
      }),
    /INVALID_REPAIR_MANIFEST_FILE_RANGE/,
  );
});

test('finalizes an interrupted delete deterministically from the observed file state', () => {
  const manifest = createRepairManifest({
    bounds: { end: 18, start: 1 },
    files: sortAndValidateSequenceFiles(['seq_1-9.jpg', 'seq_10-18.jpg']),
    now: '2026-08-30T00:00:00.000Z',
    repairKey: 'repair-1',
    selectedDirectoryName: 'selected',
  });
  const pendingOperation = {
    checksumSha256: 'a'.repeat(64),
    expectedFileState: 'absent',
    fileName: 'seq_1-9.jpg',
    id: 'delete-1',
    kind: 'delete',
    occurredAt: '2026-08-30T00:01:00.000Z',
    rangeEnd: 9,
    rangeStart: 1,
    sourceIndex: null,
    sourcePath: null,
  };
  const recovered = finalizePendingRepairOperation(
    { ...manifest, pendingOperation },
    'absent',
    '2026-08-30T00:02:00.000Z',
  );
  assert.deepEqual(
    recovered.activeFiles.map((file) => file.fileName),
    ['seq_10-18.jpg'],
  );
  assert.deepEqual(recovered.deletedRanges, [{ end: 9, start: 1 }]);
  assert.deepEqual(recovered.deletedSources, [
    {
      checksumSha256: 'a'.repeat(64),
      end: 9,
      fileName: 'seq_1-9.jpg',
      sourceIndex: null,
      sourcePath: null,
      start: 1,
    },
  ]);
  assert.deepEqual(recovered.filledGapEntries, []);
  assert.equal(recovered.pendingOperation, null);
  assert.throws(
    () =>
      finalizePendingRepairOperation(
        { ...manifest, pendingOperation },
        'present',
        '2026-08-30T00:02:00.000Z',
      ),
    /REPAIR_PENDING_OPERATION_NOT_APPLIED/,
  );
});

test('derives only active, checksummed fills for the crop handoff', () => {
  const base = createRepairManifest({
    bounds: { end: 27, start: 1 },
    files: sortAndValidateSequenceFiles(['seq_1-9.jpg']),
    now: '2026-09-04T10:00:00.000Z',
    repairKey: 'repair-1',
    selectedDirectoryName: 'selected',
  });
  const fill = {
    checksumSha256: 'a'.repeat(64),
    expectedFileState: 'present',
    fileName: 'seq_10-18.jpg',
    id: 'fill-1',
    kind: 'fill',
    occurredAt: '2026-09-04T10:01:00.000Z',
    rangeEnd: 18,
    rangeStart: 10,
    sourceIndex: 7,
    sourcePath: 'better/photo-7.jpg',
  };
  const filled = finalizePendingRepairOperation(
    { ...base, pendingOperation: fill },
    'present',
    '2026-09-04T10:02:00.000Z',
  );
  const handoff = deriveFilledGapsManifest(filled);
  assert.deepEqual(handoff.entries, [
    {
      checksumSha256: 'a'.repeat(64),
      end: 18,
      fileName: 'seq_10-18.jpg',
      fillOperationId: 'fill-1',
      filledAt: '2026-09-04T10:01:00.000Z',
      sourceIndex: 7,
      sourcePath: 'better/photo-7.jpg',
      start: 10,
    },
  ]);
  assert.equal(validateFilledGapsManifest(handoff), handoff);

  const undo = {
    ...fill,
    expectedFileState: 'absent',
    id: 'undo-1',
    kind: 'undo_fill',
    occurredAt: '2026-09-04T10:03:00.000Z',
  };
  const undone = finalizePendingRepairOperation(
    { ...filled, pendingOperation: undo },
    'absent',
    '2026-09-04T10:04:00.000Z',
  );
  assert.deepEqual(deriveFilledGapsManifest(undone).entries, []);
});

test('migrates legacy history to compact active fills and deletion receipts', () => {
  const legacy = {
    activeFiles: [
      {
        checksumSha256: 'a'.repeat(64),
        end: 9,
        fileName: 'seq_1-9.jpg',
        start: 1,
      },
      {
        checksumSha256: 'b'.repeat(64),
        end: 18,
        fileName: 'seq_10-18.jpg',
        start: 10,
      },
    ],
    collectionEnd: 36,
    collectionStart: 1,
    deletedRanges: [{ end: 27, start: 19 }],
    operations: [
      {
        checksumSha256: 'b'.repeat(64),
        fileName: 'seq_10-18.jpg',
        id: 'fill-active',
        kind: 'fill',
        occurredAt: '2026-09-15T10:00:00.000Z',
        rangeEnd: 18,
        rangeStart: 10,
        sourceIndex: 4,
        sourcePath: 'source/fill.jpg',
      },
      {
        checksumSha256: 'c'.repeat(64),
        fileName: 'seq_19-27.jpg',
        id: 'delete-active',
        kind: 'delete',
        occurredAt: '2026-09-15T10:01:00.000Z',
        rangeEnd: 27,
        rangeStart: 19,
        sourceIndex: 7,
        sourcePath: 'source/deleted.jpg',
      },
      {
        checksumSha256: 'd'.repeat(64),
        fileName: 'seq_28-36.jpg',
        id: 'restore-old',
        kind: 'restore',
        occurredAt: '2026-09-15T10:02:00.000Z',
        rangeEnd: 36,
        rangeStart: 28,
        sourceIndex: null,
        sourcePath: null,
      },
    ],
    pendingOperation: null,
    repairKey: 'legacy-repair',
    revision: 4,
    schemaVersion: 'manual-image-selection-repair-v1',
    selectedDirectoryName: 'selected',
    updatedAt: '2026-09-15T10:03:00.000Z',
  };
  const migrated = migrateLegacyRepairManifest(legacy);
  assert.equal(migrated.schemaVersion, 'manual-image-selection-repair-v2');
  assert.equal('operations' in migrated, false);
  assert.deepEqual(migrated.filledGapEntries, [
    {
      checksumSha256: 'b'.repeat(64),
      end: 18,
      fileName: 'seq_10-18.jpg',
      fillOperationId: 'fill-active',
      filledAt: '2026-09-15T10:00:00.000Z',
      sourceIndex: 4,
      sourcePath: 'source/fill.jpg',
      start: 10,
    },
  ]);
  assert.deepEqual(migrated.deletedSources, [
    {
      checksumSha256: 'c'.repeat(64),
      end: 27,
      fileName: 'seq_19-27.jpg',
      sourceIndex: 7,
      sourcePath: 'source/deleted.jpg',
      start: 19,
    },
  ]);
});
