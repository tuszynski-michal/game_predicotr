'use client';

import {
  beginSelectedImageCropWrite,
  createSelectedImageCropManifest,
  finalizeSelectedImageCropWrite,
  rollbackSelectedImageCropWrite,
  selectedImageCropRecoveryAction,
  validateSelectedImageCropBand,
  validateSelectedImageCropManifest,
  validateSelectedImageCropSources,
  SELECTED_IMAGE_CROP_FILLED_GAPS_OUTPUT_SUFFIX,
  SELECTED_IMAGE_CROP_JPEG_QUALITY,
  type SelectedImageCropBand,
  type SelectedImageCropManifestV1,
  type SelectedImageCropSourceEntry,
} from '@game-predictor/manual-image-selection-core/crop';
import {
  clearSelectedImageCropFailure,
  materializeSelectedImageCropManifestV1,
  markSelectedImageCropCorrected,
  migrateSelectedImageCropManifestV1,
  recordSelectedImageCropFailure,
  selectedImageCropRecalculationFileNames,
  selectedImageCropShardIndex,
  updateSelectedImageCropCorrections,
  type SelectedImageCropPreparationFailure,
  type SelectedImageCropPreparationStage,
  type SelectedImageCropReviewV2,
  type SelectedImageCropSessionSnapshotV2,
} from '@game-predictor/manual-image-selection-core/crop-session';
import {
  detectSelectedImageCropBand,
  SELECTED_IMAGE_AUTO_CROP_POLICY,
  SELECTED_IMAGE_AUTO_CROP_SAMPLE_WIDTH,
  type SelectedImageAutoCropProposal,
} from '@game-predictor/manual-image-selection-core/auto-crop';

import { pickLocalDirectory } from '@/lib/local-directory-picker';
import { readActiveFilledGapsManifest } from '@/features/manual-image-selection/manual-selection-repair-storage';

import { prepareSelectedImageCropInWorker } from './selected-image-crop-worker-client';

export const SELECTED_IMAGE_CROP_MANIFEST_NAME =
  'manual-image-crop-output-v1.json';
export const SELECTED_IMAGE_CROP_STATE_DIRECTORY = '.manual-image-crop-state';
const INVENTORY_NAME = 'inventory-v2.json';
const SESSION_NAME = 'session-v2.json';
const REVIEW_NAME = 'review-v2.json';
const RESULTS_DIRECTORY = 'results';
export const SELECTED_IMAGE_CROP_ATLAS_DIRECTORY = 'atlases';
type SelectedImageCropPermissionMode = 'read' | 'readwrite';
export type SelectedImageCropSourceSelection = 'all' | 'filled_gaps';

export interface SelectedImageCropSourceFile extends SelectedImageCropSourceEntry {
  readonly handle: FileSystemFileHandle;
  readonly relativePath: string;
}

export interface PreparedSelectedImageCropDirectory {
  readonly sourceDirectory: FileSystemDirectoryHandle;
  readonly outputDirectory: FileSystemDirectoryHandle;
  readonly sourceFiles: readonly SelectedImageCropSourceFile[];
  readonly manifest: SelectedImageCropManifestV1;
  readonly snapshot: SelectedImageCropSessionSnapshotV2;
}

export interface SelectedImageCropRenderedFile {
  readonly blob: Blob;
  readonly dimensions: { readonly width: number; readonly height: number };
}

export interface SelectedImageCropPreparationProgress {
  readonly completed: number;
  readonly total: number;
  readonly manifest: SelectedImageCropManifestV1;
  readonly prepared: PreparedSelectedImageCropDirectory;
  readonly lastFileName: string | null;
  readonly failures: readonly SelectedImageCropPreparationFailure[];
}

export interface SelectedImageCropPreparationResult {
  readonly prepared: PreparedSelectedImageCropDirectory;
  readonly failures: readonly SelectedImageCropPreparationFailure[];
}

export async function proposeSelectedImageCrop(
  source: File,
): Promise<SelectedImageAutoCropProposal> {
  const bitmap = await createImageBitmap(source, {
    imageOrientation: 'from-image',
  });
  try {
    const width = Math.min(SELECTED_IMAGE_AUTO_CROP_SAMPLE_WIDTH, bitmap.width);
    const height = Math.max(
      1,
      Math.round((bitmap.height * width) / bitmap.width),
    );
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext('2d', {
      alpha: false,
      willReadFrequently: true,
    });
    if (context === null) {
      throw new Error('SELECTED_IMAGE_AUTO_CROP_CANVAS_UNAVAILABLE');
    }
    context.drawImage(bitmap, 0, 0, width, height);
    const pixels = context.getImageData(0, 0, width, height);
    return detectSelectedImageCropBand(
      { width, height, rgba: pixels.data },
      { width: bitmap.width, height: bitmap.height },
    );
  } finally {
    bitmap.close();
  }
}

export async function pickSelectedImageCropParentDirectory(): Promise<FileSystemDirectoryHandle> {
  return pickLocalDirectory({
    id: 'gp-selected-image-crop-parent',
    mode: 'readwrite',
  });
}

export async function listSelectedImageCropSourceDirectories(
  parent: FileSystemDirectoryHandle,
): Promise<readonly string[]> {
  await ensureDirectoryPermission(parent, 'readwrite');
  const names: string[] = [];
  for await (const [name, handle] of directoryEntries(parent)) {
    if (handle.kind === 'directory' && !name.endsWith(' cut')) names.push(name);
  }
  return names.sort(naturalCompare);
}

export async function prepareSelectedImageCropDirectory(
  parent: FileSystemDirectoryHandle,
  sourceDirectoryName: string,
  sourceSelection: SelectedImageCropSourceSelection = 'all',
): Promise<PreparedSelectedImageCropDirectory> {
  await ensureDirectoryPermission(parent, 'readwrite');
  const sourceDirectory = await parent.getDirectoryHandle(sourceDirectoryName);
  const allSourceFiles =
    await listSelectedImageCropSourceFiles(sourceDirectory);
  const sourceFiles =
    sourceSelection === 'filled_gaps'
      ? await selectActiveFilledGapFiles(sourceDirectory, allSourceFiles)
      : allSourceFiles;
  const inventoryChecksum =
    await selectedImageCropInventoryChecksum(sourceFiles);
  const outputName =
    sourceSelection === 'filled_gaps'
      ? `${sourceDirectoryName}${SELECTED_IMAGE_CROP_FILLED_GAPS_OUTPUT_SUFFIX}`
      : `${sourceDirectoryName} cut`;
  const outputExisted = await directoryContainsEntry(parent, outputName);
  const outputDirectory = await parent.getDirectoryHandle(outputName, {
    create: true,
  });
  await ensureDirectoryPermission(outputDirectory, 'readwrite');

  const existingManifest = await readSelectedImageCropManifest(outputDirectory);
  let manifest: SelectedImageCropManifestV1;
  if (existingManifest !== null) {
    manifest = validateSelectedImageCropManifest(
      existingManifest,
      inventoryChecksum,
    );
    if (manifest.sourceDirectoryName !== sourceDirectoryName)
      throw new Error('SELECTED_IMAGE_CROP_OUTPUT_FOREIGN');
  } else {
    const entries = await listDirectoryEntryNames(outputDirectory);
    if (outputExisted && entries.length > 0)
      throw new Error('SELECTED_IMAGE_CROP_OUTPUT_NOT_EMPTY');
    manifest = createSelectedImageCropManifest({
      sourceDirectoryName,
      outputDirectoryName: outputName,
      sourceInventoryChecksumSha256: inventoryChecksum,
      entries: sourceFiles,
      now: new Date().toISOString(),
    });
    await writeSelectedImageCropManifest(outputDirectory, manifest);
  }

  let snapshot = await openSelectedImageCropSnapshot(
    outputDirectory,
    manifest,
    existingManifest === null,
  );
  snapshot = await recoverSelectedImageCropSnapshot(outputDirectory, snapshot);
  manifest = materializeSelectedImageCropManifestV1(snapshot);
  await assertOwnedOutputContents(outputDirectory, manifest);
  return {
    sourceDirectory,
    outputDirectory,
    sourceFiles,
    manifest,
    snapshot,
  };
}

async function selectActiveFilledGapFiles(
  directory: FileSystemDirectoryHandle,
  files: readonly SelectedImageCropSourceFile[],
): Promise<readonly SelectedImageCropSourceFile[]> {
  const handoff = await readActiveFilledGapsManifest(directory);
  if (handoff === null)
    throw new Error('SELECTED_IMAGE_CROP_FILLED_GAPS_MANIFEST_MISSING');
  if (handoff.selectedDirectoryName !== directory.name)
    throw new Error('SELECTED_IMAGE_CROP_FILLED_GAPS_DIRECTORY_CHANGED');
  if (handoff.entries.length === 0)
    throw new Error('SELECTED_IMAGE_CROP_FILLED_GAPS_EMPTY');
  const byName = new Map(files.map((file) => [file.fileName, file]));
  const selected: SelectedImageCropSourceFile[] = [];
  for (const entry of handoff.entries) {
    const file = byName.get(entry.fileName);
    if (file === undefined)
      throw new Error(
        `SELECTED_IMAGE_CROP_FILLED_GAP_MISSING:${entry.fileName}`,
      );
    if (
      (await sha256Blob(await file.handle.getFile())) !== entry.checksumSha256
    )
      throw new Error(
        `SELECTED_IMAGE_CROP_FILLED_GAP_CHANGED:${entry.fileName}`,
      );
    selected.push(file);
  }
  return selected;
}

export async function listSelectedImageCropSourceFiles(
  directory: FileSystemDirectoryHandle,
): Promise<readonly SelectedImageCropSourceFile[]> {
  await ensureDirectoryPermission(directory, 'read');
  const candidates: Array<{
    readonly fileName: string;
    readonly sizeBytes: number;
    readonly lastModifiedMs: number;
    readonly handle: FileSystemFileHandle;
  }> = [];
  const invalidJpegs: string[] = [];
  for await (const [name, handle] of directoryEntries(directory)) {
    if (handle.kind !== 'file') continue;
    if (!/\.jpe?g$/iu.test(name)) continue;
    if (!/^seq_\d+-\d+\.jpe?g$/iu.test(name)) {
      invalidJpegs.push(name);
      continue;
    }
    const file = await handle.getFile();
    candidates.push({
      fileName: name,
      sizeBytes: file.size,
      lastModifiedMs: file.lastModified,
      handle,
    });
  }
  if (invalidJpegs.length > 0)
    throw new Error(
      `SELECTED_IMAGE_CROP_INVALID_NAMES:${invalidJpegs.join(',')}`,
    );
  const validated = validateSelectedImageCropSources(candidates);
  const byName = new Map(
    candidates.map((file) => [file.fileName, file.handle]),
  );
  return validated.map((entry) => ({
    ...entry,
    handle: byName.get(entry.fileName)!,
    relativePath: entry.fileName,
  }));
}

export async function renderSelectedImageCrop(
  source: File,
  crop: SelectedImageCropBand,
): Promise<SelectedImageCropRenderedFile> {
  validateSelectedImageCropBand(crop);
  const bitmap = await createImageBitmap(source, {
    imageOrientation: 'from-image',
  });
  try {
    if (bitmap.width !== crop.width || bitmap.height !== crop.height)
      throw new Error('SELECTED_IMAGE_CROP_SOURCE_DIMENSIONS_CHANGED');
    const outputHeight = crop.bottomY - crop.topY;
    const canvas = document.createElement('canvas');
    canvas.width = crop.width;
    canvas.height = outputHeight;
    const context = canvas.getContext('2d');
    if (context === null)
      throw new Error('SELECTED_IMAGE_CROP_CANVAS_UNAVAILABLE');
    context.drawImage(
      bitmap,
      0,
      crop.topY,
      crop.width,
      outputHeight,
      0,
      0,
      crop.width,
      outputHeight,
    );
    const blob = await canvasToBlob(
      canvas,
      'image/jpeg',
      SELECTED_IMAGE_CROP_JPEG_QUALITY,
    );
    return { blob, dimensions: { width: crop.width, height: outputHeight } };
  } finally {
    bitmap.close();
  }
}

export async function saveSelectedImageCrop(input: {
  readonly prepared: PreparedSelectedImageCropDirectory;
  readonly sourceFile: SelectedImageCropSourceFile;
  readonly crop: SelectedImageCropBand;
  readonly markReviewed?: boolean;
  readonly autoCropProposal?: SelectedImageAutoCropProposal;
  readonly render?: (
    source: File,
    crop: SelectedImageCropBand,
  ) => Promise<SelectedImageCropRenderedFile>;
}): Promise<PreparedSelectedImageCropDirectory> {
  const render = input.render ?? renderSelectedImageCrop;
  const currentSource = await input.sourceFile.handle.getFile();
  if (
    currentSource.size !== input.sourceFile.sizeBytes ||
    currentSource.lastModified !== input.sourceFile.lastModifiedMs
  ) {
    throw new Error('SELECTED_IMAGE_CROP_SOURCE_CHANGED');
  }
  const sourceChecksum = await sha256Blob(currentSource);
  const rendered = await render(currentSource, input.crop);
  const outputChecksum = await sha256Blob(rendered.blob);
  const existingResult = input.prepared.manifest.entries.find(
    (entry) => entry.fileName === input.sourceFile.fileName,
  )?.result;
  const observedExistingChecksum = await readOptionalFileChecksum(
    input.prepared.outputDirectory,
    input.sourceFile.fileName,
  );
  if (
    observedExistingChecksum !== (existingResult?.outputChecksumSha256 ?? null)
  ) {
    throw new Error('SELECTED_IMAGE_CROP_OUTPUT_CHANGED');
  }

  const now = new Date().toISOString();
  let manifest = beginSelectedImageCropWrite(
    input.prepared.manifest,
    {
      kind: 'write_crop',
      fileName: input.sourceFile.fileName,
      expectedSourceChecksumSha256: sourceChecksum,
      expectedOutputChecksumSha256: outputChecksum,
      crop: input.crop,
      startedAt: now,
      replacesOutputChecksumSha256:
        existingResult?.outputChecksumSha256 ?? null,
      markReviewed: input.markReviewed,
      autoCropProposal: input.autoCropProposal,
    },
    now,
  );
  let snapshot = snapshotWithManifestSession(input.prepared.snapshot, manifest);
  await writeSelectedImageCropSession(
    input.prepared.outputDirectory,
    snapshot.session,
  );
  await writeBlob(
    input.prepared.outputDirectory,
    input.sourceFile.fileName,
    rendered.blob,
  );
  const verifiedChecksum = await readOptionalFileChecksum(
    input.prepared.outputDirectory,
    input.sourceFile.fileName,
  );
  if (verifiedChecksum !== outputChecksum)
    throw new Error('SELECTED_IMAGE_CROP_OUTPUT_CHECKSUM_MISMATCH');
  manifest = finalizeSelectedImageCropWrite(manifest, new Date().toISOString());
  snapshot = snapshotWithFinalizedResult(
    snapshot,
    manifest,
    input.sourceFile.fileName,
  );
  await writeSelectedImageCropResultShard(
    input.prepared.outputDirectory,
    snapshot,
    input.sourceFile.fileName,
  );
  await writeSelectedImageCropReview(
    input.prepared.outputDirectory,
    snapshot.review,
  );
  await writeSelectedImageCropSession(
    input.prepared.outputDirectory,
    snapshot.session,
  );
  return { ...input.prepared, manifest, snapshot };
}

export async function prepareAllSelectedImageCrops(
  prepared: PreparedSelectedImageCropDirectory,
  onProgress?: (progress: SelectedImageCropPreparationProgress) => void,
  onlyFileNames?: ReadonlySet<string>,
  signal?: AbortSignal,
): Promise<SelectedImageCropPreparationResult> {
  if (
    prepared.snapshot.session.preparationPolicyVersion !==
    SELECTED_IMAGE_AUTO_CROP_POLICY
  ) {
    throw new Error('SELECTED_IMAGE_CROP_POLICY_RECALCULATION_REQUIRED');
  }
  let current = prepared;
  const missing = prepared.sourceFiles.filter(
    (source) =>
      prepared.manifest.entries.find(
        (entry) => entry.fileName === source.fileName,
      )?.result === null &&
      (onlyFileNames === undefined || onlyFileNames.has(source.fileName)),
  );
  let completed = current.manifest.entries.filter(
    (entry) => entry.result !== null,
  ).length;
  const emit = (lastFileName: string | null) =>
    onProgress?.({
      completed,
      total: current.manifest.entries.length,
      manifest: current.manifest,
      prepared: current,
      lastFileName,
      failures: current.snapshot.session.failures,
    });
  emit(null);
  for (const sourceFile of missing) {
    if (signal?.aborted === true) break;
    try {
      const source = await sourceFile.handle.getFile();
      let proposal: SelectedImageAutoCropProposal;
      let workerRendered: SelectedImageCropRenderedFile | null = null;
      try {
        const workerResult = await prepareSelectedImageCropInWorker(source);
        if (workerResult === null) {
          proposal = await proposeSelectedImageCrop(source);
        } else {
          proposal = workerResult.proposal;
          workerRendered = workerResult.rendered;
        }
      } catch (cause) {
        throw preparationError(stageFromError(cause), cause);
      }
      try {
        current = await saveSelectedImageCrop({
          prepared: current,
          sourceFile,
          crop: proposal.crop,
          markReviewed: false,
          autoCropProposal: proposal,
          render:
            workerRendered === null ? undefined : async () => workerRendered,
        });
      } catch (cause) {
        throw preparationError(stageFromError(cause), cause);
      }
      current = await clearPersistedPreparationFailure(
        current,
        sourceFile.fileName,
      );
      completed += 1;
    } catch (cause) {
      current = await persistPreparationFailure(
        current,
        sourceFile.fileName,
        cause,
      );
    }
    if (!signal?.aborted) emit(sourceFile.fileName);
    await yieldToBrowser();
  }
  return { prepared: current, failures: current.snapshot.session.failures };
}

export async function recalculateUnreviewedSelectedImageCrops(
  prepared: PreparedSelectedImageCropDirectory,
  onProgress?: (progress: SelectedImageCropPreparationProgress) => void,
  signal?: AbortSignal,
): Promise<SelectedImageCropPreparationResult> {
  let current = await pinSelectedImageCropPreparationPolicy(prepared);
  const recalculationNames = new Set(
    selectedImageCropRecalculationFileNames(current.snapshot),
  );
  const candidates = current.sourceFiles.filter((source) => {
    return recalculationNames.has(source.fileName);
  });
  const missingCount = current.manifest.entries.filter(
    (entry) => entry.result === null,
  ).length;
  const actionTotal = candidates.length + missingCount;
  let completed = 0;
  for (const sourceFile of candidates) {
    if (signal?.aborted === true) break;
    try {
      const source = await sourceFile.handle.getFile();
      const workerResult = await prepareSelectedImageCropInWorker(source);
      const proposal =
        workerResult?.proposal ?? (await proposeSelectedImageCrop(source));
      current = await saveSelectedImageCrop({
        prepared: current,
        sourceFile,
        crop: proposal.crop,
        markReviewed: false,
        autoCropProposal: proposal,
        render:
          workerResult === null ? undefined : async () => workerResult.rendered,
      });
      current = await clearPersistedPreparationFailure(
        current,
        sourceFile.fileName,
      );
    } catch (cause) {
      current = await persistPreparationFailure(
        current,
        sourceFile.fileName,
        preparationError(stageFromError(cause), cause),
      );
    }
    completed += 1;
    onProgress?.({
      completed,
      total: actionTotal,
      manifest: current.manifest,
      prepared: current,
      lastFileName: sourceFile.fileName,
      failures: current.snapshot.session.failures,
    });
    await yieldToBrowser();
  }
  if (signal?.aborted === true)
    return { prepared: current, failures: current.snapshot.session.failures };
  const preparedBeforeMissing = current.manifest.entries.filter(
    (entry) => entry.result !== null,
  ).length;
  return prepareAllSelectedImageCrops(
    current,
    (progress) =>
      onProgress?.({
        ...progress,
        completed:
          candidates.length +
          Math.max(0, progress.completed - preparedBeforeMissing),
        total: actionTotal,
      }),
    undefined,
    signal,
  );
}

export async function setSelectedImageCropCorrection(input: {
  readonly prepared: PreparedSelectedImageCropDirectory;
  readonly fileName: string;
  readonly selected: boolean;
}): Promise<PreparedSelectedImageCropDirectory> {
  const review = updateSelectedImageCropCorrections(
    input.prepared.snapshot.review,
    input.fileName,
    input.selected,
  );
  await writeSelectedImageCropReview(input.prepared.outputDirectory, review);
  return {
    ...input.prepared,
    snapshot: { ...input.prepared.snapshot, review },
  };
}

export async function clearSelectedImageCropCorrections(
  prepared: PreparedSelectedImageCropDirectory,
): Promise<PreparedSelectedImageCropDirectory> {
  const review: SelectedImageCropReviewV2 = {
    ...prepared.snapshot.review,
    correctionFileNames: [],
    correctionCursor: 0,
    completedAt: null,
  };
  await writeSelectedImageCropReview(prepared.outputDirectory, review);
  return { ...prepared, snapshot: { ...prepared.snapshot, review } };
}

export async function completeSelectedImageCropCorrection(input: {
  readonly prepared: PreparedSelectedImageCropDirectory;
  readonly fileName: string;
}): Promise<PreparedSelectedImageCropDirectory> {
  const review = markSelectedImageCropCorrected(
    input.prepared.snapshot.review,
    input.fileName,
  );
  await writeSelectedImageCropReview(input.prepared.outputDirectory, review);
  const manifest = {
    ...input.prepared.manifest,
    reviewedFileNames: review.reviewedFileNames,
  };
  return {
    ...input.prepared,
    manifest,
    snapshot: { ...input.prepared.snapshot, review },
  };
}

export async function completeSelectedImageCropReview(
  prepared: PreparedSelectedImageCropDirectory,
): Promise<PreparedSelectedImageCropDirectory> {
  if (
    prepared.manifest.entries.some((entry) => entry.result === null) ||
    prepared.snapshot.session.failures.length > 0 ||
    prepared.snapshot.review.correctionFileNames.length > 0 ||
    prepared.snapshot.session.pendingOperation !== null
  ) {
    throw new Error('SELECTED_IMAGE_CROP_REVIEW_INCOMPLETE');
  }
  const review: SelectedImageCropReviewV2 = {
    ...prepared.snapshot.review,
    reviewedFileNames: prepared.manifest.entries.map((entry) => entry.fileName),
    completedAt: new Date().toISOString(),
  };
  await writeSelectedImageCropReview(prepared.outputDirectory, review);
  const manifest = {
    ...prepared.manifest,
    reviewedFileNames: review.reviewedFileNames,
  };
  return {
    ...prepared,
    manifest,
    snapshot: { ...prepared.snapshot, review },
  };
}

async function openSelectedImageCropSnapshot(
  outputDirectory: FileSystemDirectoryHandle,
  legacyManifest: SelectedImageCropManifestV1,
  isNewSession: boolean,
): Promise<SelectedImageCropSessionSnapshotV2> {
  const stateDirectory = await outputDirectory.getDirectoryHandle(
    SELECTED_IMAGE_CROP_STATE_DIRECTORY,
    { create: true },
  );
  const existingInventory = await readJsonFile<
    SelectedImageCropSessionSnapshotV2['inventory']
  >(stateDirectory, INVENTORY_NAME);
  if (existingInventory === null) {
    const migratedBase = migrateSelectedImageCropManifestV1(legacyManifest);
    const migrated: SelectedImageCropSessionSnapshotV2 = {
      ...migratedBase,
      session: {
        ...migratedBase.session,
        preparationPolicyVersion: isNewSession
          ? SELECTED_IMAGE_AUTO_CROP_POLICY
          : null,
      },
    };
    await writeJsonFile(stateDirectory, SESSION_NAME, migrated.session);
    await writeJsonFile(stateDirectory, REVIEW_NAME, migrated.review);
    const resultsDirectory = await stateDirectory.getDirectoryHandle(
      RESULTS_DIRECTORY,
      { create: true },
    );
    for (const shard of migrated.shards)
      await writeJsonFile(
        resultsDirectory,
        resultShardName(shard.shardIndex),
        shard,
      );
    await stateDirectory.getDirectoryHandle(
      SELECTED_IMAGE_CROP_ATLAS_DIRECTORY,
      {
        create: true,
      },
    );
    await writeJsonFile(stateDirectory, INVENTORY_NAME, migrated.inventory);
    return migrated;
  }
  if (
    existingInventory.sourceInventoryChecksumSha256 !==
      legacyManifest.sourceInventoryChecksumSha256 ||
    existingInventory.sourceDirectoryName !== legacyManifest.sourceDirectoryName
  ) {
    throw new Error('SELECTED_IMAGE_CROP_SOURCE_CHANGED');
  }
  const storedSession = await requiredJsonFile<
    SelectedImageCropSessionSnapshotV2['session']
  >(stateDirectory, SESSION_NAME);
  const session: SelectedImageCropSessionSnapshotV2['session'] = {
    ...storedSession,
    preparationPolicyVersion: storedSession.preparationPolicyVersion ?? null,
  };
  const storedReview = await requiredJsonFile<SelectedImageCropReviewV2>(
    stateDirectory,
    REVIEW_NAME,
  );
  const review: SelectedImageCropReviewV2 = {
    ...storedReview,
    correctedFileNames: storedReview.correctedFileNames ?? [],
  };
  const resultsDirectory =
    await stateDirectory.getDirectoryHandle(RESULTS_DIRECTORY);
  const shardCount = Math.ceil(existingInventory.entries.length / 64);
  const shards = await Promise.all(
    Array.from({ length: shardCount }, async (_, shardIndex) =>
      requiredJsonFile<SelectedImageCropSessionSnapshotV2['shards'][number]>(
        resultsDirectory,
        resultShardName(shardIndex),
      ),
    ),
  );
  return { inventory: existingInventory, session, review, shards };
}

async function pinSelectedImageCropPreparationPolicy(
  prepared: PreparedSelectedImageCropDirectory,
): Promise<PreparedSelectedImageCropDirectory> {
  if (
    prepared.snapshot.session.preparationPolicyVersion ===
    SELECTED_IMAGE_AUTO_CROP_POLICY
  )
    return prepared;
  const session = {
    ...prepared.snapshot.session,
    revision: prepared.snapshot.session.revision + 1,
    preparationPolicyVersion: SELECTED_IMAGE_AUTO_CROP_POLICY,
    updatedAt: new Date().toISOString(),
  };
  await writeSelectedImageCropSession(prepared.outputDirectory, session);
  return { ...prepared, snapshot: { ...prepared.snapshot, session } };
}

function snapshotWithManifestSession(
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

function snapshotWithFinalizedResult(
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
  const shards = snapshot.shards.map((shard) =>
    shard.shardIndex === shardIndex
      ? { ...shard, results: { ...shard.results, [fileName]: result } }
      : shard,
  );
  return {
    ...snapshotWithManifestSession(snapshot, manifest),
    shards,
  };
}

async function recoverSelectedImageCropSnapshot(
  outputDirectory: FileSystemDirectoryHandle,
  snapshot: SelectedImageCropSessionSnapshotV2,
): Promise<SelectedImageCropSessionSnapshotV2> {
  const pending = snapshot.session.pendingOperation;
  if (pending === null) return snapshot;
  const observed = await readOptionalFileChecksum(
    outputDirectory,
    pending.fileName,
  );
  const manifest = materializeSelectedImageCropManifestV1(snapshot);
  const action = selectedImageCropRecoveryAction(manifest, observed);
  if (action === 'block_conflicting_output')
    throw new Error('SELECTED_IMAGE_CROP_RECOVERY_CONFLICT');
  if (action === 'rollback_missing_output') {
    const rolledBack = rollbackSelectedImageCropWrite(
      manifest,
      new Date().toISOString(),
    );
    const recovered = snapshotWithManifestSession(snapshot, rolledBack);
    await writeSelectedImageCropSession(outputDirectory, recovered.session);
    return recovered;
  }
  const finalized = finalizeSelectedImageCropWrite(
    manifest,
    new Date().toISOString(),
  );
  const recovered = snapshotWithFinalizedResult(
    snapshot,
    finalized,
    pending.fileName,
  );
  await writeSelectedImageCropResultShard(
    outputDirectory,
    recovered,
    pending.fileName,
  );
  await writeSelectedImageCropReview(outputDirectory, recovered.review);
  await writeSelectedImageCropSession(outputDirectory, recovered.session);
  return recovered;
}

async function writeSelectedImageCropSession(
  outputDirectory: FileSystemDirectoryHandle,
  session: SelectedImageCropSessionSnapshotV2['session'],
): Promise<void> {
  const stateDirectory = await outputDirectory.getDirectoryHandle(
    SELECTED_IMAGE_CROP_STATE_DIRECTORY,
  );
  await writeJsonFile(stateDirectory, SESSION_NAME, session);
}

async function writeSelectedImageCropReview(
  outputDirectory: FileSystemDirectoryHandle,
  review: SelectedImageCropReviewV2,
): Promise<void> {
  const stateDirectory = await outputDirectory.getDirectoryHandle(
    SELECTED_IMAGE_CROP_STATE_DIRECTORY,
  );
  await writeJsonFile(stateDirectory, REVIEW_NAME, review);
}

async function writeSelectedImageCropResultShard(
  outputDirectory: FileSystemDirectoryHandle,
  snapshot: SelectedImageCropSessionSnapshotV2,
  fileName: string,
): Promise<void> {
  const entryIndex = snapshot.inventory.entries.findIndex(
    (entry) => entry.fileName === fileName,
  );
  const shardIndex = selectedImageCropShardIndex(entryIndex);
  const shard = snapshot.shards.find((item) => item.shardIndex === shardIndex);
  if (shard === undefined) throw new Error('SELECTED_IMAGE_CROP_SHARD_MISSING');
  const stateDirectory = await outputDirectory.getDirectoryHandle(
    SELECTED_IMAGE_CROP_STATE_DIRECTORY,
  );
  const resultsDirectory =
    await stateDirectory.getDirectoryHandle(RESULTS_DIRECTORY);
  await writeJsonFile(resultsDirectory, resultShardName(shardIndex), shard);
}

async function persistPreparationFailure(
  prepared: PreparedSelectedImageCropDirectory,
  fileName: string,
  cause: unknown,
): Promise<PreparedSelectedImageCropDirectory> {
  const details = unwrapPreparationError(cause);
  const session = recordSelectedImageCropFailure(prepared.snapshot.session, {
    fileName,
    stage: details.stage,
    code: details.code,
    failedAt: new Date().toISOString(),
  });
  await writeSelectedImageCropSession(prepared.outputDirectory, session);
  return { ...prepared, snapshot: { ...prepared.snapshot, session } };
}

async function clearPersistedPreparationFailure(
  prepared: PreparedSelectedImageCropDirectory,
  fileName: string,
): Promise<PreparedSelectedImageCropDirectory> {
  if (
    !prepared.snapshot.session.failures.some(
      (item) => item.fileName === fileName,
    )
  )
    return prepared;
  const session = clearSelectedImageCropFailure(
    prepared.snapshot.session,
    fileName,
    new Date().toISOString(),
  );
  await writeSelectedImageCropSession(prepared.outputDirectory, session);
  return { ...prepared, snapshot: { ...prepared.snapshot, session } };
}

interface PreparationErrorDetails {
  readonly stage: SelectedImageCropPreparationStage;
  readonly code: string;
}

function preparationError(
  stage: SelectedImageCropPreparationStage,
  cause: unknown,
): Error & { details: PreparationErrorDetails } {
  const code = cause instanceof Error ? cause.message : 'UNKNOWN_ERROR';
  return Object.assign(new Error(code), { details: { stage, code } });
}

function unwrapPreparationError(cause: unknown): PreparationErrorDetails {
  if (
    cause instanceof Error &&
    'details' in cause &&
    typeof cause.details === 'object' &&
    cause.details !== null &&
    'stage' in cause.details &&
    'code' in cause.details
  ) {
    return cause.details as PreparationErrorDetails;
  }
  return { stage: stageFromError(cause), code: errorCode(cause) };
}

function stageFromError(cause: unknown): SelectedImageCropPreparationStage {
  const code = errorCode(cause);
  if (code.includes('DECODE') || code.includes('DIMENSIONS')) return 'decode';
  if (code.includes('ENCOD')) return 'render';
  if (code.includes('CHECKSUM')) return 'verify';
  return 'write';
}

function errorCode(cause: unknown): string {
  return cause instanceof Error ? cause.message : 'UNKNOWN_ERROR';
}

function resultShardName(index: number): string {
  return `${String(index).padStart(6, '0')}.json`;
}

async function requiredJsonFile<T>(
  directory: FileSystemDirectoryHandle,
  name: string,
): Promise<T> {
  const value = await readJsonFile<T>(directory, name);
  if (value === null)
    throw new Error(`SELECTED_IMAGE_CROP_STATE_MISSING:${name}`);
  return value;
}

async function readJsonFile<T>(
  directory: FileSystemDirectoryHandle,
  name: string,
): Promise<T | null> {
  try {
    const handle = await directory.getFileHandle(name);
    return JSON.parse(await (await handle.getFile()).text()) as T;
  } catch (cause) {
    if (isNotFound(cause)) return null;
    throw cause;
  }
}

async function writeJsonFile(
  directory: FileSystemDirectoryHandle,
  name: string,
  value: unknown,
): Promise<void> {
  await writeBlob(
    directory,
    name,
    new Blob([`${JSON.stringify(value)}\n`], { type: 'application/json' }),
  );
}

export async function readCanonicalSelectedImageDimensions(
  source: File,
): Promise<{ readonly width: number; readonly height: number }> {
  const bitmap = await createImageBitmap(source, {
    imageOrientation: 'from-image',
  });
  try {
    return { width: bitmap.width, height: bitmap.height };
  } finally {
    bitmap.close();
  }
}

async function assertOwnedOutputContents(
  outputDirectory: FileSystemDirectoryHandle,
  manifest: SelectedImageCropManifestV1,
): Promise<void> {
  const allowed = new Set([
    SELECTED_IMAGE_CROP_MANIFEST_NAME.toLocaleLowerCase('en-US'),
    SELECTED_IMAGE_CROP_STATE_DIRECTORY.toLocaleLowerCase('en-US'),
    ...manifest.entries
      .filter((entry) => entry.result !== null)
      .map((entry) => entry.fileName.toLocaleLowerCase('en-US')),
  ]);
  if (manifest.pendingOperation !== null)
    allowed.add(manifest.pendingOperation.fileName.toLocaleLowerCase('en-US'));
  for (const name of await listDirectoryEntryNames(outputDirectory)) {
    if (!allowed.has(name.toLocaleLowerCase('en-US')))
      throw new Error(`SELECTED_IMAGE_CROP_OUTPUT_FOREIGN:${name}`);
  }
}

async function readSelectedImageCropManifest(
  directory: FileSystemDirectoryHandle,
): Promise<SelectedImageCropManifestV1 | null> {
  try {
    const handle = await directory.getFileHandle(
      SELECTED_IMAGE_CROP_MANIFEST_NAME,
    );
    const value: unknown = JSON.parse(await (await handle.getFile()).text());
    if (value === null || typeof value !== 'object')
      throw new Error('SELECTED_IMAGE_CROP_MANIFEST_INVALID');
    return validateSelectedImageCropManifest(
      value as SelectedImageCropManifestV1,
    );
  } catch (cause) {
    if (isNotFound(cause)) return null;
    throw cause;
  }
}

export async function writeSelectedImageCropManifest(
  directory: FileSystemDirectoryHandle,
  manifest: SelectedImageCropManifestV1,
): Promise<void> {
  validateSelectedImageCropManifest(manifest);
  const blob = new Blob([`${JSON.stringify(manifest, null, 2)}\n`], {
    type: 'application/json',
  });
  await writeBlob(directory, SELECTED_IMAGE_CROP_MANIFEST_NAME, blob);
}

async function writeBlob(
  directory: FileSystemDirectoryHandle,
  name: string,
  blob: Blob,
): Promise<void> {
  const target = await directory.getFileHandle(name, { create: true });
  const writable = await target.createWritable();
  try {
    await writable.write(blob);
    await writable.close();
  } catch (cause) {
    await writable.abort().catch(() => undefined);
    throw cause;
  }
}

async function readOptionalFileChecksum(
  directory: FileSystemDirectoryHandle,
  name: string,
): Promise<string | null> {
  try {
    const handle = await directory.getFileHandle(name);
    return sha256Blob(await handle.getFile());
  } catch (cause) {
    if (isNotFound(cause)) return null;
    throw cause;
  }
}

async function yieldToBrowser(): Promise<void> {
  await new Promise<void>((resolve) => window.setTimeout(resolve, 0));
}

async function selectedImageCropInventoryChecksum(
  files: readonly SelectedImageCropSourceFile[],
): Promise<string> {
  return sha256Blob(
    new Blob([
      JSON.stringify(
        files.map(({ fileName, sizeBytes, lastModifiedMs }) => ({
          fileName,
          sizeBytes,
          lastModifiedMs,
        })),
      ),
    ]),
  );
}

export async function sha256Blob(blob: Blob): Promise<string> {
  const digest = await crypto.subtle.digest(
    'SHA-256',
    await blob.arrayBuffer(),
  );
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('');
}

async function ensureDirectoryPermission(
  directory: FileSystemDirectoryHandle,
  mode: SelectedImageCropPermissionMode,
): Promise<void> {
  const permissionHandle = directory as FileSystemDirectoryHandle & {
    queryPermission(options: {
      mode: SelectedImageCropPermissionMode;
    }): Promise<PermissionState>;
    requestPermission(options: {
      mode: SelectedImageCropPermissionMode;
    }): Promise<PermissionState>;
  };
  const existing = await permissionHandle.queryPermission({ mode });
  if (existing === 'granted') return;
  if ((await permissionHandle.requestPermission({ mode })) !== 'granted')
    throw new Error('SELECTED_IMAGE_CROP_DIRECTORY_PERMISSION_DENIED');
}

function directoryEntries(
  directory: FileSystemDirectoryHandle,
): AsyncIterable<
  readonly [string, FileSystemFileHandle | FileSystemDirectoryHandle]
> {
  return (
    directory as FileSystemDirectoryHandle & {
      entries(): AsyncIterable<
        readonly [string, FileSystemFileHandle | FileSystemDirectoryHandle]
      >;
    }
  ).entries();
}

async function listDirectoryEntryNames(
  directory: FileSystemDirectoryHandle,
): Promise<readonly string[]> {
  const names: string[] = [];
  for await (const [name] of directoryEntries(directory)) names.push(name);
  return names;
}

async function directoryContainsEntry(
  directory: FileSystemDirectoryHandle,
  expectedName: string,
): Promise<boolean> {
  for await (const [name] of directoryEntries(directory)) {
    if (name === expectedName) return true;
  }
  return false;
}

function canvasToBlob(
  canvas: HTMLCanvasElement,
  type: string,
  quality: number,
): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) =>
        blob === null
          ? reject(new Error('SELECTED_IMAGE_CROP_ENCODING_FAILED'))
          : resolve(blob),
      type,
      quality,
    );
  });
}

function isNotFound(cause: unknown): boolean {
  return cause instanceof DOMException && cause.name === 'NotFoundError';
}

function naturalCompare(left: string, right: string): number {
  return left.localeCompare(right, undefined, {
    numeric: true,
    sensitivity: 'base',
  });
}
