import assert from 'node:assert/strict';
import test from 'node:test';

import {
  acceptRequiredSelectedImageCropCorrections,
  canAdoptActiveSelectedImageCropPolicy,
  clearSelectedImageCropFailure,
  selectedImageCropReviewReason,
  requiredSelectedImageCropCorrections,
  materializeSelectedImageCropManifestV1,
  markSelectedImageCropCorrected,
  migrateSelectedImageCropManifestV1,
  recordSelectedImageCropFailure,
  recoverSelectedImageCropPendingBatch,
  replaceSelectedImageCropCorrections,
  selectedImageCropFileState,
  selectedImageCropAutomaticCorrectionRecalculationFileNames,
  selectedImageCropRecalculationFileNames,
  selectedImageCropShardIndex,
  updateSelectedImageCropCorrections,
} from '../src/crop-session.ts';

const HASH_A = 'a'.repeat(64);
const HASH_B = 'b'.repeat(64);
const HASH_C = 'c'.repeat(64);
const HASH_D = 'd'.repeat(64);
const HASH_E = 'e'.repeat(64);

test('only a completely pristine versionless crop snapshot may adopt the active policy', () => {
  const migrated = migrateSelectedImageCropManifestV1(manifest(3));
  const pristine = {
    ...migrated,
    session: {
      ...migrated.session,
      currentIndex: 0,
      failures: [],
      pendingOperation: null,
      preparationPolicyVersion: null,
    },
    review: {
      ...migrated.review,
      acceptedSuggestionFileNames: [],
      completedAt: null,
      correctedFileNames: [],
      correctionFileNames: [],
      reviewedFileNames: [],
    },
    shards: migrated.shards.map((shard) => ({ ...shard, results: {} })),
  };

  assert.equal(canAdoptActiveSelectedImageCropPolicy(pristine), true);
  assert.equal(
    canAdoptActiveSelectedImageCropPolicy({
      ...pristine,
      session: { ...pristine.session, preparationPolicyVersion: 'known-v10' },
    }),
    false,
  );
  assert.equal(
    canAdoptActiveSelectedImageCropPolicy({
      ...pristine,
      session: {
        ...pristine.session,
        failures: [
          {
            code: 'BROKEN_JPEG',
            failedAt: '2026-09-14T18:00:00.000Z',
            fileName: pristine.inventory.entries[0].fileName,
            stage: 'decode',
          },
        ],
      },
    }),
    false,
  );
  assert.equal(
    canAdoptActiveSelectedImageCropPolicy({
      ...pristine,
      session: {
        ...pristine.session,
        pendingOperation: { kind: 'write_crop' },
      },
    }),
    false,
  );
  assert.equal(
    canAdoptActiveSelectedImageCropPolicy({
      ...pristine,
      session: {
        ...pristine.session,
        pendingBatch: [
          pendingOperation(pristine.inventory.entries[0].fileName, HASH_C),
        ],
      },
    }),
    false,
  );
  assert.equal(
    canAdoptActiveSelectedImageCropPolicy({
      ...pristine,
      shards: migrated.shards,
    }),
    false,
  );
  for (const field of [
    'reviewedFileNames',
    'correctionFileNames',
    'acceptedSuggestionFileNames',
    'correctedFileNames',
  ]) {
    assert.equal(
      canAdoptActiveSelectedImageCropPolicy({
        ...pristine,
        review: {
          ...pristine.review,
          [field]: [pristine.inventory.entries[0].fileName],
        },
      }),
      false,
      field,
    );
  }
  assert.equal(
    canAdoptActiveSelectedImageCropPolicy({
      ...pristine,
      review: {
        ...pristine.review,
        completedAt: '2026-09-14T18:00:00.000Z',
      },
    }),
    false,
  );
});

test('top-row confidence cannot hide a persisted failed bottom-boundary proof', () => {
  const proposal = {
    classification: 'high_confidence',
    evidence: { fallbackReason: 'no_wide_evidence' },
  };
  assert.equal(selectedImageCropReviewReason(proposal), 'no_wide_evidence');
  const snapshot = migrateSelectedImageCropManifestV1(manifest(3));
  const name = snapshot.inventory.entries[0].fileName;
  snapshot.review.reviewedFileNames = [];
  snapshot.shards[0].results[name].autoCropProposal = proposal;
  const restored = JSON.parse(JSON.stringify(snapshot));
  restored.review = replaceSelectedImageCropCorrections(restored.review, []);
  assert.deepEqual(requiredSelectedImageCropCorrections(restored), [name]);
  assert.equal(selectedImageCropFileState(restored, name), 'needs_correction');
  restored.review = markSelectedImageCropCorrected(restored.review, name);
  assert.deepEqual(requiredSelectedImageCropCorrections(restored), []);
  assert.deepEqual(snapshot.shards[0].results[name].autoCropProposal, proposal);
});

test('bulk review accepts automatic warnings without consuming explicit correction selections', () => {
  const snapshot = migrateSelectedImageCropManifestV1(manifest(4));
  const names = snapshot.inventory.entries.map((entry) => entry.fileName);
  snapshot.review = {
    ...snapshot.review,
    reviewedFileNames: [],
    correctionFileNames: [names[0]],
    acceptedSuggestionFileNames: [],
    correctedFileNames: [],
  };
  snapshot.shards[0].results[names[0]].autoCropProposal = {
    classification: 'conservative',
    evidence: { fallbackReason: 'crop_too_short' },
  };
  snapshot.shards[0].results[names[1]].autoCropProposal = {
    classification: 'conservative',
    evidence: { fallbackReason: 'no_wide_evidence' },
  };

  const accepted = acceptRequiredSelectedImageCropCorrections(snapshot);

  assert.deepEqual(accepted.correctionFileNames, [names[0]]);
  assert.deepEqual(accepted.acceptedSuggestionFileNames, [names[1]]);
  assert.equal(accepted.completedAt, null);
});

test('operator can accept one automatic warning without sending it to correction', () => {
  const snapshot = migrateSelectedImageCropManifestV1(manifest(3));
  const name = snapshot.inventory.entries[0].fileName;
  snapshot.review.reviewedFileNames = [];
  snapshot.shards[0].results[name].autoCropProposal = {
    classification: 'conservative',
    evidence: { fallbackReason: null },
  };

  const accepted = updateSelectedImageCropCorrections(
    snapshot.review,
    name,
    false,
    true,
  );
  const restored = { ...snapshot, review: accepted };

  assert.deepEqual(requiredSelectedImageCropCorrections(restored), []);
  assert.deepEqual(accepted.acceptedSuggestionFileNames, [name]);
  assert.equal(selectedImageCropFileState(restored, name), 'reviewed');
});

test('review decisions override warnings but conflict cannot become an automatic success', () => {
  assert.equal(
    selectedImageCropReviewReason({
      structural: { status: 'detected' },
      registration: {
        status: 'needs_manual_crop',
        reason: 'structural_registration_conflict',
      },
    }),
    'structural_registration_conflict',
  );
  assert.equal(
    selectedImageCropReviewReason({
      structural: { status: 'detected' },
      registration: {
        status: 'needs_manual_crop',
        reason: 'insufficient_matches',
      },
    }),
    null,
  );
  assert.equal(
    selectedImageCropReviewReason({
      classification: 'conservative',
      evidence: { fallbackReason: null },
    }),
    'unconfirmed_crop_boundaries',
  );
  assert.equal(
    selectedImageCropReviewReason({
      classification: 'high_confidence',
      evidence: { fallbackReason: null },
    }),
    null,
  );
  assert.equal(selectedImageCropReviewReason(undefined), null);
});

function manifest(count = 130) {
  return {
    schemaVersion: 1,
    rendererVersion: 'manual-selected-image-band-crop-jpeg-v1',
    sourceDirectoryName: 'picked',
    outputDirectoryName: 'picked cut',
    sourceInventoryChecksumSha256: HASH_A,
    revision: 42,
    currentIndex: 98,
    entries: Array.from({ length: count }, (_, index) => ({
      fileName: `seq_${index * 9 + 1}-${index * 9 + 9}.jpg`,
      sizeBytes: 100,
      lastModifiedMs: index,
      rangeStart: index * 9 + 1,
      rangeEnd: index * 9 + 9,
      result:
        index < count - 2
          ? {
              status: 'accepted',
              crop: { width: 1080, height: 1920, topY: 400, bottomY: 1100 },
              sourceChecksumSha256: HASH_A,
              outputChecksumSha256: HASH_B,
              acceptedAt: '2026-09-04T10:00:00.000Z',
            }
          : null,
    })),
    reviewedFileNames: Array.from(
      { length: 98 },
      (_, index) => `seq_${index * 9 + 1}-${index * 9 + 9}.jpg`,
    ),
    pendingOperation: null,
    updatedAt: '2026-09-04T10:00:00.000Z',
  };
}

function pendingOperation(fileName, outputChecksumSha256) {
  return {
    kind: 'write_crop',
    fileName,
    expectedSourceChecksumSha256: HASH_A,
    expectedOutputChecksumSha256: outputChecksumSha256,
    crop: { width: 1080, height: 1920, topY: 400, bottomY: 1100 },
    startedAt: '2026-09-15T07:59:00.000Z',
    replacesOutputChecksumSha256: null,
    markReviewed: false,
  };
}

test('migrates prepared and reviewed state without rerendering results', () => {
  const source = manifest();
  const snapshot = migrateSelectedImageCropManifestV1(source);
  assert.equal(snapshot.session.pendingBatch, null);
  assert.equal(snapshot.shards.length, 3);
  assert.equal(Object.keys(snapshot.shards[0].results).length, 64);
  assert.equal(Object.keys(snapshot.shards[1].results).length, 64);
  assert.equal(Object.keys(snapshot.shards[2].results).length, 0);
  assert.equal(snapshot.review.reviewedFileNames.length, 98);
  assert.deepEqual(materializeSelectedImageCropManifestV1(snapshot), source);
});

test('recovers a partially written crop batch and remains idempotent after shard publication', () => {
  const source = manifest(4);
  source.entries = source.entries.map((entry) => ({ ...entry, result: null }));
  source.reviewedFileNames = [];
  source.currentIndex = 0;
  const base = migrateSelectedImageCropManifestV1(source);
  const names = base.inventory.entries.map((entry) => entry.fileName);
  const operations = [
    pendingOperation(names[0], HASH_C),
    pendingOperation(names[1], HASH_D),
    pendingOperation(names[2], HASH_E),
    pendingOperation(names[3], HASH_C),
  ];
  const pending = {
    ...base,
    session: { ...base.session, pendingBatch: operations },
  };

  const recovered = recoverSelectedImageCropPendingBatch(
    pending,
    {
      [names[0]]: HASH_C,
      [names[1]]: HASH_D,
      [names[2]]: null,
      [names[3]]: HASH_B,
    },
    '2026-09-15T08:00:00.000Z',
  );

  assert.equal(recovered.snapshot.session.pendingBatch, null);
  assert.deepEqual(recovered.missingFileNames, [names[2]]);
  assert.deepEqual(recovered.touchedShardFileNames, [names[3]]);
  assert.equal(
    recovered.snapshot.shards[0].results[names[0]].outputChecksumSha256,
    HASH_C,
  );
  assert.equal(
    recovered.snapshot.shards[0].results[names[1]].outputChecksumSha256,
    HASH_D,
  );
  assert.equal(recovered.snapshot.shards[0].results[names[2]], undefined);
  assert.equal(
    recovered.snapshot.shards[0].results[names[3]].outputChecksumSha256,
    HASH_B,
  );
  assert.deepEqual(recovered.snapshot.review.correctionFileNames, [names[3]]);

  const afterShardBeforeSession = {
    ...recovered.snapshot,
    session: pending.session,
  };
  const replayed = recoverSelectedImageCropPendingBatch(
    afterShardBeforeSession,
    {
      [names[0]]: HASH_C,
      [names[1]]: HASH_D,
      [names[2]]: null,
      [names[3]]: HASH_B,
    },
    '2026-09-15T08:01:00.000Z',
  );
  assert.equal(replayed.snapshot.session.pendingBatch, null);
  assert.deepEqual(replayed.touchedShardFileNames, []);
  assert.deepEqual(replayed.missingFileNames, [names[2]]);
  assert.deepEqual(replayed.snapshot.review.correctionFileNames, [names[3]]);
});

test('pending batch entries are reported as processing', () => {
  const snapshot = migrateSelectedImageCropManifestV1(manifest(3));
  const name = snapshot.inventory.entries[2].fileName;
  snapshot.session.pendingBatch = [pendingOperation(name, HASH_C)];
  assert.equal(selectedImageCropFileState(snapshot, name), 'processing');
});

test('batch recovery requests one write for each touched result shard', () => {
  const source = manifest(66);
  source.entries = source.entries.map((entry) => ({ ...entry, result: null }));
  source.reviewedFileNames = [];
  source.currentIndex = 0;
  const base = migrateSelectedImageCropManifestV1(source);
  const names = base.inventory.entries.map((entry) => entry.fileName);
  const selectedNames = names.slice(62, 66);
  const pending = {
    ...base,
    session: {
      ...base.session,
      pendingBatch: selectedNames.map((name) => pendingOperation(name, HASH_C)),
    },
  };

  const recovered = recoverSelectedImageCropPendingBatch(
    pending,
    Object.fromEntries(selectedNames.map((name) => [name, HASH_C])),
    '2026-09-15T08:02:00.000Z',
  );

  assert.deepEqual(recovered.touchedShardFileNames, [
    selectedNames[1],
    selectedNames[3],
  ]);
  assert.equal(
    recovered.snapshot.shards[0].results[selectedNames[1]].outputChecksumSha256,
    HASH_C,
  );
  assert.equal(
    recovered.snapshot.shards[1].results[selectedNames[3]].outputChecksumSha256,
    HASH_C,
  );
});

test('replaces a bulk correction selection deterministically', () => {
  const review = {
    schemaVersion: 2,
    reviewedFileNames: [],
    correctionFileNames: ['seq_1-9.jpg'],
    correctedFileNames: [],
    correctionCursor: 7,
    completedAt: '2026-09-05T10:00:00.000Z',
  };
  const updated = replaceSelectedImageCropCorrections(review, [
    'seq_10-18.jpg',
    'seq_19-27.jpg',
    'seq_10-18.jpg',
  ]);
  assert.deepEqual(updated.correctionFileNames, [
    'seq_10-18.jpg',
    'seq_19-27.jpg',
  ]);
  assert.equal(updated.correctionCursor, 1);
  assert.equal(updated.completedAt, null);
});

test('preserves the reported 2815 of 2817 recovery checkpoint', () => {
  const snapshot = migrateSelectedImageCropManifestV1(manifest(2817));
  const restored = materializeSelectedImageCropManifestV1(snapshot);
  assert.equal(snapshot.shards.length, 45);
  assert.equal(
    restored.entries.filter((entry) => entry.result !== null).length,
    2815,
  );
  assert.deepEqual(
    restored.entries.slice(-2).map((entry) => entry.fileName),
    ['seq_25336-25344.jpg', 'seq_25345-25353.jpg'],
  );
  assert.equal(snapshot.review.reviewedFileNames.length, 98);
});

test('maps result indices to bounded shards', () => {
  assert.equal(selectedImageCropShardIndex(0), 0);
  assert.equal(selectedImageCropShardIndex(63), 0);
  assert.equal(selectedImageCropShardIndex(64), 1);
});

test('persists correction selection and isolated preparation failures', () => {
  const snapshot = migrateSelectedImageCropManifestV1(manifest(3));
  const selected = updateSelectedImageCropCorrections(
    snapshot.review,
    'seq_1-9.jpg',
    true,
  );
  assert.deepEqual(selected.correctionFileNames, ['seq_1-9.jpg']);
  const corrected = markSelectedImageCropCorrected(selected, 'seq_1-9.jpg');
  assert.deepEqual(corrected.correctionFileNames, []);
  assert.deepEqual(corrected.correctedFileNames, ['seq_1-9.jpg']);
  const failed = recordSelectedImageCropFailure(snapshot.session, {
    fileName: 'seq_19-27.jpg',
    stage: 'render',
    code: 'ENCODING_FAILED',
    failedAt: '2026-09-04T11:00:00.000Z',
  });
  assert.equal(failed.failures.length, 1);
  assert.equal(
    clearSelectedImageCropFailure(
      failed,
      'seq_19-27.jpg',
      '2026-09-04T11:01:00.000Z',
    ).failures.length,
    0,
  );
});

test('derives every durable file state without duplicating it in shards', () => {
  const migrated = migrateSelectedImageCropManifestV1(manifest(103));
  const preparedName = migrated.inventory.entries[98].fileName;
  const queuedName = migrated.inventory.entries[102].fileName;
  const failedName = migrated.inventory.entries[101].fileName;
  const correctionName = migrated.inventory.entries[0].fileName;
  const correctedName = migrated.inventory.entries[1].fileName;
  const snapshot = {
    ...migrated,
    session: recordSelectedImageCropFailure(migrated.session, {
      fileName: failedName,
      stage: 'decode',
      code: 'BROKEN_JPEG',
      failedAt: '2026-09-04T11:00:00.000Z',
    }),
    review: {
      ...migrated.review,
      correctionFileNames: [correctionName],
      correctedFileNames: [correctedName],
    },
  };

  assert.equal(
    selectedImageCropFileState(snapshot, correctionName),
    'needs_correction',
  );
  assert.equal(
    selectedImageCropFileState(snapshot, correctedName),
    'corrected',
  );
  assert.equal(selectedImageCropFileState(snapshot, preparedName), 'prepared');
  assert.equal(selectedImageCropFileState(snapshot, failedName), 'failed');
  assert.equal(selectedImageCropFileState(snapshot, queuedName), 'queued');
});

test('recalculates only prepared results untouched by review or correction', () => {
  const migrated = migrateSelectedImageCropManifestV1(manifest(6));
  const preparedNames = migrated.inventory.entries
    .slice(0, 4)
    .map((entry) => entry.fileName);
  const snapshot = {
    ...migrated,
    review: {
      ...migrated.review,
      reviewedFileNames: [preparedNames[0]],
      correctionFileNames: [preparedNames[1]],
      correctedFileNames: [preparedNames[2]],
    },
  };
  assert.deepEqual(selectedImageCropRecalculationFileNames(snapshot), [
    preparedNames[3],
  ]);
  assert.equal(migrated.session.preparationPolicyVersion, null);
});

test('recalculates automatic correction warnings but protects operator-only selections', () => {
  const migrated = migrateSelectedImageCropManifestV1(manifest(6));
  const names = migrated.inventory.entries.map((entry) => entry.fileName);
  migrated.review = {
    ...migrated.review,
    reviewedFileNames: [],
    correctedFileNames: [],
    acceptedSuggestionFileNames: [],
    correctionFileNames: [names[0], names[1]],
  };
  migrated.shards[0].results[names[0]].autoCropProposal = {
    classification: 'high_confidence',
    evidence: { fallbackReason: 'crop_too_short' },
  };
  migrated.shards[0].results[names[1]].autoCropProposal = {
    classification: 'high_confidence',
    evidence: { fallbackReason: null },
  };
  migrated.shards[0].results[names[2]].autoCropProposal = {
    classification: 'conservative',
    evidence: { fallbackReason: null },
  };
  migrated.review.reviewedFileNames = [names[2]];

  assert.deepEqual(
    selectedImageCropAutomaticCorrectionRecalculationFileNames(migrated),
    [names[0]],
  );

  migrated.review.acceptedSuggestionFileNames = [names[0]];
  assert.deepEqual(
    selectedImageCropAutomaticCorrectionRecalculationFileNames(migrated),
    [],
  );
});
