import {
  sortAndValidateSequenceFiles,
  type ParsedSequenceFile,
} from '@game-predictor/manual-image-selection-core/repair';

export const SELECTED_IMAGE_CROP_SCHEMA_VERSION = 1 as const;
export const SELECTED_IMAGE_CROP_RENDERER =
  'manual-selected-image-band-crop-jpeg-v1' as const;
export const SELECTED_IMAGE_CROP_JPEG_QUALITY = 0.98 as const;
export const SELECTED_IMAGE_CROP_DEFAULT_TOP_RATIO = 0.18 as const;
export const SELECTED_IMAGE_CROP_DEFAULT_BOTTOM_RATIO = 0.86 as const;
export const SELECTED_IMAGE_CROP_MINIMUM_HEIGHT_PX = 64 as const;
export const SELECTED_IMAGE_CROP_MINIMUM_HEIGHT_RATIO = 0.1 as const;

export interface SelectedImageDimensions {
  readonly width: number;
  readonly height: number;
}

export interface SelectedImageCropBand extends SelectedImageDimensions {
  readonly topY: number;
  readonly bottomY: number;
}

export interface SelectedImageCropSourceEntry {
  readonly fileName: string;
  readonly sizeBytes: number;
  readonly lastModifiedMs: number;
  readonly rangeStart: number;
  readonly rangeEnd: number;
}

export interface SelectedImageCropResult {
  readonly status: 'accepted';
  readonly crop: SelectedImageCropBand;
  readonly sourceChecksumSha256: string;
  readonly outputChecksumSha256: string;
  readonly acceptedAt: string;
}

export interface SelectedImageCropManifestEntry
  extends SelectedImageCropSourceEntry {
  readonly result: SelectedImageCropResult | null;
}

export interface SelectedImageCropPendingOperation {
  readonly kind: 'write_crop';
  readonly fileName: string;
  readonly expectedSourceChecksumSha256: string;
  readonly expectedOutputChecksumSha256: string;
  readonly crop: SelectedImageCropBand;
  readonly startedAt: string;
  readonly replacesOutputChecksumSha256: string | null;
}

export interface SelectedImageCropManifestV1 {
  readonly schemaVersion: typeof SELECTED_IMAGE_CROP_SCHEMA_VERSION;
  readonly rendererVersion: typeof SELECTED_IMAGE_CROP_RENDERER;
  readonly sourceDirectoryName: string;
  readonly outputDirectoryName: string;
  readonly sourceInventoryChecksumSha256: string;
  readonly revision: number;
  readonly currentIndex: number;
  readonly entries: readonly SelectedImageCropManifestEntry[];
  readonly pendingOperation: SelectedImageCropPendingOperation | null;
  readonly updatedAt: string;
}

export type SelectedImageCropRecoveryAction =
  | 'none'
  | 'rollback_missing_output'
  | 'finalize_matching_output'
  | 'block_conflicting_output';

export function createDefaultSelectedImageCropBand(
  dimensions: SelectedImageDimensions,
): SelectedImageCropBand {
  assertDimensions(dimensions);
  return validateSelectedImageCropBand({
    ...dimensions,
    topY: Math.round(dimensions.height * SELECTED_IMAGE_CROP_DEFAULT_TOP_RATIO),
    bottomY: Math.round(
      dimensions.height * SELECTED_IMAGE_CROP_DEFAULT_BOTTOM_RATIO,
    ),
  });
}

export function inheritSelectedImageCropBand(
  previous: SelectedImageCropBand,
  dimensions: SelectedImageDimensions,
): SelectedImageCropBand {
  validateSelectedImageCropBand(previous);
  assertDimensions(dimensions);
  return validateSelectedImageCropBand({
    ...dimensions,
    topY: Math.round((previous.topY / previous.height) * dimensions.height),
    bottomY: Math.round(
      (previous.bottomY / previous.height) * dimensions.height,
    ),
  });
}

export function validateSelectedImageCropBand(
  crop: SelectedImageCropBand,
): SelectedImageCropBand {
  assertDimensions(crop);
  if (
    !Number.isInteger(crop.topY) ||
    !Number.isInteger(crop.bottomY) ||
    crop.topY < 0 ||
    crop.bottomY > crop.height ||
    crop.bottomY <= crop.topY
  ) {
    throw new Error('SELECTED_IMAGE_CROP_BOUNDS_INVALID');
  }
  const minimumHeight = Math.max(
    SELECTED_IMAGE_CROP_MINIMUM_HEIGHT_PX,
    Math.ceil(crop.height * SELECTED_IMAGE_CROP_MINIMUM_HEIGHT_RATIO),
  );
  if (crop.bottomY - crop.topY < minimumHeight) {
    throw new Error('SELECTED_IMAGE_CROP_TOO_SHORT');
  }
  return crop;
}

export function selectedImageCropRatios(crop: SelectedImageCropBand): {
  readonly top: number;
  readonly bottom: number;
} {
  validateSelectedImageCropBand(crop);
  return { top: crop.topY / crop.height, bottom: crop.bottomY / crop.height };
}

export function validateSelectedImageCropSources(
  files: readonly {
    readonly fileName: string;
    readonly sizeBytes: number;
    readonly lastModifiedMs: number;
  }[],
): readonly SelectedImageCropSourceEntry[] {
  const metadata = new Map(files.map((file) => [file.fileName, file]));
  return sortAndValidateSequenceFiles(files.map((file) => file.fileName)).map(
    (range: ParsedSequenceFile) => {
      const file = metadata.get(range.fileName);
      if (
        file === undefined ||
        !Number.isSafeInteger(file.sizeBytes) ||
        file.sizeBytes <= 0 ||
        !Number.isSafeInteger(file.lastModifiedMs) ||
        file.lastModifiedMs < 0
      ) {
        throw new Error(`SELECTED_IMAGE_CROP_SOURCE_INVALID:${range.fileName}`);
      }
      return {
        fileName: range.fileName,
        sizeBytes: file.sizeBytes,
        lastModifiedMs: file.lastModifiedMs,
        rangeStart: range.start,
        rangeEnd: range.end,
      };
    },
  );
}

export function createSelectedImageCropManifest(input: {
  readonly sourceDirectoryName: string;
  readonly outputDirectoryName: string;
  readonly sourceInventoryChecksumSha256: string;
  readonly entries: readonly SelectedImageCropSourceEntry[];
  readonly now: string;
}): SelectedImageCropManifestV1 {
  if (input.sourceDirectoryName.trim() === '')
    throw new Error('SELECTED_IMAGE_CROP_SOURCE_NAME_REQUIRED');
  if (input.outputDirectoryName !== `${input.sourceDirectoryName} cut`)
    throw new Error('SELECTED_IMAGE_CROP_OUTPUT_NAME_INVALID');
  assertSha256(input.sourceInventoryChecksumSha256);
  const entries = validateSelectedImageCropSources(input.entries);
  if (entries.length === 0) throw new Error('SELECTED_IMAGE_CROP_SOURCE_EMPTY');
  return {
    schemaVersion: SELECTED_IMAGE_CROP_SCHEMA_VERSION,
    rendererVersion: SELECTED_IMAGE_CROP_RENDERER,
    sourceDirectoryName: input.sourceDirectoryName,
    outputDirectoryName: input.outputDirectoryName,
    sourceInventoryChecksumSha256: input.sourceInventoryChecksumSha256,
    revision: 0,
    currentIndex: 0,
    entries: entries.map((entry) => ({ ...entry, result: null })),
    pendingOperation: null,
    updatedAt: input.now,
  };
}

export function validateSelectedImageCropManifest(
  manifest: SelectedImageCropManifestV1,
  expectedInventoryChecksumSha256?: string,
): SelectedImageCropManifestV1 {
  if (
    manifest.schemaVersion !== SELECTED_IMAGE_CROP_SCHEMA_VERSION ||
    manifest.rendererVersion !== SELECTED_IMAGE_CROP_RENDERER ||
    manifest.outputDirectoryName !== `${manifest.sourceDirectoryName} cut`
  ) {
    throw new Error('SELECTED_IMAGE_CROP_MANIFEST_INCOMPATIBLE');
  }
  assertSha256(manifest.sourceInventoryChecksumSha256);
  if (
    expectedInventoryChecksumSha256 !== undefined &&
    manifest.sourceInventoryChecksumSha256 !==
      expectedInventoryChecksumSha256
  ) {
    throw new Error('SELECTED_IMAGE_CROP_SOURCE_CHANGED');
  }
  if (
    !Number.isInteger(manifest.revision) ||
    manifest.revision < 0 ||
    !Number.isInteger(manifest.currentIndex) ||
    manifest.currentIndex < 0 ||
    manifest.currentIndex >= manifest.entries.length
  ) {
    throw new Error('SELECTED_IMAGE_CROP_MANIFEST_INVALID');
  }
  validateSelectedImageCropSources(manifest.entries);
  for (const entry of manifest.entries) {
    if (entry.result !== null) {
      validateSelectedImageCropBand(entry.result.crop);
      assertSha256(entry.result.sourceChecksumSha256);
      assertSha256(entry.result.outputChecksumSha256);
    }
  }
  if (manifest.pendingOperation !== null) {
    validateSelectedImageCropBand(manifest.pendingOperation.crop);
    assertSha256(manifest.pendingOperation.expectedSourceChecksumSha256);
    assertSha256(manifest.pendingOperation.expectedOutputChecksumSha256);
  }
  return manifest;
}

export function beginSelectedImageCropWrite(
  manifest: SelectedImageCropManifestV1,
  operation: SelectedImageCropPendingOperation,
  now: string,
): SelectedImageCropManifestV1 {
  validateSelectedImageCropManifest(manifest);
  if (manifest.pendingOperation !== null)
    throw new Error('SELECTED_IMAGE_CROP_OPERATION_ACTIVE');
  const entry = manifest.entries.find(
    (candidate) => candidate.fileName === operation.fileName,
  );
  if (entry === undefined) throw new Error('SELECTED_IMAGE_CROP_SOURCE_UNKNOWN');
  validateSelectedImageCropBand(operation.crop);
  assertSha256(operation.expectedSourceChecksumSha256);
  assertSha256(operation.expectedOutputChecksumSha256);
  const currentOutputChecksum = entry.result?.outputChecksumSha256 ?? null;
  if (currentOutputChecksum !== operation.replacesOutputChecksumSha256) {
    throw new Error('SELECTED_IMAGE_CROP_REPLACEMENT_STALE');
  }
  return {
    ...manifest,
    revision: manifest.revision + 1,
    pendingOperation: operation,
    updatedAt: now,
  };
}

export function finalizeSelectedImageCropWrite(
  manifest: SelectedImageCropManifestV1,
  now: string,
): SelectedImageCropManifestV1 {
  const pending = manifest.pendingOperation;
  if (pending === null) throw new Error('SELECTED_IMAGE_CROP_OPERATION_MISSING');
  const index = manifest.entries.findIndex(
    (entry) => entry.fileName === pending.fileName,
  );
  if (index < 0) throw new Error('SELECTED_IMAGE_CROP_SOURCE_UNKNOWN');
  const entries = [...manifest.entries];
  entries[index] = {
    ...entries[index]!,
    result: {
      status: 'accepted',
      crop: pending.crop,
      sourceChecksumSha256: pending.expectedSourceChecksumSha256,
      outputChecksumSha256: pending.expectedOutputChecksumSha256,
      acceptedAt: now,
    },
  };
  return {
    ...manifest,
    revision: manifest.revision + 1,
    currentIndex: Math.min(index + 1, entries.length - 1),
    entries,
    pendingOperation: null,
    updatedAt: now,
  };
}

export function selectedImageCropRecoveryAction(
  manifest: SelectedImageCropManifestV1,
  observedOutputChecksumSha256: string | null,
): SelectedImageCropRecoveryAction {
  const pending = manifest.pendingOperation;
  if (pending === null) return 'none';
  if (observedOutputChecksumSha256 === null) return 'rollback_missing_output';
  return observedOutputChecksumSha256 ===
    pending.expectedOutputChecksumSha256
    ? 'finalize_matching_output'
    : 'block_conflicting_output';
}

export function rollbackSelectedImageCropWrite(
  manifest: SelectedImageCropManifestV1,
  now: string,
): SelectedImageCropManifestV1 {
  if (manifest.pendingOperation === null) return manifest;
  return {
    ...manifest,
    revision: manifest.revision + 1,
    pendingOperation: null,
    updatedAt: now,
  };
}

function assertDimensions(dimensions: SelectedImageDimensions): void {
  if (
    !Number.isInteger(dimensions.width) ||
    !Number.isInteger(dimensions.height) ||
    dimensions.width <= 0 ||
    dimensions.height <= 0
  ) {
    throw new Error('SELECTED_IMAGE_CROP_DIMENSIONS_INVALID');
  }
}

function assertSha256(value: string): void {
  if (!/^[a-f0-9]{64}$/u.test(value))
    throw new Error('SELECTED_IMAGE_CROP_CHECKSUM_INVALID');
}
