'use client';

import type {
  AdminApiClient,
  SemiAutomaticSelectionRangeResponse,
  SemiAutomaticSelectionRunResponse,
} from '@game-predictor/admin-api-client';

import {
  acknowledgeSemiAutomaticLocalSelection,
  assertSemiAutomaticManifestMatchesRun,
  beginSemiAutomaticOutputOperation,
  createSemiAutomaticSelectionOutputManifest,
  finalizeSemiAutomaticOutputOperation,
  outputFileName,
  recordSemiAutomaticOutputConflict,
  rollbackSemiAutomaticOutputOperation,
  updateSemiAutomaticOutputSummary,
  type SemiAutomaticLocalSourceIdentity,
  type SemiAutomaticRunIdentity,
  type SemiAutomaticSelectionOutputManifestV1,
} from './semi-automatic-selection-output.ts';
import {
  readLocalOutputFile,
  readSemiAutomaticSelectionOutputManifest,
  writeOriginalOutputBytes,
  writeSemiAutomaticSelectionOutputManifest,
  type SemiAutomaticOutputDirectoryHandle,
} from './semi-automatic-selection-output-storage.ts';

export type SemiAutomaticSelectionOutputSyncClient = Pick<
  AdminApiClient,
  | 'acknowledgeSemiAutomaticImageSelectionOutput'
  | 'getSemiAutomaticImageSelectionSourceAsset'
>;

export interface SemiAutomaticSelectionOutputSyncResult {
  readonly acknowledgedCount: number;
  readonly conflictCount: number;
  readonly gapCount: number;
  readonly manifest: SemiAutomaticSelectionOutputManifestV1;
  readonly manifestChecksumSha256: string;
  readonly writtenCount: number;
}

export async function synchronizeSemiAutomaticSelectionOutput(input: {
  readonly client: SemiAutomaticSelectionOutputSyncClient;
  readonly directory: SemiAutomaticOutputDirectoryHandle;
  readonly ranges: readonly SemiAutomaticSelectionRangeResponse[];
  readonly run: SemiAutomaticSelectionRunResponse;
  readonly now?: () => string;
  readonly onProgress?: (processed: number, total: number) => void;
  readonly operationId?: () => string;
}): Promise<SemiAutomaticSelectionOutputSyncResult> {
  const now = input.now ?? (() => new Date().toISOString());
  const operationId = input.operationId ?? (() => crypto.randomUUID());
  const run = toRunIdentity(input.run);
  const ranges = validateCompleteRangeSnapshot(input.run, input.ranges);
  let manifest = await readSemiAutomaticSelectionOutputManifest(
    input.directory,
  );
  if (manifest === null) {
    manifest = createSemiAutomaticSelectionOutputManifest({
      now: now(),
      outputDirectoryName: input.directory.name,
      run,
    });
    await writeSemiAutomaticSelectionOutputManifest(input.directory, manifest);
  } else {
    assertSemiAutomaticManifestMatchesRun(manifest, run, input.directory.name);
  }

  manifest = await reconcilePendingOperation(
    input.directory,
    manifest,
    ranges,
    now,
  );
  let writtenCount = 0;
  let acknowledgedCount = 0;
  const gaps: number[] = [];

  for (let rangeOffset = 0; rangeOffset < ranges.length; rangeOffset += 1) {
    const range = ranges[rangeOffset]!;
    if (range.status === 'missing' || range.status === 'conflict') {
      const manual = manifest.selections.find(
        (selection) =>
          selection.expectedIndex === range.expectedIndex &&
          (selection.status === 'MANUALLY_ADDED' ||
            selection.status === 'MANUALLY_REPLACED'),
      );
      if (manual !== undefined && !manual.acknowledged) {
        const acknowledgement =
          await input.client.acknowledgeSemiAutomaticImageSelectionOutput(
            input.run.id,
            range.expectedIndex,
            {
              expectedRevision: range.revision,
              expectedSourceChecksumSha256: manual.source.checksumSha256,
              outputChecksumSha256: manual.outputChecksumSha256,
              sourceIndex: manual.source.sourceIndex,
            },
          );
        if (
          acknowledgement.error !== undefined ||
          acknowledgement.data === undefined
        ) {
          throw new Error(
            'SEMI_AUTOMATIC_SELECTION_OUTPUT_ACKNOWLEDGEMENT_FAILED',
          );
        }
        manifest = acknowledgeSemiAutomaticLocalSelection(
          manifest,
          range.expectedIndex,
          acknowledgement.data.revision,
          now(),
        );
        await writeSemiAutomaticSelectionOutputManifest(
          input.directory,
          manifest,
        );
        acknowledgedCount += 1;
        input.onProgress?.(rangeOffset + 1, ranges.length);
        continue;
      }
      gaps.push(range.expectedIndex);
      input.onProgress?.(rangeOffset + 1, ranges.length);
      continue;
    }
    const source = sourceIdentity(range);
    const targetName = outputFileName(range.rangeStart, range.rangeEnd);
    const local = await readLocalOutputFile(input.directory, targetName);
    const recoveringOwnedEmptyTarget =
      local !== null &&
      local.file.size === 0 &&
      pendingMatchesRange(manifest, range, source, targetName);
    if (
      local !== null &&
      local.checksumSha256 !== source.checksumSha256 &&
      !recoveringOwnedEmptyTarget
    ) {
      manifest = recordSemiAutomaticOutputConflict(
        manifest,
        {
          actualChecksumSha256: local.checksumSha256,
          detectedAt: now(),
          expectedChecksumSha256: source.checksumSha256,
          expectedIndex: range.expectedIndex,
          outputName: targetName,
          reason: 'TARGET_CONTENT_CHANGED',
        },
        now(),
      );
      await writeSemiAutomaticSelectionOutputManifest(
        input.directory,
        manifest,
      );
      gaps.push(range.expectedIndex);
      input.onProgress?.(rangeOffset + 1, ranges.length);
      continue;
    }

    const current = manifest.selections.find(
      (selection) => selection.expectedIndex === range.expectedIndex,
    );
    const currentMatches =
      current !== undefined &&
      current.outputName === targetName &&
      current.outputChecksumSha256 === source.checksumSha256 &&
      current.source.relativePath === source.relativePath &&
      current.source.sourceIndex === source.sourceIndex;

    if (!currentMatches || local === null || recoveringOwnedEmptyTarget) {
      if (!recoveringOwnedEmptyTarget) {
        manifest = beginSemiAutomaticOutputOperation(
          manifest,
          {
            expectedIndex: range.expectedIndex,
            expectedRangeRevision: range.revision,
            operationId: operationId(),
            outputName: targetName,
            rangeEnd: range.rangeEnd,
            rangeStart: range.rangeStart,
            selectionStatus:
              local === null ? 'AUTO_SELECTED' : 'PREEXISTING_PROTECTED',
            source,
            startedAt: now(),
          },
          now(),
        );
        await writeSemiAutomaticSelectionOutputManifest(
          input.directory,
          manifest,
        );
      }

      if (local === null || recoveringOwnedEmptyTarget) {
        const sourceAsset =
          await input.client.getSemiAutomaticImageSelectionSourceAsset(
            input.run.id,
            source.sourceIndex,
            source.checksumSha256,
          );
        if (sourceAsset.error !== undefined || sourceAsset.data === undefined) {
          throw new Error('SEMI_AUTOMATIC_SELECTION_SOURCE_ASSET_UNAVAILABLE');
        }
        const sourceBlob = toBlob(sourceAsset.data);
        if (sourceBlob === null) {
          throw new Error('SEMI_AUTOMATIC_SELECTION_SOURCE_ASSET_INVALID');
        }
        const result = await writeOriginalOutputBytes({
          directory: input.directory,
          expectedChecksumSha256: source.checksumSha256,
          expectedSizeBytes: source.sizeBytes,
          allowOwnedEmptyTarget: recoveringOwnedEmptyTarget,
          outputName: targetName,
          source: sourceBlob,
        });
        if (result.created) writtenCount += 1;
      }

      manifest = finalizeSemiAutomaticOutputOperation(manifest, now());
      await writeSemiAutomaticSelectionOutputManifest(
        input.directory,
        manifest,
      );
    }

    const selection = manifest.selections.find(
      (item) => item.expectedIndex === range.expectedIndex,
    );
    if (selection === undefined) {
      throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_SELECTION_MISSING');
    }
    if (
      range.status === 'output_synced' &&
      range.outputChecksumSha256 === selection.outputChecksumSha256
    ) {
      if (
        !selection.acknowledged ||
        selection.serverRangeRevision !== range.revision
      ) {
        manifest = acknowledgeSemiAutomaticLocalSelection(
          manifest,
          range.expectedIndex,
          range.revision,
          now(),
        );
        await writeSemiAutomaticSelectionOutputManifest(
          input.directory,
          manifest,
        );
      }
      input.onProgress?.(rangeOffset + 1, ranges.length);
      continue;
    }
    if (
      selection.acknowledged &&
      selection.serverRangeRevision === range.revision
    ) {
      input.onProgress?.(rangeOffset + 1, ranges.length);
      continue;
    }

    const acknowledgement =
      await input.client.acknowledgeSemiAutomaticImageSelectionOutput(
        input.run.id,
        range.expectedIndex,
        {
          expectedRevision: range.revision,
          expectedSourceChecksumSha256: source.checksumSha256,
          outputChecksumSha256: selection.outputChecksumSha256,
        },
      );
    if (
      acknowledgement.error !== undefined ||
      acknowledgement.data === undefined
    ) {
      throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_ACKNOWLEDGEMENT_FAILED');
    }
    manifest = acknowledgeSemiAutomaticLocalSelection(
      manifest,
      range.expectedIndex,
      acknowledgement.data.revision,
      now(),
    );
    await writeSemiAutomaticSelectionOutputManifest(input.directory, manifest);
    acknowledgedCount += 1;
    input.onProgress?.(rangeOffset + 1, ranges.length);
  }

  manifest = updateSemiAutomaticOutputSummary(manifest, {
    gaps,
    now: now(),
    status: 'review_mode',
  });
  const manifestChecksumSha256 =
    await writeSemiAutomaticSelectionOutputManifest(input.directory, manifest);
  return {
    acknowledgedCount,
    conflictCount: manifest.conflicts.length,
    gapCount: manifest.gaps.length,
    manifest,
    manifestChecksumSha256,
    writtenCount,
  };
}

async function reconcilePendingOperation(
  directory: SemiAutomaticOutputDirectoryHandle,
  manifest: SemiAutomaticSelectionOutputManifestV1,
  ranges: readonly SemiAutomaticSelectionRangeResponse[],
  now: () => string,
): Promise<SemiAutomaticSelectionOutputManifestV1> {
  const pending = manifest.pendingOperation;
  if (pending === null) return manifest;
  const range = ranges.find(
    (item) => item.expectedIndex === pending.expectedIndex,
  );
  const manual =
    pending.selectionStatus === 'MANUALLY_ADDED' ||
    pending.selectionStatus === 'MANUALLY_REPLACED';
  if (manual) {
    if (range === undefined) {
      throw new Error('SEMI_AUTOMATIC_SELECTION_PENDING_SOURCE_CHANGED');
    }
    const local = await readLocalOutputFile(directory, pending.outputName);
    if (local === null) {
      const rolledBack = rollbackSemiAutomaticOutputOperation(manifest, now());
      await writeSemiAutomaticSelectionOutputManifest(directory, rolledBack);
      return rolledBack;
    }
    if (local.checksumSha256 === pending.source.checksumSha256) {
      let finalized = finalizeSemiAutomaticOutputOperation(manifest, now());
      if (
        range.status === 'output_synced' &&
        range.sourceIndex === pending.source.sourceIndex &&
        range.sourceRelativePath === pending.source.relativePath &&
        range.sourceSizeBytes === pending.source.sizeBytes &&
        range.sourceChecksumSha256 === pending.source.checksumSha256 &&
        range.outputChecksumSha256 === pending.source.checksumSha256
      ) {
        finalized = acknowledgeSemiAutomaticLocalSelection(
          finalized,
          range.expectedIndex,
          range.revision,
          now(),
        );
      } else if (range.revision !== pending.expectedRangeRevision) {
        throw new Error('SEMI_AUTOMATIC_SELECTION_PENDING_SOURCE_CHANGED');
      }
      await writeSemiAutomaticSelectionOutputManifest(directory, finalized);
      return finalized;
    }
    if (
      pending.previousOutputChecksumSha256 !== null &&
      pending.previousOutputChecksumSha256 !== undefined &&
      local.checksumSha256 === pending.previousOutputChecksumSha256
    ) {
      const rolledBack = rollbackSemiAutomaticOutputOperation(manifest, now());
      await writeSemiAutomaticSelectionOutputManifest(directory, rolledBack);
      return rolledBack;
    }
    const conflicted = recordSemiAutomaticOutputConflict(
      manifest,
      {
        actualChecksumSha256: local.checksumSha256,
        detectedAt: now(),
        expectedChecksumSha256: pending.source.checksumSha256,
        expectedIndex: pending.expectedIndex,
        outputName: pending.outputName,
        reason: 'PENDING_TARGET_CHANGED',
      },
      now(),
    );
    await writeSemiAutomaticSelectionOutputManifest(directory, conflicted);
    return conflicted;
  }
  if (
    range === undefined ||
    (range.status !== 'auto_selected' && range.status !== 'output_synced') ||
    range.revision !== pending.expectedRangeRevision ||
    range.sourceChecksumSha256 !== pending.source.checksumSha256
  ) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_PENDING_SOURCE_CHANGED');
  }
  const local = await readLocalOutputFile(directory, pending.outputName);
  if (local === null) {
    const rolledBack = rollbackSemiAutomaticOutputOperation(manifest, now());
    await writeSemiAutomaticSelectionOutputManifest(directory, rolledBack);
    return rolledBack;
  }
  if (local.checksumSha256 === pending.source.checksumSha256) {
    const finalized = finalizeSemiAutomaticOutputOperation(manifest, now());
    await writeSemiAutomaticSelectionOutputManifest(directory, finalized);
    return finalized;
  }
  if (local.file.size === 0 && pending.selectionStatus === 'AUTO_SELECTED') {
    return manifest;
  }
  const conflicted = recordSemiAutomaticOutputConflict(
    manifest,
    {
      actualChecksumSha256: local.checksumSha256,
      detectedAt: now(),
      expectedChecksumSha256: pending.source.checksumSha256,
      expectedIndex: pending.expectedIndex,
      outputName: pending.outputName,
      reason: 'PENDING_TARGET_CHANGED',
    },
    now(),
  );
  await writeSemiAutomaticSelectionOutputManifest(directory, conflicted);
  return conflicted;
}

function pendingMatchesRange(
  manifest: SemiAutomaticSelectionOutputManifestV1,
  range: SemiAutomaticSelectionRangeResponse,
  source: SemiAutomaticLocalSourceIdentity,
  outputName: string,
): boolean {
  const pending = manifest.pendingOperation;
  return (
    pending !== null &&
    pending.selectionStatus === 'AUTO_SELECTED' &&
    pending.expectedIndex === range.expectedIndex &&
    pending.expectedRangeRevision === range.revision &&
    pending.outputName === outputName &&
    pending.source.sourceIndex === source.sourceIndex &&
    pending.source.relativePath === source.relativePath &&
    pending.source.sizeBytes === source.sizeBytes &&
    pending.source.checksumSha256 === source.checksumSha256
  );
}

function validateCompleteRangeSnapshot(
  run: SemiAutomaticSelectionRunResponse,
  ranges: readonly SemiAutomaticSelectionRangeResponse[],
): readonly SemiAutomaticSelectionRangeResponse[] {
  if (run.lastSequenceNumber < run.firstSequenceNumber) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_RANGE_SNAPSHOT_INVALID');
  }
  const expectedCount =
    Math.floor(
      (run.lastSequenceNumber - run.firstSequenceNumber) / run.fullRangeSize,
    ) + 1;
  const sorted = [...ranges].sort(
    (left, right) => left.expectedIndex - right.expectedIndex,
  );
  if (sorted.length !== expectedCount) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_RANGE_SNAPSHOT_INCOMPLETE');
  }
  for (let index = 0; index < sorted.length; index += 1) {
    const item = sorted[index];
    const rangeStart = run.firstSequenceNumber + index * run.fullRangeSize;
    const rangeEnd = Math.min(
      run.lastSequenceNumber,
      rangeStart + run.fullRangeSize - 1,
    );
    if (
      item === undefined ||
      item.runId !== run.id ||
      item.expectedIndex !== index ||
      item.rangeStart !== rangeStart ||
      item.rangeEnd !== rangeEnd ||
      item.fileName !== outputFileName(rangeStart, rangeEnd)
    ) {
      throw new Error('SEMI_AUTOMATIC_SELECTION_RANGE_SNAPSHOT_INVALID');
    }
  }
  return sorted;
}

function sourceIdentity(
  range: SemiAutomaticSelectionRangeResponse,
): SemiAutomaticLocalSourceIdentity {
  if (
    range.sourceIndex === null ||
    range.sourceIndex === undefined ||
    range.sourceRelativePath === null ||
    range.sourceSizeBytes === null ||
    range.sourceSizeBytes === undefined ||
    range.sourceChecksumSha256 === null
  ) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_RANGE_SOURCE_INCOMPLETE');
  }
  return {
    checksumSha256: range.sourceChecksumSha256,
    relativePath: range.sourceRelativePath,
    sizeBytes: range.sourceSizeBytes,
    sourceIndex: range.sourceIndex,
  };
}

function toRunIdentity(
  run: SemiAutomaticSelectionRunResponse,
): SemiAutomaticRunIdentity {
  return {
    diagnosticsChecksumSha256: run.diagnosticsChecksumSha256,
    direction: run.direction,
    expectedRangesFingerprint: run.expectedRangesFingerprint,
    firstSequenceNumber: run.firstSequenceNumber,
    fullRangeSize: run.fullRangeSize,
    groupingPolicyFingerprint: run.groupingPolicyFingerprint,
    id: run.id,
    lastSequenceNumber: run.lastSequenceNumber,
    rangeConvention: run.rangeConvention,
    recognizerFingerprint: run.recognizerFingerprint,
    source: {
      displayName: run.source.displayName,
      manifestChecksumSha256: run.source.manifestChecksumSha256,
      sourceFingerprint: run.source.sourceFingerprint,
    },
  };
}

function toBlob(value: unknown): Blob | null {
  if (value instanceof Blob) return value;
  if (value instanceof ArrayBuffer) return new Blob([value]);
  if (ArrayBuffer.isView(value)) {
    const bytes = new Uint8Array(value.byteLength);
    bytes.set(new Uint8Array(value.buffer, value.byteOffset, value.byteLength));
    return new Blob([bytes]);
  }
  return null;
}
