import type {
  SelectedImageCropManifestV1,
  SelectedImageCropPendingOperation,
  SelectedImageCropResult,
  SelectedImageCropSourceEntry,
} from './crop.ts';

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
  readonly failures: readonly SelectedImageCropPreparationFailure[];
  /** Null or absent identifies a historical session that predates policy pinning. */
  readonly preparationPolicyVersion?: string | null;
  readonly updatedAt: string;
}

export interface SelectedImageCropReviewV2 {
  readonly schemaVersion: typeof SELECTED_IMAGE_CROP_SESSION_SCHEMA_VERSION;
  readonly reviewedFileNames: readonly string[];
  readonly correctionFileNames: readonly string[];
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
  if (requiredSelectedImageCropCorrections(snapshot).includes(fileName))
    return 'needs_correction';
  if (snapshot.review.correctionFileNames.includes(fileName))
    return 'needs_correction';
  if (snapshot.review.correctedFileNames.includes(fileName)) return 'corrected';
  if (snapshot.review.reviewedFileNames.includes(fileName)) return 'reviewed';
  if (snapshot.session.failures.some((item) => item.fileName === fileName))
    return 'failed';
  if (snapshot.session.pendingOperation?.fileName === fileName)
    return 'processing';
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
  ]);
  return snapshot.shards.flatMap((shard) =>
    Object.entries(shard.results)
      .filter(
        ([name, result]) =>
          !resolved.has(name) &&
          result.autoCropProposal?.structural?.status === 'needs_manual_crop',
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

export function selectedImageCropRecalculationFileNames(
  snapshot: SelectedImageCropSessionSnapshotV2,
): readonly string[] {
  const protectedNames = new Set([
    ...requiredSelectedImageCropCorrections(snapshot),
    ...snapshot.review.reviewedFileNames,
    ...snapshot.review.correctedFileNames,
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
      failures: [],
      preparationPolicyVersion: null,
      updatedAt: manifest.updatedAt,
    },
    review: {
      schemaVersion: 2,
      reviewedFileNames: [...reviewed],
      correctionFileNames: [],
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

export function updateSelectedImageCropCorrections(
  review: SelectedImageCropReviewV2,
  fileName: string,
  selected: boolean,
): SelectedImageCropReviewV2 {
  const names = new Set(review.correctionFileNames);
  if (selected) names.add(fileName);
  else names.delete(fileName);
  return {
    ...review,
    correctionFileNames: [...names],
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
): SelectedImageCropReviewV2 {
  const unique = [...new Set(fileNames)];
  return {
    ...review,
    correctionFileNames: unique,
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
  corrected.add(fileName);
  const reviewed = new Set(review.reviewedFileNames);
  reviewed.add(fileName);
  return {
    ...review,
    reviewedFileNames: [...reviewed],
    correctionFileNames: corrections,
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
