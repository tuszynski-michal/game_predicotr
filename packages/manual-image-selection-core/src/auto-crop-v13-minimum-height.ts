import type { SelectedImageCropBand } from '@game-predictor/manual-image-selection-core/crop';
import { CROP_V12_FINGERPRINT } from '@game-predictor/manual-image-selection-core/auto-crop-v12-registration';

export const CROP_V13_POLICY =
  'selected-image-board-band-v13-v12-minimum-height' as const;

/**
 * Read-only measurement of 2482 known-good JPEGs in `200575 - 222912 cut`
 * on 2026-09-17. It is versioned here so runtime does not depend on that
 * operator-local directory.
 */
export const CROP_V13_MINIMUM_HEIGHT_CONFIG = Object.freeze({
  referenceOutputCount: 2482,
  referenceWidthPx: 1080,
  referenceHeightMinimumPx: 402,
  referenceHeightMaximumPx: 714,
  referenceHeightMeanPx: 501.38,
  lowerTailShare: 0.05,
  lowerTailCount: 125,
  lowerTailMeanHeightPx: 422.96,
  safetyBufferRatio: 0.05,
  minimumHeightPxAtReferenceWidth: 401,
  expansionStrategy: 'centered-clamped-v1',
} as const);

export const CROP_V13_FINGERPRINT = `${CROP_V13_POLICY}|base:${CROP_V12_FINGERPRINT}|${JSON.stringify(CROP_V13_MINIMUM_HEIGHT_CONFIG)}`;

export function isCompatibleCropV13Fingerprint(value: string): boolean {
  return value === CROP_V13_FINGERPRINT;
}

export function cropV13MinimumHeightPx(crop: {
  readonly width: number;
  readonly height: number;
}): number {
  if (
    !Number.isInteger(crop.width) ||
    !Number.isInteger(crop.height) ||
    crop.width <= 0 ||
    crop.height <= 0
  )
    throw new Error('CROP_V13_DIMENSIONS_INVALID');
  return Math.min(
    crop.height,
    Math.ceil(
      (crop.width * CROP_V13_MINIMUM_HEIGHT_CONFIG.minimumHeightPxAtReferenceWidth) /
        CROP_V13_MINIMUM_HEIGHT_CONFIG.referenceWidthPx,
    ),
  );
}

export function cropMeetsV13MinimumHeight(crop: SelectedImageCropBand): boolean {
  return crop.bottomY - crop.topY >= cropV13MinimumHeightPx(crop);
}

/**
 * Preserve the v12 candidate and add context only. The result never moves
 * beyond the source bounds and retains the whole source if it is too short to
 * meet the proportional reference threshold.
 */
export function enforceCropV13MinimumHeight(
  crop: SelectedImageCropBand,
): SelectedImageCropBand {
  if (
    !Number.isInteger(crop.topY) ||
    !Number.isInteger(crop.bottomY) ||
    crop.topY < 0 ||
    crop.bottomY > crop.height ||
    crop.bottomY <= crop.topY
  )
    throw new Error('CROP_V13_BOUNDS_INVALID');
  const minimumHeight = cropV13MinimumHeightPx(crop);
  const currentHeight = crop.bottomY - crop.topY;
  if (currentHeight >= minimumHeight) return crop;

  const missingHeight = minimumHeight - currentHeight;
  let topY = Math.max(0, crop.topY - Math.floor(missingHeight / 2));
  let bottomY = Math.min(
    crop.height,
    crop.bottomY + Math.ceil(missingHeight / 2),
  );
  if (bottomY - topY < minimumHeight) {
    if (topY === 0) bottomY = Math.min(crop.height, minimumHeight);
    else topY = Math.max(0, bottomY - minimumHeight);
  }
  return { ...crop, topY, bottomY };
}
