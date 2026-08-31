'use client';

import type {
  AdminApiClient,
  SemiAutomaticSelectionRangeResponse,
} from '@game-predictor/admin-api-client';

import {
  acknowledgeSemiAutomaticLocalSelection,
  beginSemiAutomaticOutputOperation,
  finalizeSemiAutomaticOutputOperation,
  updateSemiAutomaticOutputSummary,
  type SemiAutomaticLocalSourceIdentity,
  type SemiAutomaticSelectionOutputManifestV1,
} from './semi-automatic-selection-output.ts';
import {
  replaceOwnedOutputBytes,
  sha256Hex,
  writeSemiAutomaticSelectionOutputManifest,
  type SemiAutomaticOutputDirectoryHandle,
} from './semi-automatic-selection-output-storage.ts';

export type SemiAutomaticSelectionReviewClient = Pick<
  AdminApiClient,
  | 'acknowledgeSemiAutomaticImageSelectionOutput'
  | 'listSemiAutomaticImageSelectionRanges'
>;

export interface ManualSemiAutomaticSource {
  readonly file: File;
  readonly relativePath: string;
  readonly sourceIndex: number;
}

export async function loadAllSemiAutomaticSelectionRanges(
  client: SemiAutomaticSelectionReviewClient,
  runId: string,
): Promise<readonly SemiAutomaticSelectionRangeResponse[]> {
  const ranges: SemiAutomaticSelectionRangeResponse[] = [];
  let afterExpectedIndex: number | undefined;
  for (;;) {
    const page = await client.listSemiAutomaticImageSelectionRanges(
      runId,
      afterExpectedIndex,
      500,
    );
    if (page.error !== undefined || page.data === undefined) {
      throw new Error('SEMI_AUTOMATIC_SELECTION_RANGES_UNAVAILABLE');
    }
    for (const item of page.data.items) {
      if (
        item.runId !== runId ||
        item.expectedIndex !== ranges.length ||
        (afterExpectedIndex !== undefined &&
          item.expectedIndex <= afterExpectedIndex)
      ) {
        throw new Error('SEMI_AUTOMATIC_SELECTION_RANGE_SNAPSHOT_INVALID');
      }
      ranges.push(item);
    }
    const next = page.data.nextAfterExpectedIndex;
    if (next === null || next === undefined) return ranges;
    if (page.data.items.length === 0 || next === afterExpectedIndex) {
      throw new Error('SEMI_AUTOMATIC_SELECTION_RANGE_SNAPSHOT_INVALID');
    }
    afterExpectedIndex = next;
  }
}

export function manualEditSourceStartIndex(
  ranges: readonly SemiAutomaticSelectionRangeResponse[],
  expectedIndex: number,
  sourceCount: number,
): number {
  if (sourceCount < 1) return 0;
  const active = ranges[expectedIndex];
  if (active?.sourceIndex !== null && active?.sourceIndex !== undefined) {
    return clampSourceIndex(active.sourceIndex, sourceCount);
  }
  for (let index = expectedIndex - 1; index >= 0; index -= 1) {
    const sourceIndex = ranges[index]?.sourceIndex;
    if (sourceIndex !== null && sourceIndex !== undefined) {
      return clampSourceIndex(sourceIndex + 1, sourceCount);
    }
  }
  return 0;
}

export async function writeManualSemiAutomaticSelection(input: {
  readonly client: Pick<
    AdminApiClient,
    'acknowledgeSemiAutomaticImageSelectionOutput'
  >;
  readonly directory: SemiAutomaticOutputDirectoryHandle;
  readonly manifest: SemiAutomaticSelectionOutputManifestV1;
  readonly range: SemiAutomaticSelectionRangeResponse;
  readonly runId: string;
  readonly source: ManualSemiAutomaticSource;
  readonly now?: () => string;
  readonly operationId?: () => string;
}): Promise<{
  readonly manifest: SemiAutomaticSelectionOutputManifestV1;
  readonly manifestChecksumSha256: string;
  readonly range: SemiAutomaticSelectionRangeResponse;
}> {
  const now = input.now ?? (() => new Date().toISOString());
  const operationId = input.operationId ?? (() => crypto.randomUUID());
  const previous = input.manifest.selections.find(
    (selection) => selection.expectedIndex === input.range.expectedIndex,
  );
  const checksumSha256 = await sha256Hex(input.source.file);
  const source: SemiAutomaticLocalSourceIdentity = {
    checksumSha256,
    relativePath: input.source.relativePath,
    sizeBytes: input.source.file.size,
    sourceIndex: input.source.sourceIndex,
  };
  let manifest = beginSemiAutomaticOutputOperation(
    input.manifest,
    {
      expectedIndex: input.range.expectedIndex,
      expectedRangeRevision: input.range.revision,
      operationId: operationId(),
      outputName: input.range.fileName,
      previousOutputChecksumSha256: previous?.outputChecksumSha256 ?? null,
      rangeEnd: input.range.rangeEnd,
      rangeStart: input.range.rangeStart,
      selectionStatus:
        previous === undefined ? 'MANUALLY_ADDED' : 'MANUALLY_REPLACED',
      source,
      startedAt: now(),
    },
    now(),
  );
  await writeSemiAutomaticSelectionOutputManifest(input.directory, manifest);
  await replaceOwnedOutputBytes({
    directory: input.directory,
    expectedChecksumSha256: source.checksumSha256,
    expectedPreviousChecksumSha256: previous?.outputChecksumSha256 ?? null,
    expectedSizeBytes: source.sizeBytes,
    outputName: input.range.fileName,
    source: input.source.file,
  });
  manifest = finalizeSemiAutomaticOutputOperation(manifest, now());
  await writeSemiAutomaticSelectionOutputManifest(input.directory, manifest);

  const acknowledgement =
    await input.client.acknowledgeSemiAutomaticImageSelectionOutput(
      input.runId,
      input.range.expectedIndex,
      {
        expectedRevision: input.range.revision,
        expectedSourceChecksumSha256: source.checksumSha256,
        outputChecksumSha256: source.checksumSha256,
        sourceIndex: source.sourceIndex,
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
    input.range.expectedIndex,
    acknowledgement.data.revision,
    now(),
  );
  const gaps = manifest.gaps.filter(
    (expectedIndex) => expectedIndex !== input.range.expectedIndex,
  );
  manifest = updateSemiAutomaticOutputSummary(manifest, {
    gaps,
    now: now(),
    status: gaps.length === 0 ? 'completed' : 'review_mode',
  });
  const manifestChecksumSha256 =
    await writeSemiAutomaticSelectionOutputManifest(input.directory, manifest);
  return {
    manifest,
    manifestChecksumSha256,
    range: acknowledgement.data,
  };
}

export function isFormInteractionTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.isContentEditable ||
    target.closest(
      'input, select, textarea, button, [contenteditable="true"]',
    ) !== null
  );
}

function clampSourceIndex(value: number, sourceCount: number): number {
  return Math.max(0, Math.min(sourceCount - 1, value));
}
