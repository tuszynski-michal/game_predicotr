import {
  createDefaultSelectedImageCropBand,
  validateSelectedImageCropBand,
  type SelectedImageCropBand,
  type SelectedImageDimensions,
} from '@game-predictor/manual-image-selection-core/crop';

export const SELECTED_IMAGE_AUTO_CROP_POLICY =
  'selected-image-board-band-v4-conservative-multicolumn' as const;
export const SELECTED_IMAGE_AUTO_CROP_SAMPLE_WIDTH = 512 as const;
/** Preserve more context above the detected board band for tilted cabinet screens. */
export const SELECTED_IMAGE_AUTO_CROP_TOP_PADDING_RATIO = 0.12 as const;
export const SELECTED_IMAGE_AUTO_CROP_BOTTOM_PADDING_RATIO = 0.045 as const;
export const SELECTED_IMAGE_AUTO_CROP_SAFE_WIDE_TOP_RATIO = 0.05 as const;
export const SELECTED_IMAGE_AUTO_CROP_SAFE_WIDE_BOTTOM_RATIO = 0.95 as const;

export type SelectedImageAutoCropStrategy = 'multicolumn_panel' | 'safe_wide';

export type SelectedImageAutoCropClassification =
  'high_confidence' | 'conservative' | 'safe_wide';

export type SelectedImageAutoCropSignal = 'chromatic' | 'structural';

export type SelectedImageAutoCropFallbackReason =
  'no_wide_evidence' | 'crop_too_short' | 'invalid_bounds' | null;

export interface SelectedImageAutoCropLocalBoundary {
  readonly signal: SelectedImageAutoCropSignal;
  readonly stripIndex: number;
  readonly topRatio: number;
  readonly bottomRatio: number;
}

export interface SelectedImageAutoCropEvidence {
  readonly sampleWidth: number;
  readonly sampleHeight: number;
  readonly localBounds: readonly SelectedImageAutoCropLocalBoundary[];
  readonly chromaticCandidateCount: number;
  readonly structuralCandidateCount: number;
  readonly chromaticSupportedStrips: readonly number[];
  readonly structuralSupportedStrips: readonly number[];
  readonly evidenceIoU: number | null;
  readonly boundaryExpanded: boolean;
  readonly fallbackReason: SelectedImageAutoCropFallbackReason;
}

export interface SelectedImageAutoCropProposal {
  readonly crop: SelectedImageCropBand;
  readonly strategy: SelectedImageAutoCropStrategy;
  readonly classification: SelectedImageAutoCropClassification;
  readonly confidence: number;
  readonly policyVersion: typeof SELECTED_IMAGE_AUTO_CROP_POLICY;
  readonly evidence: SelectedImageAutoCropEvidence;
}

export interface SelectedImageAutoCropSample {
  readonly width: number;
  readonly height: number;
  readonly rgba: Uint8ClampedArray;
}

interface SignalCandidate {
  readonly start: number;
  readonly end: number;
  readonly localBounds: readonly LocalBoundary[];
  readonly score: number;
  readonly supportedStrips: readonly number[];
}

interface LocalBoundary {
  readonly top: number;
  readonly bottom: number;
}

interface SignalGrid {
  readonly scoresByStrip: readonly (readonly number[])[];
  readonly activeByStrip: readonly (readonly boolean[])[];
}

const STRIP_COUNT = 9;
const REQUIRED_STRIP_COUNT = 5;
const ANALYSIS_X_MARGIN_RATIO = 0.03;

export function detectSelectedImageCropBand(
  sample: SelectedImageAutoCropSample,
  source: SelectedImageDimensions,
): SelectedImageAutoCropProposal {
  assertSample(sample);
  const { width, height, rgba } = sample;
  const { chromatic, structural } = measureSignals(width, height, rgba);
  const chromaticCandidates = signalCandidates(chromatic, height, 0.075);
  const structuralCandidates = signalCandidates(structural, height, 0.085);
  const selected = selectEvidence(chromaticCandidates, structuralCandidates);
  if (selected === null)
    return safeWideProposal(source, width, height, {
      chromaticCandidateCount: chromaticCandidates.length,
      structuralCandidateCount: structuralCandidates.length,
      fallbackReason: 'no_wide_evidence',
    });

  const localBounds = selected.candidates.flatMap(
    (candidate) => candidate.localBounds,
  );
  let top =
    percentile(
      localBounds.map((boundary) => boundary.top),
      0.1,
    ) - Math.round(height * SELECTED_IMAGE_AUTO_CROP_TOP_PADDING_RATIO);
  let bottom =
    percentile(
      localBounds.map((boundary) => boundary.bottom),
      0.9,
    ) + Math.round(height * SELECTED_IMAGE_AUTO_CROP_BOTTOM_PADDING_RATIO);
  const broadContent = broadContentRows(chromatic, structural, height);
  const initialTop = top;
  const initialBottom = bottom;
  [top, bottom] = expandPastBoundaryContent(top, bottom, broadContent, height);
  top = Math.max(0, top);
  bottom = Math.min(height, bottom + 1);
  if ((bottom - top) / height < 0.4)
    return safeWideProposal(source, width, height, {
      chromaticCandidateCount: chromaticCandidates.length,
      structuralCandidateCount: structuralCandidates.length,
      fallbackReason: 'crop_too_short',
    });

  try {
    return {
      crop: validateSelectedImageCropBand({
        ...source,
        topY: Math.round((top / height) * source.height),
        bottomY: Math.round((bottom / height) * source.height),
      }),
      strategy: 'multicolumn_panel',
      classification: selected.classification,
      confidence: Number(selected.confidence.toFixed(3)),
      policyVersion: SELECTED_IMAGE_AUTO_CROP_POLICY,
      evidence: buildEvidence({
        width,
        height,
        chromaticCandidates,
        structuralCandidates,
        selected,
        boundaryExpanded: top !== initialTop || bottom !== initialBottom,
        fallbackReason: null,
      }),
    };
  } catch {
    return safeWideProposal(source, width, height, {
      chromaticCandidateCount: chromaticCandidates.length,
      structuralCandidateCount: structuralCandidates.length,
      fallbackReason: 'invalid_bounds',
    });
  }
}

function safeWideProposal(
  source: SelectedImageDimensions,
  sampleWidth: number,
  sampleHeight: number,
  summary: {
    readonly chromaticCandidateCount: number;
    readonly structuralCandidateCount: number;
    readonly fallbackReason: Exclude<SelectedImageAutoCropFallbackReason, null>;
  },
): SelectedImageAutoCropProposal {
  const evidence: SelectedImageAutoCropEvidence = {
    sampleWidth,
    sampleHeight,
    localBounds: [],
    chromaticCandidateCount: summary.chromaticCandidateCount,
    structuralCandidateCount: summary.structuralCandidateCount,
    chromaticSupportedStrips: [],
    structuralSupportedStrips: [],
    evidenceIoU: null,
    boundaryExpanded: false,
    fallbackReason: summary.fallbackReason,
  };
  try {
    return {
      crop: validateSelectedImageCropBand({
        ...source,
        topY: Math.floor(
          source.height * SELECTED_IMAGE_AUTO_CROP_SAFE_WIDE_TOP_RATIO,
        ),
        bottomY: Math.ceil(
          source.height * SELECTED_IMAGE_AUTO_CROP_SAFE_WIDE_BOTTOM_RATIO,
        ),
      }),
      strategy: 'safe_wide',
      classification: 'safe_wide',
      confidence: 0,
      policyVersion: SELECTED_IMAGE_AUTO_CROP_POLICY,
      evidence,
    };
  } catch {
    return {
      crop: createDefaultSelectedImageCropBand(source),
      strategy: 'safe_wide',
      classification: 'safe_wide',
      confidence: 0,
      policyVersion: SELECTED_IMAGE_AUTO_CROP_POLICY,
      evidence,
    };
  }
}

function measureSignals(
  width: number,
  height: number,
  rgba: Uint8ClampedArray,
): { readonly chromatic: SignalGrid; readonly structural: SignalGrid } {
  const xStart = Math.floor(width * ANALYSIS_X_MARGIN_RATIO);
  const xEnd = Math.ceil(width * (1 - ANALYSIS_X_MARGIN_RATIO));
  const usableWidth = Math.max(STRIP_COUNT, xEnd - xStart);
  const chromaticScores = emptySignalScores(height);
  const structuralScores = emptySignalScores(height);
  for (let strip = 0; strip < STRIP_COUNT; strip += 1) {
    const stripStart = xStart + Math.floor((usableWidth * strip) / STRIP_COUNT);
    const stripEnd =
      xStart + Math.floor((usableWidth * (strip + 1)) / STRIP_COUNT);
    const stripWidth = Math.max(1, stripEnd - stripStart);
    for (let y = 0; y < height; y += 1) {
      let chromatic = 0;
      let legacyBlue = 0;
      let edgeCount = 0;
      let contrastTotal = 0;
      for (let x = stripStart; x < stripEnd; x += 1) {
        const offset = (y * width + x) * 4;
        const red = rgba[offset] ?? 0;
        const green = rgba[offset + 1] ?? 0;
        const blue = rgba[offset + 2] ?? 0;
        const maximum = Math.max(red, green, blue);
        const minimum = Math.min(red, green, blue);
        if (maximum >= 48 && maximum - minimum >= 30) chromatic += 1;
        if (
          blue >= 60 &&
          blue >= red * 1.12 &&
          blue >= green * 1.04 &&
          maximum - minimum >= 28
        ) {
          legacyBlue += 1;
        }
        if (x > stripStart && y > 0) {
          const luminance = luminanceAt(rgba, offset);
          const contrast =
            Math.abs(luminance - luminanceAt(rgba, offset - 4)) +
            Math.abs(luminance - luminanceAt(rgba, offset - width * 4));
          contrastTotal += Math.min(96, contrast) / 96;
          if (contrast >= 38) edgeCount += 1;
        }
      }
      chromaticScores[strip]![y] = Math.min(
        1,
        chromatic / stripWidth + (legacyBlue / stripWidth) * 0.15,
      );
      structuralScores[strip]![y] =
        (edgeCount / stripWidth) * 0.65 + (contrastTotal / stripWidth) * 0.35;
    }
  }
  return {
    chromatic: activateSignalGrid(chromaticScores, height, 0.055),
    structural: activateSignalGrid(structuralScores, height, 0.05),
  };
}

function emptySignalScores(height: number): number[][] {
  return Array.from({ length: STRIP_COUNT }, () =>
    Array.from({ length: height }, () => 0),
  );
}

function activateSignalGrid(
  scores: readonly (readonly number[])[],
  height: number,
  floor: number,
): SignalGrid {
  const radius = Math.max(1, Math.round(height * 0.008));
  const smoothed = scores.map((rows) => smoothRows(rows, radius));
  return {
    scoresByStrip: smoothed,
    activeByStrip: smoothed.map((rows) => {
      const threshold = Math.max(floor, percentile(rows, 0.7) * 0.78);
      return rows.map((value) => value >= threshold);
    }),
  };
}

function signalCandidates(
  signal: SignalGrid,
  height: number,
  minimumScore: number,
): SignalCandidate[] {
  const support = Array.from({ length: height }, (_, row) =>
    signal.activeByStrip.reduce(
      (total, strip) => total + (strip[row] === true ? 1 : 0),
      0,
    ),
  );
  const clusters = booleanClusters(
    support.map((count) => count >= REQUIRED_STRIP_COUNT),
    Math.max(1, Math.round(height * 0.025)),
    Math.max(2, Math.round(height * 0.08)),
  );
  return clusters.flatMap(({ start, end }) => {
    const supportedStrips = signal.activeByStrip.flatMap((rows, strip) =>
      rows.slice(start, end + 1).some(Boolean) ? [strip] : [],
    );
    if (!hasWideSupport(supportedStrips)) return [];
    const localBounds = supportedStrips.map((strip) => {
      const rows = signal.activeByStrip[strip]!;
      let top = start;
      let bottom = end;
      while (top <= end && rows[top] !== true) top += 1;
      while (bottom >= start && rows[bottom] !== true) bottom -= 1;
      return { top, bottom };
    });
    const meanSupport =
      support.slice(start, end + 1).reduce((sum, value) => sum + value, 0) /
      ((end - start + 1) * STRIP_COUNT);
    const meanSignal =
      supportedStrips.reduce((total, strip) => {
        const rows = signal.scoresByStrip[strip]!.slice(start, end + 1);
        return (
          total + rows.reduce((sum, value) => sum + value, 0) / rows.length
        );
      }, 0) / supportedStrips.length;
    const score = meanSupport * 0.65 + meanSignal * 0.35;
    return score >= minimumScore
      ? [{ start, end, localBounds, score, supportedStrips }]
      : [];
  });
}

function selectEvidence(
  chromatic: readonly SignalCandidate[],
  structural: readonly SignalCandidate[],
): {
  readonly candidates: readonly SignalCandidate[];
  readonly chromatic: SignalCandidate | null;
  readonly structural: SignalCandidate | null;
  readonly evidenceIoU: number | null;
  readonly classification: Exclude<
    SelectedImageAutoCropClassification,
    'safe_wide'
  >;
  readonly confidence: number;
} | null {
  let bestPair: {
    readonly chromatic: SignalCandidate;
    readonly structural: SignalCandidate;
    readonly iou: number;
  } | null = null;
  for (const color of chromatic) {
    for (const structure of structural) {
      const iou = intervalIoU(color, structure);
      if (
        bestPair === null ||
        iou > bestPair.iou ||
        (iou === bestPair.iou &&
          color.score + structure.score >
            bestPair.chromatic.score + bestPair.structural.score)
      ) {
        bestPair = { chromatic: color, structural: structure, iou };
      }
    }
  }
  if (bestPair !== null && bestPair.iou >= 0.65) {
    return {
      candidates: [bestPair.chromatic, bestPair.structural],
      chromatic: bestPair.chromatic,
      structural: bestPair.structural,
      evidenceIoU: bestPair.iou,
      classification: 'high_confidence',
      confidence: clamp01(
        0.72 +
          bestPair.iou * 0.18 +
          (bestPair.chromatic.score + bestPair.structural.score) * 0.1,
      ),
    };
  }
  const strongestColor = strongestCandidate(chromatic);
  const strongestStructure = strongestCandidate(structural);
  if (strongestColor === null && strongestStructure === null) return null;
  const candidates = [strongestColor, strongestStructure].filter(
    (candidate): candidate is SignalCandidate => candidate !== null,
  );
  return {
    candidates,
    chromatic: strongestColor,
    structural: strongestStructure,
    evidenceIoU:
      strongestColor === null || strongestStructure === null
        ? null
        : intervalIoU(strongestColor, strongestStructure),
    classification: 'conservative',
    confidence: clamp01(
      0.42 +
        (candidates.reduce((total, candidate) => total + candidate.score, 0) /
          candidates.length) *
          0.35,
    ),
  };
}

function buildEvidence(input: {
  readonly width: number;
  readonly height: number;
  readonly chromaticCandidates: readonly SignalCandidate[];
  readonly structuralCandidates: readonly SignalCandidate[];
  readonly selected: NonNullable<ReturnType<typeof selectEvidence>>;
  readonly boundaryExpanded: boolean;
  readonly fallbackReason: SelectedImageAutoCropFallbackReason;
}): SelectedImageAutoCropEvidence {
  const boundaries = (
    signal: SelectedImageAutoCropSignal,
    candidate: SignalCandidate | null,
  ): readonly SelectedImageAutoCropLocalBoundary[] =>
    candidate === null
      ? []
      : candidate.localBounds.map((boundary, index) => ({
          signal,
          stripIndex: candidate.supportedStrips[index] ?? index,
          topRatio: Number((boundary.top / input.height).toFixed(6)),
          bottomRatio: Number((boundary.bottom / input.height).toFixed(6)),
        }));
  return {
    sampleWidth: input.width,
    sampleHeight: input.height,
    localBounds: [
      ...boundaries('chromatic', input.selected.chromatic),
      ...boundaries('structural', input.selected.structural),
    ],
    chromaticCandidateCount: input.chromaticCandidates.length,
    structuralCandidateCount: input.structuralCandidates.length,
    chromaticSupportedStrips: input.selected.chromatic?.supportedStrips ?? [],
    structuralSupportedStrips: input.selected.structural?.supportedStrips ?? [],
    evidenceIoU:
      input.selected.evidenceIoU === null
        ? null
        : Number(input.selected.evidenceIoU.toFixed(6)),
    boundaryExpanded: input.boundaryExpanded,
    fallbackReason: input.fallbackReason,
  };
}

function broadContentRows(
  chromatic: SignalGrid,
  structural: SignalGrid,
  height: number,
): readonly boolean[] {
  return Array.from({ length: height }, (_, row) => {
    const activeStrips = Array.from({ length: STRIP_COUNT }, (_, strip) =>
      chromatic.activeByStrip[strip]![row] === true ||
      structural.activeByStrip[strip]![row] === true
        ? strip
        : -1,
    ).filter((strip) => strip >= 0);
    return hasWideSupport(activeStrips);
  });
}

function expandPastBoundaryContent(
  initialTop: number,
  initialBottom: number,
  contentRows: readonly boolean[],
  height: number,
): [number, number] {
  const safety = Math.max(1, Math.round(height * 0.03));
  let top = Math.max(0, initialTop);
  let bottom = Math.min(height - 1, initialBottom);
  while (
    top > 0 &&
    contentRows.slice(top, Math.min(height, top + safety)).some(Boolean)
  ) {
    top = Math.max(0, top - safety);
  }
  while (
    bottom < height - 1 &&
    contentRows
      .slice(Math.max(0, bottom - safety + 1), bottom + 1)
      .some(Boolean)
  ) {
    bottom = Math.min(height - 1, bottom + safety);
  }
  return [top, bottom];
}

function booleanClusters(
  active: readonly boolean[],
  allowedGap: number,
  minimumLength: number,
): Array<{ readonly start: number; readonly end: number }> {
  const clusters: Array<{ start: number; end: number }> = [];
  let start = -1;
  let lastActive = -1;
  for (let index = 0; index <= active.length; index += 1) {
    if (active[index] === true) {
      if (start < 0) start = index;
      lastActive = index;
    }
    if (
      start >= 0 &&
      active[index] !== true &&
      (index - lastActive > allowedGap || index === active.length)
    ) {
      if (lastActive - start + 1 >= minimumLength)
        clusters.push({ start, end: lastActive });
      start = -1;
      lastActive = -1;
    }
  }
  return clusters;
}

function hasWideSupport(strips: readonly number[]): boolean {
  const unique = new Set(strips);
  return (
    unique.size >= REQUIRED_STRIP_COUNT &&
    [0, 1, 2].some((strip) => unique.has(strip)) &&
    [3, 4, 5].some((strip) => unique.has(strip)) &&
    [6, 7, 8].some((strip) => unique.has(strip))
  );
}

function strongestCandidate(
  candidates: readonly SignalCandidate[],
): SignalCandidate | null {
  return (
    [...candidates].sort(
      (left, right) =>
        right.score - left.score ||
        right.end - right.start - (left.end - left.start) ||
        left.start - right.start,
    )[0] ?? null
  );
}

function intervalIoU(left: SignalCandidate, right: SignalCandidate): number {
  const intersection = Math.max(
    0,
    Math.min(left.end, right.end) - Math.max(left.start, right.start) + 1,
  );
  const union =
    Math.max(left.end, right.end) - Math.min(left.start, right.start) + 1;
  return union === 0 ? 0 : intersection / union;
}

function smoothRows(values: readonly number[], radius: number): number[] {
  const prefix = [0];
  for (const value of values) prefix.push(prefix[prefix.length - 1]! + value);
  return values.map((_, index) => {
    const start = Math.max(0, index - radius);
    const end = Math.min(values.length, index + radius + 1);
    return (prefix[end]! - prefix[start]!) / (end - start);
  });
}

function percentile(values: readonly number[], ratio: number): number {
  const sorted = [...values].sort((left, right) => left - right);
  return (
    sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * ratio))] ?? 0
  );
}

function luminanceAt(rgba: Uint8ClampedArray, offset: number): number {
  return (
    (rgba[offset] ?? 0) * 0.299 +
    (rgba[offset + 1] ?? 0) * 0.587 +
    (rgba[offset + 2] ?? 0) * 0.114
  );
}

function assertSample(sample: SelectedImageAutoCropSample): void {
  if (
    !Number.isInteger(sample.width) ||
    !Number.isInteger(sample.height) ||
    sample.width <= 0 ||
    sample.height <= 0 ||
    sample.rgba.length !== sample.width * sample.height * 4
  ) {
    throw new Error('SELECTED_IMAGE_AUTO_CROP_SAMPLE_INVALID');
  }
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}
