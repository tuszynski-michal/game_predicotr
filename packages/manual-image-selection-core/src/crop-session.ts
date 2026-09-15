import {
  beginSelectedImageCropWrite,
  finalizeRecoveredSelectedImageCropWrite,
  finalizeSelectedImageCropWrite,
  rollbackSelectedImageCropWrite,
  type SelectedImageCropBand,
  type SelectedImageCropManifestV1,
  type SelectedImageCropPendingOperation,
  type SelectedImageCropResult,
  type SelectedImageCropSourceEntry,
} from '@game-predictor/manual-image-selection-core/crop';
import type { SelectedImageAutoCropProposal } from './auto-crop.ts';

/** Review policy only: never changes persisted detector pixels or fingerprints. */
export function selectedImageCropReviewReason(
  proposal: SelectedImageAutoCropProposal | null | undefined,
): string | null {
  if (!proposal) return null;
  if (proposal.registration?.reason === 'structural_registration_conflict')
    return 'structural_registration_conflict';
  if (proposal.registration?.status === 'registered') return null;
  if (proposal.structural)
    return proposal.structural.status === 'detected'
      ? null
      : proposal.structural.reason;
  // V10 can promote a top-row refinement to high_confidence while retaining
  // the unverified lower boundary and fallback evidence from its baseline.
  if (proposal.evidence.fallbackReason) return proposal.evidence.fallbackReason;
  if (proposal.classification !== 'high_confidence')
    return 'unconfirmed_crop_boundaries';
  return null;
}

export const SELECTED_IMAGE_CROP_SESSION_SCHEMA_VERSION = 2 as const;
export const SELECTED_IMAGE_CROP_RESULT_SHARD_SIZE = 64 as const;

export type SelectedImageCropPreparationStage =
  'decode' | 'detect' | 'render' | 'write' | 'verify';

export interface SelectedImageCropPreparationFailure {
  readonly fileName: string;
  readonly stage: SelectedImageCropPreparationStage;
  readonly code: string;
  readonly failedAt: string;
}

export interface SelectedImageCropInventoryV2 {
  readonly schemaVersion: typeof SELECTED_IMAGE_CROP_SESSION_SCHEMA_VERSION;
  readonly sourceDirectoryName: string;
  readonly outputDirectoryName: string;
  readonly sourceInventoryChecksumSha256: string;
  readonly entries: readonly SelectedImageCropSourceEntry[];
}

export interface SelectedImageCropSessionV2 {
  readonly schemaVersion: typeof SELECTED_IMAGE_CROP_SESSION_SCHEMA_VERSION;
  readonly revision: number;
  readonly currentIndex: number;
  readonly pendingOperation: SelectedImageCropPendingOperation | null;
  /**
   * Compatible v2 extension used only by automatic batch publication.
   * Historical snapshots omit the field and readers normalize it to null.
   */
  readonly pendingBatch: readonly SelectedImageCropPendingOperation[] | null;
  readonly failures: readonly SelectedImageCropPreparationFailure[];
  /** Null or absent identifies a historical session that predates policy pinning. */
  readonly preparationPolicyVersion?: string | null;
  readonly updatedAt: string;
}

export interface SelectedImageCropReviewV2 {
  readonly schemaVersion: typeof SELECTED_IMAGE_CROP_SESSION_SCHEMA_VERSION;
  readonly reviewedFileNames: readonly string[];
  readonly correctionFileNames: readonly string[];
  /** Operator accepted an automatic warning without changing the crop. */
  readonly acceptedSuggestionFileNames?: readonly string[];
  readonly correctionCursor: number;
  readonly correctedFileNames: readonly string[];
  readonly completedAt: string | null;
}

export interface SelectedImageCropResultShardV2 {
  readonly schemaVersion: typeof SELECTED_IMAGE_CROP_SESSION_SCHEMA_VERSION;
  readonly shardIndex: number;
  readonly results: Readonly<Record<string, SelectedImageCropResult>>;
}

export interface SelectedImageCropSessionSnapshotV2 {
  readonly inventory: SelectedImageCropInventoryV2;
  readonly session: SelectedImageCropSessionV2;
  readonly review: SelectedImageCropReviewV2;
  readonly shards: readonly SelectedImageCropResultShardV2[];
}

/**
 * A versionless snapshot may adopt today's active detector only before any
 * durable work or operator decision exists.
 */
export function canAdoptActiveSelectedImageCropPolicy(
  snapshot: SelectedImageCropSessionSnapshotV2,
): boolean {
  return (
    snapshot.session.preparationPolicyVersion == null &&
    snapshot.session.pendingOperation === null &&
    snapshot.session.pendingBatch === null &&
    snapshot.session.failures.length === 0 &&
    snapshot.shards.every((shard) => Object.keys(shard.results).length === 0) &&
    snapshot.review.reviewedFileNames.length === 0 &&
    snapshot.review.correctionFileNames.length === 0 &&
    (snapshot.review.acceptedSuggestionFileNames ?? []).length === 0 &&
    snapshot.review.correctedFileNames.length === 0 &&
    snapshot.review.completedAt === null
  );
}

export type SelectedImageCropFileState =
  | 'queued'
  | 'processing'
  | 'prepared'
  | 'failed'
  | 'reviewed'
  | 'needs_correction'
  | 'corrected';

export function selectedImageCropFileState(
  snapshot: SelectedImageCropSessionSnapshotV2,
  fileName: string,
): SelectedImageCropFileState {
  if (snapshot.session.pendingOperation?.fileName === fileName)
    return 'processing';
  if (
    snapshot.session.pendingBatch?.some(
      (operation) => operation.fileName === fileName,
    )
  )
    return 'processing';
  if (requiredSelectedImageCropCorrections(snapshot).includes(fileName))
    return 'needs_correction';
  if (snapshot.review.correctionFileNames.includes(fileName))
    return 'needs_correction';
  if (snapshot.review.correctedFileNames.includes(fileName)) return 'corrected';
  if (snapshot.review.reviewedFileNames.includes(fileName)) return 'reviewed';
  if ((snapshot.review.acceptedSuggestionFileNames ?? []).includes(fileName))
    return 'reviewed';
  if (snapshot.session.failures.some((item) => item.fileName === fileName))
    return 'failed';
  if (snapshot.shards.some((shard) => fileName in shard.results))
    return 'prepared';
  return 'queued';
}

export function requiredSelectedImageCropCorrections(
  snapshot: SelectedImageCropSessionSnapshotV2,
): readonly string[] {
  const resolved = new Set([
    ...snapshot.review.reviewedFileNames,
    ...snapshot.review.correctedFileNames,
    ...(snapshot.review.acceptedSuggestionFileNames ?? []),
  ]);
  return snapshot.shards.flatMap((shard) =>
    Object.entries(shard.results)
      .filter(
        ([name, result]) =>
          !resolved.has(name) &&
          selectedImageCropReviewReason(result.autoCropProposal) !== null,
      )
      .map(([name]) => name),
  );
}

export function effectiveSelectedImageCropCorrections(
  snapshot: SelectedImageCropSessionSnapshotV2,
): readonly string[] {
  const names = new Set([
    ...snapshot.review.correctionFileNames,
    ...requiredSelectedImageCropCorrections(snapshot),
  ]);
  return snapshot.inventory.entries
    .filter((entry) => names.has(entry.fileName))
    .map((entry) => entry.fileName);
}

export function acceptRequiredSelectedImageCropCorrections(
  snapshot: SelectedImageCropSessionSnapshotV2,
): SelectedImageCropReviewV2 {
  const acceptedSuggestions = new Set(
    snapshot.review.acceptedSuggestionFileNames ?? [],
  );
  const selected = new Set(snapshot.review.correctionFileNames);
  for (const fileName of requiredSelectedImageCropCorrections(snapshot)) {
    if (!selected.has(fileName)) acceptedSuggestions.add(fileName);
  }
  return {
    ...snapshot.review,
    acceptedSuggestionFileNames: [...acceptedSuggestions],
    completedAt: null,
  };
}

export function selectedImageCropRecalculationFileNames(
  snapshot: SelectedImageCropSessionSnapshotV2,
): readonly string[] {
  const protectedNames = new Set([
    ...requiredSelectedImageCropCorrections(snapshot),
    ...snapshot.review.reviewedFileNames,
    ...snapshot.review.correctedFileNames,
    ...(snapshot.review.acceptedSuggestionFileNames ?? []),
    ...snapshot.review.correctionFileNames,
  ]);
  const preparedNames = new Set(
    snapshot.shards.flatMap((shard) => Object.keys(shard.results)),
  );
  return snapshot.inventory.entries
    .map((entry) => entry.fileName)
    .filter(
      (fileName) =>
        preparedNames.has(fileName) && !protectedNames.has(fileName),
    );
}

/**
 * Automatic warnings may be recalculated by an explicit detector-upgrade
 * action. A file selected only by the operator has no persisted detector
 * reason and remains protected.
 */
export function selectedImageCropAutomaticCorrectionRecalculationFileNames(
  snapshot: SelectedImageCropSessionSnapshotV2,
): readonly string[] {
  const required = new Set(requiredSelectedImageCropCorrections(snapshot));
  return snapshot.inventory.entries
    .map((entry) => entry.fileName)
    .filter((fileName) => required.has(fileName));
}

export function migrateSelectedImageCropManifestV1(
  manifest: SelectedImageCropManifestV1,
): SelectedImageCropSessionSnapshotV2 {
  const results = manifest.entries.flatMap((entry) =>
    entry.result === null ? [] : [[entry.fileName, entry.result] as const],
  );
  const reviewed = manifest.reviewedFileNames ?? results.map(([name]) => name);
  return {
    inventory: {
      schemaVersion: 2,
      sourceDirectoryName: manifest.sourceDirectoryName,
      outputDirectoryName: manifest.outputDirectoryName,
      sourceInventoryChecksumSha256: manifest.sourceInventoryChecksumSha256,
      entries: manifest.entries.map(({ result: _result, ...entry }) => entry),
    },
    session: {
      schemaVersion: 2,
      revision: manifest.revision,
      currentIndex: manifest.currentIndex,
      pendingOperation: manifest.pendingOperation,
      pendingBatch: null,
      failures: [],
      preparationPolicyVersion: null,
      updatedAt: manifest.updatedAt,
    },
    review: {
      schemaVersion: 2,
      reviewedFileNames: [...reviewed],
      correctionFileNames: [],
      acceptedSuggestionFileNames: [],
      correctionCursor: 0,
      correctedFileNames: [],
      completedAt:
        reviewed.length === manifest.entries.length ? manifest.updatedAt : null,
    },
    shards: Array.from(
      {
        length: Math.ceil(
          manifest.entries.length / SELECTED_IMAGE_CROP_RESULT_SHARD_SIZE,
        ),
      },
      (_, shardIndex) => ({
        schemaVersion: 2 as const,
        shardIndex,
        results: Object.fromEntries(
          manifest.entries
            .slice(
              shardIndex * SELECTED_IMAGE_CROP_RESULT_SHARD_SIZE,
              (shardIndex + 1) * SELECTED_IMAGE_CROP_RESULT_SHARD_SIZE,
            )
            .flatMap((entry) =>
              entry.result === null
                ? []
                : [[entry.fileName, entry.result] as const],
            ),
        ),
      }),
    ),
  };
}

export function buildSelectedImageCropResultShards(
  results: readonly (readonly [string, SelectedImageCropResult])[],
): readonly SelectedImageCropResultShardV2[] {
  const shards: SelectedImageCropResultShardV2[] = [];
  for (
    let offset = 0;
    offset < results.length;
    offset += SELECTED_IMAGE_CROP_RESULT_SHARD_SIZE
  ) {
    const slice = results.slice(
      offset,
      offset + SELECTED_IMAGE_CROP_RESULT_SHARD_SIZE,
    );
    shards.push({
      schemaVersion: 2,
      shardIndex: Math.floor(offset / SELECTED_IMAGE_CROP_RESULT_SHARD_SIZE),
      results: Object.fromEntries(slice),
    });
  }
  return shards;
}

export function selectedImageCropShardIndex(entryIndex: number): number {
  if (!Number.isInteger(entryIndex) || entryIndex < 0)
    throw new Error('SELECTED_IMAGE_CROP_ENTRY_INDEX_INVALID');
  return Math.floor(entryIndex / SELECTED_IMAGE_CROP_RESULT_SHARD_SIZE);
}

export function materializeSelectedImageCropManifestV1(
  snapshot: SelectedImageCropSessionSnapshotV2,
): SelectedImageCropManifestV1 {
  const results = new Map(
    snapshot.shards.flatMap((shard) => Object.entries(shard.results)),
  );
  return {
    schemaVersion: 1,
    rendererVersion: 'manual-selected-image-band-crop-jpeg-v1',
    sourceDirectoryName: snapshot.inventory.sourceDirectoryName,
    outputDirectoryName: snapshot.inventory.outputDirectoryName,
    sourceInventoryChecksumSha256:
      snapshot.inventory.sourceInventoryChecksumSha256,
    revision: snapshot.session.revision,
    currentIndex: snapshot.session.currentIndex,
    entries: snapshot.inventory.entries.map((entry) => ({
      ...entry,
      result: results.get(entry.fileName) ?? null,
    })),
    reviewedFileNames: snapshot.review.reviewedFileNames,
    pendingOperation: snapshot.session.pendingOperation,
    updatedAt: snapshot.session.updatedAt,
  };
}

export interface SelectedImageCropBatchRecoveryResult {
  readonly snapshot: SelectedImageCropSessionSnapshotV2;
  /** One representative file name for each shard that must be persisted. */
  readonly touchedShardFileNames: readonly string[];
  readonly missingFileNames: readonly string[];
}

/**
 * Materializes a pending automatic publication after a restart. JPEG bytes
 * remain the source of truth: matching files are finalized, missing files are
 * left queued, and differing bytes are retained but require review.
 */
export function recoverSelectedImageCropPendingBatch(
  snapshot: SelectedImageCropSessionSnapshotV2,
  observedOutputChecksums: Readonly<Record<string, string | null>>,
  now: string,
): SelectedImageCropBatchRecoveryResult {
  const pendingBatch = snapshot.session.pendingBatch ?? null;
  if (pendingBatch === null || pendingBatch.length === 0)
    return { snapshot, touchedShardFileNames: [], missingFileNames: [] };
  if (snapshot.session.pendingOperation !== null)
    throw new Error('SELECTED_IMAGE_CROP_OPERATION_ACTIVE');
  if (
    new Set(pendingBatch.map((operation) => operation.fileName)).size !==
    pendingBatch.length
  )
    throw new Error('SELECTED_IMAGE_CROP_BATCH_INVALID');

  let manifest = materializeSelectedImageCropManifestV1(snapshot);
  let recovered = snapshot;
  let review = snapshot.review;
  const touchedShardFiles = new Map<number, string>();
  const missingFileNames: string[] = [];

  for (const operation of pendingBatch) {
    const observed = observedOutputChecksums[operation.fileName] ?? null;
    const entryIndex = manifest.entries.findIndex(
      (entry) => entry.fileName === operation.fileName,
    );
    if (entryIndex < 0) throw new Error('SELECTED_IMAGE_CROP_SOURCE_UNKNOWN');
    const existing = manifest.entries[entryIndex]!.result;
    const existingMatchesObserved =
      observed !== null &&
      existing?.sourceChecksumSha256 ===
        operation.expectedSourceChecksumSha256 &&
      existing.outputChecksumSha256 === observed &&
      selectedImageCropBandsEqual(existing.crop, operation.crop);
    if (existingMatchesObserved) {
      manifest = advanceRecoveredSelectedImageCropManifest(
        manifest,
        entryIndex,
        now,
      );
      recovered = snapshotWithRecoveredManifest(recovered, manifest);
      if (observed !== operation.expectedOutputChecksumSha256)
        review = updateSelectedImageCropCorrections(
          review,
          operation.fileName,
          true,
        );
      continue;
    }
    if (
      existing?.outputChecksumSha256 === operation.expectedOutputChecksumSha256
    )
      throw new Error('SELECTED_IMAGE_CROP_OUTPUT_CHANGED');

    manifest = beginSelectedImageCropWrite(manifest, operation, now);
    if (observed === null) {
      manifest = rollbackSelectedImageCropWrite(manifest, now);
      recovered = snapshotWithRecoveredManifest(recovered, manifest);
      missingFileNames.push(operation.fileName);
      continue;
    }
    manifest =
      observed === operation.expectedOutputChecksumSha256
        ? finalizeSelectedImageCropWrite(manifest, now)
        : finalizeRecoveredSelectedImageCropWrite(manifest, observed, now);
    recovered = snapshotWithRecoveredResult(
      recovered,
      manifest,
      operation.fileName,
    );
    touchedShardFiles.set(
      selectedImageCropShardIndex(entryIndex),
      operation.fileName,
    );
    if (observed !== operation.expectedOutputChecksumSha256)
      review = updateSelectedImageCropCorrections(
        review,
        operation.fileName,
        true,
      );
  }

  const finalized = snapshotWithRecoveredManifest(recovered, manifest);
  return {
    snapshot: {
      ...finalized,
      session: { ...finalized.session, pendingBatch: null },
      review,
    },
    touchedShardFileNames: [...touchedShardFiles.values()],
    missingFileNames,
  };
}

function advanceRecoveredSelectedImageCropManifest(
  manifest: SelectedImageCropManifestV1,
  entryIndex: number,
  now: string,
): SelectedImageCropManifestV1 {
  return {
    ...manifest,
    revision: manifest.revision + 1,
    currentIndex: Math.max(
      manifest.currentIndex,
      Math.min(entryIndex + 1, manifest.entries.length - 1),
    ),
    updatedAt: now,
  };
}

function snapshotWithRecoveredManifest(
  snapshot: SelectedImageCropSessionSnapshotV2,
  manifest: SelectedImageCropManifestV1,
): SelectedImageCropSessionSnapshotV2 {
  return {
    ...snapshot,
    session: {
      ...snapshot.session,
      revision: manifest.revision,
      currentIndex: manifest.currentIndex,
      pendingOperation: manifest.pendingOperation,
      updatedAt: manifest.updatedAt,
    },
    review: {
      ...snapshot.review,
      reviewedFileNames: manifest.reviewedFileNames ?? [],
    },
  };
}

function snapshotWithRecoveredResult(
  snapshot: SelectedImageCropSessionSnapshotV2,
  manifest: SelectedImageCropManifestV1,
  fileName: string,
): SelectedImageCropSessionSnapshotV2 {
  const entryIndex = manifest.entries.findIndex(
    (entry) => entry.fileName === fileName,
  );
  const result = manifest.entries[entryIndex]?.result;
  if (entryIndex < 0 || result === null || result === undefined)
    throw new Error('SELECTED_IMAGE_CROP_RESULT_NOT_PREPARED');
  const shardIndex = selectedImageCropShardIndex(entryIndex);
  return {
    ...snapshotWithRecoveredManifest(snapshot, manifest),
    shards: snapshot.shards.map((shard) =>
      shard.shardIndex === shardIndex
        ? { ...shard, results: { ...shard.results, [fileName]: result } }
        : shard,
    ),
  };
}

function selectedImageCropBandsEqual(
  left: SelectedImageCropBand,
  right: SelectedImageCropBand,
): boolean {
  return (
    left.width === right.width &&
    left.height === right.height &&
    left.topY === right.topY &&
    left.bottomY === right.bottomY
  );
}

export function updateSelectedImageCropCorrections(
  review: SelectedImageCropReviewV2,
  fileName: string,
  selected: boolean,
  acceptAutomaticSuggestion = false,
): SelectedImageCropReviewV2 {
  const names = new Set(review.correctionFileNames);
  const acceptedSuggestions = new Set(review.acceptedSuggestionFileNames ?? []);
  if (selected) names.add(fileName);
  else names.delete(fileName);
  if (selected) acceptedSuggestions.delete(fileName);
  else if (acceptAutomaticSuggestion) acceptedSuggestions.add(fileName);
  return {
    ...review,
    correctionFileNames: [...names],
    acceptedSuggestionFileNames: [...acceptedSuggestions],
    correctionCursor: Math.min(
      review.correctionCursor,
      Math.max(0, names.size - 1),
    ),
    completedAt: null,
  };
}

export function replaceSelectedImageCropCorrections(
  review: SelectedImageCropReviewV2,
  fileNames: readonly string[],
  automaticSuggestionFileNames: readonly string[] = [],
): SelectedImageCropReviewV2 {
  const unique = [...new Set(fileNames)];
  const selected = new Set(unique);
  const acceptedSuggestions = new Set(review.acceptedSuggestionFileNames ?? []);
  for (const fileName of unique) acceptedSuggestions.delete(fileName);
  for (const fileName of automaticSuggestionFileNames) {
    if (!selected.has(fileName)) acceptedSuggestions.add(fileName);
  }
  return {
    ...review,
    correctionFileNames: unique,
    acceptedSuggestionFileNames: [...acceptedSuggestions],
    correctionCursor: Math.min(
      review.correctionCursor,
      Math.max(0, unique.length - 1),
    ),
    completedAt: null,
  };
}

export function markSelectedImageCropCorrected(
  review: SelectedImageCropReviewV2,
  fileName: string,
): SelectedImageCropReviewV2 {
  const corrections = review.correctionFileNames.filter(
    (name) => name !== fileName,
  );
  const corrected = new Set(review.correctedFileNames);
  const acceptedSuggestions = new Set(review.acceptedSuggestionFileNames ?? []);
  corrected.add(fileName);
  acceptedSuggestions.delete(fileName);
  const reviewed = new Set(review.reviewedFileNames);
  reviewed.add(fileName);
  return {
    ...review,
    reviewedFileNames: [...reviewed],
    correctionFileNames: corrections,
    acceptedSuggestionFileNames: [...acceptedSuggestions],
    correctedFileNames: [...corrected],
    correctionCursor: Math.min(
      review.correctionCursor,
      Math.max(0, corrections.length - 1),
    ),
    completedAt: null,
  };
}

export function recordSelectedImageCropFailure(
  session: SelectedImageCropSessionV2,
  failure: SelectedImageCropPreparationFailure,
): SelectedImageCropSessionV2 {
  return {
    ...session,
    revision: session.revision + 1,
    failures: [
      ...session.failures.filter((item) => item.fileName !== failure.fileName),
      failure,
    ],
    updatedAt: failure.failedAt,
  };
}

export function clearSelectedImageCropFailure(
  session: SelectedImageCropSessionV2,
  fileName: string,
  now: string,
): SelectedImageCropSessionV2 {
  return {
    ...session,
    revision: session.revision + 1,
    failures: session.failures.filter((item) => item.fileName !== fileName),
    updatedAt: now,
  };
}
