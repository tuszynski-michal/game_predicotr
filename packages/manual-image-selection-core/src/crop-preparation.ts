import {
  CROP_V11_POLICY,
  CROP_V11_CONFIG,
  type LayoutEvidence,
  type StructuralSample,
} from '@game-predictor/manual-image-selection-core/auto-crop-v11';
import {
  boundStructuralCrop,
  detectStructuralCrop,
  findNumberRegions,
} from '@game-predictor/manual-image-selection-core/auto-crop-v11-boundaries';
import {
  SELECTED_IMAGE_AUTO_CROP_POLICY,
  type SelectedImageAutoCropProposal,
} from '@game-predictor/manual-image-selection-core/auto-crop';
import type { SelectedImageCropBand } from '@game-predictor/manual-image-selection-core/crop';
import {
  CROP_V12_FINGERPRINT,
  CROP_V12_POLICY,
  cropFromRegisteredBoardBand,
  registerFourPointBoardBand,
  type FourPointCropAnchor,
  type PreparedFourPointRegistrationAnchor,
} from '@game-predictor/manual-image-selection-core/auto-crop-v12-registration';

// Activation is a separate quality decision. No hidden shadow/default switch.
export const CROP_V11_RELEASE_ENABLED = false;
export const CROP_V12_RELEASE_ENABLED = true;
export const ACTIVE_SELECTED_IMAGE_CROP_POLICY = CROP_V12_POLICY;
export { CROP_V12_FINGERPRINT } from '@game-predictor/manual-image-selection-core/auto-crop-v12-registration';
export { CROP_V11_FINGERPRINT } from '@game-predictor/manual-image-selection-core/auto-crop-v11';
import { CROP_V11_FINGERPRINT } from '@game-predictor/manual-image-selection-core/auto-crop-v11';
export function assertCropPreparationPolicy(policy: string): void {
  if (
    policy !== SELECTED_IMAGE_AUTO_CROP_POLICY &&
    policy !== CROP_V11_POLICY &&
    policy !== CROP_V12_POLICY
  )
    throw new Error('SELECTED_IMAGE_CROP_POLICY_UNSUPPORTED');
}

export interface FourPointCropPreparationAnchor {
  readonly descriptor: FourPointCropAnchor;
  readonly image: StructuralSample;
}

export interface PreparedFourPointCropPreparationAnchor {
  readonly descriptor: FourPointCropAnchor;
  readonly prepared: PreparedFourPointRegistrationAnchor;
}

export function intersectRegisteredAndStructuralCrop(input: {
  readonly registeredCrop: SelectedImageCropBand;
  readonly structuralCrop: SelectedImageCropBand;
  readonly registeredBoardBand: FourPointCropAnchor['boardBand'];
}): SelectedImageCropBand {
  const boardTop = Math.floor(
    Math.min(...input.registeredBoardBand.map((point) => point.y)),
  );
  const boardBottom = Math.ceil(
    Math.max(...input.registeredBoardBand.map((point) => point.y)),
  );
  return {
    ...input.registeredCrop,
    topY: Math.min(
      Math.max(input.registeredCrop.topY, input.structuralCrop.topY),
      boardTop,
    ),
    bottomY: Math.max(
      Math.min(input.registeredCrop.bottomY, input.structuralCrop.bottomY),
      boardBottom,
    ),
  };
}

export async function prepareFourPointRegisteredCrop(
  source: StructuralSample,
  anchor: FourPointCropPreparationAnchor | null,
  yieldBetween: () => Promise<void> = () => Promise.resolve(),
): Promise<SelectedImageAutoCropProposal> {
  const structural = await prepareStructuralCrop(source, yieldBetween);
  return finishFourPointRegisteredCrop(
    source,
    structural,
    anchor,
    yieldBetween,
  );
}

export async function finishFourPointRegisteredCrop(
  source: StructuralSample,
  structural: SelectedImageAutoCropProposal,
  anchor:
    | FourPointCropPreparationAnchor
    | PreparedFourPointCropPreparationAnchor
    | null,
  yieldBetween: () => Promise<void> = () => Promise.resolve(),
): Promise<SelectedImageAutoCropProposal> {
  if (anchor === null) {
    return {
      ...structural,
      policyVersion: CROP_V12_POLICY,
      preparationFingerprint: CROP_V12_FINGERPRINT,
    };
  }
  if (structural.structural?.reason === 'complete_layout_board_buffer') {
    return {
      ...structural,
      policyVersion: CROP_V12_POLICY,
      preparationFingerprint: CROP_V12_FINGERPRINT,
    };
  }
  await yieldBetween();
  const registration = registerFourPointBoardBand({
    anchor: anchor.descriptor,
    ...('prepared' in anchor
      ? { preparedAnchor: anchor.prepared }
      : { anchorImage: anchor.image }),
    targetImage: source,
    structuralCrossCheck: structural.structural?.status === 'detected',
  });
  const crop = cropFromRegisteredBoardBand({
    evidence: registration,
    sourceWidth: source.width,
    sourceHeight: source.height,
    anchorMedianBoardHeight: anchor.descriptor.medianBoardHeight,
  });
  const currentEvidence = structural.structural;
  const currentContent = currentEvidence
    ? [...currentEvidence.boards, ...currentEvidence.labels]
    : [];
  const protectsCurrentEvidence =
    crop !== null &&
    (currentEvidence?.status !== 'detected' ||
      (currentContent.length === 18 &&
        crop.topY <= Math.min(...currentContent.map((box) => box.top)) - 4 &&
        crop.bottomY >=
          Math.max(...currentContent.map((box) => box.bottom)) + 4));
  if (
    registration.status !== 'registered' ||
    crop === null ||
    !protectsCurrentEvidence
  ) {
    const retainedRegistration =
      registration.status === 'registered' && !protectsCurrentEvidence
        ? {
            ...registration,
            status: 'needs_manual_crop' as const,
            reason: 'structural_registration_conflict' as const,
            registeredBoardBand: null,
          }
        : registration;
    return {
      ...structural,
      policyVersion: CROP_V12_POLICY,
      preparationFingerprint: CROP_V12_FINGERPRINT,
      registration: retainedRegistration,
    };
  }
  const consensusCrop =
    currentEvidence?.status === 'detected'
      ? intersectRegisteredAndStructuralCrop({
          registeredCrop: crop,
          structuralCrop: structural.crop,
          registeredBoardBand: registration.registeredBoardBand!,
        })
      : crop;
  return {
    ...structural,
    crop: consensusCrop,
    policyVersion: CROP_V12_POLICY,
    preparationFingerprint: CROP_V12_FINGERPRINT,
    registration,
    classification: 'conservative',
    strategy: 'multicolumn_panel',
  };
}
// Same deterministic sampler for Canvas pixels and Node pixels. EXIF has already
// been applied by the decoder; this module never rotates or stretches the source.
export function sampleCanonicalCropImage(
  source: StructuralSample,
  level: number,
): StructuralSample {
  if (
    ![960, 1600].includes(level) ||
    !Number.isInteger(source.width) ||
    !Number.isInteger(source.height) ||
    source.width < 8 ||
    source.height < 8 ||
    source.width * source.height > 80_000_000 ||
    source.rgba.length !== source.width * source.height * 4
  )
    throw new Error('CROP_V11_SOURCE_INVALID');
  const ratio = Math.min(1, level / Math.max(source.width, source.height));
  const width = Math.round(source.width * ratio),
    height = Math.round(source.height * ratio),
    rgba = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++)
    for (let x = 0; x < width; x++) {
      const fx = Math.max(0, ((x + 0.5) * source.width) / width - 0.5),
        fy = Math.max(0, ((y + 0.5) * source.height) / height - 0.5);
      const x0 = Math.floor(fx),
        y0 = Math.floor(fy),
        x1 = Math.min(source.width - 1, x0 + 1),
        y1 = Math.min(source.height - 1, y0 + 1),
        dx = fx - x0,
        dy = fy - y0;
      for (let c = 0; c < 3; c++)
        rgba[(y * width + x) * 4 + c] = Math.round(
          (source.rgba[(y0 * source.width + x0) * 4 + c]! * (1 - dx) +
            source.rgba[(y0 * source.width + x1) * 4 + c]! * dx) *
            (1 - dy) +
            (source.rgba[(y1 * source.width + x0) * 4 + c]! * (1 - dx) +
              source.rgba[(y1 * source.width + x1) * 4 + c]! * dx) *
              dy,
        );
      rgba[(y * width + x) * 4 + 3] = 255;
    }
  return { width, height, rgba };
}

export function projectDetectedLayout(
  layout: LayoutEvidence,
  target: { width: number; height: number },
): LayoutEvidence {
  if (layout.status !== 'detected' || layout.boards.length !== 9)
    throw new Error('CROP_V11_LAYOUT_NOT_DETECTED');
  const sx = target.width / layout.analysisWidth;
  const sy = target.height / layout.analysisHeight;
  if (
    !Number.isFinite(sx) ||
    !Number.isFinite(sy) ||
    Math.abs(sx / sy - 1) > 0.01
  )
    throw new Error('CROP_V11_COORDINATES_INVALID');
  return {
    ...layout,
    analysisWidth: target.width,
    analysisHeight: target.height,
    boards: layout.boards.map((board) => ({
      ...board,
      left: board.left * sx,
      top: board.top * sy,
      right: board.right * sx,
      bottom: board.bottom * sy,
    })),
  };
}

export async function prepareStructuralCrop(
  source: StructuralSample,
  yieldBetween: () => Promise<void> = () => Promise.resolve(),
): Promise<SelectedImageAutoCropProposal> {
  let result: ReturnType<typeof detectStructuralCrop> | undefined;
  let retainedLayout: LayoutEvidence | undefined;
  const executed: number[] = [];
  for (const level of CROP_V11_CONFIG.levels) {
    if (executed.length && Math.max(source.width, source.height) <= 960) break;
    const sample = sampleCanonicalCropImage(source, level);
    result = detectStructuralCrop(sample, {
      width: source.width,
      height: source.height,
    });
    executed.push(level);
    if (result.status === 'detected') break;
    if (retainedLayout) {
      const projected = projectDetectedLayout(retainedLayout, sample);
      const labels = findNumberRegions(sample, projected.boards);
      const refined = boundStructuralCrop(projected, labels, {
        width: source.width,
        height: source.height,
      });
      if (refined.status === 'detected') {
        result = refined;
        break;
      }
    }
    if (
      result.reason === 'number_regions_missing' &&
      result.boards.length === 9
    )
      retainedLayout = {
        status: 'detected',
        reason: 'complete_layout',
        boards: result.boards.map((board) => ({
          ...board,
          support: 0,
          textureTiles: 0,
        })),
        candidateCount: result.candidateCount,
        analysisWidth: source.width,
        analysisHeight: source.height,
      };
    await yieldBetween();
  }
  if (!result) throw new Error('CROP_V11_RESULT_MISSING');
  return {
    crop: result.crop,
    policyVersion: CROP_V11_POLICY,
    confidence: null,
    structural: result,
    preparationFingerprint: CROP_V11_FINGERPRINT,
    analysisLevels: executed,
    // Legacy display envelope retained for old readers. V11 UI uses structural.
    classification: result.status === 'detected' ? 'conservative' : 'safe_wide',
    strategy: result.status === 'detected' ? 'multicolumn_panel' : 'safe_wide',
    evidence: {
      sampleWidth: result.analysisWidth,
      sampleHeight: result.analysisHeight,
      localBounds: [],
      chromaticCandidateCount: 0,
      structuralCandidateCount: result.candidateCount,
      chromaticSupportedStrips: [],
      structuralSupportedStrips: [],
      evidenceIoU: null,
      boundaryExpanded: false,
      fallbackReason: result.status === 'detected' ? null : 'no_wide_evidence',
    },
  };
}
